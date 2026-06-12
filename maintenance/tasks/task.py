"""
Tâches Celery asynchrones pour AeroPredict SaaS
Version: 9.0.0 - Production Ready - CORRIGÉE
"""

import time
import logging
import sys
import json
from typing import Dict, Any, Optional
from datetime import datetime

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded, MaxRetriesExceededError
from django.core.mail import send_mail
from django.db import transaction
from django.conf import settings
from django.utils import timezone

from ai_engine.core.predictor import AIEngine
from maintenance.models import Company, Engine, PredictionHistory, MaintenanceAlert

logger = logging.getLogger(__name__)

# ============================================================
# DÉTECTION WINDOWS
# ============================================================
IS_WINDOWS = sys.platform == 'win32'

# ============================================================
# MÉTRIQUES PROMETHEUS (Monitoring)
# ============================================================
try:
    from prometheus_client import Counter, Histogram, Gauge
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Fallback mock
    class MockMetric:
        def labels(self, *args, **kwargs): return self
        def inc(self): pass
        def observe(self, *args): pass
        def set(self, *args): pass
    Counter = Histogram = Gauge = lambda *args, **kwargs: MockMetric()

if PROMETHEUS_AVAILABLE:
    TASK_COUNTER = Counter(
        'aeropredict_tasks_total',
        'Total des tâches exécutées',
        ['status', 'engine_id']
    )
    TASK_DURATION = Histogram(
        'aeropredict_task_duration_seconds',
        'Durée des tâches',
        ['engine_id']
    )
    RUL_GAUGE = Gauge(
        'aeropredict_rul_current',
        'RUL actuel par moteur',
        ['engine_id']
    )
    ANOMALY_COUNTER = Counter(
        'aeropredict_anomalies_total',
        'Total des anomalies détectées',
        ['severity', 'engine_id']
    )
else:
    TASK_COUNTER = Counter()
    TASK_DURATION = Histogram()
    RUL_GAUGE = Gauge()
    ANOMALY_COUNTER = Counter()


# ============================================================
# FONCTIONS AUXILIAIRES
# ============================================================

def _make_json_serializable(obj):
    """
    Convertit récursivement les objets non-sérialisables en types JSON compatibles.
    """
    if isinstance(obj, dict):
        return {str(k): _make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_make_json_serializable(item) for item in obj]
    elif isinstance(obj, bool):
        return bool(obj)
    elif isinstance(obj, (int, float, str, type(None))):
        return obj
    elif hasattr(obj, '__dict__'):
        return _make_json_serializable(obj.__dict__)
    else:
        return str(obj)


def _validate_sensor_data(sensor_data: Dict[str, Any]) -> None:
    """Valide que toutes les données capteurs sont présentes."""
    required_sensors = [
        'Altitude', 'Mach', 'Regime',
        'Temp_Entree_LPC', 'Temp_Sortie_HPC', 'Temp_Sortie_LPT',
        'Pression_Sortie_HPC', 'Vitesse_Physique_Fan', 'Vitesse_Physique_Core',
        'Pression_Sortie_LPT', 'Vitesse_HPC_Sortie', 'Vitesse_LPC_Sortie',
        'Vitesse_Bypass', 'Pression_Bouchon', 'Vitesse_Rotation_HPC',
        'Rapport_Pression_HPC', 'Pression_Entree_Fan'
    ]
    missing = [s for s in required_sensors if s not in sensor_data]
    if missing:
        raise ValueError(f"Capteurs manquants: {missing}")


def _get_next_cycle(engine: Engine) -> int:
    """Calcule le prochain numéro de cycle."""
    last = PredictionHistory.objects.filter(engine=engine).order_by('-cycle').first()
    return (last.cycle + 1) if last else 1


def _get_recipients_for_engine(engine_id: str, critical_only: bool = True) -> list:
    """Récupère la liste des destinataires pour un moteur."""
    default_recipients = getattr(settings, 'ALERT_EMAIL_RECIPIENTS', ['claudeatsou8@gmail.com'])
    try:
        engine = Engine.objects.get(unit_id=engine_id)
        recipients = []
        if engine.technician_email:
            recipients.append(engine.technician_email)
        return recipients if recipients else default_recipients
    except Engine.DoesNotExist:
        return default_recipients


def _send_critical_alerts(engine_id: str, rul: float, diagnosis: Dict, anomalies: list) -> None:
    """Envoie les alertes critiques par email."""
    recipients = _get_recipients_for_engine(engine_id)
    subject = f"🚨 ALERTE CRITIQUE - Moteur {engine_id} - RUL: {rul:.1f} cycles"
    body = f"""
    ╔══════════════════════════════════════════════╗
    ║           ALERTE CRITIQUE MOTEUR              ║
    ╚══════════════════════════════════════════════╝
    
    Moteur      : {engine_id}
    RUL estimé  : {rul:.1f} cycles
    Statut      : 🔴 CRITICAL
    
    📊 DIAGNOSTIC
    ─────────────────────────────────────────────────
    Résumé      : {diagnosis.get('summary', 'N/A')}
    Risque      : {diagnosis.get('global_risk_score', 0)}%
    
    🔧 CAUSES PROBABLES
    ─────────────────────────────────────────────────
    {chr(10).join(f'    • {c}' for c in diagnosis.get('causes', []))}
    
    ✅ ACTIONS REQUISES (IMMÉDIATES)
    ─────────────────────────────────────────────────
    {chr(10).join(f'    • {a}' for a in diagnosis.get('actions', []))}
    
    ⚠️ ANOMALIES DÉTECTÉES
    ─────────────────────────────────────────────────
    {chr(10).join(f'    • {a["sensor_name"]}: Z={a["z_score"]:.2f}' for a in anomalies[:5])}
    
    ---
    AeroPredict SaaS - Système autonome de maintenance prédictive
    """
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
        logger.info(f"📧 Email critique envoyé pour {engine_id}")
    except Exception as e:
        logger.error(f"❌ Échec envoi email: {e}")


def _send_warning_alerts(engine_id: str, rul: float, diagnosis: Dict, anomalies: list) -> None:
    """Envoie les alertes de warning."""
    recipients = _get_recipients_for_engine(engine_id)
    subject = f"⚠️ ALERTE WARNING - Moteur {engine_id} - RUL: {rul:.1f} cycles"
    body = f"""
    ╔══════════════════════════════════════════════╗
    ║           ALERTE WARNING MOTEUR               ║
    ╚══════════════════════════════════════════════╝
    
    Moteur      : {engine_id}
    RUL estimé  : {rul:.1f} cycles
    Statut      : 🟠 WARNING
    
    📊 DIAGNOSTIC
    ─────────────────────────────────────────────────
    {diagnosis.get('summary', 'N/A')}
    
    🔧 ACTIONS RECOMMANDÉES
    ─────────────────────────────────────────────────
    {chr(10).join(f'    • {a}' for a in diagnosis.get('actions', []))}
    
    ---
    AeroPredict SaaS - Surveillance automatique
    """
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=True,
        )
        logger.info(f"📧 Email warning envoyé pour {engine_id}")
    except Exception as e:
        logger.warning(f"⚠️ Échec envoi email warning: {e}")


def _trigger_webhooks(engine_id: str, result: Dict[str, Any]) -> None:
    """Déclenche les webhooks configurés."""
    webhook_url = getattr(settings, 'AEROPREDICT_WEBHOOK_URL', None)
    if webhook_url:
        logger.debug(f"Webhook déclenché pour {engine_id}")


def _create_system_error_alert(engine_id: str, error_msg: str) -> None:
    """Crée une alerte système en cas d'échec définitif."""
    try:
        engine, _ = Engine.objects.get_or_create(unit_id=engine_id)
        MaintenanceAlert.objects.create(
            engine=engine,
            severity="SYSTEM_ERROR",
            diagnosis=f"L'analyse a échoué: {error_msg[:200]}",
            recommended_action="Vérifier les logs Celery",
            predicted_rul_at_alert=0.0
        )
        send_mail(
            f"❌ ERREUR SYSTÈME - {engine_id}",
            f"Échec analyse moteur {engine_id}.\n\nErreur: {error_msg}",
            settings.DEFAULT_FROM_EMAIL,
            [admin[1] for admin in settings.ADMINS],
            fail_silently=True,
        )
    except Exception as e:
        logger.critical(f"❌ Impossible de créer l'alerte système: {e}")


def notify_dashboard(engine_id: str, status: str, rul: float, anomalies_count: int, diagnosis: dict = None) -> bool:
    """
    Envoie une notification WebSocket au dashboard en temps réel.
    """
    try:
        channel_layer = get_channel_layer()
        
        if not channel_layer:
            logger.error("❌ Channel layer non disponible")
            return False
        
        payload = {
            "engine_id": engine_id,
            "status": status,
            "rul": round(rul, 2),
            "anomalies_count": anomalies_count,
            "timestamp_display": datetime.now().strftime("%H:%M:%S")
        }
        
        if diagnosis:
            payload["diagnosis"] = {
                "summary": diagnosis.get('summary', ''),
                "risk_level": diagnosis.get('risk_level', ''),
                "global_risk_score": diagnosis.get('global_risk_score', 0),
                "actions": diagnosis.get('actions', [])[:3],
                "causes": diagnosis.get('causes', [])[:3]
            }
        
        # Envoi au groupe FLEET (tous les moteurs)
        async_to_sync(channel_layer.group_send)(
            "fleet_alerts",
            {
                "type": "send_prediction_alert",
                "content": payload
            }
        )
        
        # Envoi au groupe ENGINE (moteur spécifique)
        async_to_sync(channel_layer.group_send)(
            f"engine_{engine_id}",
            {
                "type": "send_prediction_alert",
                "content": payload
            }
        )
        
        logger.info(f"📡 WebSocket push pour {engine_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ WebSocket push failed: {e}")
        return False


# ============================================================
# TÂCHE PRINCIPALE - DIAGNOSTIC
# ============================================================
@shared_task(
    bind=True,
    name='maintenance.tasks.process_engine_telemetry',
    max_retries=3,
    default_retry_delay=30,      # 🔥 30 secondes au lieu de 60
    soft_time_limit=45,           # 🔥 45 secondes max (corrigé)
    time_limit=60,                # 🔥 60 secondes max (corrigé)
    rate_limit='100/m',
    # queue='engine_analysis'     # 🔥 COMMENTÉ pour utiliser queue par défaut
)
def process_engine_telemetry(
    self,
    engine_id: str,
    sensor_data: Dict[str, Any],
    cycle: Optional[int] = None,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Analyse asynchrone d'un moteur avec monitoring complet.
    """
    start_time = time.time()
    task_id = self.request.id
    
    # 🔥 Mise à jour du statut pour le frontend (évite le timeout)
    self.update_state(
        state='PROGRESS',
        meta={
            'status': 'processing',
            'message': '🔍 Analyse des capteurs en cours...',
            'task_id': task_id
        }
    )
    
    logger.info(f"🚀 Tâche {task_id} démarrée pour moteur {engine_id}")

    try:
        # ----------------------------------------------------
        # ÉTAPE 1: VALIDATION
        # ----------------------------------------------------
        self.update_state(
            state='PROGRESS',
            meta={'status': 'validating', 'message': '📋 Validation des données...'}
        )
        _validate_sensor_data(sensor_data)

        # ----------------------------------------------------
        # ÉTAPE 2: INFÉRENCE IA
        # ----------------------------------------------------
        self.update_state(
            state='PROGRESS',
            meta={'status': 'processing', 'message': '🧠 Inférence IA en cours...'}
        )
        engine_ai = AIEngine()
        result = engine_ai.predict(engine_id, sensor_data)

        status = result.get('status', 'UNKNOWN')
        rul = result.get('ai_prediction', {}).get('predicted_rul', 0.0)
        health_score = result.get('ai_prediction', {}).get('health_score', 0.0)
        anomalies = result.get('raw_anomalies', [])
        diagnosis = result.get('diagnosis', {})

        # ----------------------------------------------------
        # ÉTAPE 3: SAUVEGARDE EN BASE
        # ----------------------------------------------------
        self.update_state(
            state='PROGRESS',
            meta={'status': 'saving', 'message': '💾 Sauvegarde des résultats...'}
        )
        
        with transaction.atomic():
            company = Company.objects.filter(name="AeroDefault").first()
            if not company:
                company = Company.objects.create(name="AeroDefault")

            engine, created = Engine.objects.get_or_create(
                unit_id=engine_id,
                defaults={
                    'status': status,
                    'last_check': timezone.now(),
                    'company': company,
                    'technician_email': 'claudeatsou8@gmail.com'
                }
            )

            if not created:
                engine.status = status
                engine.last_check = timezone.now()
                engine.save()

            clean_result = _make_json_serializable(result)

            prediction, created = PredictionHistory.objects.update_or_create(
                engine=engine,
                cycle=cycle or _get_next_cycle(engine),
                defaults={
                    'predicted_rul': rul,
                    'health_index': health_score,
                    'status': status,
                    'anomaly_count': len(anomalies),
                    'raw_result': clean_result,
                    'task_id': task_id,
                    'triggered_by_id': user_id
                }
            )

            alert_created = False
            if status in ["🔴 CRITICAL", "🟠 WARNING"]:
                MaintenanceAlert.objects.create(
                    engine=engine,
                    prediction=prediction,
                    triggered_at=timezone.now(),
                    predicted_rul_at_alert=rul,
                    severity=status.replace('🔴 ', '').replace('🟠 ', ''),
                    diagnosis=diagnosis.get('summary', ''),
                    recommended_action=', '.join(diagnosis.get('actions', [])[:3]),
                    cycle_at_alert=prediction.cycle,
                    anomaly_count=len(anomalies),
                    risk_score=diagnosis.get('global_risk_score', 0.0)
                )
                alert_created = True

        # ----------------------------------------------------
        # ÉTAPE 4: NOTIFICATION WEBSOCKET
        # ----------------------------------------------------
        notify_dashboard(engine_id, status, rul, len(anomalies), diagnosis)

        # ----------------------------------------------------
        # ÉTAPE 5: MÉTRIQUES PROMETHEUS
        # ----------------------------------------------------
        duration = time.time() - start_time

        if PROMETHEUS_AVAILABLE:
            TASK_COUNTER.labels(status=status, engine_id=engine_id).inc()
            TASK_DURATION.labels(engine_id=engine_id).observe(duration)
            RUL_GAUGE.labels(engine_id=engine_id).set(rul)
            for anomaly in anomalies:
                ANOMALY_COUNTER.labels(
                    severity=anomaly.get('severity', 'UNKNOWN'),
                    engine_id=engine_id
                ).inc()

        # ----------------------------------------------------
        # ÉTAPE 6: ALERTING EMAIL
        # ----------------------------------------------------
        if status == "🔴 CRITICAL":
            _send_critical_alerts(engine_id, rul, diagnosis, anomalies)
        elif status == "🟠 WARNING":
            _send_warning_alerts(engine_id, rul, diagnosis, anomalies)

        _trigger_webhooks(engine_id, result)

        logger.info(
            f"✅ Tâche {task_id} terminée | "
            f"Engine: {engine_id} | RUL: {rul} | Status: {status} | "
            f"Durée: {duration:.2f}s | Anomalies: {len(anomalies)}"
        )

        return {
            'task_id': task_id,
            'engine_id': engine_id,
            'prediction_id': prediction.id,
            'status': status,
            'rul': rul,
            'health_score': health_score,
            'anomalies_count': len(anomalies),
            'alert_created': alert_created,
            'duration': round(duration, 2),
            'timestamp': datetime.now().isoformat(),
            'diagnosis': diagnosis
        }

    except SoftTimeLimitExceeded:
        logger.error(f"⏰ Timeout pour tâche {task_id}")
        if PROMETHEUS_AVAILABLE:
            TASK_COUNTER.labels(status='timeout', engine_id=engine_id).inc()
        return {
            'task_id': task_id,
            'engine_id': engine_id,
            'status': 'TIMEOUT',
            'error': 'Le diagnostic a pris trop de temps'
        }

    except Exception as e:
        logger.error(f"❌ Échec tâche {task_id} pour {engine_id}: {str(e)}", exc_info=True)
        
        if PROMETHEUS_AVAILABLE:
            TASK_COUNTER.labels(status='error', engine_id=engine_id).inc()

        if self.request.retries < self.max_retries:
            retry_in = 30 * (2 ** self.request.retries)
            logger.info(f"🔄 Retry {self.request.retries + 1}/{self.max_retries} dans {retry_in}s")
            raise self.retry(exc=e, countdown=retry_in)

        _create_system_error_alert(engine_id, str(e))
        
        return {
            'task_id': task_id,
            'engine_id': engine_id,
            'status': 'ERROR',
            'error': str(e)
        }