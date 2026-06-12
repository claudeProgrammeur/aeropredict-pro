# test_celery_simple.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aeronoth.settings')
django.setup()

from celery import current_app

# Test 1: Vérifier que la tâche est enregistrée
from maintenance.tasks.train import train_model_task
print(f"✅ Tâche enregistrée: {train_model_task.name}")

# Test 2: Lancer une tâche simple
task = train_model_task.delay([], epochs=1)
print(f"✅ Task ID: {task.id}")
print(f"État: {task.state}")

# Test 3: Attendre le résultat avec timeout
try:
    result = task.get(timeout=10)
    print(f"Résultat: {result}")
except Exception as e:
    print(f"Erreur: {e}")