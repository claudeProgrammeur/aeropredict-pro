# train_all_nasa.py
import pandas as pd
import redis
import time

# Vérifier Redis
try:
    r = redis.Redis(host='localhost', port=6379)
    r.ping()
    print("✅ Redis connecté")
except:
    print("❌ Lancez Redis : redis-server")
    exit(1)

# Attendre que Celery soit prêt
time.sleep(2)

from maintenance.tasks.train import train_model_task

# Charger TOUS les moteurs FD001
columns = ['unit', 'cycle', 'setting1', 'setting2', 'setting3'] + [f's{i}' for i in range(1, 22)]
df = pd.read_csv('processed/train_FD001.txt', sep=r'\s+', header=None, names=columns)
df = df.dropna(axis=1)

df = df.rename(columns={'setting1': 'altitude', 'setting2': 'mach', 'setting3': 'regime'})

rul_list = []
for unit_id in df['unit'].unique():
    unit_df = df[df['unit'] == unit_id].copy()
    max_cycle = unit_df['cycle'].max()
    unit_df['rul'] = max_cycle - unit_df['cycle']
    unit_df['engine_id'] = f'NASA_FD001_UNIT_{unit_id}'
    rul_list.append(unit_df)

all_data = pd.concat(rul_list, ignore_index=True)

useful = ['engine_id', 'cycle', 'altitude', 'mach', 'regime', 
          's2', 's3', 's4', 's7', 's8', 's9', 
          's11', 's12', 's13', 's14', 's15', 
          's17', 's20', 's21', 'rul']
training_data = all_data[useful].to_dict('records')

print(f"📊 {len(training_data)} cycles chargés ({len(all_data['unit'].unique())} moteurs)")

# 🔥 CORRECTION : Utiliser apply_async avec timeout
try:
    task = train_model_task.apply_async(args=[training_data], kwargs={'epochs': 50}, timeout=10)
    print(f"🚀 Task ID: {task.id}")
    print("⏳ Entraînement lancé sur 20 631 cycles, 50 époques...")
    print("📡 Surveillez avec : celery -A aeronoth flower")
except Exception as e:
    print(f"❌ Erreur: {e}")
    print("Vérifiez que Celery worker tourne dans un autre terminal")