# maintenance/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Route pour la vue globale (tous les moteurs)
    re_path(r'ws/alerts/fleet/$', consumers.FleetAlertConsumer.as_asgi()),
    
    # Route pour un moteur spécifique (ex: ws/alerts/engine/B737_001/)
    re_path(r'ws/alerts/engine/(?P<engine_id>\w+)/$', consumers.EngineConsumer.as_asgi()),
]