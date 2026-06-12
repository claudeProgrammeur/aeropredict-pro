# maintenance/consumers.py

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class FleetAlertConsumer(AsyncWebsocketConsumer):
    """
    Consumer global - Toutes les alertes de la flotte.
    Utilisé pour le dashboard "Vue d'ensemble".
    """
    
    async def connect(self):
        self.group_name = "fleet_alerts"
        
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()
        logger.info(f"🔌 Fleet WebSocket connecté")
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        logger.info(f"🔌 Fleet WebSocket déconnecté")
    
    async def send_prediction_alert(self, event):
        """Appelé par Celery pour envoyer une alerte."""
        await self.send(text_data=json.dumps(event['content']))


class EngineConsumer(AsyncWebsocketConsumer):
    """
    Consumer spécifique - Un seul moteur.
    Utilisé pour le dashboard "Détail Moteur".
    """
    
    async def connect(self):
        self.engine_id = self.scope['url_route']['kwargs']['engine_id']
        self.group_name = f"engine_{self.engine_id}"
        
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()
        logger.info(f"🔌 Engine WebSocket connecté: {self.engine_id}")
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        logger.info(f"🔌 Engine WebSocket déconnecté: {self.engine_id}")
    
    async def send_prediction_alert(self, event):
        """Appelé par Celery pour envoyer une alerte."""
        await self.send(text_data=json.dumps(event['content']))