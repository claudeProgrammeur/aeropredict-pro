# maintenance/services/alerting.py
import json
import os
import logging
from django.conf import settings
from django.core.mail import send_mail
from maintenance.models import MaintenanceAlert

logger = logging.getLogger(__name__)

def trigger_smart_alert(engine, predicted_rul, anomalies, current_context):
    """
    🚀 Smart Alert Engine - Génère une alerte de maintenance intelligente
    """
    try:
        # =========================================================
        # 1. DÉTERMINATION DE LA SÉVÉRITÉ
        # =========================================================
        severity_score = 0
        for a in anomalies:
            z_score = abs(a.get('z_score', 0))
            if z_score > 7.0:
                severity_score += 5
            elif z_score > 5.0:
                severity_score += 3
            elif z_score > 3.5:
                severity_score += 1
        
        # Décision finale
        if predicted_rul <= 25 or severity_score >= 8:
            final_severity = "CRITICAL"
        elif predicted_rul <= 60 or severity_score >= 4:
            final_severity = "WARNING"
        else:
            final_severity = "INFO"
        
        # =========================================================
        # 2. CONSTRUCTION DU DIAGNOSTIC
        # =========================================================
        diagnosis_lines = []
        for a in anomalies:
            s_name = a.get('sensor_name', a.get('sensor_id', 'Inconnu'))
            z_score = a.get('z_score', 0)
            diagnosis_lines.append(f"• {s_name}: Z-score = {z_score:.2f}")
        
        diagnosis_text = "\n".join(diagnosis_lines) if diagnosis_lines else "Aucune anomalie détectée"
        
        # =========================================================
        # 3. CRÉATION DE L'ALERTE EN BASE
        # =========================================================
        alert = MaintenanceAlert.objects.create(
            engine=engine,
            predicted_rul_at_alert=predicted_rul,
            severity=final_severity,
            diagnosis=diagnosis_text,
            recommended_action=_get_recommended_action(final_severity, predicted_rul),
            cycle_at_alert=current_context.get('cycle', 0),
            anomaly_count=len(anomalies),
            risk_score=min(100, int((1 - predicted_rul/125) * 100) + severity_score)
        )
        
        # =========================================================
        # 4. ENVOI D'EMAIL SI CRITIQUE
        # =========================================================
        if final_severity == "CRITICAL":
            _send_alert_email(engine, predicted_rul, diagnosis_text, final_severity)
        
        logger.info(f"✅ Alerte créée pour {engine.unit_id} - Sévérité: {final_severity}")
        return alert
        
    except Exception as e:
        logger.error(f"❌ Échec Smart Alert: {e}")
        return None


def _get_recommended_action(severity, rul):
    """Retourne l'action recommandée selon la sévérité"""
    if severity == "CRITICAL":
        return f"🔴 INTERVENTION IMMÉDIATE - RUL = {rul} cycles. Arrêter le moteur et inspecter."
    elif severity == "WARNING":
        return f"🟠 PLANIFIER MAINTENANCE - RUL = {rul} cycles. Inspection sous 50 cycles."
    else:
        return f"🟢 SURVEILLANCE NORMALE - RUL = {rul} cycles. Aucune action immédiate."


def _send_alert_email(engine, rul, diagnosis, severity):
    """Envoie l'email d'alerte"""
    try:
        recipient = engine.technician_email or getattr(settings, 'ALERT_EMAIL_RECIPIENTS', ['admin@aeropredict.com'])[0]
        
        subject = f"🚨 ALERTE {severity} - Moteur {engine.unit_id} - RUL {rul} cycles"
        body = f"""
╔══════════════════════════════════════════════╗
║           ALERTE CRITIQUE MOTEUR              ║
╚══════════════════════════════════════════════╝

Moteur      : {engine.unit_id}
RUL estimé  : {rul} cycles
Sévérité    : {severity}

📊 DIAGNOSTIC :
{diagnosis}

✅ ACTION REQUISE :
Intervention immédiate requise. Consultez le Live Radar.

---
AeroPredict Pro - Alerte automatique
"""
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=True,
        )
        logger.info(f"📧 Email d'alerte envoyé pour {engine.unit_id}")
    except Exception as e:
        logger.warning(f"⚠️ Échec envoi email: {e}")
        