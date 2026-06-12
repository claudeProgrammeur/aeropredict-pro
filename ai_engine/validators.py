# ai_engine/validators.py
"""
Validateurs pour les données d'entrée du modèle.
Version PRO - CORRIGÉE avec limites élargies pour données NASA
"""

import logging
import math
from typing import Dict, List, Any, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTES CORRIGÉES (limites élargies pour NASA)
# ============================================================

REQUIRED_SENSORS = [
    'Altitude', 'Mach', 'Regime',
    'Temp_Entree_LPC', 'Temp_Sortie_HPC', 'Temp_Sortie_LPT',
    'Pression_Sortie_HPC', 'Vitesse_Physique_Fan', 'Vitesse_Physique_Core',
    'Pression_Sortie_LPT', 'Vitesse_HPC_Sortie', 'Vitesse_LPC_Sortie',
    'Vitesse_Bypass', 'Pression_Bouchon', 'Vitesse_Rotation_HPC',
    'Rapport_Pression_HPC', 'Pression_Entree_Fan'
]

# 🔥 LIMITES ÉLARGIES pour données NASA C-MAPSS réelles
PHYSICAL_LIMITS = {
    'Altitude': (0, 50000),           # NASA: 0-42000 ft
    'Mach': (0, 1.5),                 # NASA: 0-0.9
    'Regime': (0, 150),               # NASA: 0-100
    'Temp_Entree_LPC': (400, 2500),   # NASA: 518-620
    'Temp_Sortie_HPC': (400, 3000),   # NASA: 1589
    'Temp_Sortie_LPT': (400, 3000),   # NASA: 1406
    'Pression_Sortie_HPC': (100, 1000),  # NASA: 554
    'Vitesse_Physique_Fan': (1000, 3500),  # NASA: 2388
    'Vitesse_Physique_Core': (3000, 15000),  # NASA: 9064
    'Pression_Sortie_LPT': (10, 200),     # NASA: 47
    'Vitesse_HPC_Sortie': (100, 2000),    # NASA: 522
    'Vitesse_LPC_Sortie': (1000, 10000),  # NASA: 2388
    'Vitesse_Bypass': (2000, 20000),      # NASA: 8143
    'Pression_Bouchon': (0, 100),         # NASA: 8.4
    'Vitesse_Rotation_HPC': (100, 2000),  # NASA: 392
    'Rapport_Pression_HPC': (10, 80),     # NASA: 39
    'Pression_Entree_Fan': (10, 200),     # NASA: 23
}

# Mapping pour flexibilité des noms de colonnes (minuscule → exact)
COLUMN_MAPPING = {
    'altitude': 'Altitude',
    'mach': 'Mach',
    'regime': 'Regime',
    'temp_entree_lpc': 'Temp_Entree_LPC',
    'temp_sortie_hpc': 'Temp_Sortie_HPC',
    'temp_sortie_lpt': 'Temp_Sortie_LPT',
    'pression_sortie_hpc': 'Pression_Sortie_HPC',
    'vitesse_physique_fan': 'Vitesse_Physique_Fan',
    'vitesse_physique_core': 'Vitesse_Physique_Core',
    'pression_sortie_lpt': 'Pression_Sortie_LPT',
    'vitesse_hpc_sortie': 'Vitesse_HPC_Sortie',
    'vitesse_lpc_sortie': 'Vitesse_LPC_Sortie',
    'vitesse_bypass': 'Vitesse_Bypass',
    'pression_bouchon': 'Pression_Bouchon',
    'vitesse_rotation_hpc': 'Vitesse_Rotation_HPC',
    'rapport_pression_hpc': 'Rapport_Pression_HPC',
    'pression_entree_fan': 'Pression_Entree_Fan',
}


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def _normalize_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalise les clés du dictionnaire pour gérer les variations de casse.
    """
    normalized = {}
    for key, value in data.items():
        key_lower = key.lower()
        if key_lower in COLUMN_MAPPING:
            normalized[COLUMN_MAPPING[key_lower]] = value
        else:
            normalized[key] = value
    return normalized


def _is_valid_number(val: Any) -> bool:
    """
    Vérifie si une valeur est un nombre valide (pas NaN, pas Infini).
    """
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return False
        return True
    except (ValueError, TypeError):
        return False


# ============================================================
# VALIDATION DES DONNÉES CAPTEURS
# ============================================================

def validate_sensor_data(sensor_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Valide les données d'un capteur individuel.
    
    Args:
        sensor_data: Dictionnaire des valeurs des capteurs
        
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    data = _normalize_keys(sensor_data)
    
    # Vérification des capteurs manquants
    missing = [s for s in REQUIRED_SENSORS if s not in data]
    if missing:
        errors.append(f"Capteurs manquants: {missing}")
        return False, errors
    
    # Vérification des valeurs
    for sensor, (min_val, max_val) in PHYSICAL_LIMITS.items():
        if sensor in data:
            val = data[sensor]
            
            if not _is_valid_number(val):
                errors.append(f"{sensor}: valeur NaN ou Infini détectée")
                continue
            
            val = float(val)
            if not (min_val <= val <= max_val):
                errors.append(f"{sensor}: {val} hors limites [{min_val}, {max_val}]")
    
    return len(errors) == 0, errors


def validate_sensor_batch(sensor_batch: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """
    Valide un batch de données capteurs.
    
    Args:
        sensor_batch: Liste de dictionnaires de capteurs
        
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    
    for idx, data in enumerate(sensor_batch):
        is_valid, batch_errors = validate_sensor_data(data)
        if not is_valid:
            errors.append(f"Échantillon {idx}: {batch_errors}")
    
    return len(errors) == 0, errors


# ============================================================
# VALIDATION DES DONNÉES D'ENTRAÎNEMENT
# ============================================================

def validate_training_data(data_list: List[Dict[str, Any]]) -> Tuple[bool, Dict[str, Any]]:
    """
    Validation adaptée aux données NASA multi-moteurs.
    
    Args:
        data_list: Liste des échantillons d'entraînement
        
    Returns:
        (is_valid, report_dict)
    """
    report = {
        'valid': True,
        'total_samples': len(data_list),
        'valid_samples': len(data_list),
        'invalid_samples': 0,
        'errors': [],
        'warnings': []
    }
    
    if not data_list:
        report['valid'] = False
        report['errors'].append("Aucune donnée fournie")
        return False, report
    
    # Vérification par moteur
    engine_cycles = {}
    engine_rul_values = {}
    
    for idx, sample in enumerate(data_list):
        engine_id = sample.get('engine_id', 'unknown')
        cycle = sample.get('cycle')
        rul = sample.get('rul', sample.get('RUL'))
        
        # Collecte des cycles
        if engine_id not in engine_cycles:
            engine_cycles[engine_id] = []
            engine_rul_values[engine_id] = []
        if cycle is not None:
            engine_cycles[engine_id].append(cycle)
        if rul is not None:
            engine_rul_values[engine_id].append(rul)
    
    # Vérification de l'ordre des cycles
    for engine_id, cycles in engine_cycles.items():
        if len(cycles) > 1 and cycles != sorted(cycles):
            report['warnings'].append(f"Moteur {engine_id}: cycles non ordonnés")
        
        # Vérification que les RUL sont décroissantes
        ruls = engine_rul_values.get(engine_id, [])
        if len(ruls) > 1:
            for i in range(len(ruls) - 1):
                if ruls[i] < ruls[i + 1]:
                    report['warnings'].append(
                        f"Moteur {engine_id}: RUL croissante (cycle {i} → {i+1})"
                    )
                    break
    
    # Vérification des NaN/Inf
    nan_count = 0
    for idx, sample in enumerate(data_list[:500]):  # Limite pour performance
        for key, value in sample.items():
            if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
                nan_count += 1
                if len(report['errors']) < 10:  # Limite à 10 erreurs
                    report['errors'].append(f"NaN/Inf détecté: {key} dans échantillon {idx}")
    
    if nan_count > 0:
        report['invalid_samples'] = nan_count
        report['valid_samples'] = len(data_list) - nan_count
    
    # Vérification des RUL négatives
    for sample in data_list[:100]:
        rul = sample.get('rul', sample.get('RUL'))
        if rul is not None and rul < 0:
            report['errors'].append(f"RUL négative: {rul}")
    
    report['valid'] = len(report['errors']) == 0
    
    return report['valid'], report


def get_validation_summary(report: Dict[str, Any]) -> str:
    """
    Génère un résumé lisible du rapport de validation.
    """
    if report.get('valid', False):
        return f"✅ {report.get('valid_samples', 0)} échantillons valides sur {report.get('total_samples', 0)}"
    else:
        errors_count = len(report.get('errors', []))
        return f"❌ {report.get('invalid_samples', 0)} échantillons invalides, {errors_count} erreurs"


def get_detailed_validation_report(data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Génère un rapport de validation détaillé pour l'affichage frontend.
    
    Args:
        data_list: Liste des échantillons
        
    Returns:
        Rapport détaillé avec statistiques
    """
    is_valid, report = validate_training_data(data_list)
    
    # Statistiques supplémentaires
    engine_count = len(set(s.get('engine_id', 'unknown') for s in data_list))
    avg_rul = np.mean([s.get('rul', s.get('RUL', 125)) for s in data_list if s.get('rul') is not None]) if data_list else 0
    
    return {
        'is_valid': is_valid,
        'summary': get_validation_summary(report),
        'total_samples': len(data_list),
        'engine_count': engine_count,
        'average_rul': round(avg_rul, 2),
        'errors': report.get('errors', [])[:10],
        'warnings': report.get('warnings', [])[:5]
    }