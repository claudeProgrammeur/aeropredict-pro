"""
Fine-tuning du modèle LSTM pour AeroPredict.
Version RENFORCÉE - Production Ready - AVEC HISTORIQUE
"""

import os
import logging
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
from typing import Dict, Any, List, Optional, Tuple, Callable
from datetime import datetime
from django.conf import settings
from django.utils import timezone

from ai_engine.validators import validate_training_data
from ai_engine.evaluator import evaluate_predictions, compare_models, get_evaluation_summary

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTES CORRIGÉES
# ============================================================

DEFAULT_EPOCHS = 50
DEFAULT_BATCH_SIZE = 16
DEFAULT_LEARNING_RATE = 0.0001
EARLY_STOPPING_PATIENCE = 15
VALIDATION_SPLIT = 0.2
MIN_SAMPLES_FOR_VALIDATION = 5
RUL_SCALE_FACTOR = 1.0


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def _normalize_training_data(training_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalise les données d'entraînement."""
    sensor_mapping = {
        's2': 'Temp_Entree_LPC', 's3': 'Temp_Sortie_HPC', 's4': 'Temp_Sortie_LPT',
        's7': 'Pression_Sortie_HPC', 's8': 'Vitesse_Physique_Fan', 's9': 'Vitesse_Physique_Core',
        's11': 'Pression_Sortie_LPT', 's12': 'Vitesse_HPC_Sortie', 's13': 'Vitesse_LPC_Sortie',
        's14': 'Vitesse_Bypass', 's15': 'Pression_Bouchon', 's17': 'Vitesse_Rotation_HPC',
        's20': 'Rapport_Pression_HPC', 's21': 'Pression_Entree_Fan',
    }
    
    normalized = []
    for sample in training_data:
        norm_sample = {}
        
        for key in ['engine_id', 'cycle', 'rul', 'RUL', 'engineId']:
            if key in sample:
                norm_sample['engine_id'] = sample[key]
                break
        
        if 'engine_id' not in norm_sample:
            norm_sample['engine_id'] = f"ENGINE_{len(normalized):04d}"
        
        norm_sample['rul'] = float(sample.get('rul', sample.get('RUL', 125.0)))
        
        norm_sample['Altitude'] = float(sample.get('Altitude', sample.get('altitude', sample.get('setting1', 35000))))
        norm_sample['Mach'] = float(sample.get('Mach', sample.get('mach', sample.get('setting2', 0.6))))
        norm_sample['Regime'] = float(sample.get('Regime', sample.get('regime', sample.get('setting3', 100))))
        
        for short_name, long_name in sensor_mapping.items():
            value = sample.get(long_name, sample.get(short_name))
            norm_sample[long_name] = float(value) if value is not None else 0.0
        
        normalized.append(norm_sample)
    
    return normalized


def asymmetric_rul_loss(y_pred: torch.Tensor, y_true: torch.Tensor) -> torch.Tensor:
    """Loss asymétrique : pénalise plus les prédictions optimistes."""
    error = y_pred - y_true
    penalty = torch.where(error > 0, 2.0, 1.0)
    return torch.mean(penalty * torch.pow(error, 2))


def prepare_data_from_list(data_list: List[Dict[str, Any]], preprocessor) -> Tuple[np.ndarray, np.ndarray]:
    """Prépare les données d'entraînement."""
    X_list, y_list, skipped = [], [], 0
    
    for idx, sample in enumerate(data_list):
        engine_id = sample.get('engine_id', 'training_engine')
        
        try:
            sequence = preprocessor.process(engine_id, sample)
            X_list.append(sequence[0])
            y_list.append(float(sample.get('rul', 125.0)))
        except Exception as e:
            skipped += 1
            if skipped <= 10:
                logger.debug(f"Échantillon ignoré {idx}: {e}")
            continue
    
    if skipped > 0:
        logger.warning(f"⚠️ {skipped} échantillons ignorés sur {len(data_list)}")
    
    if not X_list:
        raise ValueError("Aucun échantillon valide après preprocessing")
    
    return np.stack(X_list, axis=0), np.array(y_list)


def create_dataloaders(X: np.ndarray, y: np.ndarray, batch_size: int = DEFAULT_BATCH_SIZE,
                       val_split: float = VALIDATION_SPLIT) -> Tuple[DataLoader, DataLoader]:
    """Crée les DataLoaders."""
    n_samples = len(X)
    
    if n_samples < MIN_SAMPLES_FOR_VALIDATION:
        logger.warning(f"⚠️ Seulement {n_samples} échantillons. Pas de validation séparée.")
        X_tensor, y_tensor = torch.FloatTensor(X), torch.FloatTensor(y).view(-1, 1)
        dataset = TensorDataset(X_tensor, y_tensor)
        loader = DataLoader(dataset, batch_size=min(batch_size, n_samples), shuffle=True)
        return loader, loader
    
    n_val = max(1, int(n_samples * val_split))
    n_train = n_samples - n_val
    
    X_tensor, y_tensor = torch.FloatTensor(X), torch.FloatTensor(y).view(-1, 1)
    indices = torch.randperm(n_samples)
    
    train_dataset = TensorDataset(X_tensor[indices[:n_train]], y_tensor[indices[:n_train]])
    val_dataset = TensorDataset(X_tensor[indices[n_train:]], y_tensor[indices[n_train:]])
    
    return (DataLoader(train_dataset, batch_size=min(batch_size, n_train), shuffle=True),
            DataLoader(val_dataset, batch_size=min(batch_size, n_val), shuffle=False))


# ============================================================
# ENTRAÎNEMENT PRINCIPAL
# ============================================================

def train_lstm_model(
    training_data: Optional[List[Dict[str, Any]]] = None,
    epochs: int = DEFAULT_EPOCHS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    save_model: bool = True,
    progress_callback: Optional[Callable] = None,
    training_history_id: Optional[int] = None,  # 🔥 NOUVEAU: ID de l'historique
    user_id: Optional[int] = None,              # 🔥 NOUVEAU: ID de l'utilisateur
    engine_id_for_prediction: Optional[str] = None  # 🔥 NOUVEAU: Moteur à analyser
) -> Dict[str, Any]:
    """
    Fine-tune le modèle LSTM avec de nouvelles données.
    
    Args:
        training_data: Liste des données d'entraînement
        epochs: Nombre d'époques
        batch_size: Taille des batchs
        learning_rate: Taux d'apprentissage
        save_model: Sauvegarder le modèle
        progress_callback: Callback de progression
        training_history_id: ID de l'objet TrainingHistory à mettre à jour
        user_id: ID de l'utilisateur
        engine_id_for_prediction: ID du moteur à analyser après entraînement
    """
    logger.info("=" * 60)
    logger.info("🚀 DÉMARRAGE DU FINE-TUNING LSTM")
    logger.info("=" * 60)
    
    start_time = datetime.now()
    
    # 🔥 Récupérer ou créer l'historique
    from maintenance.models import TrainingHistory
    training_history = None
    if training_history_id:
        try:
            training_history = TrainingHistory.objects.get(id=training_history_id)
            training_history.status = 'RUNNING'
            training_history.save(update_fields=['status'])
        except TrainingHistory.DoesNotExist:
            logger.warning(f"Historique {training_history_id} non trouvé")
    
    try:
        # ========================================================
        # ÉTAPE 1: VALIDATION DES DONNÉES
        # ========================================================
        logger.info("📋 Validation des données d'entraînement...")
        
        if training_data is None or len(training_data) == 0:
            raise ValueError("Aucune donnée d'entraînement fournie")
        
        logger.info(f"📊 {len(training_data)} échantillons reçus")
        
        normalized_data = _normalize_training_data(training_data)
        is_valid, validation_report = validate_training_data(normalized_data)
        
        if not is_valid:
            error_msg = f"Données invalides: {validation_report.get('errors', [])[:3]}"
            logger.error(f"❌ {error_msg}")
            if training_history:
                training_history.status = 'FAILED'
                training_history.error_message = error_msg
                training_history.completed_at = timezone.now()
                training_history.save()
            return {'status': 'failed', 'error': error_msg, 'validation_report': validation_report}
        
        valid_samples = validation_report.get('valid_samples', len(normalized_data))
        logger.info(f"✅ {valid_samples} échantillons valides")
        
        if training_history:
            training_history.samples_count = valid_samples
            training_history.epochs = epochs
            training_history.batch_size = batch_size
            training_history.learning_rate = learning_rate
            training_history.save(update_fields=['samples_count', 'epochs', 'batch_size', 'learning_rate'])
        
        # ========================================================
        # ÉTAPE 2: CHARGEMENT DU MODÈLE
        # ========================================================
        logger.info("📦 Chargement du modèle pré-entraîné...")
        
        from ai_engine.core.predictor import AIEngine
        
        ai_engine = AIEngine()
        model = ai_engine.model
        device = ai_engine.device
        preprocessor = ai_engine.preprocessor
        
        preprocessor.buffers.clear()
        logger.info(f"✅ Modèle chargé sur {device}")
        
        # ========================================================
        # ÉTAPE 3: PRÉPARATION DES DONNÉES
        # ========================================================
        logger.info("🔄 Préparation des données (preprocessing)...")
        
        X, y = prepare_data_from_list(normalized_data, preprocessor)
        logger.info(f"✅ Données préparées: X.shape={X.shape}, y.shape={y.shape}")
        
        train_loader, val_loader = create_dataloaders(X, y, batch_size)
        logger.info(f"📊 Train: {len(train_loader.dataset)} | Val: {len(val_loader.dataset)}")
        
        # ========================================================
        # ÉTAPE 4: ÉVALUATION AVANT ENTRAÎNEMENT
        # ========================================================
        logger.info("📊 Évaluation AVANT fine-tuning...")
        
        model.eval()
        all_preds_before, all_true_before = [], []
        
        with torch.no_grad():
            for inputs, targets in val_loader:
                inputs = inputs.to(device)
                outputs = model(inputs).cpu().numpy().flatten()
                all_preds_before.extend(outputs.tolist())
                all_true_before.extend(targets.numpy().flatten().tolist())
        
        before_metrics = evaluate_predictions(all_true_before, all_preds_before)
        logger.info(f"   Avant: {get_evaluation_summary(before_metrics)}")
        
        if training_history:
            training_history.rmse_before = before_metrics['metrics']['rmse']
            training_history.r2_before = before_metrics['metrics']['r2']
            training_history.safety_score_before = before_metrics['metrics']['safety_score']
            training_history.save(update_fields=['rmse_before', 'r2_before', 'safety_score_before'])
        
        # ========================================================
        # ÉTAPE 5: ENTRAÎNEMENT
        # ========================================================
        logger.info(f" Démarrage de l'entraînement ({epochs} époques)...")
        
        model.train()
        optimizer = optim.Adam(model.parameters(), lr=learning_rate, weight_decay=1e-5)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=4)
        criterion = asymmetric_rul_loss
        
        best_val_loss = float('inf')
        patience_counter = 0
        train_losses, val_losses = [], []
        best_model_state = None
        
        for epoch in range(epochs):
            # Train
            model.train()
            epoch_train_losses = []
            for inputs, targets in train_loader:
                inputs, targets = inputs.to(device), targets.to(device)
                optimizer.zero_grad()
                outputs = model(inputs)
                loss = criterion(outputs, targets)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()
                epoch_train_losses.append(loss.item())
            
            avg_train_loss = np.mean(epoch_train_losses)
            train_losses.append(avg_train_loss)
            
            # Validation
            model.eval()
            epoch_val_losses = []
            with torch.no_grad():
                for inputs, targets in val_loader:
                    inputs, targets = inputs.to(device), targets.to(device)
                    val_loss = nn.MSELoss()(model(inputs), targets)
                    epoch_val_losses.append(val_loss.item())
            
            avg_val_loss = np.mean(epoch_val_losses)
            val_losses.append(avg_val_loss)
            scheduler.step(avg_val_loss)
            
            logger.info(f"   Epoch {epoch+1}/{epochs} | Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f} | LR: {optimizer.param_groups[0]['lr']:.6f}")
            
            if progress_callback:
                progress_callback(epoch + 1, avg_train_loss, avg_val_loss)
            
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                patience_counter = 0
                best_model_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                logger.info(f"      ⭐ Nouveau meilleur modèle! Loss: {avg_val_loss:.4f}")
            else:
                patience_counter += 1
                if patience_counter >= EARLY_STOPPING_PATIENCE:
                    logger.info(f"      🛑 Early stopping à l'époque {epoch+1}")
                    break
        
        if best_model_state:
            model.load_state_dict(best_model_state)
        
        # ========================================================
        # ÉTAPE 6: ÉVALUATION APRÈS ENTRAÎNEMENT
        # ========================================================
        logger.info("📊 Évaluation APRÈS fine-tuning...")
        
        model.eval()
        all_preds_after, all_true_after = [], []
        
        with torch.no_grad():
            for inputs, targets in val_loader:
                inputs = inputs.to(device)
                outputs = model(inputs).cpu().numpy().flatten()
                all_preds_after.extend(outputs.tolist())
                all_true_after.extend(targets.numpy().flatten().tolist())
        
        after_metrics = evaluate_predictions(all_true_after, all_preds_after)
        logger.info(f"   Après: {get_evaluation_summary(after_metrics)}")
        
        comparison = compare_models(before_metrics, after_metrics)
        logger.info(f"📈 {comparison['verdict']}")
        
        # ========================================================
        # 🔥 ÉTAPE 7: PRÉDICTION SUR LE MOTEUR SPÉCIFIÉ
        # ========================================================
        predicted_rul = None
        health_status = None
        anomalies = []
        diagnosis = {}
        
        if engine_id_for_prediction and training_data:
            try:
                # Prendre la dernière ligne des données d'entraînement comme exemple
                last_sample = normalized_data[-1] if normalized_data else normalized_data[0]
                sensor_data = {
                    "Altitude": last_sample['Altitude'],
                    "Mach": last_sample['Mach'],
                    "Regime": last_sample['Regime'],
                    "Temp_Entree_LPC": last_sample.get('Temp_Entree_LPC', 518.67),
                    "Temp_Sortie_HPC": last_sample.get('Temp_Sortie_HPC', 1589.0),
                    "Temp_Sortie_LPT": last_sample.get('Temp_Sortie_LPT', 1406.0),
                    "Pression_Sortie_HPC": last_sample.get('Pression_Sortie_HPC', 554.0),
                    "Vitesse_Physique_Fan": last_sample.get('Vitesse_Physique_Fan', 2388.0),
                    "Vitesse_Physique_Core": last_sample.get('Vitesse_Physique_Core', 9064.0),
                    "Pression_Sortie_LPT": last_sample.get('Pression_Sortie_LPT', 47.0),
                    "Vitesse_HPC_Sortie": last_sample.get('Vitesse_HPC_Sortie', 522.0),
                    "Vitesse_LPC_Sortie": last_sample.get('Vitesse_LPC_Sortie', 2388.0),
                    "Vitesse_Bypass": last_sample.get('Vitesse_Bypass', 8143.0),
                    "Pression_Bouchon": last_sample.get('Pression_Bouchon', 8.4),
                    "Vitesse_Rotation_HPC": last_sample.get('Vitesse_Rotation_HPC', 392.0),
                    "Rapport_Pression_HPC": last_sample.get('Rapport_Pression_HPC', 39.0),
                    "Pression_Entree_Fan": last_sample.get('Pression_Entree_Fan', 23.0),
                }
                
                result = ai_engine.predict(engine_id_for_prediction, sensor_data)
                predicted_rul = result.get('ai_prediction', {}).get('predicted_rul', 0)
                health_status = result.get('status', 'UNKNOWN')
                anomalies = result.get('raw_anomalies', [])
                diagnosis = result.get('diagnosis', {})
                
                logger.info(f"🔮 Prédiction pour {engine_id_for_prediction}: RUL={predicted_rul}, Status={health_status}")
                
            except Exception as e:
                logger.warning(f"⚠️ Impossible de faire la prédiction: {e}")
        if training_history:
            if not training_history.health_status:
                training_history.health_status = 'UNKNOWN'
            
            training_history.status = 'SUCCESS'
            training_history.completed_at = timezone.now()
        # ========================================================
        # ÉTAPE 8: SAUVEGARDE DU MODÈLE
        # ========================================================
        model_saved = False
        if save_model:
            model_path = os.path.join(settings.BASE_DIR, 'ai_engine', 'configs', 'models_files', 'best_model.pth')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_path = model_path.replace('.pth', f'_backup_{timestamp}.pth')
            
            if os.path.exists(model_path):
                try:
                    os.rename(model_path, backup_path)
                    logger.info(f"💾 Backup créé: {backup_path}")
                except Exception as e:
                    logger.warning(f"⚠️ Backup échoué: {e}")
            
            torch.save(model.state_dict(), model_path)
            logger.info(f"💾 Modèle sauvegardé: {model_path}")
            model_saved = True
            
            from ai_engine.core.predictor import AIEngine
            AIEngine.force_reload()
            logger.info("🔄 Modèle rechargé à chaud")
        
        # ========================================================
        # ÉTAPE 9: MISE À JOUR DE L'HISTORIQUE
        # ========================================================
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        global_score = after_metrics['global_score']
        performance_level = after_metrics['performance_level']
        
        if len(training_data) < 50:
            global_score = min(global_score, 50.0)
            performance_level = "⚠️ DONNÉES INSUFFISANTES"
        
        result = {
            'status': 'success',
            'timestamp': end_time.isoformat(),
            'duration_seconds': round(duration, 1),
            'training': {
                'epochs_completed': len(train_losses),
                'final_train_loss': round(train_losses[-1], 4) if train_losses else 0,
                'final_val_loss': round(val_losses[-1], 4) if val_losses else 0,
                'best_val_loss': round(best_val_loss, 4),
            },
            'metrics_before': before_metrics['metrics'],
            'metrics_after': after_metrics['metrics'],
            'comparison': comparison,
            'performance_level': performance_level,
            'global_score': global_score,
            'recommendation': after_metrics['recommendation'],
            'samples_used': len(training_data),
            'model_saved': model_saved,
            # 🔥 Ajout des données de prédiction
            'predicted_rul': predicted_rul,
            'health_status': health_status,
            'anomalies': anomalies,
            'diagnosis': diagnosis
        }
        
        # 🔥 Mettre à jour l'objet TrainingHistory
        if training_history:
            training_history.status = 'SUCCESS'
            training_history.completed_at = timezone.now()
            training_history.duration_seconds = duration
            training_history.rmse_after = after_metrics['metrics']['rmse']
            training_history.r2_after = after_metrics['metrics']['r2']
            training_history.safety_score_after = after_metrics['metrics']['safety_score']
            training_history.global_score = global_score
            training_history.performance_level = performance_level
            training_history.predicted_rul = predicted_rul
            training_history.health_status = health_status
            training_history.detected_anomalies = anomalies
            training_history.causes = diagnosis.get('causes', [])
            training_history.actions = diagnosis.get('actions', [])
            training_history.full_result = result
            
            # 🔥 Générer les messages automatiquement
            training_history.generate_message()
            training_history.save()
            
            result['training_history_id'] = training_history.id
            result['short_message'] = training_history.short_message
            result['long_message'] = training_history.long_message
        
        logger.info("=" * 60)
        logger.info(f"✅ ENTRAÎNEMENT TERMINÉ - {performance_level}")
        logger.info(f"   Score: {global_score:.1f}/100 | Durée: {duration:.1f}s")
        if predicted_rul:
            logger.info(f"   Prédiction: {predicted_rul} cycles | Status: {health_status}")
        logger.info("=" * 60)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Échec entraînement: {e}", exc_info=True)
        if training_history:
            training_history.status = 'FAILED'
            training_history.error_message = str(e)
            training_history.completed_at = timezone.now()
            training_history.save()
        return {'status': 'failed', 'error': str(e), 'timestamp': datetime.now().isoformat()}


def quick_test():
    """Test rapide de l'entraînement avec des données simulées."""
    dummy_data = []
    for cycle in range(1, 31):
        dummy_data.append({
            'engine_id': 'TEST_ENGINE', 'cycle': cycle, 'rul': 125 - cycle * 2,
            'Altitude': 35000, 'Mach': 0.6, 'Regime': 100,
            'Temp_Entree_LPC': 518.67, 'Temp_Sortie_HPC': 1589.0,
            'Temp_Sortie_LPT': 1406.0, 'Pression_Sortie_HPC': 554.0,
            'Vitesse_Physique_Fan': 2388.0, 'Vitesse_Physique_Core': 9064.0,
            'Pression_Sortie_LPT': 47.0, 'Vitesse_HPC_Sortie': 522.0,
            'Vitesse_LPC_Sortie': 2388.0, 'Vitesse_Bypass': 8143.0,
            'Pression_Bouchon': 8.4, 'Vitesse_Rotation_HPC': 392.0,
            'Rapport_Pression_HPC': 39.0, 'Pression_Entree_Fan': 23.0,
        })
    return train_lstm_model(dummy_data, epochs=5)