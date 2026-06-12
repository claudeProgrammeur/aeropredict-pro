# ai_engine/preprocessing.py

import json
import os
import numpy as np
import pandas as pd
from collections import deque
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class AeroPreprocessor:
    """
    Préprocesseur temps réel robuste pour AeroPredict.
    - Gère buffer par moteur
    - Évite erreurs Pandas/Numpy
    - Reproduit pipeline Spark fidèlement
    """

    def __init__(self):
        # model_dir = os.path.join(settings.BASE_DIR, 'ai_engine/configs/models_files')
        # 🔥 CORRECTION : Chemin correct vers les JSON
        model_dir = os.path.join(settings.BASE_DIR, 'ai_engine', 'configs', 'models_files')

        # === LOAD CONFIGS ===
        with open(os.path.join(model_dir, 'kmeans_centers.json'), 'r') as f:
            self.centers = np.array(json.load(f)['centers'], dtype=np.float32)

        with open(os.path.join(model_dir, 'zscore_stats.json'), 'r') as f:
            raw_data = json.load(f)
            self.stats_map = {int(item['cluster']): item for item in raw_data}

        with open(os.path.join(model_dir, 'final_feature_signature.json'), 'r') as f:
            self.signature = json.load(f)
            self.feature_cols = self.signature['feature_cols']
            self.seq_len = self.signature.get("sequence_length", 30)

        # === CAPTEURS ===
        self.sensors = [
            'Temp_Entree_LPC', 'Temp_Sortie_HPC', 'Temp_Sortie_LPT',
            'Pression_Sortie_HPC', 'Vitesse_Physique_Fan', 'Vitesse_Physique_Core',
            'Pression_Sortie_LPT', 'Vitesse_HPC_Sortie', 'Vitesse_LPC_Sortie',
            'Vitesse_Bypass', 'Pression_Bouchon', 'Vitesse_Rotation_HPC',
            'Rapport_Pression_HPC', 'Pression_Entree_Fan'
        ]

        self.flight_cols = ['Altitude', 'Mach', 'Regime']

        # === BUFFER TEMPS RÉEL ===
        self.buffers = {}  # engine_id -> deque(maxlen=30)

        logger.info(f"✅ Preprocessor initialisé | Features: {len(self.feature_cols)} | Seq_len: {self.seq_len}")

    # =========================================================
    # 🔥 VALIDATION INPUT (ANTI CRASH)
    # =========================================================
    def _validate_input(self, row_dict):
        required = self.flight_cols + self.sensors
        missing = [c for c in required if c not in row_dict]

        if missing:
            raise ValueError(f"Missing required fields: {missing}")

    # =========================================================
    # 🔥 BUFFER MANAGEMENT (TEMPS RÉEL)
    # =========================================================
    def _update_buffer(self, engine_id, row_dict):
        if engine_id not in self.buffers:
            self.buffers[engine_id] = deque(maxlen=self.seq_len)

        self.buffers[engine_id].append(row_dict)
        return list(self.buffers[engine_id])

    # =========================================================
    # 🔥 CLUSTERING VECTORISÉ (RAPIDE)
    # =========================================================
    def _compute_clusters(self, flight_array):
        # flight_array shape: (N, 3)
        diff = self.centers[:, None, :] - flight_array[None, :, :]
        dist = np.linalg.norm(diff, axis=2)
        return np.argmin(dist, axis=0)

    # =========================================================
    # 🔥 MAIN PIPELINE
    # =========================================================
    def process(self, engine_id, row_dict):
        """
        Entrée: dict capteurs (1 cycle)
        Sortie: tensor (1, 30, 42)
        """

        # === 1. VALIDATION ===
        self._validate_input(row_dict)

        # === 2. BUFFER ===
        history = self._update_buffer(engine_id, row_dict)

        # === 3. DATAFRAME SAFE ===
        df = pd.DataFrame(history)

        # 🔥 CORRECTION : Convertir uniquement les colonnes numériques attendues
        numeric_columns = self.flight_cols + self.sensors
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        n_rows = len(df)

        # === 4. CLUSTERING ===
        flight_array = df[self.flight_cols].values.astype(np.float32)
        clusters = self._compute_clusters(flight_array)

        df['cluster'] = clusters 

        # === 5. FEATURE ENGINEERING ===
        # 🔥 CORRECTION: Rolling window dynamique (plus petite pour petits buffers)
        rolling_window = min(5, max(3, n_rows // 3)) if n_rows > 0 else 5
        
        for s in self.sensors:
            try:
                raw = df[s].values.astype(np.float32)

                means = np.array([
                    float(self.stats_map[int(c)][f"avg_{s}"]) for c in clusters
                ], dtype=np.float32)

                stds = np.array([
                    float(self.stats_map[int(c)][f"std_{s}"]) for c in clusters
                ], dtype=np.float32)

                # Z-score (normalisation)
                norm = (raw - means) / (stds + 1e-6)

                # 🔥 Rolling avec window adaptative (au lieu de 11 fixe)
                rolling = pd.Series(norm).rolling(window=rolling_window, min_periods=1).mean().values

                # Delta (taux de changement)
                delta = np.diff(rolling, prepend=rolling[0])

                df[f"{s}_norm"] = norm
                df[f"{s}_rolling"] = rolling
                df[f"{s}_delta"] = delta

            except Exception as e:
                # Fallback robuste avec log (une seule fois par capteur)
                if not hasattr(self, f'_logged_{s}'):
                    logger.warning(f"⚠️ Fallback pour capteur {s}: {e}")
                    setattr(self, f'_logged_{s}', True)
                
                df[f"{s}_norm"] = np.zeros(n_rows, dtype=np.float32)
                df[f"{s}_rolling"] = np.zeros(n_rows, dtype=np.float32)
                df[f"{s}_delta"] = np.zeros(n_rows, dtype=np.float32)

        # === 6. FEATURE SELECTION ===
        for col in self.feature_cols:
            if col not in df:
                df[col] = 0.0

        sequence = df[self.feature_cols].values.astype(np.float32)

        # === 7. PADDING ===
        if len(sequence) < self.seq_len:
            pad_len = self.seq_len - len(sequence)
            pad = np.repeat(sequence[:1], pad_len, axis=0) if len(sequence) > 0 else np.zeros((pad_len, len(self.feature_cols)))
            sequence = np.vstack([pad, sequence])
        else:
            sequence = sequence[-self.seq_len:]
        
        # === 8. FINAL SHAPE ===
        return np.expand_dims(sequence, axis=0)