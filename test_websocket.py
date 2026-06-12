# test_websocket.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aeronoth.settings')
django.setup()

from maintenance.tasks.task import process_engine_telemetry

# Données simulant un moteur CRITIQUE
sensor_data = {
    "Altitude": 10000, "Mach": 0.6, "Regime": 100,
    "Temp_Entree_LPC": 518.67, "Temp_Sortie_HPC": 650.0,  # 🔥 Surchauffe
    "Temp_Sortie_LPT": 1589.0, "Pression_Sortie_HPC": 540.0,  # 🔥 Chute pression
    "Vitesse_Physique_Fan": 2388.0, "Vitesse_Physique_Core": 9046.0,
    "Pression_Sortie_LPT": 47.0, "Vitesse_HPC_Sortie": 521.0,
    "Vitesse_LPC_Sortie": 2388.0, "Vitesse_Bypass": 8138.0,
    "Pression_Bouchon": 8.4, "Vitesse_Rotation_HPC": 405.0,
    "Rapport_Pression_HPC": 39.0, "Pression_Entree_Fan": 23.0,
}

print("🚀 Envoi d'une alerte de test...")
task = process_engine_telemetry.delay("TEST_WEBSOCKET_001", sensor_data, cycle=1)
print(f"📋 Task ID: {task.id}")

# Attendre le résultat
result = task.get(timeout=30)
print(f"✅ Résultat: {result['status']} - RUL: {result['rul']}")
print("📡 Vérifiez votre dashboard : http://127.0.0.1:8000/maintenance/test-radar/")