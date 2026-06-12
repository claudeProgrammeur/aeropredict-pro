# maintenance/signals.py
"""
Signaux Django pour automatiser les notifications.
C'est le "réflexe" du système : dès qu'une alerte est créée,
elle est automatiquement poussée vers le WebSocket.
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from ai_engine.core.predictor import AIEngine
from .models import MaintenanceAlert, PredictionHistory, SensorData, EngineTimeSeries

logger = logging.getLogger(__name__)


# ============================================================
# SIGNAL 1 : ANALYSE IA AUTOMATIQUE SUR NOUVELLE DONNÉE
# ============================================================

@receiver(post_save, sender=SensorData)
def trigger_ai_analysis(sender, instance, created, **kwargs):
    """
    Lance automatiquement l'IA quand de nouvelles données capteurs arrivent.
    """
    if not created:
        return
    
    try:
        engine = instance.engine
        
        # 🔥 CORRECTION : Construire le dictionnaire au format attendu par AIEngine
        sensor_data = {
            "Altitude": instance.altitude,
            "Mach": instance.mach,
            "Regime": instance.regime,
            "Temp_Entree_LPC": instance.s2,
            "Temp_Sortie_HPC": instance.s3,
            "Temp_Sortie_LPT": instance.s4,
            "Pression_Sortie_HPC": instance.s7,
            "Vitesse_Physique_Fan": instance.s8,
            "Vitesse_Physique_Core": instance.s9,
            "Pression_Sortie_LPT": instance.s11,
            "Vitesse_HPC_Sortie": instance.s12,
            "Vitesse_LPC_Sortie": instance.s13,
            "Vitesse_Bypass": instance.s14,
            "Pression_Bouchon": instance.s15,
            "Vitesse_Rotation_HPC": instance.s17,
            "Rapport_Pression_HPC": instance.s20,
            "Pression_Entree_Fan": instance.s21,
        }
        
        # Appeler l'IA
        predictor = AIEngine()
        result = predictor.predict(engine.unit_id, sensor_data)
        
        # Mettre à jour l'instance avec les résultats
        instance.predicted_rul = result['ai_prediction']['predicted_rul']
        instance.health_index = result['ai_prediction']['health_score'] * 100
        instance.save()
        
        logger.info(f"🤖 IA déclenchée pour {engine.unit_id} | RUL: {instance.predicted_rul}")
        
        # 🔥 NOTE : La création d'alerte est gérée par process_engine_telemetry
        # Pas besoin de la dupliquer ici
        
    except Exception as e:
        logger.error(f"❌ Échec analyse IA automatique pour {instance.engine.unit_id}: {e}")


# ============================================================
# SIGNAL 2 : ROUTAGE INTELLIGENT DES ALERTES
# ============================================================

@receiver(post_save, sender=MaintenanceAlert)
def smart_alert_router(sender, instance, created, **kwargs):
    """
    Dès qu'une MaintenanceAlert est créée :
    1. Push WebSocket vers le Live Radar
    2. Si CRITICAL, envoie un email
    3. Log l'événement
    """
    if not created:
        return
    
    try:
        engine_id = instance.engine.unit_id
        prediction = instance.prediction
        
        # 🔥 CORRECTION : Gérer le cas où prediction est None
        status = prediction.status if prediction else instance.severity
        
        # Données à envoyer
        alert_data = {
            'id': instance.id,
            'engine_id': engine_id,
            'status': status,
            'rul': instance.predicted_rul_at_alert,
            'anomalies_count': instance.anomaly_count,
            'timestamp_display': instance.triggered_at.strftime('%H:%M:%S'),
            'is_read': instance.is_read,
            'diagnosis': {
                'summary': instance.diagnosis,
                'global_risk_score': instance.risk_score or 0,
                'actions': instance.recommended_action.split(', ') if instance.recommended_action else [],
                'causes': []
            }
        }
        
        # 1. PUSH WEBSOCKET (Live Radar)
        try:
            channel_layer = get_channel_layer()
            
            # Groupe Fleet (tous les moteurs)
            async_to_sync(channel_layer.group_send)(
                "fleet_alerts",
                {
                    "type": "send_prediction_alert",
                    "content": alert_data
                }
            )
            
            # Groupe spécifique au moteur
            async_to_sync(channel_layer.group_send)(
                f"engine_{engine_id}",
                {
                    "type": "send_prediction_alert",
                    "content": alert_data
                }
            )
            
            logger.info(f"📡 WebSocket push pour alerte {instance.id} - {engine_id}")
            
        except Exception as e:
            logger.error(f"❌ WebSocket push failed: {e}")
        
        # 2. EMAIL SI CRITIQUE
        if instance.severity in ['CRITICAL', '🔴 CRITICAL', 'HIGH']:
            try:
                subject = f"🚨 ALERTE CRITIQUE - Moteur {engine_id}"
                body = f"""
╔══════════════════════════════════════════════╗
║           ALERTE CRITIQUE MOTEUR              ║
╚══════════════════════════════════════════════╝

Moteur      : {engine_id}
RUL estimé  : {instance.predicted_rul_at_alert:.1f} cycles
Risque      : {instance.risk_score or 0:.1f}%

Diagnostic  : {instance.diagnosis}

Actions     : {instance.recommended_action}

---
AeroPredict SaaS - Alerte automatique
"""
                
                # Récupérer le destinataire
                if instance.engine.technician_email:
                    recipient = instance.engine.technician_email
                else:
                    # Gérer le cas où ALERT_EMAIL_RECIPIENTS est une liste ou une string
                    alert_recipients = settings.ALERT_EMAIL_RECIPIENTS
                    if isinstance(alert_recipients, list):
                        recipient = alert_recipients[0] if alert_recipients else 'claudeatsou8@gmail.com'
                    else:
                        recipient = alert_recipients.split(',')[0].strip() if alert_recipients else 'claudeatsou8@gmail.com'

                send_mail(
                    subject=subject,
                    message=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient],
                    fail_silently=False,
                )
                logger.info(f"📧 Email envoyé pour {engine_id} à {recipient}")
                
            except Exception as e:
                logger.error(f"❌ Email failed: {e}")
                
    except Exception as e:
        logger.error(f"❌ Signal error: {e}")


# ============================================================
# SIGNAL 3 : MISE À JOUR STATUT MOTEUR
# ============================================================

@receiver(post_save, sender=PredictionHistory)
def update_engine_status_on_prediction(sender, instance, created, **kwargs):
    """
    Met à jour automatiquement le statut du moteur
    quand une nouvelle prédiction est enregistrée.
    """
    if created:
        engine = instance.engine
        engine.status = instance.status
        engine.last_check = instance.timestamp
        engine.save()
        logger.info(f"🔄 Moteur {engine.unit_id} mis à jour: {instance.status}")


# ============================================================
# 🔥 SIGNAL 4 : SAUVEGARDE DANS ENGINE TIME SERIES (NOUVEAU)
# ============================================================

@receiver(post_save, sender=PredictionHistory)
def save_to_time_series(sender, instance, created, **kwargs):
    """
    Sauvegarde automatiquement dans EngineTimeSeries
    pour les graphiques de dégradation.
    """
    if created:
        try:
            # Récupérer les données capteurs brutes si disponibles
            sensor_data = {}
            last_sensor = SensorData.objects.filter(
                engine=instance.engine, 
                cycle=instance.cycle
            ).first()
            
            if last_sensor:
                sensor_data = {
                    'altitude': last_sensor.altitude,
                    'mach': last_sensor.mach,
                    'regime': last_sensor.regime,
                    's2': last_sensor.s2, 's3': last_sensor.s3, 's4': last_sensor.s4,
                    's7': last_sensor.s7, 's8': last_sensor.s8, 's9': last_sensor.s9,
                    's11': last_sensor.s11, 's12': last_sensor.s12, 's13': last_sensor.s13,
                    's14': last_sensor.s14, 's15': last_sensor.s15, 's17': last_sensor.s17,
                    's20': last_sensor.s20, 's21': last_sensor.s21,
                }
            
            EngineTimeSeries.objects.update_or_create(
                engine=instance.engine,
                cycle=instance.cycle,
                defaults={
                    'predicted_rul': instance.predicted_rul,
                    'health_index': instance.health_index,
                    'status': instance.status,
                    'anomaly_count': instance.anomaly_count,
                    'sensor_data': sensor_data
                }
            )
            logger.info(f"📊 TimeSeries mis à jour pour {instance.engine.unit_id} cycle {instance.cycle}")
            
        except Exception as e:
            logger.error(f"❌ Échec sauvegarde TimeSeries: {e}")


# ============================================================
# 🔥 SIGNAL 5 : NOTIFICATION ENTRAÎNEMENT TERMINÉ (NOUVEAU)
# ============================================================

# Ce signal sera utilisé quand vous créerez un modèle TrainingHistory
# Pour l'instant, il est commenté mais prêt à l'emploi

"""
@receiver(post_save, sender=TrainingHistory)
def notify_training_complete(sender, instance, created, **kwargs):
    '''
    Notifie le frontend quand l'entraînement est terminé.
    '''
    if created and instance.status == 'success':
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "fleet_alerts",
                {
                    "type": "send_training_complete",
                    "content": {
                        "type": "training_complete",
                        "score": instance.global_score,
                        "performance_level": instance.performance_level,
                        "message": f"✅ Entraînement terminé - Score: {instance.global_score}/100"
                    }
                }
            )
            logger.info(f"📡 Notification entraînement envoyée")
        except Exception as e:
            logger.error(f"❌ Échec notification entraînement: {e}")
"""