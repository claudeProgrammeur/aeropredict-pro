
# ai_engine/model_loader.py
import torch
import torch.nn as nn
import os
from django.conf import settings

# --- ARCHITECTURE EXACTE DU NOTEBOOK ---
class LSTMWithAttention(nn.Module):
    def __init__(self, input_size=42, hidden_size=64, num_layers=2, output_size=1, dropout_prob=0.4):
        super(LSTMWithAttention, self).__init__()

        # 1. Le LSTM Bidirectionnel
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers,
                            batch_first=True,
                            bidirectional=True,
                            dropout=dropout_prob if num_layers > 1 else 0)

        # 2. Couche d'Attention (Calculée sur le double de hidden_size car bidirectionnel)
        self.attention = nn.Linear(hidden_size * 2, 1)

        # 3. Couches de sortie
        self.fc = nn.Sequential(
            nn.Linear(hidden_size * 2, 64),
            nn.ReLU(),
            nn.Dropout(dropout_prob),
            nn.Linear(64, output_size)
        )

    def forward(self, x):
        # x shape: [batch, seq_len, input_size]
        lstm_out, _ = self.lstm(x) 

        # Calcul des poids d'attention
        attn_scores = self.attention(lstm_out) 
        attn_weights = torch.softmax(attn_scores, dim=1)

        # Appliquer l'attention : Somme pondérée
        context = torch.sum(attn_weights * lstm_out, dim=1) 

        out = self.fc(context)
        return out

# --- FONCTION DE CHARGEMENT ---
def load_trained_model():
    # Paramètres identiques à ton initialisation Notebook
    input_size = 42   
    hidden_size = 64
    num_layers = 2
    
    model = LSTMWithAttention(input_size, hidden_size, num_layers)
    # model_path = os.path.join(settings.BASE_DIR, 'ai_engine/configs/models_files/best_model.pth')
   
    model_path = os.path.join(settings.BASE_DIR, 'ai_engine', 'configs', 'models_files', 'best_model.pth')
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    if os.path.exists(model_path):
        model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
        model.to(device)
        model.eval()
        return model, device
    else:
        raise FileNotFoundError(f"❌ Le fichier {model_path} est introuvable. Vérifie le dossier models_files.")