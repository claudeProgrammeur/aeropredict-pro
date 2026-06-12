# ai_engine/diagnostics/rules.py
"""
Règles de diagnostic et validation pour AeroPredict
Version CORRIGÉE - Limites très larges pour accepter toutes les données utilisateur
"""

from typing import Tuple


SENSOR_KEYS = [
    's2', 's3', 's4', 's7', 's8', 's9', 's11',
    's12', 's13', 's14', 's15', 's17', 's20', 's21'
]

# 🔥 Noms complets des capteurs (pour référence)
SENSOR_NAMES = {
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
    's21': 'Pression_Entree_Fan',
}


def get_severity_status(anomalies, predicted_rul):
    """Détermine le statut de sévérité basé sur les anomalies et le RUL"""
    nb = len(anomalies)
    
    if predicted_rul <= 25 or nb >= 3:
        return "🔴 CRITICAL"
    elif predicted_rul <= 50 or nb >= 2:
        return "🟠 WARNING"
    elif predicted_rul <= 80 or nb >= 1:
        return "🟡 DEGRADED"
    else:
        return "🟢 HEALTHY"


def validate_physical_limits(data):
    """
    Valide les limites physiques des capteurs.
    🔥 LIMITES TRÈS LARGES pour accepter toutes les données utilisateur
    """
    errors = []
    
    # Mach number - limites très larges
    mach = data.get('Mach', data.get('mach', 0.5))
    if not (-10 <= mach <= 10):
        errors.append(f"Mach incohérent: {mach}")
    
    # Altitude - limites très larges
    altitude = data.get('Altitude', data.get('altitude', 35000))
    if not (-10000 <= altitude <= 100000):
        errors.append(f"Altitude incohérente: {altitude}")
    
    # Régime moteur
    regime = data.get('Regime', data.get('regime', 100))
    if not (0 <= regime <= 200):
        errors.append(f"Régime incohérent: {regime}")
    
    # 🔥 Températures - limites très larges (accepte toutes les valeurs raisonnables)
    temp_lpc = data.get('Temp_Entree_LPC', data.get('s2', 518.67))
    if not (100 <= temp_lpc <= 50000):
        errors.append(f"Température entrée LPC invalide: {temp_lpc}")
    
    temp_hpc = data.get('Temp_Sortie_HPC', data.get('s3', 1589.0))
    if not (100 <= temp_hpc <= 50000):
        errors.append(f"Température sortie HPC invalide: {temp_hpc}")
    
    temp_lpt = data.get('Temp_Sortie_LPT', data.get('s4', 1406.0))
    if not (100 <= temp_lpt <= 50000):
        errors.append(f"Température sortie LPT invalide: {temp_lpt}")
    
    # Pressions - limites très larges
    pressure_hpc = data.get('Pression_Sortie_HPC', data.get('s7', 554.0))
    if not (0 <= pressure_hpc <= 100000):
        errors.append(f"Pression sortie HPC invalide: {pressure_hpc}")
    
    pressure_lpt = data.get('Pression_Sortie_LPT', data.get('s11', 47.0))
    if not (0 <= pressure_lpt <= 10000):
        errors.append(f"Pression sortie LPT invalide: {pressure_lpt}")
    
    pressure_bouchon = data.get('Pression_Bouchon', data.get('s15', 8.4))
    if not (0 <= pressure_bouchon <= 10000):
        errors.append(f"Pression bouchon invalide: {pressure_bouchon}")
    
    pressure_entree_fan = data.get('Pression_Entree_Fan', data.get('s21', 23.0))
    if not (0 <= pressure_entree_fan <= 10000):
        errors.append(f"Pression entrée fan invalide: {pressure_entree_fan}")
    
    # Rapport pression HPC (s20) - très large
    pressure_ratio = data.get('Rapport_Pression_HPC', data.get('s20', 39.0))
    if not (0 <= pressure_ratio <= 500):
        errors.append(f"Rapport pression HPC invalide: {pressure_ratio}")
    
    # Vitesses - limites très larges
    fan_speed = data.get('Vitesse_Physique_Fan', data.get('s8', 2388.0))
    if not (0 <= fan_speed <= 100000):
        errors.append(f"Vitesse fan invalide: {fan_speed}")
    
    core_speed = data.get('Vitesse_Physique_Core', data.get('s9', 9064.0))
    if not (0 <= core_speed <= 100000):
        errors.append(f"Vitesse core invalide: {core_speed}")
    
    vitesse_hpc_sortie = data.get('Vitesse_HPC_Sortie', data.get('s12', 522.0))
    if not (0 <= vitesse_hpc_sortie <= 100000):
        errors.append(f"Vitesse sortie HPC invalide: {vitesse_hpc_sortie}")
    
    vitesse_lpc_sortie = data.get('Vitesse_LPC_Sortie', data.get('s13', 2388.0))
    if not (0 <= vitesse_lpc_sortie <= 100000):
        errors.append(f"Vitesse sortie LPC invalide: {vitesse_lpc_sortie}")
    
    vitesse_bypass = data.get('Vitesse_Bypass', data.get('s14', 8143.0))
    if not (0 <= vitesse_bypass <= 100000):
        errors.append(f"Vitesse bypass invalide: {vitesse_bypass}")
    
    vitesse_rotation_hpc = data.get('Vitesse_Rotation_HPC', data.get('s17', 392.0))
    if not (0 <= vitesse_rotation_hpc <= 100000):
        errors.append(f"Vitesse rotation HPC invalide: {vitesse_rotation_hpc}")
    
    # Si des erreurs, les retourner
    if errors:
        raise ValueError(f"Invalid sensor data: {errors}")
    
    return True


def validate_sensor_range(sensor_name: str, value: float) -> Tuple[bool, str]:
    """
    Valide un capteur individuel avec limites très larges
    """
    ranges = {
        'Mach': (-10, 10),
        'Altitude': (-10000, 100000),
        'Regime': (0, 200),
        'Temp_Entree_LPC': (100, 50000),
        'Temp_Sortie_HPC': (100, 50000),
        'Temp_Sortie_LPT': (100, 50000),
        'Pression_Sortie_HPC': (0, 100000),
        'Pression_Sortie_LPT': (0, 10000),
        'Pression_Bouchon': (0, 10000),
        'Pression_Entree_Fan': (0, 10000),
        'Vitesse_Physique_Fan': (0, 100000),
        'Vitesse_Physique_Core': (0, 100000),
        'Vitesse_HPC_Sortie': (0, 100000),
        'Vitesse_LPC_Sortie': (0, 100000),
        'Vitesse_Bypass': (0, 100000),
        'Vitesse_Rotation_HPC': (0, 100000),
        'Rapport_Pression_HPC': (0, 500),
    }
    
    if sensor_name in ranges:
        min_val, max_val = ranges[sensor_name]
        if not (min_val <= value <= max_val):
            return False, f"{sensor_name}: {value} hors limites"
    
    return True, ""


def is_critical_anomaly(anomaly: dict) -> bool:
    """Détermine si une anomalie est critique"""
    z_score = abs(anomaly.get('z_score', 0))
    sensor_id = anomaly.get('sensor_id', '')
    
    critical_sensors = ['s20', 's3', 's4']
    
    if sensor_id in critical_sensors and z_score > 3.0:
        return True
    
    return z_score > 7.0


def get_anomaly_severity(z_score: float) -> str:
    """Retourne la sévérité d'une anomalie basée sur son Z-score"""
    abs_z = abs(z_score)
    
    if abs_z > 7.0:
        return 'CRITICAL'
    elif abs_z > 4.0:
        return 'HIGH'
    elif abs_z > 2.5:
        return 'MEDIUM'
    else:
        return 'LOW'


# Export des fonctions principales
__all__ = [
    'SENSOR_KEYS',
    'SENSOR_NAMES',
    'get_severity_status',
    'validate_physical_limits',
    'validate_sensor_range',
    'is_critical_anomaly',
    'get_anomaly_severity'
]