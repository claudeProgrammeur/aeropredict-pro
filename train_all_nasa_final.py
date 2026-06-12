# train_all_nasa_final.py
"""
Script COMPLET pour charger FD001, FD002, FD003, FD004
et lancer le fine-tuning du LSTM.
"""

# ============================================================
# 🔥 INITIALISATION DJANGO (OBLIGATOIRE)
# ============================================================
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aeronoth.settings')
django.setup()

# ============================================================
# IMPORTS
# ============================================================
import pandas as pd
import numpy as np
from maintenance.tasks.train import train_model_task

# ============================================================
# CONFIGURATION
# ============================================================
DATASETS = ['FD001', 'FD002', 'FD003', 'FD004']
DATA_DIR = 'processed'
EPOCHS = 50

COLUMNS = [
    'unit', 'cycle', 'setting1', 'setting2', 'setting3',
    's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9',
    's10', 's11', 's12', 's13', 's14', 's15', 's16', 's17',
    's18', 's19', 's20', 's21'
]

USEFUL_COLUMNS = [
    'engine_id', 'cycle', 'altitude', 'mach', 'regime',
    's2', 's3', 's4', 's7', 's8', 's9',
    's11', 's12', 's13', 's14', 's15',
    's17', 's20', 's21', 'rul'
]

# ============================================================
# FONCTION DE CHARGEMENT
# ============================================================
def load_nasa_dataset(dataset_name):
    file_path = os.path.join(DATA_DIR, f'train_{dataset_name}.txt')
    
    if not os.path.exists(file_path):
        print(f"❌ Fichier introuvable : {file_path}")
        return None
    
    print(f"📂 Chargement de {dataset_name}...")
    df = pd.read_csv(file_path, sep=r'\s+', header=None, names=COLUMNS)
    df = df.dropna(axis=1, how='all')
    
    df = df.rename(columns={'setting1': 'altitude', 'setting2': 'mach', 'setting3': 'regime'})
    
    all_engines = []
    for unit_id in df['unit'].unique():
        engine_df = df[df['unit'] == unit_id].copy()
        max_cycle = engine_df['cycle'].max()
        engine_df['rul'] = max_cycle - engine_df['cycle']
        engine_df['engine_id'] = f'NASA_{dataset_name}_UNIT_{int(unit_id)}'
        all_engines.append(engine_df)
    
    result = pd.concat(all_engines, ignore_index=True)
    result = result[USEFUL_COLUMNS]
    print(f"   ✅ {len(result)} cycles, {result['engine_id'].nunique()} moteurs")
    return result

# ============================================================
# CHARGEMENT PRINCIPAL
# ============================================================
print("=" * 60)
print("🚀 AEROPREDICT - FINE-TUNING NASA COMPLET")
print("=" * 60)

all_data = []
for dataset in DATASETS:
    df = load_nasa_dataset(dataset)
    if df is not None:
        all_data.append(df)

if not all_data:
    print("❌ Aucun dataset chargé !")
    exit(1)

final_df = pd.concat(all_data, ignore_index=True)
training_data = final_df.to_dict('records')

print("\n" + "=" * 60)
print("📊 STATISTIQUES FINALES")
print("=" * 60)
print(f"📁 Datasets chargés : {len(all_data)}/4")
print(f"🔢 Total cycles      : {len(training_data):,}")
print(f"🚁 Total moteurs     : {final_df['engine_id'].nunique()}")

print("\n" + "=" * 60)
print("🔥 LANCEMENT DU FINE-TUNING")
print("=" * 60)
print(f"⚙️  Époques : {EPOCHS}")
print(f"📊 Échantillons : {len(training_data):,}")

# Lancer la tâche Celery
task = train_model_task.delay(training_data, epochs=EPOCHS)

print(f"\n✅ Tâche envoyée !")
print(f"🆔 Task ID : {task.id}")
print("\n📡 Surveillez Celery : celery -A aeronoth worker -l info")
print("=" * 60)