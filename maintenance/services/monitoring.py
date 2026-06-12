# maintenance/services/monitoring.py
from ai_engine.diagnostics.anomaly import detect_anomalies_from_z_scores
from ai_engine.diagnostics.knowledge import get_nasa_solution
from ai_engine.core.predictor import AIEngine
from maintenance.models import Engine, SensorData, MaintenanceAlert
import json

class MonitoringService:
    def __init__(self):
        self.ai = AIEngine() # Utilise notre Singleton optimisé

    def process_engine_update(self, engine_id):
        """
        Cette fonction fait tout : 
        1. Récupère les données 
        2. Prédit 
        3. Alerte si besoin
        """
        engine = Engine.objects.get(unit_id=engine_id)
        
        # 1. On récupère les 30 derniers cycles (SEQ_LENGTH = 30 dans ton notebook)
        history = SensorData.objects.filter(engine=engine).order_by('cycle')[:30]
        
        if len(history) < 30:
            return "Besoin de plus de données pour la séquence (min 30)"

        # 2. Prédiction RUL
        # On passe la liste des objets SensorData à l'IA
        rul_pred = self.ai.predict(history)
        
        # 3. Sauvegarde du RUL sur le dernier cycle
        latest_cycle = history.last()
        latest_cycle.predicted_rul = rul_pred
        latest_cycle.save()

        # 4. Analyse des anomalies (Diagnostic NASA)
        # On convertit le dernier cycle en dict pour l'analyseur
        current_sensors = {
            's2': latest_cycle.s2, 's3': latest_cycle.s3, 's4': latest_cycle.s4,
            's7': latest_cycle.s7, 's11': latest_cycle.s11, 's12': latest_cycle.s12
            # ... ajoute les autres selon tes stats
        }
        
        anomalies = detect_anomalies_from_z_scores(current_sensors, self.ai.stats)
        
        # 5. Gestion de l'état et des alertes
        if rul_pred <= 60:
            severity = 'HIGH' if rul_pred <= 30 else 'MEDIUM'
            engine.status = 'CRITICAL' if rul_pred <= 30 else 'WARNING'
            engine.save()

            # Création de l'alerte pour le Dashboard
            MaintenanceAlert.objects.create(
                engine=engine,
                predicted_rul_at_alert=rul_pred,
                severity=severity,
                diagnosis=f"Anomalies détectées sur : {', '.join(anomalies)}",
                recommended_action=get_nasa_solution(anomalies)
            )
            
            return f"Alerte déclenchée : RUL={rul_pred}"
            
        return f"Moteur stable : RUL={rul_pred}"