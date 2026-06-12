
# maintenance/models.py
from django.db import models
from django.utils import timezone


class Company(models.Model):
    """Représente une compagnie aérienne cliente"""
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name


class Engine(models.Model):
    """Représente un moteur physique (Unité dans CMaps)"""
    STATUS_CHOICES = [
        ('HEALTHY', 'Sain'),
        ('WARNING', 'Attention'),
        ('CRITICAL', 'Critique'),
        ('MAINTENANCE', 'En Réparation'),
    ]
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='engines'
    )
    unit_id = models.CharField(max_length=50, unique=True, verbose_name="ID du Moteur")
    model_type = models.CharField(max_length=100, default="CFM56-7B")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='HEALTHY')
    last_check = models.DateTimeField(auto_now=True)
    last_alert_sent = models.DateTimeField(null=True, blank=True)
    technician_email = models.EmailField(help_text="Email pour les alertes automatiques")

    class Meta:
        verbose_name = "Moteur"
        verbose_name_plural = "Moteurs"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['company']),
        ]

    def __str__(self):
        return f"{self.unit_id} ({self.status})"


class SensorData(models.Model):
    """Données de capteurs pour un moteur à un cycle donné"""
    engine = models.ForeignKey(
        Engine,
        on_delete=models.CASCADE,
        related_name='telemetry'
    )
    cycle = models.PositiveIntegerField()
    timestamp = models.DateTimeField(default=timezone.now)

    # Paramètres de vol
    altitude = models.FloatField(verbose_name="Altitude (kft)", default=0.0)
    mach = models.FloatField(verbose_name="Nombre de Mach", default=0.0)
    regime = models.FloatField(verbose_name="Régime Moteur (TRA)", default=0.0)

    # Capteurs moteur (NASA CMaps nomenclature)
    s2 = models.FloatField(verbose_name="Temp Entrée LPC")
    s3 = models.FloatField(verbose_name="Temp Sortie HPC")
    s4 = models.FloatField(verbose_name="Temp Sortie LPT")
    s7 = models.FloatField(verbose_name="Pression Sortie HPC")
    s8 = models.FloatField(verbose_name="Vitesse Physique Fan")
    s9 = models.FloatField(verbose_name="Vitesse Physique Core")
    s11 = models.FloatField(verbose_name="Pression Sortie LPT")
    s12 = models.FloatField(verbose_name="Vitesse HPC Sortie")
    s13 = models.FloatField(verbose_name="Vitesse LPC Sortie")
    s14 = models.FloatField(verbose_name="Vitesse Bypass")
    s15 = models.FloatField(verbose_name="Pression Bouchon")
    s17 = models.FloatField(verbose_name="Vitesse Rotation HPC")
    s20 = models.FloatField(verbose_name="Rapport Pression HPC")
    s21 = models.FloatField(verbose_name="Pression Entree Fan")

    # Résultats d'inférence
    health_index = models.FloatField(null=True, blank=True, verbose_name="Indice de Santé")
    predicted_rul = models.FloatField(null=True, blank=True, verbose_name="RUL Prédite (cycles)")

    class Meta:
        ordering = ['cycle']
        unique_together = ('engine', 'cycle')
        indexes = [
            models.Index(fields=['engine', '-cycle']),
            models.Index(fields=['timestamp']),
        ]
        verbose_name = "Donnée Capteur"
        verbose_name_plural = "Données Capteurs"

    def __str__(self):
        return f"{self.engine.unit_id} - Cycle {self.cycle}"


class PredictionHistory(models.Model):
    """
    Historique complet des prédictions IA pour traçabilité et analyse.
    """
    engine = models.ForeignKey(
        Engine,
        on_delete=models.CASCADE,
        related_name='predictions'
    )
    cycle = models.PositiveIntegerField()
    timestamp = models.DateTimeField(default=timezone.now)

    # Résultats de l'IA
    predicted_rul = models.FloatField()
    health_index = models.FloatField()
    status = models.CharField(max_length=50)
    anomaly_count = models.IntegerField(default=0)

    # Résultat complet (JSON) pour analyse ultérieure
    raw_result = models.JSONField(default=dict, blank=True)

    # Métadonnées de la tâche
    task_id = models.CharField(max_length=100, blank=True, null=True)
    triggered_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['-cycle']
        unique_together = ('engine', 'cycle')
        indexes = [
            models.Index(fields=['engine', '-cycle']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['status']),
        ]
        verbose_name = "Historique de Prédiction"
        verbose_name_plural = "Historiques de Prédictions"

    def __str__(self):
        return f"{self.engine.unit_id} - Cycle {self.cycle} - RUL: {self.predicted_rul:.1f}"


class MaintenanceAlert(models.Model):
    """Historique des alertes déclenchées par l'IA"""
    SEVERITY_CHOICES = [
        ('LOW', 'Faible'),
        ('MEDIUM', 'Moyenne'),
        ('HIGH', 'Haute'),
        ('CRITICAL', 'Critique'),
        ('WARNING', 'Attention'),
    ]

    engine = models.ForeignKey(
        Engine,
        on_delete=models.CASCADE,
        related_name='alerts'
    )
    prediction = models.ForeignKey(
        PredictionHistory,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alerts'
    )

    is_read = models.BooleanField(default=False, help_text="Si le technicien a vu l'alerte")
    acknowledged_at = models.DateTimeField(null=True, blank=True, help_text="Date de la prise en compte")

    triggered_at = models.DateTimeField(auto_now_add=True)
    predicted_rul_at_alert = models.FloatField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='MEDIUM')
    diagnosis = models.TextField(verbose_name="Diagnostic NASA", blank=True)
    recommended_action = models.TextField(verbose_name="Action Corrective", blank=True)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)

    # Champs supplémentaires
    cycle_at_alert = models.IntegerField(null=True, blank=True)
    anomaly_count = models.IntegerField(default=0)
    risk_score = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['-triggered_at']
        indexes = [
            models.Index(fields=['engine', '-triggered_at']),
            models.Index(fields=['severity']),
            models.Index(fields=['is_resolved']),
        ]
        verbose_name = "Alerte de Maintenance"
        verbose_name_plural = "Alertes de Maintenance"

    def __str__(self):
        return f"Alerte {self.engine.unit_id} - {self.severity} - {self.triggered_at.strftime('%Y-%m-%d %H:%M')}"


# À ajouter dans maintenance/models.py (après Engine ou avant SensorData)

class EngineTimeSeries(models.Model):
    """
    Série temporelle agrégée pour un moteur.
    Permet de suivre l'évolution des indicateurs clés dans le temps.
    Utile pour les graphiques de tendance et l'analyse historique.
    """
    engine = models.ForeignKey(
        Engine,
        on_delete=models.CASCADE,
        related_name='time_series'
    )
    
    # Indicateurs temporels
    cycle = models.PositiveIntegerField(help_text="Cycle de vie du moteur")
    timestamp = models.DateTimeField(default=timezone.now)
    
    # Indicateurs de santé
    rul_remaining = models.FloatField(
        null=True, 
        blank=True, 
        verbose_name="RUL restante (cycles)",
        help_text="Remaining Useful Life prédite"
    )
    health_score = models.FloatField(
        null=True, 
        blank=True, 
        verbose_name="Score de santé (0-100)",
        help_text="0 = critique, 100 = parfait"
    )
    
    # Dégradations par composant
    fan_degradation = models.FloatField(
        default=0.0, 
        verbose_name="Dégradation Fan (%)"
    )
    lpc_degradation = models.FloatField(
        default=0.0, 
        verbose_name="Dégradation LPC (%)"
    )
    hpc_degradation = models.FloatField(
        default=0.0, 
        verbose_name="Dégradation HPC (%)"
    )
    lpt_degradation = models.FloatField(
        default=0.0, 
        verbose_name="Dégradation LPT (%)"
    )
    hpt_degradation = models.FloatField(
        default=0.0, 
        verbose_name="Dégradation HPT (%)"
    )
    
    # Indicateurs de tendance
    rul_trend = models.FloatField(
        null=True, 
        blank=True,
        verbose_name="Tendance RUL (pente)",
        help_text="Pente de dégradation sur les derniers cycles"
    )
    anomaly_score = models.FloatField(
        default=0.0,
        verbose_name="Score d'anomalie",
        help_text="0-1 : probabilité d'anomalie"
    )
    
    # Métadonnées
    is_anomaly = models.BooleanField(default=False)
    confidence = models.FloatField(
        default=1.0,
        verbose_name="Confiance de la prédiction (0-1)"
    )
    
    class Meta:
        ordering = ['engine', 'cycle']
        unique_together = ('engine', 'cycle')
        indexes = [
            models.Index(fields=['engine', '-cycle']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['health_score']),
            models.Index(fields=['is_anomaly']),
        ]
        verbose_name = "Série Temporelle Moteur"
        verbose_name_plural = "Séries Temporelles Moteurs"
    
    def __str__(self):
        return f"{self.engine.unit_id} - Cycle {self.cycle} - Santé: {self.health_score:.1f}%"
    
    @property
    def health_status(self):
        """Retourne le statut basé sur le health_score"""
        if self.health_score is None:
            return "UNKNOWN"
        if self.health_score >= 80:
            return "HEALTHY"
        elif self.health_score >= 50:
            return "WARNING"
        else:
            return "CRITICAL"


# ============================================================
# 🔥 NOUVEAU MODÈLE : HISTORIQUE DES ENTRAÎNEMENTS
# ============================================================

class TrainingHistory(models.Model):
    """
    Historique des entraînements du modèle LSTM.
    Permet de suivre les performances et de générer des rapports post-entraînement.
    """
    
    STATUS_CHOICES = [
        ('PENDING', 'En attente'),
        ('RUNNING', 'En cours'),
        ('SUCCESS', 'Réussi'),
        ('FAILED', 'Échoué'),
    ]
    
    HEALTH_STATUS_CHOICES = [
        ('HEALTHY', '🟢 Sain - Aucune action requise'),
        ('WARNING', '🟡 Attention - Surveillance recommandée'),
        ('CRITICAL', '🔴 Critique - Intervention requise'),
    ]
    
    # Identifiants
    task_id = models.CharField(max_length=100, unique=True, db_index=True)
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trainings'
    )
    
    # Métadonnées
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(default=0.0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Paramètres d'entraînement
    epochs = models.IntegerField(default=10)
    samples_count = models.IntegerField(default=0)
    batch_size = models.IntegerField(default=16)
    learning_rate = models.FloatField(default=0.0005)
    
    # Métriques de performance
    rmse_before = models.FloatField(null=True, blank=True)
    rmse_after = models.FloatField(null=True, blank=True)
    r2_before = models.FloatField(null=True, blank=True)
    r2_after = models.FloatField(null=True, blank=True)
    safety_score_before = models.FloatField(null=True, blank=True)
    safety_score_after = models.FloatField(null=True, blank=True)
    
    # Résultats
    performance_level = models.CharField(max_length=50, blank=True, default='')
    global_score = models.FloatField(default=0.0)
    
    # 🔥 PRÉDICTION POST-ENTRAÎNEMENT
    predicted_rul = models.FloatField(
        null=True, 
        blank=True,
        help_text="RUL prédite sur les données fournies (cycles)"
    )

    health_status = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,  # 🔥 AJOUTER null=True
        default='',
        help_text="HEALTHY / WARNING / CRITICAL"
    )
    
    # 🔥 CAUSES ET ACTIONS (NOUVEAU)
    detected_anomalies = models.JSONField(
        default=list, 
        blank=True,
        help_text="Liste des capteurs en anomalie avec leurs scores"
    )
    causes = models.JSONField(
        default=list, 
        blank=True,
        help_text="Liste des causes probables de la panne"
    )
    actions = models.JSONField(
        default=list, 
        blank=True,
        help_text="Liste des actions recommandées"
    )
    urgency_level = models.CharField(
        max_length=50, 
        blank=True, 
        default='',
        help_text="Niveau d'urgence : IMMÉDIATE / URGENTE / PLANIFIÉE / PRÉVENTIVE"
    )
    
    # 🔥 MESSAGES POUR L'UTILISATEUR
    short_message = models.CharField(
        max_length=255, 
        blank=True, 
        default='',
        help_text="Message court pour notification"
    )
    long_message = models.TextField(
        blank=True, 
        default='',
        help_text="Message détaillé pour l'utilisateur"
    )
    
    # 🔥 SI L'UTILISATEUR A VU LE RÉSULTAT
    is_viewed = models.BooleanField(default=False, help_text="L'utilisateur a-t-il vu le résultat ?")
    viewed_at = models.DateTimeField(null=True, blank=True)
    
    # Résultat complet (JSON)
    full_result = models.JSONField(default=dict, blank=True)
    
    # Erreur si échec
    error_message = models.TextField(blank=True, default='')
    
    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['user', '-started_at']),
            models.Index(fields=['is_viewed']),
        ]
        verbose_name = "Historique d'entraînement"
        verbose_name_plural = "Historiques d'entraînements"
    
    def __str__(self):
        return f"Training {self.task_id[:8]} - {self.status} - {self.started_at.strftime('%Y-%m-%d %H:%M')}"
    
    def _cycles_to_human_readable(self, cycles: int) -> str:
        """Convertit les cycles en texte lisible (jours/mois)"""
        if cycles <= 0:
            return "aujourd'hui"
        elif cycles == 1:
            return "1 cycle (1 jour)"
        elif cycles <= 7:
            return f"{cycles} cycles ({cycles} jours)"
        elif cycles <= 30:
            return f"{cycles} cycles (environ {cycles} jours)"
        elif cycles <= 60:
            mois = cycles / 30
            return f"{cycles} cycles (environ {mois:.0f} mois)"
        elif cycles <= 365:
            mois = cycles / 30
            return f"{cycles} cycles (environ {mois:.0f} mois)"
        else:
            annees = cycles / 365
            return f"{cycles} cycles (environ {annees:.1f} ans)"
    
    def generate_message(self):
        """
        Génère les messages automatiquement basés sur la prédiction et les anomalies
        """
        if self.predicted_rul is None:
            self.short_message = "❌ Aucune prédiction disponible"
            self.long_message = "L'entraînement n'a pas pu générer de prédiction. Vérifiez vos données."
            return
        
        cycles = int(self.predicted_rul)
        time_text = self._cycles_to_human_readable(cycles)
        
        # Récupérer les anomalies et causes depuis full_result
        diagnosis = self.full_result.get('diagnosis', {})
        anomalies = self.full_result.get('raw_anomalies', [])
        
        # Stocker les anomalies détectées
        self.detected_anomalies = [
            {
                'sensor': a.get('sensor_name', a.get('sensor_id', 'Inconnu')),
                'z_score': a.get('z_score', 0),
                'severity': a.get('severity', 'LOW')
            }
            for a in anomalies[:5]  # Limiter à 5 anomalies
        ]
        
        # Récupérer les causes et actions du diagnostic
        self.causes = diagnosis.get('causes', [])
        self.actions = diagnosis.get('actions', [])
        
        # Déterminer le statut de santé
        if cycles <= 15 or (self.causes and len(self.causes) >= 2):
            self.health_status = 'CRITICAL'
            self.urgency_level = 'IMMÉDIATE'
            emoji = "🔴"
            status_text = "CRITIQUE - Intervention immédiate requise"
            action_text = "Consultez immédiatement le Live Radar pour identifier la panne."
        elif cycles <= 45 or self.causes:
            self.health_status = 'WARNING'
            self.urgency_level = 'URGENTE'
            emoji = "🟠"
            status_text = "ATTENTION - Surveillance recommandée"
            action_text = "Planifiez une inspection sous 15 jours."
        else:
            self.health_status = 'HEALTHY'
            self.urgency_level = 'PRÉVENTIVE'
            emoji = "🟢"
            status_text = "SAIN - Aucune action immédiate"
            action_text = "Aucune panne imminente détectée. Surveillance normale."
        
        # Construction du message
        causes_text = ""
        if self.causes:
            causes_text = "\n🔍 CAUSES PROBABLES :\n" + "\n".join(f"   • {c}" for c in self.causes[:3])
        
        actions_text = ""
        if self.actions:
            actions_text = "\n✅ ACTIONS RECOMMANDÉES :\n" + "\n".join(f"   • {a}" for a in self.actions[:3])
        
        anomalies_text = ""
        if self.detected_anomalies and self.health_status != 'HEALTHY':
            anomalies_text = "\n⚠️ CAPTEURS EN ANOMALIE :\n" + "\n".join(
                f"   • {a['sensor']} : Z-score = {a['z_score']:.2f}" for a in self.detected_anomalies[:3]
            )
        
        # Message court
        self.short_message = f"{emoji} RUL estimée à {cycles} cycles ({time_text}) - {status_text}"
        
        # Message long
        self.long_message = f"""
╔══════════════════════════════════════════════════════════════╗
║                    📊 RAPPORT D'ENTRAÎNEMENT                  ║
╚══════════════════════════════════════════════════════════════╝
🔧 MOTEUR ANALYSÉ : {self.full_result.get('engine_id', 'Non spécifié')}

📈 RÉSULTAT DE LA PRÉDICTION :
   • Vie utile restante (RUL) : {cycles} cycles
   • Estimation temporelle : {time_text}
   • Statut : {emoji} {status_text}
   • Niveau d'urgence : {self.urgency_level}

📊 PERFORMANCES DU MODÈLE :
   • RMSE : {self.rmse_after:.2f} cycles
   • Score global : {self.global_score:.1f}/100
   • Niveau : {self.performance_level}
{causes_text}{anomalies_text}{actions_text}
💡 Pour plus de détails, consultez la page Live Radar :
   👉 /maintenance/test-radar/

---
AeroPredict Pro - Maintenance prédictive par IA
"""
    
    def mark_as_viewed(self):
        """Marque le résultat comme vu par l'utilisateur"""
        if not self.is_viewed:
            self.is_viewed = True
            self.viewed_at = timezone.now()
            self.save(update_fields=['is_viewed', 'viewed_at'])