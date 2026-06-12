# train_all_nasa_final.py
import pandas as pd
from maintenance.tasks.train import train_model_task

all_data = []
for dataset in ['FD001', 'FD002', 'FD003', 'FD004']:
    df = pd.read_csv(f'processed/train_{dataset}.txt', sep=r'\s+', header=None)
    # ... traitement ...
    all_data.append(df)

final_data = pd.concat(all_data)
training_data = final_data.to_dict('records')

print(f"🚀 Lancement entraînement sur {len(training_data)} cycles...")
task = train_model_task.delay(training_data, epochs=50)
print(f"Task ID: {task.id}")