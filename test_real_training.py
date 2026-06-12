# train_full_nasa.py
import pandas as pd
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aeronoth.settings')
django.setup()

from maintenance.tasks.train import train_model_task

# Charger FD001 complet
columns = ['unit', 'cycle', 'setting1', 'setting2', 'setting3'] + [f's{i}' for i in range(1, 22)]
df = pd.read_csv('processed/train_FD001.txt', sep=r'\s+', header=None, names=columns)

# Préparer les données
all_data = []
for unit_id in df['unit'].unique():
    unit_df = df[df['unit'] == unit_id].copy()
    max_cycle = unit_df['cycle'].max()
    unit_df['rul'] = max_cycle - unit_df['cycle']
    unit_df['engine_id'] = f'FD001_UNIT_{unit_id}'
    all_data.append(unit_df)

final_df = pd.concat(all_data, ignore_index=True)

training_data = final_df[[
    'engine_id', 'cycle', 'setting1', 'setting2', 'setting3',
    's2', 's3', 's4', 's7', 's8', 's9', 's11', 's12', 's13', 
    's14', 's15', 's17', 's20', 's21', 'rul'
]].rename(columns={
    'setting1': 'altitude', 'setting2': 'mach', 'setting3': 'regime'
}).to_dict('records')

print(f"📊 {len(training_data)} échantillons, {final_df['unit'].nunique()} moteurs")

# Lancer l'entraînement
task = train_model_task.delay(training_data, epochs=20)
print(f"✅ Task ID: {task.id}")

# Suivre la progression
result = task.get(timeout=3600)
print(f"Score final: {result.get('global_score')}")