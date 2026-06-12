# # dashboard/views.py
# from django.shortcuts import render
# from maintenance.models import Engine, MaintenanceAlert

# def cockpit_view(request):
#     context = {
#         'total_engines': Engine.objects.count(),
#         'active_alerts': MaintenanceAlert.objects.filter(is_read=False).count(),
#         'critical_count': Engine.objects.filter(status__contains='CRITICAL').count(),
#     }
#     return render(request, 'dashboard/cockpit.html', context)