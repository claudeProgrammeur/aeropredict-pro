"""
Tâche Celery pour l'entraînement asynchrone du modèle LSTM.
Version RENFORCÉE - Production Ready - AVEC HISTORIQUE
"""

import logging
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from datetime import datetime
from typing import Dict, Any, Optional
from django.utils import timezone
from django.contrib.auth.models import User

from ai_engine.trainer import train_lstm_model
from ai_engine.validators import validate_training_data, get_validation_summary


logger = logging.getLogger(__name__)

# ============================================================
# TÂCHE D'ENTRAÎNEMENT PRINCIPALE
# ============================================================

@shared_task(
    bind=True,
    name='maintenance.tasks.train_model_task',
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=1200,      # 20 minutes max
    time_limit=1800,           # 30 minutes hard limit
    # queue='engine_analysis'
)
def train_model_task(
    self,
    training_data: list = None,
    epochs: int = 30,
    user_id: Optional[int] = None,
    engine_id_for_prediction: Optional[str] = None,
    training_history_id: Optional[int] = None
) -> dict:
    """
    Lance l'entraînement du modèle LSTM en arrière-plan.
    
    Args:
        training_data: Liste de dictionnaires (cycles avec capteurs et RUL)
        epochs: Nombre d'époques (défaut: 30)
        user_id: ID de l'utilisateur qui a lancé l'entraînement
        engine_id_for_prediction: ID du moteur à analyser après entraînement
        training_history_id: ID de l'objet TrainingHistory à mettre à jour
        
    Returns:
        Dict contenant les résultats détaillés de l'entraînement
    """
    task_id = self.request.id
    logger.info("=" * 60)
    logger.info(f"🚀 TÂCHE D'ENTRAÎNEMENT {task_id} DÉMARRÉE")
    logger.info("=" * 60)
    
    # 🔥 Récupérer ou créer l'historique
    from maintenance.models import TrainingHistory
    
    training_history = None
    if training_history_id:
        try:
            training_history = TrainingHistory.objects.get(id=training_history_id)
            training_history.status = 'RUNNING'
            if task_id:  # 🔥 Vérifier que task_id n'est pas vide
                training_history.task_id = task_id
            training_history.save(update_fields=['status', 'task_id'])
            
            logger.info(f"📝 Historique chargé: {training_history_id}")
        except TrainingHistory.DoesNotExist:
            logger.warning(f"⚠️ Historique {training_history_id} non trouvé, création d'un nouveau")
    
    if not training_history and user_id:
        try:
            user = User.objects.get(id=user_id) if user_id else None
            training_history = TrainingHistory.objects.create(
                task_id=task_id,
                user=user,
                status='RUNNING',
                epochs=epochs,
                samples_count=len(training_data) if training_data else 0
            )
            training_history_id = training_history.id
            logger.info(f"📝 Nouvel historique créé: {training_history_id}")
        except Exception as e:
            logger.warning(f"⚠️ Impossible de créer l'historique: {e}")
    
    # Mise à jour du statut pour le frontend
    self.update_state(
        state='PROGRESS',
        meta={
            'status': 'starting',
            'message': 'Initialisation de l\'entraînement...',
            'task_id': task_id,
            'training_history_id': training_history_id
        }
    )
    
    try:
        # ========================================================
        # ÉTAPE 1: VALIDATION DES DONNÉES
        # ========================================================
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'validating',
                'message': '📋 Validation des données...',
                'task_id': task_id,
                'training_history_id': training_history_id
            }
        )
        
        if training_data is None or len(training_data) == 0:
            error_msg = 'Aucune donnée fournie'
            if training_history:
                training_history.status = 'FAILED'
                training_history.error_message = error_msg
                training_history.completed_at = timezone.now()
                training_history.save()
            return {
                'status': 'failed',
                'error': error_msg,
                'task_id': task_id,
                'message': '❌ Veuillez fournir des données d\'entraînement.',
                'training_history_id': training_history_id
            }
        
        logger.info(f"📊 {len(training_data)} échantillons reçus")
        
        # Validation rapide
        is_valid, validation_report = validate_training_data(training_data)
        
        if not is_valid:
            errors = validation_report.get('errors', [])[:5]
            error_msg = f'Données invalides: {errors}'
            if training_history:
                training_history.status = 'FAILED'
                training_history.error_message = error_msg
                training_history.completed_at = timezone.now()
                training_history.save()
            return {
                'status': 'failed',
                'error': error_msg,
                'task_id': task_id,
                'validation_report': validation_report,
                'message': f'❌ {get_validation_summary(validation_report)}',
                'training_history_id': training_history_id
            }
        
        valid_samples = validation_report.get('valid_samples', len(training_data))
        logger.info(f"✅ Validation réussie : {valid_samples} échantillons valides")
        
        if training_history:
            training_history.samples_count = valid_samples
            training_history.save(update_fields=['samples_count'])
        
        # ========================================================
        # ÉTAPE 2: LANCEMENT DE L'ENTRAÎNEMENT
        # ========================================================
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'training',
                'message': f'🔥 Entraînement sur {len(training_data)} cycles...',
                'task_id': task_id,
                'total_samples': len(training_data),
                'training_history_id': training_history_id
            }
        )
        
        # Appel au trainer avec callback de progression
        result = train_lstm_model(
            training_data=training_data,
            epochs=epochs,
            save_model=True,
            training_history_id=training_history_id,
            user_id=user_id,
            engine_id_for_prediction=engine_id_for_prediction,
            progress_callback=lambda epoch, loss, val_loss: self.update_state(
                state='PROGRESS',
                meta={
                    'status': 'epoch',
                    'message': f'⏳ Époque {epoch}/{epochs} - Loss: {loss:.4f}',
                    'task_id': task_id,
                    'current_epoch': epoch,
                    'total_epochs': epochs,
                    'loss': loss,
                    'val_loss': val_loss,
                    'training_history_id': training_history_id
                }
            )
        )
        
        # ========================================================
        # ÉTAPE 3: ANALYSE DES PRÉDICTIONS
        # ========================================================
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'predicting',
                'message': '📊 Analyse des prédictions...',
                'task_id': task_id,
                'training_history_id': training_history_id
            }
        )
        
        # Extraire les prédictions pour chaque moteur
        predictions_summary = _analyze_predictions_by_engine(result, training_data)
        
        # ========================================================
        # ÉTAPE 4: CONSTRUCTION DE LA RÉPONSE FINALE
        # ========================================================
        result['task_id'] = task_id
        result['completed_at'] = datetime.now().isoformat()
        result['predictions_summary'] = predictions_summary
        result['message'] = _build_final_message(result, predictions_summary)
        result['recommendation'] = _build_recommendation(predictions_summary)
        result['training_history_id'] = training_history_id
        
        # 🔥 Ajouter les messages générés par l'historique
        if training_history:
            # Recharger l'historique pour avoir les messages générés
            training_history.refresh_from_db()
            result['short_message'] = training_history.short_message
            result['long_message'] = training_history.long_message
            result['health_status'] = training_history.health_status
            result['predicted_rul'] = training_history.predicted_rul
            result['causes'] = training_history.causes
            result['actions'] = training_history.actions
        
        if result['status'] == 'success':
            logger.info("=" * 60)
            logger.info(f"✅ TÂCHE {task_id} TERMINÉE AVEC SUCCÈS")
            logger.info(f"   Score: {result.get('global_score', 0):.1f}/100 | {result.get('performance_level', 'N/A')}")
            logger.info(f"   Moteurs analysés: {len(predictions_summary)}")
            if result.get('predicted_rul'):
                logger.info(f"   Prédiction RUL: {result.get('predicted_rul')} cycles")
            logger.info("=" * 60)
        else:
            logger.error(f"❌ Tâche {task_id} échouée: {result.get('error')}")
        
        return result
        
    except SoftTimeLimitExceeded:
        logger.error(f"⏰ Timeout - Tâche {task_id}")
        error_msg = 'Timeout - Entraînement trop long'
        if training_history:
            training_history.status = 'FAILED'
            training_history.error_message = error_msg
            training_history.completed_at = timezone.now()
            training_history.save()
        return {
            'status': 'failed',
            'error': error_msg,
            'task_id': task_id,
            'message': '⚠️ L\'entraînement a pris trop de temps. Essayez avec moins de données ou moins d\'époques.',
            'training_history_id': training_history_id
        }
        
    except Exception as e:
        logger.error(f"❌ Exception tâche {task_id}: {e}", exc_info=True)
        if training_history:
            training_history.status = 'FAILED'
            training_history.error_message = str(e)
            training_history.completed_at = timezone.now()
            training_history.save()
        return {
            'status': 'failed',
            'error': str(e),
            'task_id': task_id,
            'message': f'❌ Erreur durant l\'entraînement: {str(e)[:100]}',
            'training_history_id': training_history_id
        }


# ============================================================
# FONCTIONS AUXILIAIRES
# ============================================================

def _analyze_predictions_by_engine(result: Dict[str, Any], training_data: list) -> list:
    """
    Analyse les prédictions pour chaque moteur dans les données d'entraînement.
    """
    try:
        # Utiliser les vraies données de prédiction si disponibles
        if result.get('predicted_rul'):
            return [{
                'engine_id': training_data[0].get('engine_id', 'UNKNOWN') if training_data else 'UNKNOWN',
                'cycles': len(training_data),
                'estimated_rul': round(result['predicted_rul'], 1),
                'status': result.get('health_status', 'UNKNOWN'),
                'causes': result.get('causes', [])[:3],
                'actions': result.get('actions', [])[:3]
            }]
        
        # Fallback: estimation basée sur les métriques
        engines = {}
        for sample in training_data:
            engine_id = sample.get('engine_id', 'UNKNOWN')
            if engine_id not in engines:
                engines[engine_id] = {'engine_id': engine_id, 'cycles': 0, 'avg_rul': 0}
            engines[engine_id]['cycles'] += 1
        
        summary = []
        for engine_id, data in engines.items():
            avg_rul = 125 - (data['cycles'] * 0.5)
            
            if avg_rul <= 30:
                status = "🔴 CRITIQUE"
            elif avg_rul <= 60:
                status = "🟠 ATTENTION"
            elif avg_rul <= 90:
                status = "🟡 DÉGRADÉ"
            else:
                status = "🟢 SAIN"
            
            summary.append({
                'engine_id': engine_id,
                'cycles': data['cycles'],
                'estimated_rul': round(avg_rul, 1),
                'status': status
            })
        
        return summary
        
    except Exception as e:
        logger.error(f"Erreur analyse prédictions: {e}")
        return []


def _build_final_message(result: Dict[str, Any], predictions: list) -> str:
    """
    Construit le message final pour l'utilisateur.
    """
    if result['status'] != 'success':
        return result.get('message', '❌ Entraînement échoué.')
    
    # 🔥 Utiliser le message généré par l'historique si disponible
    if result.get('short_message'):
        return result['short_message']
    
    score = result.get('global_score', 0)
    perf = result.get('performance_level', 'INCONNU')
    
    message = f"""
✅ ENTRAÎNEMENT TERMINÉ !
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Score : {score:.1f}/100 ({perf})
📈 RMSE : {result.get('metrics_after', {}).get('rmse', '--')} cycles

📋 ANALYSE PAR MOTEUR :
"""
    
    for p in predictions[:5]:
        message += f"\n   {p['status']} {p['engine_id']} : {p['cycles']} cycles analysés"
    
    if len(predictions) > 5:
        message += f"\n   ... et {len(predictions) - 5} autre(s) moteur(s)"
    
    # 🔥 Ajouter les causes et actions si disponibles
    if result.get('causes'):
        message += "\n\n🔍 CAUSES DÉTECTÉES :"
        for cause in result['causes'][:3]:
            message += f"\n   • {cause}"
    
    if result.get('actions'):
        message += "\n\n✅ ACTIONS RECOMMANDÉES :"
        for action in result['actions'][:3]:
            message += f"\n   • {action}"
    
    if result.get('predicted_rul'):
        message += f"\n\n🔮 RUL PRÉDITE : {result['predicted_rul']:.1f} cycles"
        message += f"\n   Statut : {result.get('health_status', 'INCONNU')}"
    
    has_critical = any(p['status'] == '🔴 CRITIQUE' for p in predictions)
    has_warning = any(p['status'] in ['🟠 ATTENTION', '🟡 DÉGRADÉ'] for p in predictions)
    
    if has_critical:
        message += "\n\n⚠️ Des pannes imminentes ont été détectées !"
        message += "\n👉 Consultez la page Live Radar pour voir l'endroit exact de la panne."
    elif has_warning:
        message += "\n\n⚠️ Des signes de dégradation sont présents."
        message += "\n👉 Consultez le Live Radar pour plus de détails."
    else:
        message += "\n\n✅ Tous les moteurs analysés sont SAINS."
    
    return message


def _build_recommendation(predictions: list) -> str:
    """
    Construit une recommandation globale.
    """
    critical_count = sum(1 for p in predictions if 'CRITIQUE' in p['status'])
    warning_count = sum(1 for p in predictions if 'ATTENTION' in p['status'] or 'DÉGRADÉ' in p['status'])
    
    if critical_count > 0:
        return f"🚨 {critical_count} moteur(s) en état CRITIQUE. Intervention immédiate requise."
    elif warning_count > 0:
        return f"⚠️ {warning_count} moteur(s) montrent des signes de dégradation. Surveillance accrue recommandée."
    else:
        return "✅ Tous les moteurs sont en bon état. Maintenance préventive selon planning."


# ============================================================
# TÂCHE DE VALIDATION SEULE
# ============================================================

@shared_task(
    bind=True,
    name='maintenance.tasks.validate_training_data_task',
    max_retries=1,
    soft_time_limit=60,
    time_limit=90,
    queue='engine_analysis'
)
def validate_training_data_task(self, training_data: list) -> dict:
    """
    Valide les données d'entraînement sans lancer l'entraînement.
    """
    task_id = self.request.id
    logger.info(f"🔍 Tâche de validation {task_id} démarrée")
    
    try:
        is_valid, report = validate_training_data(training_data)
        
        return {
            'status': 'success' if is_valid else 'invalid',
            'task_id': task_id,
            'is_valid': is_valid,
            'summary': get_validation_summary(report),
            'report': report,
            'message': get_validation_summary(report),
            'completed_at': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Validation échouée: {e}")
        return {
            'status': 'failed',
            'error': str(e),
            'task_id': task_id,
            'message': f'❌ Erreur de validation: {str(e)}'
        }


# ============================================================
# TÂCHE POUR RÉCUPÉRER L'HISTORIQUE
# ============================================================

@shared_task(
    bind=True,
    name='maintenance.tasks.get_training_history_task',
    max_retries=2,
    default_retry_delay=5,
    queue='engine_analysis'
)
def get_training_history_task(self, training_history_id: int) -> dict:
    """
    Récupère les détails d'un entraînement depuis l'historique.
    """
    from maintenance.models import TrainingHistory
    
    try:
        history = TrainingHistory.objects.get(id=training_history_id)
        
        return {
            'status': history.status,
            'task_id': history.task_id,
            'started_at': history.started_at.isoformat() if history.started_at else None,
            'completed_at': history.completed_at.isoformat() if history.completed_at else None,
            'duration_seconds': history.duration_seconds,
            'epochs': history.epochs,
            'samples_count': history.samples_count,
            'rmse_before': history.rmse_before,
            'rmse_after': history.rmse_after,
            'global_score': history.global_score,
            'performance_level': history.performance_level,
            'predicted_rul': history.predicted_rul,
            'health_status': history.health_status,
            'short_message': history.short_message,
            'long_message': history.long_message,
            'causes': history.causes,
            'actions': history.actions,
            'detected_anomalies': history.detected_anomalies,
            'is_viewed': history.is_viewed,
            'error_message': history.error_message
        }
        
    except TrainingHistory.DoesNotExist:
        return {'status': 'not_found', 'error': 'Historique non trouvé'}
    except Exception as e:
        logger.error(f"Erreur récupération historique: {e}")
        return {'status': 'error', 'error': str(e)}