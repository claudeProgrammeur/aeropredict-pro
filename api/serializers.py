from rest_framework import serializers
from maintenance.models import SensorData, Engine

class SensorDataIngestSerializer(serializers.Serializer):
    """
    Sert à valider les données JSON envoyées par les clients (SaaS).
    C'est le filtre de sécurité avant l'enregistrement.
    """
    # --- IDENTITÉ ---
    engine_id = serializers.CharField(max_length=50) # On utilise engine_id pour le JSON
    cycle = serializers.IntegerField(min_value=1)

    # --- PARAMÈTRES DE VOL (K-Means) ---
    altitude = serializers.FloatField()
    mach = serializers.FloatField()
    regime = serializers.FloatField()

    # --- CAPTEURS (Les 14 features de ton Notebook) ---
    s2 = serializers.FloatField()
    s3 = serializers.FloatField()
    s4 = serializers.FloatField()
    s7 = serializers.FloatField()
    s8 = serializers.FloatField()
    s9 = serializers.FloatField()
    s11 = serializers.FloatField()
    s12 = serializers.FloatField()
    s13 = serializers.FloatField()
    s14 = serializers.FloatField()
    s15 = serializers.FloatField()
    s17 = serializers.FloatField()
    s20 = serializers.FloatField()
    s21 = serializers.FloatField()

    # --- LOGIQUE DE VALIDATION TECHNIQUE ---
    def validate_altitude(self, value):
        if value < 0:
            raise serializers.ValidationError("L'altitude ne peut pas être négative.")
        return value

    def validate_mach(self, value):
        if not (0 <= value <= 1.2): # Ajusté aux normes aéronautiques civiles
            raise serializers.ValidationError("Vitesse Mach incohérente pour ce type de moteur.")
        return value

# --- SÉRIALISEUR DE MODÈLE POUR LE DASHBOARD ---
class SensorDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = SensorData
        fields = '__all__'

# --- RÉPONSE FINALE DU SAAS ---
class PredictionResponseSerializer(serializers.Serializer):
    engine_id = serializers.CharField()
    cycle = serializers.IntegerField()
    predicted_rul = serializers.FloatField()
    status = serializers.CharField()
    diagnosis = serializers.CharField() # Ajouté pour le diagnostic NASA
    probability = serializers.FloatField(required=False)