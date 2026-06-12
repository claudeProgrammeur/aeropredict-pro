# api/urls.py
"""
AeroPredict SaaS - API Routes
Version: 9.0.0
"""

from django.urls import path

from api.views import EngineHealthView, FleetOverviewView, PredictRULView


app_name = 'api'

urlpatterns = [
    # Endpoint principal - Prédiction RUL
    path('predict/', PredictRULView.as_view(), name='predict_rul'),
    
    # Endpoints de monitoring
    path('engine/<str:engine_id>/health/', EngineHealthView.as_view(), name='engine_health'),
    path('fleet/overview/', FleetOverviewView.as_view(), name='fleet_overview'),
]