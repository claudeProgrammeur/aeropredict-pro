"""
Utilitaires pour l'analyse des moteurs
"""
import numpy as np
from maintenance.constants import (
    TREND_RAPID_DEGRADATION, TREND_DEGRADING, TREND_STABLE, TREND_IMPROVING,
    TREND_SLOPE_CRITICAL, TREND_SLOPE_WARNING, TREND_SLOPE_IMPROVING
)


def calculate_trend_slope(cycles: list, ruls: list) -> float:
    """
    Calcule la pente de régression linéaire entre cycles et RUL.
    
    Args:
        cycles: Liste des numéros de cycles
        ruls: Liste des RUL correspondantes
        
    Returns:
        Pente de la tendance (négative = dégradation, positive = amélioration)
    """
    if len(cycles) < 2:
        return 0.0

    try:
        # Utiliser numpy pour une régression plus robuste
        coefficients = np.polyfit(cycles, ruls, 1)
        return float(coefficients[0])
    except Exception:
        # Fallback au calcul manuel si numpy échoue
        n = len(ruls)
        sum_x = sum(cycles)
        sum_y = sum(ruls)
        sum_xy = sum(x * y for x, y in zip(cycles, ruls))
        sum_xx = sum(x * x for x in cycles)

        denominator = n * sum_xx - sum_x * sum_x
        if denominator == 0:
            return 0.0

        return (n * sum_xy - sum_x * sum_y) / denominator


def classify_trend(slope: float) -> tuple:
    """
    Classifie la tendance basée sur la pente.
    
    Args:
        slope: Pente de la régression
        
    Returns:
        Tuple (trend_code, message)
    """
    if slope < TREND_SLOPE_CRITICAL:
        return TREND_RAPID_DEGRADATION, "Dégradation rapide détectée !"
    elif slope < TREND_SLOPE_WARNING:
        return TREND_DEGRADING, "Dégradation progressive."
    elif slope > TREND_SLOPE_IMPROVING:
        return TREND_IMPROVING, "Amélioration détectée."
    else:
        return TREND_STABLE, "État stable."


def estimate_training_duration(n_samples: int, epochs: int) -> str:
    """
    Estime la durée d'entraînement basée sur le nombre d'échantillons.
    
    Args:
        n_samples: Nombre d'échantillons d'entraînement
        epochs: Nombre d'epochs
        
    Returns:
        Estimation textuelle de la durée
    """
    if n_samples < 10:
        return "quelques secondes"
    elif n_samples < 50:
        return "30-60 secondes"
    elif n_samples < 200:
        return "1-2 minutes"
    elif n_samples < 1000:
        return "3-5 minutes"
    else:
        return "5-10 minutes"
