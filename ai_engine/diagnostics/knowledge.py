# ai_engine/diagnostics/knowledge.py
"""
Moteur de diagnostic NASA - Version Française CORRIGÉE
"""

import json
import os
import logging
from django.conf import settings
from numpy.ma import anomalies

logger = logging.getLogger(__name__)


class NASAKnowledgeEngine:
    """
    Moteur de diagnostic basé sur la base de connaissance NASA (FR)
    """
    
    _translations = None
    
    @classmethod
    def _load_translations(cls):
        """Charge les traductions françaises"""
        if cls._translations is None:
            trans_path = os.path.join(
                settings.BASE_DIR, 
                'ai_engine', 'knowledge_base', 'french_translations.json'
            )
            try:
                with open(trans_path, 'r', encoding='utf-8') as f:
                    cls._translations = json.load(f)
                logger.info("✅ Traductions françaises chargées")
            except FileNotFoundError:
                logger.warning(f"⚠️ Fichier de traduction introuvable: {trans_path}")
                cls._translations = {}
            except Exception as e:
                logger.error(f"❌ Erreur chargement traductions: {e}")
                cls._translations = {}
        return cls._translations
    
    def __init__(self):
        self.kb_path = os.path.join(
            settings.BASE_DIR, 
            'ai_engine', 'knowledge_base', 'nasa_knowledge.json'
        )
        self.translations = self._load_translations()
        
        self.SYSTEM_MAPPING = {
            "THERMAL": ["s2", "s3", "s4", "s15"],
            "PRESSURE": ["s7", "s11", "s20", "s21"],
            "MECHANICAL/SPEED": ["s8", "s9", "s12", "s13", "s17"],
            "BYPASS/FLOW": ["s14"]
        }
        
        self.SYSTEM_NAMES_FR = {
            "THERMAL": "Thermique",
            "PRESSURE": "Pression",
            "MECHANICAL/SPEED": "Mécanique/Vitesse",
            "BYPASS/FLOW": "Bypass/Débit",
            "OTHER": "Autre"
        }
        
        # 🔥 Dictionnaire des causes et actions par capteur (fallback)
        self.SENSOR_DIAGNOSTICS = {
            "s2": {
                "causes": ["Problème de débit d'air", "Fuite au niveau de l'entrée LPC"],
                "actions": ["Vérifier le circuit d'admission", "Inspecter les aubes LPC"],
                "component": "LPC"
            },
            "s3": {
                "causes": ["Érosion des aubes HPC", "Fuite de refroidissement", "Usure du compresseur HP"],
                "actions": ["Endoscopie du compresseur HP", "Nettoyage du moteur", "Vérifier le système de refroidissement"],
                "component": "HPC"
            },
            "s4": {
                "causes": ["Surcharge thermique", "Problème de turbine BP", "Fluage de turbine"],
                "actions": ["Réduire la puissance immédiatement", "Inspecter les aubes LPT", "Vérifier les températures"],
                "component": "LPT"
            },
            "s7": {
                "causes": ["Fuite de pression", "Joint défectueux", "Problème de compresseur"],
                "actions": ["Vérifier l'étanchéité du circuit", "Inspecter les joints", "Contrôle pression"],
                "component": "HPC"
            },
            "s8": {
                "causes": ["Déséquilibre du fan", "Dégât corps étranger (FOD)", "Usure des aubes fan"],
                "actions": ["Inspection visuelle du fan", "Équilibrage statique", "Remplacement si nécessaire"],
                "component": "FAN"
            },
            "s9": {
                "causes": ["Usure du noyau moteur", "Problème de lubrification", "Vibrations anormales"],
                "actions": ["Analyse des vibrations", "Vérifier le circuit d'huile", "Surveillance rapprochée"],
                "component": "CORE"
            },
            "s11": {
                "causes": ["Contre-pression turbine", "Problème de sortie LPT", "Efficacité turbine réduite"],
                "actions": ["Inspecter la turbine LPT", "Vérifier le rapport pression", "Contrôle EGT"],
                "component": "LPT"
            },
            "s12": {
                "causes": ["Problème de vitesse HPC", "Régulation défaillante", "Capteur de vitesse"],
                "actions": ["Vérifier le régulateur", "Contrôle de la vitesse", "Calibration capteur"],
                "component": "HPC"
            },
            "s13": {
                "causes": ["Problème de vitesse LPC", "Désynchronisation", "Capteur défectueux"],
                "actions": ["Vérifier la synchronisation", "Contrôle du capteur de vitesse", "Maintenance LPC"],
                "component": "LPC"
            },
            "s14": {
                "causes": ["Débit bypass anormal", "Clapet anti-retour", "Problème de flux secondaire"],
                "actions": ["Inspecter le circuit bypass", "Vérifier les clapets", "Contrôle débit"],
                "component": "BYPASS"
            },
            "s15": {
                "causes": ["Pression bouchon anormale", "Problème de ligne d'échappement", "Capteur pression"],
                "actions": ["Vérifier la ligne d'échappement", "Contrôle capteur pression", "Inspection"],
                "component": "EXHAUST"
            },
            "s17": {
                "causes": ["Vitesse rotation HPC anormale", "Problème palier", "Roulement usé"],
                "actions": ["Analyse vibratoire", "Contrôle roulements", "Surveillance température"],
                "component": "HPC"
            },
            "s20": {
                "causes": ["Pompage compresseur", "Perte de marge au décrochage", "Instabilité aérodynamique"],
                "actions": ["RÉDUCTION IMMÉDIATE DE PUISSANCE", "Vérification complète de sécurité", "Inspection HPC urgente"],
                "component": "HPC",
                "critical": True
            },
            "s21": {
                "causes": ["Pression entrée fan anormale", "Obstruction admission", "Problème débit"],
                "actions": ["Vérifier admission", "Inspecter le fan", "Contrôle pression"],
                "component": "FAN"
            }
        }
    
    def _translate(self, text: str, category: str = 'actions') -> str:
        """Traduit un texte anglais en français"""
        trans_dict = self.translations.get(category, {})
        
        if text in trans_dict:
            return trans_dict[text]
        
        if text in self.translations.get('statuses', {}):
            return self.translations['statuses'][text]
        
        if text in self.translations.get('components', {}):
            return self.translations['components'][text]
        
        if text in self.translations.get('risk_levels', {}):
            return self.translations['risk_levels'][text]
        
        return text
    
    def _translate_sensor_name(self, sensor_id: str) -> str:
        """Traduit le nom du capteur"""
        trans = self.translations.get('sensor_names', {})
        
        if sensor_id in trans:
            return trans[sensor_id]
        
        sensor_names = {
            "s2": "Température Entrée LPC",
            "s3": "Température Sortie HPC",
            "s4": "Température Sortie LPT",
            "s7": "Pression Sortie HPC",
            "s8": "Vitesse Fan",
            "s9": "Vitesse Core",
            "s11": "Pression Sortie LPT",
            "s12": "Vitesse HPC",
            "s13": "Vitesse LPC",
            "s14": "Vitesse Bypass",
            "s15": "Pression Bouchon",
            "s17": "Vitesse Rotation HPC",
            "s20": "Rapport Pression HPC",
            "s21": "Pression Entrée Fan"
        }
        return sensor_names.get(sensor_id, sensor_id)
    

    def _get_causes_and_actions(self, sensor_id: str, z_score: float) -> tuple:
        """Retourne les causes et actions spécifiques à un capteur"""
        #  CRITIQUE : Si Z-score < 2.5, ce n'est pas une vraie anomalie
        if z_score < 2.5:
            return [], [], "UNKNOWN"
        diag = self.SENSOR_DIAGNOSTICS.get(sensor_id, {
            "causes": ["Dégradation générale détectée"],
            "actions": ["Programmer une inspection détaillée"],
            "component": "UNKNOWN"
        })
        causes = diag.get("causes", [])
        actions = diag.get("actions", [])
        # Ajouter des messages plus critiques si le Z-score est élevé
        if z_score > 7.0:
            actions.insert(0, "🔴 URGENCE - Intervention immédiate requise")
        elif z_score > 5.0:
            actions.insert(0, "⚠️ Action rapide recommandée")
        return causes, actions, diag.get("component", "UNKNOWN")


    def get_diagnosis(self, anomalies):
        """
        Analyse les anomalies et retourne les causes et actions en FRANÇAIS
        """
        result = {
            "status": "🟢 SAIN",
            "risk_level": "FAIBLE",
            "global_risk_score": 0.0,
            "critical_faults": [],
            "systems_impacted": {},
            "summary": "🟢 Surveillance nominale - aucun problème détecté",
            "causes": [],
            "actions": []
        }
        if not anomalies or len(anomalies) == 0:
            return result
        
        try:
            # 🔥 Ne prendre que les vraies anomalies (Z-score >= 2.5)
            real_anomalies = [a for a in anomalies if abs(a.get("z_score", 0)) >= 2.5]

            if not real_anomalies:
                return result  # Pas de vraies anomalies

            total_z = sum(min(abs(a.get("z_score", 0)), 15.0) for a in real_anomalies)
            risk_percent = min(round((total_z / 50) * 100, 1), 100.0)
            result["global_risk_score"] = risk_percent
            
            # Détermination du niveau de risque
            if risk_percent >= 70:
                result["risk_level"] = "🔴 URGENCE"
                result["status"] = "🔴 CRITIQUE"
            elif risk_percent >= 40:
                result["risk_level"] = "🟠 CRITIQUE"
                result["status"] = "🟠 ATTENTION"
            elif risk_percent >= 15:
                result["risk_level"] = "🟡 ATTENTION"
                result["status"] = "🟡 DÉGRADÉ"
            else:
                result["risk_level"] = "🟢 FAIBLE"
                result["status"] = "🟢 SAIN"
            
            # 🔥 Analyse de chaque anomalie
            all_causes = set()
            all_actions = set()
            top_faults = []
            systems_status = {}
            
            for a in anomalies:
                sensor_id = a.get("sensor_id", "")
                z_score = abs(a.get("z_score", 0))
                sensor_name = self._translate_sensor_name(sensor_id)
                
                # Récupérer les causes et actions spécifiques
                causes, actions, component = self._get_causes_and_actions(sensor_id, z_score)
                
                for cause in causes:
                    all_causes.add(cause)
                for action in actions:
                    all_actions.add(action)
                
                # Système impacté
                system_fr = self.SYSTEM_NAMES_FR.get(component, component)
                if system_fr not in systems_status:
                    systems_status[system_fr] = {"count": 0, "max_z": z_score}
                systems_status[system_fr]["count"] += 1
                systems_status[system_fr]["max_z"] = max(systems_status[system_fr]["max_z"], z_score)
                
                # Top fautes
                if len(top_faults) < 3:
                    severity = "⚠️" if z_score > 5 else "🔸"
                    top_faults.append(f"{severity} {sensor_name} ({system_fr})")
            
            # Construction du résumé
            result.update({
                "systems_impacted": systems_status,
                "critical_faults": top_faults[:3],
                "causes": list(all_causes)[:5],
                "actions": list(all_actions)[:5],
                "summary": f"RISQUE {result['risk_level']} ({risk_percent:.0f}%) | {', '.join(top_faults[:2])}"
            })
            
        except Exception as e:
            logger.error(f"❌ Erreur diagnostic: {e}")
            result["summary"] = f"❌ Erreur diagnostic: {str(e)}"
        
        return result


# Instance unique
_engine = NASAKnowledgeEngine()
get_nasa_solution = _engine.get_diagnosis