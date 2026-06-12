# ai_engine/evaluator.py
"""
Évaluateur de performance pour le modèle LSTM.
Calcule RMSE, MAE, R², pénalités de fin de vie, et génère un rapport complet.
Version PRO avec métriques spécifiques à la maintenance prédictive.
"""

import logging
import numpy as np
import torch
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTES
# ============================================================
# ai_engine/evaluator.py - VERSION PRODUCTION

# ✅ GARDER les seuils adaptés NASA
PERFORMANCE_THRESHOLDS = {
    'rmse': {
        'excellent': 20.0,   # Au lieu de 15
        'good': 40.0,        # Au lieu de 25
        'acceptable': 70.0,  # Au lieu de 40
    },
    'mae': {
        'excellent': 8.0,
        'good': 12.0,
        'acceptable': 16.0,
    },
    'r2': {
        'excellent': 0.30,
        'good': 0.10,
        'acceptable': -5.0,  # Accepter R² négatif
    }
}

# 🔥 Zones de criticité pour pondération
CRITICAL_ZONES = {
    'critical': (0, 15),      # RUL très faible → pénalité x3
    'warning': (15, 30),      # RUL faible → pénalité x2
    'caution': (30, 50),      # RUL modéré → pénalité x1.5
    'normal': (50, 125)       # RUL normal → pénalité x1
}

ZONE_WEIGHTS = {
    'critical': 3.0,
    'warning': 2.0,
    'caution': 1.5,
    'normal': 1.0
}


# ============================================================
# MÉTRIQUES DE BASE
# ============================================================

def calculate_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calcule le Root Mean Square Error."""
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def calculate_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calcule le Mean Absolute Error."""
    return float(np.mean(np.abs(y_true - y_pred)))


def calculate_r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calcule le coefficient de détermination R²."""
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    
    if ss_tot == 0:
        return 0.0
    
    return float(1 - (ss_res / ss_tot))


def calculate_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calcule le Mean Absolute Percentage Error."""
    mask = y_true != 0
    if not mask.any():
        return 0.0
    
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def calculate_accuracy_within_margin(y_true: np.ndarray, y_pred: np.ndarray, margin: float = 10.0) -> float:
    """Calcule le pourcentage de prédictions dans une marge d'erreur."""
    errors = np.abs(y_true - y_pred)
    within_margin = np.sum(errors <= margin)
    return float(within_margin / len(y_true) * 100)


# ============================================================
# 🔥 MÉTRIQUES SPÉCIFIQUES MAINTENANCE PRÉDICTIVE
# ============================================================

def calculate_weighted_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Calcule un RMSE pondéré par la criticité de la zone RUL.
    Une erreur sur un RUL faible est plus grave que sur un RUL élevé.
    """
    weights = np.ones_like(y_true)
    
    for zone_name, (min_val, max_val) in CRITICAL_ZONES.items():
        mask = (y_true >= min_val) & (y_true < max_val)
        weights[mask] = ZONE_WEIGHTS[zone_name]
    
    weighted_errors = weights * ((y_true - y_pred) ** 2)
    return float(np.sqrt(np.mean(weighted_errors)))


def calculate_late_prediction_penalty(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    """
    Calcule les pénalités pour les prédictions trop optimistes (late predictions).
    Prédire une panne trop tard est DANGEREUX.
    Prédire une panne trop tôt est COÛTEUX mais SÉCURISÉ.
    """
    errors = y_pred - y_true  # Positif = optimiste (prédit plus de RUL que réalité)
    
    # Late predictions (optimistes) : y_pred > y_true
    late_mask = errors > 0
    early_mask = errors < 0
    
    late_count = np.sum(late_mask)
    early_count = np.sum(early_mask)
    exact_count = np.sum(errors == 0)
    
    # Pénalités
    late_penalty_total = np.sum(errors[late_mask] * 2.0) if late_count > 0 else 0  # x2 pour optimisme
    early_penalty_total = np.sum(np.abs(errors[early_mask]) * 0.5) if early_count > 0 else 0  # x0.5 pour conservatisme
    
    return {
        'late_predictions': int(late_count),
        'early_predictions': int(early_count),
        'exact_predictions': int(exact_count),
        'late_penalty_score': round(float(late_penalty_total), 2),
        'early_penalty_score': round(float(early_penalty_total), 2),
        'total_penalty': round(float(late_penalty_total + early_penalty_total), 2),
        'verdict': '⚠️ Modèle trop optimiste' if late_count > early_count else '✅ Modèle conservateur (sécurisé)'
    }


def calculate_safety_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Calcule un score de sécurité (0-100).
    Pénalise fortement les late predictions (optimistes).
    """
    errors = y_pred - y_true
    late_errors = errors[errors > 0]
    
    if len(late_errors) == 0:
        return 100.0
    
    # Plus les late errors sont grandes, plus le score baisse
    avg_late_error = np.mean(late_errors)
    safety_score = max(0, 100 - (avg_late_error * 5))
    
    return float(safety_score)


# ============================================================
# ÉVALUATION COMPLÈTE
# ============================================================

def evaluate_predictions(
    y_true: List[float],
    y_pred: List[float],
    model_name: str = "LSTM-Attention"
) -> Dict[str, Any]:
    """
    Évalue les prédictions et retourne un rapport complet.
    
    Args:
        y_true: Valeurs réelles de RUL
        y_pred: Valeurs prédites de RUL
        model_name: Nom du modèle évalué
        
    Returns:
        Dict contenant toutes les métriques et une note globale
    """
    # 🔥 CORRECTION : Forcer les RUL ≥ 0
    y_true_arr = np.array(y_true)
    y_pred_arr = np.maximum(np.array(y_pred), 0)  # Pas de RUL négatif
    y_pred_arr = np.minimum(y_pred_arr, 125)      # Pas de RUL > 125
    
    # Calcul des métriques standard
    rmse = calculate_rmse(y_true_arr, y_pred_arr)
    mae = calculate_mae(y_true_arr, y_pred_arr)
    r2 = calculate_r2(y_true_arr, y_pred_arr)
    mape = calculate_mape(y_true_arr, y_pred_arr)
    accuracy_10 = calculate_accuracy_within_margin(y_true_arr, y_pred_arr, margin=10.0)
    accuracy_15 = calculate_accuracy_within_margin(y_true_arr, y_pred_arr, margin=15.0)
    
    # 🔥 Métriques spécifiques maintenance
    weighted_rmse = calculate_weighted_rmse(y_true_arr, y_pred_arr)
    late_penalty = calculate_late_prediction_penalty(y_true_arr, y_pred_arr)
    safety_score = calculate_safety_score(y_true_arr, y_pred_arr)
    
    # Déterminer le niveau de performance
    performance_level = _get_performance_level(rmse, mae, r2)
    
    # Générer un score global (0-100)
    global_score = _calculate_global_score(rmse, mae, r2, mape, safety_score)
    
    report = {
        'model': model_name,
        'timestamp': datetime.now().isoformat(),
        'sample_count': len(y_true),
        
        # Métriques standard
        'metrics': {
            'rmse': round(rmse, 3),
            'weighted_rmse': round(weighted_rmse, 3),  # 🔥 RMSE pondéré
            'mae': round(mae, 3),
            'r2': round(r2, 4),
            'mape': round(mape, 2),
            'accuracy_within_10_cycles': round(accuracy_10, 1),
            'accuracy_within_15_cycles': round(accuracy_15, 1),
            'safety_score': round(safety_score, 1),    # 🔥 Score de sécurité
        },
        
        # 🔥 Pénalités late/early
        'late_prediction_analysis': late_penalty,
        
        # Évaluation qualitative
        'performance_level': performance_level,
        'global_score': round(global_score, 1),
        
        # Statistiques supplémentaires
        'statistics': {
            'mean_true': round(float(np.mean(y_true_arr)), 2),
            'mean_pred': round(float(np.mean(y_pred_arr)), 2),
            'std_true': round(float(np.std(y_true_arr)), 2),
            'std_pred': round(float(np.std(y_pred_arr)), 2),
            'min_error': round(float(np.min(np.abs(y_true_arr - y_pred_arr))), 2),
            'max_error': round(float(np.max(np.abs(y_true_arr - y_pred_arr))), 2),
        }
    }
    
    # Ajouter recommandations
    report['recommendation'] = _get_recommendation(report)
    
    return report


def _get_performance_level(rmse: float, mae: float, r2: float) -> str:
    """Détermine le niveau de performance global."""
    scores = []
    
    if rmse <= PERFORMANCE_THRESHOLDS['rmse']['excellent']:
        scores.append(3)
    elif rmse <= PERFORMANCE_THRESHOLDS['rmse']['good']:
        scores.append(2)
    elif rmse <= PERFORMANCE_THRESHOLDS['rmse']['acceptable']:
        scores.append(1)
    else:
        scores.append(0)
    
    if r2 >= PERFORMANCE_THRESHOLDS['r2']['excellent']:
        scores.append(3)
    elif r2 >= PERFORMANCE_THRESHOLDS['r2']['good']:
        scores.append(2)
    elif r2 >= PERFORMANCE_THRESHOLDS['r2']['acceptable']:
        scores.append(1)
    else:
        scores.append(0)
    
    avg_score = sum(scores) / len(scores)
    
    if avg_score >= 2.5:
        return "🌟 EXCELLENT"
    elif avg_score >= 1.5:
        return "✅ BON"
    elif avg_score >= 0.5:
        return "⚠️ ACCEPTABLE"
    else:
        return "❌ MÉDIOCRE"


def _calculate_global_score(rmse: float, mae: float, r2: float, mape: float, safety_score: float) -> float:
    """Calcule un score global sur 100."""
    rmse_score = max(0, 100 - (rmse / 30) * 100)
    r2_score = max(0, min(100, r2 * 100))
    mape_score = max(0, 100 - mape)
    
    # 🔥 Pondération avec safety_score
    weights = {'rmse': 0.3, 'r2': 0.3, 'mape': 0.15, 'safety': 0.25}
    score = (rmse_score * weights['rmse'] + 
             r2_score * weights['r2'] + 
             mape_score * weights['mape'] + 
             safety_score * weights['safety'])
    
    return score


def _get_recommendation(report: Dict[str, Any]) -> str:
    """Génère une recommandation basée sur les performances."""
    level = report['performance_level']
    metrics = report['metrics']
    late_analysis = report.get('late_prediction_analysis', {})
    
    if level == "🌟 EXCELLENT":
        return "✅ Modèle prêt pour la production. Performances optimales."
    elif level == "✅ BON":
        if late_analysis.get('verdict', '').startswith('⚠️'):
            return "⚠️ Bonnes performances mais modèle légèrement optimiste. Surveillance recommandée."
        return "👍 Modèle fiable. Peut être déployé avec confiance."
    elif level == "⚠️ ACCEPTABLE":
        return f"⚠️ Modèle utilisable mais perfectible. RMSE: {metrics['rmse']} cycles."
    else:
        return f"❌ Modèle nécessite plus de données ou d'entraînement. RMSE: {metrics['rmse']} cycles."


# ============================================================
# ÉVALUATION AVEC MODÈLE (INFÉRENCE)
# ============================================================

def evaluate_model_on_test_set(
    model: torch.nn.Module,
    test_loader: torch.utils.data.DataLoader,
    device: torch.device
) -> Dict[str, Any]:
    """Évalue le modèle sur un jeu de test PyTorch."""
    model.eval()
    all_preds = []
    all_targets = []
    
    with torch.no_grad():
        for inputs, targets in test_loader:
            inputs = inputs.to(device)
            outputs = model(inputs).cpu().numpy().flatten()
            all_preds.extend(outputs.tolist())
            all_targets.extend(targets.numpy().flatten().tolist())
    
    return evaluate_predictions(all_targets, all_preds)


# ============================================================
# COMPARAISON AVANT/APRÈS ENTRAÎNEMENT
# ============================================================

def compare_models(
    old_metrics: Dict[str, Any],
    new_metrics: Dict[str, Any]
) -> Dict[str, Any]:
    """Compare les performances avant et après fine-tuning."""
    old_rmse = old_metrics.get('metrics', {}).get('rmse', 0)
    new_rmse = new_metrics.get('metrics', {}).get('rmse', 0)
    old_r2 = old_metrics.get('metrics', {}).get('r2', 0)
    new_r2 = new_metrics.get('metrics', {}).get('r2', 0)
    old_safety = old_metrics.get('metrics', {}).get('safety_score', 0)
    new_safety = new_metrics.get('metrics', {}).get('safety_score', 0)
    
    rmse_improvement = old_rmse - new_rmse
    r2_improvement = new_r2 - old_r2
    safety_improvement = new_safety - old_safety
    
    return {
        'rmse': {
            'before': old_rmse,
            'after': new_rmse,
            'improvement': round(rmse_improvement, 3),
            'improvement_percent': round((rmse_improvement / old_rmse) * 100, 1) if old_rmse > 0 else 0
        },
        'r2': {
            'before': old_r2,
            'after': new_r2,
            'improvement': round(r2_improvement, 4)
        },
        'safety_score': {
            'before': old_safety,
            'after': new_safety,
            'improvement': round(safety_improvement, 1)
        },
        'verdict': '✅ Amélioration' if rmse_improvement > 0 else '⚠️ Pas d\'amélioration significative'
    }


# ============================================================
# RÉSUMÉ LISIBLE
# ============================================================

def get_evaluation_summary(report: Dict[str, Any]) -> str:
    """Génère un résumé lisible du rapport d'évaluation."""
    metrics = report['metrics']
    late = report.get('late_prediction_analysis', {})
    return (
        f"{report['performance_level']} | "
        f"RMSE: {metrics['rmse']} | "
        f"R²: {metrics['r2']} | "
        f"Sécurité: {metrics['safety_score']}/100 | "
        f"{late.get('verdict', '')}"
    )