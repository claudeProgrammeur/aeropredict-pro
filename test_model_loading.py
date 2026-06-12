# test_model_loading.py
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aeronoth.settings')
django.setup()

from ai_engine.core.model_loader import load_trained_model
import torch

model, device = load_trained_model()

# Vérifier l'état du modèle
print(f"Device: {device}")

# Tester avec une entrée aléatoire
import numpy as np
test_input = torch.randn(1, 30, 42).to(device)
with torch.no_grad():
    output = model(test_input)
    print(f"Output pour entrée aléatoire: {output.item()}")

print(f"Chemin du modèle: {model.__class__.__name__}")