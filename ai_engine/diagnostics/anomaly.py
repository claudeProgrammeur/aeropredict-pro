# ai_engine/diagnostics/anomaly.py

import logging

logger = logging.getLogger(__name__)

# =========================================================
# SENSOR MAPPING OFFICIEL (SaaS ↔ IA)
# =========================================================
SENSOR_MAPPING = {
    's2': 'Temp_Entree_LPC',
    's3': 'Temp_Sortie_HPC',
    's4': 'Temp_Sortie_LPT',
    's7': 'Pression_Sortie_HPC',
    's8': 'Vitesse_Physique_Fan',
    's9': 'Vitesse_Physique_Core',
    's11': 'Pression_Sortie_LPT',
    's12': 'Vitesse_HPC_Sortie',
    's13': 'Vitesse_LPC_Sortie',
    's14': 'Vitesse_Bypass',
    's15': 'Pression_Bouchon',
    's17': 'Vitesse_Rotation_HPC',
    's20': 'Rapport_Pression_HPC',
    's21': 'Pression_Entree_Fan'
}

# =========================================================
# 🔥 Z-SCORE ANOMALY DETECTION ENGINE - CORRIGÉ
# =========================================================

def detect_anomalies_from_z_scores(z_scores, sensor_keys, sensor_names, threshold=3.5, critical_threshold=7.0):
    """
    🔥 SEUILS CALIBRÉS pour données réelles
    - threshold: 3.5 (Z-score > 3.5 = anomalie)
    - critical_threshold: 7.0 (Z-score > 7.0 = critique)
    """
    anomalies = []
    
    for i, z_val in enumerate(z_scores):
        abs_z = abs(z_val)
        
        # 🔥 Seuil abaissé à 3.5 pour détecter les vraies anomalies
        if abs_z >= threshold:
            s_id = sensor_keys[i]
            s_name = sensor_names[i]
            
            anomalies.append({
                "sensor_id": s_id,
                "sensor_name": s_name,
                "z_score": float(round(z_val, 3)),
                "severity": "CRITICAL" if abs_z >= critical_threshold else "HIGH",
                "is_critical": abs_z >= critical_threshold
            })
            
    return anomalies