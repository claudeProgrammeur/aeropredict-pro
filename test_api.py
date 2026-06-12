"""
Test complet du pipeline IA AeroPredict
"""
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aeronoth.settings')
django.setup()

from ai_engine.core.predictor import AIEngine

# Données de test - représentatives d'un moteur sain et dégradé
HEALTHY_ENGINE_DATA = {
    "Altitude": 0.0004, "Mach": 0.0001, "Regime": 100,
    "Temp_Entree_LPC": 642.56,
    "Temp_Sortie_HPC": 1589.25,
    "Temp_Sortie_LPT": 1406.62,
    "Pression_Sortie_HPC": 554.32,
    "Vitesse_Physique_Fan": 2388.08,
    "Vitesse_Physique_Core": 9064.22,
    "Pression_Sortie_LPT": 47.47,
    "Vitesse_HPC_Sortie": 522.29,
    "Vitesse_LPC_Sortie": 2388.08,
    "Vitesse_Bypass": 8143.61,
    "Pression_Bouchon": 8.41,
    "Vitesse_Rotation_HPC": 392.87,
    "Rapport_Pression_HPC": 38.90,
    "Pression_Entree_Fan": 23.34,
}

DEGRADED_ENGINE_DATA = {
    **HEALTHY_ENGINE_DATA,
    "Temp_Sortie_HPC": 1615.0,  # +25 points (surchauffe)
    "Temp_Sortie_LPT": 1440.0,  # +34 points
    "Pression_Sortie_HPC": 540.0,  # baisse significative
}

TEST_SCENARIOS = [
    ("HEALTHY", HEALTHY_ENGINE_DATA),
    ("DEGRADED", DEGRADED_ENGINE_DATA),
]


def run_diagnostics():
    """Lance le diagnostic sur les scénarios de test."""
    print("=" * 60)
    print("AeroPredict - Full Diagnostic Test")
    print("=" * 60)

    try:
        engine = AIEngine()
    except Exception as e:
        print(f"Erreur lors de l'initialisation: {e}")
        return

    for scenario_name, data in TEST_SCENARIOS:
        print(f"\nTest Scénario: {scenario_name}")
        print("-" * 60)

        try:
            engine_id = f"TEST_{scenario_name}"
            result = engine.predict(engine_id, data)

            pred = result.get('ai_prediction', {})
            diag = result.get('diagnosis', {})

            print(f"RUL Prédite: {pred.get('predicted_rul', 'N/A')}")
            print(f"Statut: {result.get('status', 'N/A')}")

            print(f"\nAnalyse Technique:")
            print(f"  - Causes: {diag.get('causes', 'Aucune')}")
            print(f"  - Actions: {diag.get('actions', 'Aucune')}")

            if diag.get('systems_impacted'):
                print(f"  - Systèmes affectés:")
                for sys, info in diag['systems_impacted'].items():
                    max_z = round(info['max_z'], 2)
                    print(f"    * {sys}: {info['count']} anomalies | Max Z: {max_z}")

        except Exception as e:
            print(f"Erreur durant l'analyse: {str(e)}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("Test terminé")
    print("=" * 60)


if __name__ == "__main__":
    run_diagnostics()
