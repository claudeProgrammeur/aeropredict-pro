# test_forecasting.py
"""
Script de test : Simulation de dégradation progressive
Pour voir comment le modèle prédit le RUL dans le futur
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aeronoth.settings')
django.setup()

from ai_engine.core.predictor import AIEngine
import matplotlib.pyplot as plt
import numpy as np

engine = AIEngine()
engine_id = "TEST_DEGRADATION_FUTURE"

# Réinitialiser le buffer
engine.reset_buffers(engine_id)

# Simuler 50 cycles de dégradation progressive
cycles = []
rul_values = []
statuses = []

print("🔮 SIMULATION DE DÉGRADATION SUR 50 CYCLES")
print("=" * 60)

for cycle in range(1, 51):
    # Dégradation progressive : Température monte, Pression descend
    degradation = cycle * 0.8  # Facteur de dégradation
    
    sensor_data = {
        "Altitude": 10000, "Mach": 0.6, "Regime": 100,
        "Temp_Entree_LPC": 518.67,
        "Temp_Sortie_HPC": 1589.0 + degradation * 0.5,   # 🔥 Monte
        "Temp_Sortie_LPT": 1406.0 + degradation * 0.3,    # 🔥 Monte
        "Pression_Sortie_HPC": 554.0 - degradation * 0.2, # 🔥 Descend
        "Vitesse_Physique_Fan": 2388.0,
        "Vitesse_Physique_Core": 9064.0 - degradation * 0.1,
        "Pression_Sortie_LPT": 47.0,
        "Vitesse_HPC_Sortie": 522.0,
        "Vitesse_LPC_Sortie": 2388.0,
        "Vitesse_Bypass": 8143.0 - degradation * 0.3,
        "Pression_Bouchon": 8.4,
        "Vitesse_Rotation_HPC": 392.0 + degradation * 0.2,
        "Rapport_Pression_HPC": 39.0 - degradation * 0.05,
        "Pression_Entree_Fan": 23.0,
    }
    
    result = engine.predict(engine_id, sensor_data)
    rul = result['ai_prediction']['predicted_rul']
    status = result['status']
    
    cycles.append(cycle)
    rul_values.append(rul)
    statuses.append(status)
    
    if cycle % 5 == 0:
        emoji = '🔴' if 'CRITICAL' in status else ('🟠' if 'WARNING' in status else '🟢')
        print(f"Cycle {cycle:2d}: RUL={rul:.1f} | {emoji} {status} | Anomalies={len(result['raw_anomalies'])}")

# Analyse finale
print("\n" + "=" * 60)
print("📊 ANALYSE FINALE")
print("=" * 60)

final_rul = rul_values[-1]
final_status = statuses[-1]

# Prédire quand la panne arrivera (RUL = 0)
if len(rul_values) >= 10:
    # Régression linéaire sur les 10 derniers points
    x = np.array(cycles[-10:])
    y = np.array(rul_values[-10:])
    slope, intercept = np.polyfit(x, y, 1)
    
    if slope < 0:
        cycle_panne = int(-intercept / slope)
        print(f"📉 Tendance : RUL diminue de {abs(slope):.1f} cycles par cycle")
        print(f"⏰ Panne estimée au cycle : {cycle_panne}")
        print(f"⏳ Temps restant : {cycle_panne - 50} cycles après la simulation")
    else:
        print(f"📈 Tendance : RUL stable ou en amélioration")
else:
    print("📊 Pas assez de données pour projeter la panne")

print(f"\nRUL final : {final_rul:.1f} cycles")
print(f"Statut final : {final_status}")

# Résumé décisionnel
if final_rul <= 30:
    print("\n🚨 DÉCISION : INTERVENTION IMMÉDIATE REQUISE")
    print("   La panne est imminente. Planifiez la maintenance maintenant.")
elif final_rul <= 60:
    print("\n⚠️ DÉCISION : SURVEILLANCE ACCRUE")
    print("   Des signes de dégradation sont présents. Préparez la maintenance.")
elif final_rul <= 90:
    print("\n📋 DÉCISION : ÉTAT STABLE")
    print("   Le moteur fonctionne normalement. Continuez la surveillance.")
else:
    print("\n✅ DÉCISION : MOTEUR SAIN")
    print("   Aucun signe de dégradation détecté.")

# Graphique
try:
    plt.figure(figsize=(12, 6))
    colors = ['#10b981' if not s or 'HEALTHY' in s else ('#fbbf24' if 'WARNING' in s else '#ef4444') for s in statuses]
    
    plt.plot(cycles, rul_values, 'b-', linewidth=2, label='RUL Prédit')
    plt.scatter(cycles, rul_values, c=colors, s=50, zorder=5)
    plt.axhline(y=30, color='#ef4444', linestyle='--', label='Seuil Critique (30)')
    plt.axhline(y=60, color='#fbbf24', linestyle='--', label='Seuil Warning (60)')
    plt.fill_between([0, 50], 0, 30, alpha=0.1, color='#ef4444')
    plt.fill_between([0, 50], 30, 60, alpha=0.05, color='#fbbf24')
    
    plt.xlabel('Cycles', fontsize=12)
    plt.ylabel('RUL (cycles restants)', fontsize=12)
    plt.title('🔮 Projection de Dégradation - Moteur Test', fontsize=14, fontweight='bold')
    plt.legend()
    plt.grid(True, alpha=0.2)
    plt.tight_layout()
    plt.savefig('forecast_result.png', dpi=150, bbox_inches='tight')
    print("\n💾 Graphique sauvegardé : forecast_result.png")
except Exception as e:
    print(f"\n⚠️ Graphique non disponible : {e}")

print("\n" + "=" * 60)
print("✅ TEST DE FORECASTING TERMINÉ")
print("=" * 60)