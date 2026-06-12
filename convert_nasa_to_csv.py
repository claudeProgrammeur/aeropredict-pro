# convert_nasa_to_csv.py
import pandas as pd
import os

# Chercher le fichier
possible_paths = [
    'train_FD001.txt',
    'data/train_FD001.txt',
    'CMAPSSData/train_FD001.txt',
    'datasets/train_FD001.txt',
    'processed/train_FD001.txt',
]

file_path = None
for path in possible_paths:
    if os.path.exists(path):
        file_path = path
        print(f"✅ Fichier trouvé : {path}")
        break

if file_path is None:
    print("❌ Fichier train_FD001.txt introuvable !")
    exit(1)

# Colonnes NASA (26 colonnes)
columns = [
    'unit', 'cycle', 'setting1', 'setting2', 'setting3',
    's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9',
    's10', 's11', 's12', 's13', 's14', 's15', 's16', 's17',
    's18', 's19', 's20', 's21'
]

# Lire avec gestion des espaces multiples
df = pd.read_csv(file_path, sep=r'\s+', header=None, names=columns)
df = df.dropna(axis=1, how='all')

print(f"📊 Fichier chargé : {len(df)} lignes")

# Renommer settings
df = df.rename(columns={
    'setting1': 'altitude',
    'setting2': 'mach',
    'setting3': 'regime'
})

# 🔥 CORRECTION : Calculer RUL SANS perdre 'unit'
rul_list = []
for unit_id in df['unit'].unique():
    unit_df = df[df['unit'] == unit_id].copy()
    max_cycle = unit_df['cycle'].max()
    unit_df['rul'] = max_cycle - unit_df['cycle']
    rul_list.append(unit_df)

df = pd.concat(rul_list, ignore_index=True)

# Sélectionner les colonnes utiles
useful_columns = ['cycle', 'altitude', 'mach', 'regime', 
                  's2', 's3', 's4', 's7', 's8', 's9', 
                  's11', 's12', 's13', 's14', 's15', 
                  's17', 's20', 's21', 'rul']

# Prendre le moteur 1
engine_unit = 1
engine_data = df[df['unit'] == engine_unit][useful_columns].copy()
engine_data['engine_id'] = f'NASA_FD001_ENGINE_{engine_unit}'

# Réorganiser
cols = ['engine_id'] + useful_columns
engine_data = engine_data[cols]

# Sauvegarder
output_file = f'nasa_training_engine{engine_unit}_{len(engine_data)}cycles.csv'
engine_data.to_csv(output_file, index=False)

print(f"✅ {len(engine_data)} cycles exportés vers {output_file}")
print(f"📁 Fichier : {os.path.join(os.getcwd(), output_file)}")