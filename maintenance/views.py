# maintenance/views.py
from django.shortcuts import redirect, render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Avg, Q
from datetime import timedelta
import json
import logging
from django.contrib.auth.hashers import check_password
from django.views.decorators.http import require_http_methods
from .models import EngineTimeSeries, PredictionHistory, MaintenanceAlert, Engine, TrainingHistory
from .tasks.task import process_engine_telemetry
from .tasks.train import train_model_task, validate_training_data_task, get_training_history_task
from celery.result import AsyncResult
from aeronoth.celery import app

logger = logging.getLogger(__name__)

# ============================================================
# VUES TEMPLATES
# ============================================================

def test_radar_view(request):
    """Live Radar page"""
    return render(request, 'live_radar.html')


def input_form_view(request):
    """Formulaire de saisie manuelle"""
    return render(request, 'input_form.html')


def history_view(request):
    """Historique des alertes"""
    return render(request, 'history.html')


def analytic_view(request):
    """Page d'analytique"""
    return render(request, 'analytics.html')


def dashboard_view(request):
    """Cockpit principal - Vue d'ensemble"""
    engines = Engine.objects.all()
    context = {
        'total_engines': engines.count(),
        'critical_count': engines.filter(status__contains='CRITICAL').count(),
        'warning_count': engines.filter(status__contains='WARNING').count(),
        'healthy_count': engines.filter(status__contains='HEALTHY').count(),
        'active_alerts': MaintenanceAlert.objects.filter(is_read=False).count(),
    }
    return render(request, 'cockpit.html', context)


def training_history_view(request):
    """Page d'historique des entraînements"""
    return render(request, 'training_history.html')


def training_detail_view(request, history_id):
    """Page de détail d'un entraînement"""
    context = {'history_id': history_id}
    return render(request, 'training_detail.html', context)


# ============================================================
# API - MOTEURS & ALERTES
# ============================================================

def get_engines_list(request):
    """Retourne la liste de tous les moteurs"""
    engines = Engine.objects.all().values('unit_id', 'status')
    return JsonResponse({'engines': list(engines)})


def get_engines_status(request):
    """Retourne le statut détaillé de tous les moteurs"""
    engines = Engine.objects.all().prefetch_related('predictions')
    data = []
    
    for e in engines:
        last_pred = e.predictions.first() if e.predictions.exists() else None
        data.append({
            'unit_id': e.unit_id,
            'status': e.status,
            'current_rul': last_pred.predicted_rul if last_pred else None,
            'anomaly_count': last_pred.anomaly_count if last_pred else 0,
            'last_cycle': last_pred.cycle if last_pred else None,
            'trend': 'degrading' if last_pred and last_pred.predicted_rul < 50 else 'stable'
        })
    return JsonResponse({'engines': data})


def get_recent_alerts(request):
    """API pour récupérer les alertes avec statut is_read"""
    limit = int(request.GET.get('limit', 50))

    predictions = PredictionHistory.objects.select_related('engine').prefetch_related(
        'alerts'
    ).order_by('-timestamp')[:limit]

    alerts = []
    for pred in predictions:
        diagnosis = pred.raw_result.get('diagnosis', {}) if pred.raw_result else {}
        alert_obj = pred.alerts.first()

        alerts.append({
            'id': pred.id,
            'engine_id': pred.engine.unit_id,
            'status': pred.status,
            'rul': round(pred.predicted_rul, 2),
            'anomalies_count': pred.anomaly_count,
            'cycle': pred.cycle,
            'timestamp': pred.timestamp.isoformat(),
            'timestamp_display': pred.timestamp.strftime('%H:%M:%S'),
            'is_read': alert_obj.is_read if alert_obj else True,
            'diagnosis': {
                'summary': diagnosis.get('summary', ''),
                'global_risk_score': diagnosis.get('global_risk_score', 0),
                'actions': diagnosis.get('actions', []),
                'causes': diagnosis.get('causes', [])
            }
        })
    return JsonResponse({'alerts': alerts})


@csrf_exempt
@require_http_methods(["POST"])
def mark_alert_as_read(request, alert_id):
    """Marque une alerte comme lue"""
    try:
        alert = MaintenanceAlert.objects.get(prediction_id=alert_id)
        alert.is_read = True
        alert.acknowledged_at = timezone.now()
        alert.save()
        return JsonResponse({'success': True})
    except MaintenanceAlert.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Alert not found'}, status=404)


@csrf_exempt
@require_http_methods(["POST"])
def mark_all_alerts_as_read(request):
    """Marque toutes les alertes comme lues"""
    count = MaintenanceAlert.objects.filter(is_read=False).update(
        is_read=True,
        acknowledged_at=timezone.now()
    )
    return JsonResponse({'success': True, 'count': count})


@csrf_exempt
@require_http_methods(["POST"])
def clear_all_alerts(request):
    """Supprime TOUTES les alertes de la base"""
    alert_count = MaintenanceAlert.objects.all().delete()[0]
    pred_count = PredictionHistory.objects.all().delete()[0]
    return JsonResponse({
        'success': True,
        'message': f'{alert_count} alertes et {pred_count} prédictions supprimées.'
    })


def get_unread_count(request):
    """Retourne le nombre d'alertes non lues (pour badge)"""
    count = MaintenanceAlert.objects.filter(is_read=False).count()
    return JsonResponse({'unread_count': count})


# ============================================================
# API - PRÉDICTION
# ============================================================

@csrf_exempt
@require_http_methods(["POST"])
def predict_engine_status(request):
    """Lance l'IA en arrière-plan (Celery) et retourne un task_id"""
    try:
        data = json.loads(request.body)
        engine_id = data.get('engine_id', 'UNKNOWN_ENGINE')

        sensor_data = {
            "Altitude": data.get('altitude', 35000),
            "Mach": data.get('mach', 0.6),
            "Regime": data.get('regime', 100),
            "Temp_Entree_LPC": data.get('s2', 518.67),
            "Temp_Sortie_HPC": data.get('s3', 1589.0),
            "Temp_Sortie_LPT": data.get('s4', 1406.0),
            "Pression_Sortie_HPC": data.get('s7', 554.0),
            "Vitesse_Physique_Fan": data.get('s8', 2388.0),
            "Vitesse_Physique_Core": data.get('s9', 9064.0),
            "Pression_Sortie_LPT": data.get('s11', 47.0),
            "Vitesse_HPC_Sortie": data.get('s12', 522.0),
            "Vitesse_LPC_Sortie": data.get('s13', 2388.0),
            "Vitesse_Bypass": data.get('s14', 8143.0),
            "Pression_Bouchon": data.get('s15', 8.4),
            "Vitesse_Rotation_HPC": data.get('s17', 392.0),
            "Rapport_Pression_HPC": data.get('s20', 39.0),
            "Pression_Entree_Fan": data.get('s21', 23.0),
        }
        cycle = data.get('cycle', 1)
        
        task = process_engine_telemetry.delay(engine_id, sensor_data, cycle=cycle)
        
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'status': 'processing',
            'message': f'Analyse IA lancée pour {engine_id}...'
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)
    except Exception as e:
        logger.error(f"Erreur predict_engine_status: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def get_task_status(request, task_id):
    """Vérifie le statut d'une tâche Celery (diagnostic)."""
    task = AsyncResult(task_id, app=app)
    status_map = {
        'PENDING': 'PENDING',
        'STARTED': 'PROCESSING',
        'RETRY': 'PROCESSING',
        'PROGRESS': 'PROCESSING',
        'SUCCESS': 'SUCCESS',
        'FAILURE': 'FAILURE',
    }
    response = {
        'task_id': task_id,
        'status': status_map.get(task.state, task.state),
    }
    if task.state == 'SUCCESS':
        response['result'] = task.result
        response['message'] = task.result.get('message', 'Analyse terminée')
    elif task.state == 'FAILURE':
        #  CORRECTION : Gérer le cas où task.info est une Exception
        error_msg = str(task.info) if task.info else 'Erreur inconnue'
        response['error'] = error_msg
        response['message'] = ' Échec de l\'analyse'
    elif task.state == 'PROGRESS':
        #  CORRECTION : Vérifier que task.info est un dict
        if task.info and isinstance(task.info, dict):
            response['message'] = task.info.get('message', 'Analyse en cours...')
            response['progress'] = task.info
        else:
            response['message'] = 'Analyse en cours...'
    elif task.state == 'PENDING':
        response['message'] = '⏳ En attente...'
    elif task.state == 'STARTED':
        response['message'] = '🔄 Analyse en cours...'
    else:
        response['message'] = f'État: {task.state}'
    return JsonResponse(response)
# ============================================================
# API - ANALYTIQUE & TENDANCES
# ============================================================

def get_engine_trend(request, engine_id):
    """Analyse la tendance de dégradation d'un moteur"""
    from maintenance.utils import calculate_trend_slope, classify_trend
    
    predictions = PredictionHistory.objects.filter(
        engine__unit_id=engine_id
    ).order_by('-cycle')[:10]

    if len(predictions) < 2:
        return JsonResponse({
            'trend': 'stable',
            'message': 'Pas assez de données pour analyser la tendance'
        })

    ruls = [p.predicted_rul for p in predictions]
    cycles = [p.cycle for p in predictions]

    slope = calculate_trend_slope(cycles, ruls)
    trend, message = classify_trend(slope)

    return JsonResponse({
        'engine_id': engine_id,
        'trend': trend,
        'slope': round(slope, 3),
        'message': message,
        'recent_ruls': ruls[:5],
        'recent_cycles': cycles[:5]
    })


def get_fleet_health(request):
    """Vue d'ensemble intelligente de la flotte"""
    engines = Engine.objects.all()
    
    total = engines.count()
    critical = engines.filter(status__contains='CRITICAL').count()
    warning = engines.filter(status__contains='WARNING').count()
    healthy = engines.filter(status__contains='HEALTHY').count()
    
    avg_rul_critical = PredictionHistory.objects.filter(
        status__contains='CRITICAL'
    ).values('engine').annotate(avg=Avg('predicted_rul')).aggregate(Avg('avg'))['avg__avg'] or 0
    
    unread_alerts = MaintenanceAlert.objects.filter(is_read=False).count()
    
    last_24h = timezone.now() - timedelta(hours=24)
    recent_alerts = MaintenanceAlert.objects.filter(triggered_at__gte=last_24h).count()
    
    return JsonResponse({
        'fleet': {
            'total': total,
            'critical': critical,
            'warning': warning,
            'healthy': healthy,
            'health_score': round((healthy / total * 100) if total > 0 else 0, 1)
        },
        'metrics': {
            'avg_rul_critical': round(avg_rul_critical, 1),
            'unread_alerts': unread_alerts,
            'alerts_last_24h': recent_alerts
        }
    })


def get_engine_time_series(request, engine_id):
    """Retourne l'historique complet d'un moteur pour graphiques"""
    try:
        engine = Engine.objects.get(unit_id=engine_id)
        series = EngineTimeSeries.objects.filter(engine=engine).order_by('cycle')
        
        data = {
            'engine_id': engine_id,
            'cycles': [s.cycle for s in series],
            'rul_values': [s.rul_remaining for s in series],
            'health_values': [s.health_score for s in series],
            'anomaly_counts': [s.anomaly_count for s in series],
            'statuses': [s.status for s in series],
            'timestamps': [s.timestamp.strftime('%H:%M:%S') for s in series],
        }
        return JsonResponse(data)
    except Engine.DoesNotExist:
        return JsonResponse({'error': 'Engine not found'}, status=404)


# ============================================================
# API - ENTRAÎNEMENT DU MODÈLE
# ============================================================

@csrf_exempt
@require_http_methods(["POST"])
def train_model_view(request):
    """Lance l'entraînement du modèle LSTM"""
    try:
        data = json.loads(request.body)
        training_data = data.get('training_data', [])
        epochs = data.get('epochs', 20)
        engine_id_for_prediction = data.get('engine_id_for_prediction', None)
        
        if not training_data:
            return JsonResponse({
                'success': False,
                'error': 'Aucune donnée d\'entraînement fournie'
            }, status=400)
        
        # 🔥 Créer l'historique d'entraînement
        user = request.user if request.user.is_authenticated else None
        training_history = TrainingHistory.objects.create(
            status='PENDING',
            epochs=epochs,
            samples_count=len(training_data),
            user=user
        )
        
        # Lancer la tâche Celery avec l'ID de l'historique
        task = train_model_task.delay(
            training_data=training_data,
            epochs=epochs,
            user_id=user.id if user else None,
            engine_id_for_prediction=engine_id_for_prediction,
            training_history_id=training_history.id
        )
        
        # Mettre à jour l'historique avec le task_id
        training_history.task_id = task.id
        training_history.save(update_fields=['task_id'])
        
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'training_history_id': training_history.id,
            'message': f'✅ Entraînement lancé avec {len(training_data)} échantillons',
            'estimated_duration': _estimate_duration(len(training_data), epochs)
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)
    except Exception as e:
        logger.error(f"Erreur train_model_view: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def validate_data_view(request):
    """Valide les données sans entraîner"""
    try:
        data = json.loads(request.body)
        training_data = data.get('training_data', [])
        
        if not training_data:
            return JsonResponse({'success': False, 'error': 'Aucune donnée fournie'}, status=400)
        
        task = validate_training_data_task.delay(training_data)
        
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'message': '🔍 Validation lancée'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def get_train_task_status(request, task_id):
    """Vérifie le statut d'une tâche d'entraînement"""
    task = AsyncResult(task_id, app=app)
    
    response = {
        'task_id': task_id,
        'status': task.state,
    }
    
    if task.state == 'SUCCESS':
        result = task.result
        response['result'] = result
        response['message'] = result.get('message', '✅ Entraînement terminé !')
        response['short_message'] = result.get('short_message', '')
        response['long_message'] = result.get('long_message', '')
        response['health_status'] = result.get('health_status', '')
        response['predicted_rul'] = result.get('predicted_rul')
        response['causes'] = result.get('causes', [])
        response['actions'] = result.get('actions', [])
        response['training_history_id'] = result.get('training_history_id')
    elif task.state == 'FAILURE':
        response['error'] = str(task.info)
        response['message'] = '❌ Échec de l\'entraînement'
    elif task.state == 'PROGRESS':
        response['message'] = task.info.get('message', '🔄 Entraînement en cours...')
        response['progress'] = task.info
        response['training_history_id'] = task.info.get('training_history_id')
    elif task.state == 'PENDING':
        response['message'] = '⏳ En attente...'
    elif task.state == 'STARTED':
        response['message'] = '🔄 Entraînement en cours...'
    else:
        response['message'] = f'État: {task.state}'
        if task.info:
            response['message'] = task.info.get('message', response['message'])
    
    return JsonResponse(response)


# ============================================================
# API - HISTORIQUE DES ENTRAÎNEMENTS
# ============================================================

def get_training_history_list(request):
    """Récupère la liste de tous les entraînements"""
    limit = int(request.GET.get('limit', 50))
    
    trainings = TrainingHistory.objects.select_related('user').order_by('-started_at')[:limit]
    
    data = []
    for t in trainings:
        data.append({
            'id': t.id,
            'task_id': t.task_id,
            'status': t.status,
            'started_at': t.started_at.isoformat(),
            'completed_at': t.completed_at.isoformat() if t.completed_at else None,
            'duration_seconds': t.duration_seconds,
            'epochs': t.epochs,
            'samples_count': t.samples_count,
            'global_score': t.global_score,
            'performance_level': t.performance_level,
            'predicted_rul': t.predicted_rul,
            'health_status': t.health_status,
            'short_message': t.short_message,
            'is_viewed': t.is_viewed,
            'user_name': t.user.username if t.user else None
        })
    
    return JsonResponse({'trainings': data, 'count': len(data)})


def get_training_history_detail(request, history_id):
    """Récupère les détails d'un entraînement spécifique"""
    try:
        training = TrainingHistory.objects.get(id=history_id)
        
        # 🔥 Marquer comme vu si l'utilisateur consulte
        if not training.is_viewed:
            training.mark_as_viewed()
        
        return JsonResponse({
            'id': training.id,
            'task_id': training.task_id,
            'status': training.status,
            'started_at': training.started_at.isoformat(),
            'completed_at': training.completed_at.isoformat() if training.completed_at else None,
            'duration_seconds': training.duration_seconds,
            'epochs': training.epochs,
            'samples_count': training.samples_count,
            'batch_size': training.batch_size,
            'learning_rate': training.learning_rate,
            'rmse_before': training.rmse_before,
            'rmse_after': training.rmse_after,
            'r2_before': training.r2_before,
            'r2_after': training.r2_after,
            'safety_score_before': training.safety_score_before,
            'safety_score_after': training.safety_score_after,
            'global_score': training.global_score,
            'performance_level': training.performance_level,
            'predicted_rul': training.predicted_rul,
            'health_status': training.health_status,
            'short_message': training.short_message,
            'long_message': training.long_message,
            'causes': training.causes,
            'actions': training.actions,
            'detected_anomalies': training.detected_anomalies,
            'is_viewed': training.is_viewed,
            'viewed_at': training.viewed_at.isoformat() if training.viewed_at else None,
            'error_message': training.error_message,
            'user_name': training.user.username if training.user else None,
            'full_result': training.full_result
        })
        
    except TrainingHistory.DoesNotExist:
        return JsonResponse({'error': 'Training history not found'}, status=404)


@csrf_exempt
@require_http_methods(["POST"])
def mark_training_as_viewed(request, history_id):
    """Marque un entraînement comme vu par l'utilisateur"""
    try:
        training = TrainingHistory.objects.get(id=history_id)
        training.mark_as_viewed()
        return JsonResponse({'success': True, 'viewed_at': training.viewed_at.isoformat()})
    except TrainingHistory.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Training not found'}, status=404)
# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def _estimate_duration(n_samples: int, epochs: int) -> str:
    """Estime la durée d'entraînement"""
    from maintenance.utils import estimate_training_duration
    return estimate_training_duration(n_samples, epochs)


def profile_view(request):
    """Page de profil utilisateur"""
    if not request.user.is_authenticated:
        return redirect('connexion')
    return render(request, 'profile.html')

@csrf_exempt
@require_http_methods(["PUT"])
def update_profile(request):
    """Mettre à jour le profil utilisateur"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Non authentifié'}, status=401)
    try:
        data = json.loads(request.body)
        user = request.user
        
        if 'first_name' in data:
            user.first_name = data['first_name']
        if 'last_name' in data:
            user.last_name = data['last_name']
        if 'email' in data:
            user.email = data['email']
        user.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
@require_http_methods(["POST"])
def change_password(request):
    """Changer le mot de passe"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Non authentifié'}, status=401)
    try:
        data = json.loads(request.body)
        user = request.user
        
        if not check_password(data.get('current_password'), user.password):
            return JsonResponse({'error': 'Mot de passe actuel incorrect'}, status=400)
        
        new_password = data.get('new_password')
        if len(new_password) < 8:
            return JsonResponse({'error': 'Le mot de passe doit contenir au moins 8 caractères'}, status=400)
        
        user.set_password(new_password)
        user.save()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)