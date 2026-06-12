# aeronoth/celery.py

import os
from celery import Celery  # ✅ CORRECT

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aeronoth.settings')

app = Celery('aeronoth')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()