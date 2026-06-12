"""
Constantes pour le système de maintenance AeroPredict
"""

# Status des moteurs
ENGINE_STATUS_HEALTHY = 'HEALTHY'
ENGINE_STATUS_WARNING = 'WARNING'
ENGINE_STATUS_CRITICAL = 'CRITICAL'
ENGINE_STATUS_MAINTENANCE = 'MAINTENANCE'

ENGINE_STATUS_CHOICES = [
    (ENGINE_STATUS_HEALTHY, 'Sain'),
    (ENGINE_STATUS_WARNING, 'Attention'),
    (ENGINE_STATUS_CRITICAL, 'Critique'),
    (ENGINE_STATUS_MAINTENANCE, 'En Réparation'),
]

# Sévérité des alertes
ALERT_SEVERITY_LOW = 'LOW'
ALERT_SEVERITY_MEDIUM = 'MEDIUM'
ALERT_SEVERITY_HIGH = 'HIGH'
ALERT_SEVERITY_CRITICAL = 'CRITICAL'
ALERT_SEVERITY_WARNING = 'WARNING'

ALERT_SEVERITY_CHOICES = [
    (ALERT_SEVERITY_LOW, 'Faible'),
    (ALERT_SEVERITY_MEDIUM, 'Moyenne'),
    (ALERT_SEVERITY_HIGH, 'Haute'),
    (ALERT_SEVERITY_CRITICAL, 'Critique'),
    (ALERT_SEVERITY_WARNING, 'Attention'),
]

# Seuils de dégradation (pour trends)
TREND_RAPID_DEGRADATION = 'rapid_degradation'
TREND_DEGRADING = 'degrading'
TREND_STABLE = 'stable'
TREND_IMPROVING = 'improving'

TREND_SLOPE_CRITICAL = -2.0
TREND_SLOPE_WARNING = -0.5
TREND_SLOPE_IMPROVING = 0.5

# Alerting
ALERT_CACHE_TTL = 60  # secondes
ALERT_CYCLE_THRESHOLD = 10  # saut max autorisé entre cycles

# Logging & Messaging
MSG_ENGINE_CREATED = "Nouveau moteur enregistré: {}"
MSG_STATUS_CHANGED = "Changement de statut pour {}: {} → {}"
MSG_ALERT_TRIGGERED = "Alerte déclenchée pour: {}"
MSG_ALERT_RATE_LIMITED = "Alerte ignorée (rate limit): {}"
