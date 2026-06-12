# api/views.py
"""
AeroPredict SaaS - API Endpoints
Version: 10.0.0
"""

import traceback
import logging
from typing import Dict, Any, Optional

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import UserRateThrottle
from django.db import transaction
from django.core.cache import cache

from maintenance.models import Company, Engine, SensorData
from maintenance.constants import (
    ENGINE_STATUS_CRITICAL, ENGINE_STATUS_WARNING,
    ALERT_CACHE_TTL, ALERT_CYCLE_THRESHOLD,
    MSG_ENGINE_CREATED, MSG_STATUS_CHANGED, MSG_ALERT_TRIGGERED, MSG_ALERT_RATE_LIMITED
)
from ai_engine.core.predictor import AIEngine
from ai_engine.diagnostics.anomaly import SENSOR_MAPPING
from .serializers import SensorDataIngestSerializer
from maintenance.services.alerting import trigger_smart_alert
from rest_framework.permissions import AllowAny

logger = logging.getLogger(__name__)


class AeroRateThrottle(UserRateThrottle):
    """Rate limiting personnalisé pour AeroPredict"""
    rate = '60/minute'  # 1 requête par seconde en moyenne


class PredictRULView(APIView):
    """
    AeroPredict SaaS - Endpoint de Prédiction RUL
    
    Pipeline complet:
        1. Validation des données
        2. Sauvegarde en base
        3. Inférence IA
        4. Diagnostic NASA
        5. Alerting intelligent
        6. Réponse structurée
    
    Rate limit: 60 requêtes/minute
    """

    permission_classes = [AllowAny]
    throttle_classes = [AeroRateThrottle]

    # ============================================================
    # MÉTHODES PRIVÉES
    # ============================================================

    def _map_sensor_data(self, data: Dict[str, Any]) -> Dict[str, float]:
        """
        Mappe les données du sérialiseur vers le format attendu par AIEngine.
        
        Args:
            data: Données validées du sérialiseur
            
        Returns:
            Dictionnaire formaté pour AIEngine
        """
        ai_input = {
            "Altitude": data["altitude"],
            "Mach": data["mach"],
            "Regime": data["regime"]
        }

        # Ajouter tous les capteurs dynamiquement
        for sensor_id, sensor_name in SENSOR_MAPPING.items():
            if sensor_id in data:
                ai_input[sensor_name] = data[sensor_id]
            else:
                logger.warning(f"Capteur {sensor_id} manquant dans les données")

        return ai_input

    def _get_or_create_company(self) -> Company:
        """
        Récupère ou crée la company par défaut.
        À remplacer par la logique multi-tenant réelle.
        """
        company, created = Company.objects.get_or_create(
            name="AeroDefault",
            defaults={"subscription_plan": "enterprise"}
        )
        if created:
            logger.info(f"Nouvelle company créée: {company.name}")
        return company

    def _get_or_create_engine(self, unit_id: str, company: Company) -> Engine:
        """
        Récupère ou crée un moteur.
        """
        engine, created = Engine.objects.get_or_create(
            unit_id=unit_id,
            defaults={
                "status": "HEALTHY",
                "company": company,
                "technician_email": "claudeatsou8@gmail.com"
            }
        )

        if created:
            logger.info(MSG_ENGINE_CREATED.format(unit_id))

        return engine

    def _validate_cycle_sequence(self, engine: Engine, cycle: int) -> None:
        """
        Vérifie que le cycle est cohérent avec l'historique.
        
        Args:
            engine: Instance du moteur
            cycle: Numéro de cycle à valider
            
        Raises:
            ValueError: Si le cycle est incohérent
        """
        last_sensor = SensorData.objects.filter(engine=engine).order_by('-cycle').first()

        if last_sensor:
            if cycle <= last_sensor.cycle:
                raise ValueError(
                    f"Cycle {cycle} doit être > au dernier cycle {last_sensor.cycle}"
                )
            if cycle > last_sensor.cycle + ALERT_CYCLE_THRESHOLD:
                logger.warning(
                    f"Saut de cycle important: {last_sensor.cycle} → {cycle} "
                    f"pour moteur {engine.unit_id}"
                )

    def _update_engine_status(self, engine: Engine, result: Dict[str, Any]) -> None:
        """
        Met à jour le statut du moteur et gère les transitions.
        """
        old_status = engine.status
        new_status = result["status"]

        if old_status != new_status:
            engine.status = new_status
            logger.warning(MSG_STATUS_CHANGED.format(engine.unit_id, old_status, new_status))

            # Incrémenter compteur d'alertes si dégradation
            if new_status in [ENGINE_STATUS_WARNING, ENGINE_STATUS_CRITICAL]:
                engine.alert_count = getattr(engine, 'alert_count', 0) + 1

            engine.save()

    def _create_sensor_record(
        self,
        engine: Engine,
        data: Dict[str, Any],
        result: Dict[str, Any]
    ) -> SensorData:
        """
        Crée ou met à jour l'enregistrement des données capteurs avec les résultats IA.
        """
        sensor_defaults = {
            k: v for k, v in data.items()
            if k not in ["engine_id", "timestamp"]
        }

        sensor_defaults.update({
            "predicted_rul": result.get("ai_prediction", {}).get("predicted_rul"),
            "health_index": result.get("ai_prediction", {}).get("health_score"),
        })

        sensor_instance, created = SensorData.objects.update_or_create(
            engine=engine,
            cycle=data["cycle"],
            defaults=sensor_defaults
        )

        if created:
            logger.debug(f"Nouveau cycle {data['cycle']} pour {engine.unit_id}")

        return sensor_instance

    def _should_trigger_alert(self, result: Dict[str, Any]) -> bool:
        """
        Détermine si une alerte doit être déclenchée.
        Évite les alertes en rafale avec un cache.
        """
        status_triggers = [ENGINE_STATUS_WARNING, ENGINE_STATUS_CRITICAL]

        if result["status"] not in status_triggers:
            return False

        engine_id = result["engine_id"]
        cache_key = f"last_alert_{engine_id}"

        # Éviter les alertes trop fréquentes
        if cache.get(cache_key):
            logger.info(MSG_ALERT_RATE_LIMITED.format(engine_id))
            return False

        cache.set(cache_key, True, ALERT_CACHE_TTL)
        return True

    def _build_response(
        self,
        data: Dict[str, Any],
        result: Dict[str, Any],
        alert_sent: bool
    ) -> Dict[str, Any]:
        """
        Construit la réponse finale structurée.
        """
        return {
            "engine_id": data["engine_id"],
            "cycle": data["cycle"],
            "timestamp": data.get("timestamp"),

            # Statut et prédiction
            "status": result["status"],
            "ai_prediction": result["ai_prediction"],

            # Diagnostic
            "risk_analysis": {
                "level": result["diagnosis"]["risk_level"],
                "score": result["diagnosis"]["global_risk_score"],
                "impact": result["diagnosis"]["systems_impacted"]
            },

            # Maintenance
            "maintenance_advice": {
                "summary": result["diagnosis"]["summary"],
                "top_faults": result["diagnosis"]["critical_faults"],
                "actions": result["diagnosis"]["actions"],
                "causes": result["diagnosis"]["causes"]
            },

            # Métadonnées
            "alert_sent": alert_sent,
            "anomaly_count": len(result.get("raw_anomalies", [])),
            "api_version": "10.0.0"
        }

    # ============================================================
    # ENDPOINT PRINCIPAL
    # ============================================================

    def post(self, request):
        """
        POST /api/predict/
        
        Body:
        {
            "engine_id": "FD001_42",
            "cycle": 128,
            "altitude": 1000,
            "mach": 0.7,
            "regime": 100,
            "s2": 518.67, "s3": 643.12, ...
        }
        
        Returns:
            201 Created avec diagnostic complet
        """
        # --------------------------------------------------------
        # 1. VALIDATION DES DONNÉES
        # --------------------------------------------------------
        serializer = SensorDataIngestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Validation échouée: {serializer.errors}")
            return Response(
                {"error": "VALIDATION_FAILED", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data
        engine_id = data["engine_id"]

        logger.info(f"Requête prédiction: {engine_id} cycle {data['cycle']}")

        try:
            # ────────────────────────────────────────────────────
            # 2. TRANSACTION ATOMIQUE
            # ────────────────────────────────────────────────────
            with transaction.atomic():
                # Gestion tenant
                company = self._get_or_create_company()
                engine = self._get_or_create_engine(engine_id, company)

                # Validation cycle
                self._validate_cycle_sequence(engine, data["cycle"])

                # ────────────────────────────────────────────────────
                # 3. INFÉRENCE IA
                # ────────────────────────────────────────────────────
                ai_input = self._map_sensor_data(data)
                result = AIEngine().predict(engine_id, ai_input)

                # ────────────────────────────────────────────────────
                # 4. SAUVEGARDE ET MISE À JOUR
                # ────────────────────────────────────────────────────
                sensor_instance = self._create_sensor_record(engine, data, result)
                self._update_engine_status(engine, result)

                # ────────────────────────────────────────────────────
                # 5. ALERTING INTELLIGENT
                # ────────────────────────────────────────────────────
                alert_sent = False
                if self._should_trigger_alert(result):
                    try:
                        alert_sent = trigger_smart_alert(
                            engine=engine,
                            predicted_rul=result["ai_prediction"]["predicted_rul"],
                            anomalies=result["raw_anomalies"],
                            current_context={
                                "altitude": data["altitude"],
                                "mach": data["mach"],
                                "cycle": data["cycle"]
                            }
                        )
                        if alert_sent:
                            logger.warning(MSG_ALERT_TRIGGERED.format(engine_id))
                    except Exception as e:
                        logger.error(f"Échec alerting: {e}", exc_info=True)

                # ────────────────────────────────────────────────────
                # 6. RÉPONSE
                # ────────────────────────────────────────────────────
                response_data = self._build_response(data, result, alert_sent)

                logger.info(
                    f"Prédiction réussie: {engine_id} cycle {data['cycle']} | "
                    f"RUL: {result['ai_prediction']['predicted_rul']} | "
                    f"Status: {result['status']}"
                )

                return Response(response_data, status=status.HTTP_201_CREATED)

        except ValueError as e:
            # Erreur de validation métier
            logger.warning(f"Erreur validation pour {engine_id}: {e}")
            return Response(
                {"error": "VALIDATION_ERROR", "details": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            # Erreur inattendue
            logger.error(
                f"Crash pipeline pour {engine_id} cycle {data.get('cycle')}: {e}",
                exc_info=True
            )
            traceback.print_exc()

            return Response(
                {
                    "error": "PIPELINE_CRASH",
                    "details": str(e),
                    "engine_id": engine_id,
                    "cycle": data.get("cycle")
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================
# ENDPOINTS COMPLÉMENTAIRES
# ============================================================

class EngineHealthView(APIView):
    """
    GET /api/engine/{engine_id}/health/
    Récupère l'état de santé actuel d'un moteur
    """

    def get(self, request, engine_id):
        try:
            engine = Engine.objects.get(unit_id=engine_id)
            last_sensor = SensorData.objects.filter(engine=engine).order_by('-cycle').first()

            if not last_sensor:
                return Response(
                    {"error": "Aucune donnée pour ce moteur"},
                    status=status.HTTP_404_NOT_FOUND
                )

            return Response({
                "engine_id": engine_id,
                "status": engine.status,
                "last_cycle": last_sensor.cycle,
                "current_rul": last_sensor.predicted_rul,
                "health_index": last_sensor.health_index,
                "last_update": last_sensor.timestamp
            })

        except Engine.DoesNotExist:
            return Response(
                {"error": f"Moteur {engine_id} non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )


class FleetOverviewView(APIView):
    """
    GET /api/fleet/overview/
    Vue d'ensemble de toute la flotte
    """

    def get(self, request):
        engines = Engine.objects.all()

        fleet_status = {
            "total": engines.count(),
            "critical": engines.filter(status=ENGINE_STATUS_CRITICAL).count(),
            "warning": engines.filter(status=ENGINE_STATUS_WARNING).count(),
            "healthy": engines.filter(status="HEALTHY").count(),
            "engines": []
        }

        for engine in engines:
            last_sensor = SensorData.objects.filter(engine=engine).order_by('-cycle').first()
            fleet_status["engines"].append({
                "engine_id": engine.unit_id,
                "status": engine.status,
                "current_rul": last_sensor.predicted_rul if last_sensor else None,
                "last_cycle": last_sensor.cycle if last_sensor else None
            })

        return Response(fleet_status)