# maintenance/apps.py
from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'maintenance'
    
    def ready(self):
        # Importer les signaux pour les activer
         # Import des tâches pour que Celery les découvre
        import maintenance.tasks.task  # noqa
        import maintenance.signals  # noqa
