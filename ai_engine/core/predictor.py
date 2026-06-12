# ai_engine/predictor.py
"""
AeroPredict SaaS - Moteur d'Inférence Principal
Version: 10.0.0 - CORRIGÉE
Architecture: Singleton + Preprocessing + LSTM-Attention + NASA Knowledge Base

Pipeline complet:
    14 capteurs bruts → 42 features → LSTM → RUL + Diagnostic NASA
"""

import logging
import torch
import numpy as np
from typing import Dict, List, Any, Optional

from ai_engine.core.model_loader import load_trained_model
from ai_engine.diagnostics.anomaly import detect_anomalies_from_z_scores
from ai_engine.diagnostics.rules import get_severity_status, validate_physical_limits, SENSOR_KEYS
from ai_engine.diagnostics.knowledge import get_nasa_solution

from .preprocessing import AeroPreprocessor


logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTES CORRIGÉES
# ============================================================
RUL_MAX = 125.0                     #  RUL max réel (NASA: 125 cycles)
RUL_MIN = 0.0
RUL_SCALE_FACTOR = 1.0              #  CORRIGÉ : Plus de facteur d'échelle
DEGRADATION_RUL_THRESHOLD = 50
MIN_BUFFER_SIZE_FOR_TREND = 5

#  SEUILS D'ANOMALIES CORRIGÉS (adaptés aux Z-scores réels)
ANOMALY_THRESHOLD = 3.5             #  Au lieu de 50.0 (Z-score > 3.5 = anomalie)
CRITICAL_ZSCORE_THRESHOLD = 7.0     # Au lieu de 70.0 (Z-score > 7.0 = critique)

# Seuils secondaires pour différents niveaux
WARNING_ZSCORE_THRESHOLD = 2.5
DEGRADED_ZSCORE_THRESHOLD = 1.5


class AIEngine:
    """
    Moteur d'Inférence IA - Pattern Singleton
    
    Responsabilités:
        1. Charger le modèle PyTorch une seule fois
        2. Prétraiter les données capteurs en temps réel
        3. Exécuter l'inférence LSTM avec Attention
        4. Détecter les anomalies par Z-Score
        5. Générer un diagnostic complet via la NASA Knowledge Base
    
    Usage:
        engine = AIEngine()
        result = engine.predict("FD001_42", sensor_data_dict)
    """
    
    _instance: Optional['AIEngine'] = None

    def __new__(cls) -> 'AIEngine':
        """Implémentation thread-safe du Singleton"""
        if cls._instance is None:
            cls._instance = super(AIEngine, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        logger.info("🔄 Début initialisation AIEngine...")
        
        # Initialiser TOUS les attributs AVANT de charger
        self.model = None
        self.device = None
        self.preprocessor = None
        self._prediction_count = 0
        self._error_count = 0
        
        try:
            logger.info(" Chargement du modèle...")
            self.model, self.device = load_trained_model()
            logger.info(f" Modèle chargé sur {self.device}")
            
            logger.info(" Initialisation du preprocessor...")
            self.preprocessor = AeroPreprocessor()
            logger.info(f" Preprocessor initialisé avec {len(self.preprocessor.feature_cols)} features")
            
        except Exception as e:
            logger.critical(f" Échec initialisation AIEngine: {e}", exc_info=True)
            raise RuntimeError(f"AIEngine initialization failed: {e}")

    # ============================================================
    # MÉTHODES PRIVÉES
    # ============================================================
    
    def _extract_z_scores(self, sequence: np.ndarray) -> np.ndarray:
        """Extrait les Z-scores normalisés du dernier cycle de la séquence."""
        last_step_features = sequence[0, -1, :]
        
        z_indices = [
            idx for idx, col_name in enumerate(self.preprocessor.feature_cols)
            if col_name.endswith("_norm")
        ]
        
        if len(z_indices) != len(self.preprocessor.sensors):
            logger.debug(f"Nombre de Z-scores: {len(z_indices)} (attendu: {len(self.preprocessor.sensors)})")
        
        return last_step_features[z_indices]
    
    def _infer_rul(self, input_tensor: torch.Tensor) -> float:
        """
        Exécute l'inférence du modèle LSTM.
         CORRIGÉ : Plus de facteur d'échelle (maintenant 1.0)
        """
        self.model.eval()
        with torch.no_grad():
            raw_prediction = self.model(input_tensor).cpu().item()
        
        #  CORRIGÉ : Appliquer le facteur d'échelle (1.0 = pas de correction)
        scaled_prediction = raw_prediction / RUL_SCALE_FACTOR
        
        # Clipping dans les bornes définies (0-125 cycles)
        rul = max(RUL_MIN, min(scaled_prediction, RUL_MAX))
        
        return round(rul, 2)
    
    def _analyze_trend(self, engine_id: str, current_rul: float) -> str:
        """Analyse la tendance de dégradation du moteur."""
        buffer = self.preprocessor.buffers.get(engine_id, [])
        
        if len(buffer) >= MIN_BUFFER_SIZE_FOR_TREND:
            if current_rul < DEGRADATION_RUL_THRESHOLD:
                return "degrading"
        
        return "stable"
    
    def _build_response(
        self,
        engine_id: str,
        rul: float,
        health_score: float,
        anomalies: List[Dict[str, Any]],
        diagnosis: Dict[str, Any],
        status: str,
        trend: str
    ) -> Dict[str, Any]:
        """Construit la réponse finale structurée."""
        return {
            "engine_id": engine_id,
            "status": status,
            "ai_prediction": {
                "predicted_rul": rul,
                "health_score": health_score,
                "trend": trend
            },
            "diagnosis": diagnosis,
            "raw_anomalies": anomalies,
            "metadata": {
                "version": "10.0.0",
                "model_type": "LSTM-BiDirectional-Attention",
                "features_count": len(self.preprocessor.feature_cols),
                "buffer_size": len(self.preprocessor.buffers.get(engine_id, []))
            }
        }

    # ============================================================
    # MÉTHODE PRINCIPALE
    # ============================================================
    
    def predict(self, engine_id: str, sensor_data: Dict[str, float]) -> Dict[str, Any]:
        """
        Point d'entrée principal du moteur d'inférence.
        """
        try:
            # ÉTAPE 0: Validation physique (limites élargies)
            validate_physical_limits(sensor_data)
            
            # ÉTAPE 1: Preprocessing (14 → 42 features)
            sequence = self.preprocessor.process(engine_id, sensor_data)
            
            # ÉTAPE 2: Inférence IA
            input_tensor = torch.from_numpy(sequence).float().to(self.device)
            rul = self._infer_rul(input_tensor)
            
            # 🔥 CORRIGÉ : health_score basé sur RUL max réel (125)
            health_score = min(1.0, max(0.0, rul / RUL_MAX))
            
            # ÉTAPE 3: Détection d'anomalies
            z_scores = self._extract_z_scores(sequence)

            current_anomalies = detect_anomalies_from_z_scores(
                z_scores=z_scores,
                sensor_keys=SENSOR_KEYS,
                sensor_names=self.preprocessor.sensors,
                threshold=ANOMALY_THRESHOLD,
                critical_threshold=CRITICAL_ZSCORE_THRESHOLD
            )

            logger.info(f" Z-scores reçus: {z_scores}")
            logger.info(f" Anomalies détectées: {len(current_anomalies)}")

            #  AJOUTER LA SÉVÉRITÉ À CHAQUE ANOMALIE
            for anomaly in current_anomalies:
                z_val = abs(anomaly.get('z_score', 0))
                if z_val >= CRITICAL_ZSCORE_THRESHOLD:
                    anomaly['severity'] = 'CRITICAL'
                elif z_val >= ANOMALY_THRESHOLD:
                    anomaly['severity'] = 'HIGH'
                elif z_val >= WARNING_ZSCORE_THRESHOLD:
                    anomaly['severity'] = 'WARNING'
                else:
                    anomaly['severity'] = 'LOW'

            # ============================================================
            # 🔥 NOUVEAU : AJUSTER LA RUL EN FONCTION DES ANOMALIES
            # ============================================================
            if current_anomalies:
                critical_count = sum(1 for a in current_anomalies if a.get('severity') == 'CRITICAL')
                high_count = sum(1 for a in current_anomalies if a.get('severity') == 'HIGH')
                warning_count = sum(1 for a in current_anomalies if a.get('severity') == 'WARNING')
                
                penalty = (critical_count * 15) + (high_count * 8) + (warning_count * 3)
                penalty = min(penalty, 110)  # Max 110 cycles de pénalité
                
                if penalty > 0:
                    rul_original = rul
                    rul = max(RUL_MIN, min(rul - penalty, RUL_MAX))
                    health_score = min(1.0, max(0.0, rul / RUL_MAX))
                    logger.warning(f"📉 RUL ajustée: {rul_original:.1f} -> {rul:.1f} cycles (pénalité: {penalty})")

                        
            # ÉTAPE 4: Diagnostic NASA
            diagnosis_obj = get_nasa_solution(current_anomalies)
            
            # ÉTAPE 5: Statut final (fusion IA + règles)
            final_status = get_severity_status(current_anomalies, rul)
            
            # ÉTAPE 6: Analyse de tendance
            trend = self._analyze_trend(engine_id, rul)
            
            # ÉTAPE 7: Construction réponse
            response = self._build_response(
                engine_id=engine_id,
                rul=rul,
                health_score=round(health_score, 3),
                anomalies=current_anomalies,
                diagnosis=diagnosis_obj,
                status=final_status,
                trend=trend
            )
            
            self._prediction_count += 1
            
            # Log plus détaillé
            logger.info(
                f"✅ Prédiction #{self._prediction_count} | "
                f"Engine: {engine_id} | RUL: {rul} | Status: {final_status} | "
                f"Anomalies: {len(current_anomalies)} | "
                f"Health: {health_score:.2f}"
            )
            
            # Log des anomalies si présentes
            if current_anomalies:
                critical_count = sum(1 for a in current_anomalies if a.get('severity') == 'CRITICAL')
                if critical_count > 0:
                    logger.warning(f"⚠️ {critical_count} anomalies CRITIQUES détectées sur {engine_id}")
            
            return response
            
        except ValueError as e:
            logger.warning(f"⚠️ Validation échouée pour {engine_id}: {e}")
            raise
            
        except Exception as e:
            self._error_count += 1
            logger.error(
                f"❌ Échec pipeline pour {engine_id} "
                f"(erreur #{self._error_count}): {e}",
                exc_info=True
            )
            raise RuntimeError(f"Pipeline crashed for engine {engine_id}: {str(e)}")

    # ============================================================
    # MÉTHODES DE COMPATIBILITÉ
    # ============================================================
    def predict_rul(self, engine_id: str, sensor_data: Dict[str, float]) -> float:
        result = self.predict(engine_id, sensor_data)
        return result["ai_prediction"]["predicted_rul"]
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "predictions_total": self._prediction_count,
            "errors_total": self._error_count,
            "success_rate": (
                self._prediction_count / 
                (self._prediction_count + self._error_count)
                if (self._prediction_count + self._error_count) > 0
                else 1.0
            ),
            "device": str(self.device),
            "active_buffers": len(self.preprocessor.buffers),
            "features_dimension": len(self.preprocessor.feature_cols)
        }
    
    def reset_buffers(self, engine_id: Optional[str] = None) -> None:
        if engine_id:
            if engine_id in self.preprocessor.buffers:
                del self.preprocessor.buffers[engine_id]
                logger.info(f"🔄 Buffer reset pour {engine_id}")
        else:
            self.preprocessor.buffers.clear()
            logger.info("🔄 Tous les buffers réinitialisés")

    # ============================================================
    # 🔥 HOT RELOAD DU MODÈLE (APRÈS ENTRAÎNEMENT)
    # ============================================================
    
    def reload_model(self) -> bool:
        try:
            logger.info("🔄 Rechargement du modèle LSTM...")
            self.model, self.device = load_trained_model()
            logger.info(f"✅ Modèle rechargé avec succès | Device: {self.device}")
            return True
        except Exception as e:
            logger.error(f"❌ Échec rechargement modèle: {e}")
            return False
    
    @classmethod
    def force_reload(cls) -> bool:
        if cls._instance is not None:
            return cls._instance.reload_model()
        return False