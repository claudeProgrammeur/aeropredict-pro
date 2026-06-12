"""
URL configuration for aeronoth project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django_prometheus.exports import ExportToDjangoView
from django.views.generic import TemplateView

from maintenance.views import profile_view

urlpatterns = [
    path('admin/', admin.site.urls),
     path('metrics', ExportToDjangoView, name='prometheus-metrics'),  # ← AJOUTER ICI

    # API SaaS
    path('api/', include('api.urls')),
    path('dashboarde/', RedirectView.as_view(url='/dashboard/', permanent=False)),  # ✅ Racine → Dashboard
    # Dashboard UI
    # path('dashboard/', include('dashboard.urls')),
    path('maintenance/', include('maintenance.urls')),
    path('', include('connexion.urls')),
    path('profile/', profile_view, name='profile'),


     # Features pages
    path('features/ia-lstm/', TemplateView.as_view(template_name='features/ia_lstm.html'), name='ia_lstm'),
    path('features/live-radar/', TemplateView.as_view(template_name='features/live_radar.html'), name='live_radar'),
    path('features/alertes/', TemplateView.as_view(template_name='features/alertes.html'), name='alertes'),
    path('features/analytics/', TemplateView.as_view(template_name='features/analytics.html'), name='analytics'),
    path('features/csv-import/', TemplateView.as_view(template_name='features/csv_import.html'), name='csv_import'),
    path('features/api/', TemplateView.as_view(template_name='features/api.html'), name='api'),


]

# if settings.DEBUG:
#     urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

