# maintenance/urls.py
from django.urls import path

from maintenance.views import (_estimate_duration, analytic_view, change_password, clear_all_alerts, dashboard_view, get_engine_time_series, get_engine_trend, get_engines_list, get_engines_status, get_fleet_health, 
                               get_recent_alerts, 
                               get_task_status, get_train_task_status, get_training_history_detail, get_training_history_list, get_unread_count, 
                               history_view, input_form_view, 
                               mark_alert_as_read, mark_all_alerts_as_read, mark_training_as_viewed, 
                               predict_engine_status, test_radar_view, train_model_view, training_detail_view, training_history_view, update_profile, 
                               validate_data_view)


urlpatterns = [
    path('test-radar/', test_radar_view, name='test_radar'),
    path('api/recent-alerts/', get_recent_alerts, name='recent_alerts'),
    path('api/alert/<int:alert_id>/read/', mark_alert_as_read, name='mark_alert_read'),
    path('api/alerts/read-all/', mark_all_alerts_as_read, name='mark_all_read'),
    
    # 🔥 NOUVELLES URLS INTELLIGENTES
    path('api/predict/', predict_engine_status, name='predict_engine'),
    path('api/task/<str:task_id>/status/', get_task_status, name='task_status'),
    path('api/engine/<str:engine_id>/trend/', get_engine_trend, name='engine_trend'),
    path('api/fleet/health/', get_fleet_health, name='fleet_health'),
    # maintenance/urls.py
    path('api/engine/<str:engine_id>/timeseries/', get_engine_time_series, name='engine_timeseries'),
    path('input/', input_form_view, name='input_form'),
    path('history/', history_view, name='history'),
    path('analytics/', analytic_view, name='analytics'),

    path('api/user/profile/', update_profile, name='api_update_profile'),
    path('api/user/change-password/', change_password, name='api_change_password'),


    # 🔥 Entraînement du modèle
    path('api/train/', train_model_view, name='train_model'),
    path('api/train/validate/', validate_data_view, name='validate_data'),
    path('api/train/<str:task_id>/status/', get_train_task_status, name='train_task_status'),
    
    # 🔥 Badge notifications
    path('api/unread-count/', get_unread_count, name='unread_count'),

    path('api/alerts/clear-all/',clear_all_alerts, name='clear_all_alerts'),

    path('api/engines/list/', get_engines_list, name='engines_list'),
    path('api/engines/status/', get_engines_status, name='engines_status'),

    # path('dashboard/', dashboard_view, name='dashboard'), 
      # 🔥 NOUVELLES ROUTES
    path('training-history/', training_history_view, name='training_history'),
    path('training-history/<int:history_id>/', training_detail_view, name='training_detail'),
    path('api/training-history/', get_training_history_list, name='training_history_list'),
    path('api/training-history/<int:history_id>/', get_training_history_detail, name='training_history_detail'),
    path('api/training/<int:history_id>/mark-viewed/', mark_training_as_viewed, name='training_mark_viewed'),


]