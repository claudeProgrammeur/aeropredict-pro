from django.urls import path,include

from .views import connexion,CreateCompte,deconnection,home

urlpatterns = [
    path('accueil/', home,name='accueil'),
    # path('profile/', profile,name='profile'),

    path('connexion/', connexion,name='connexion'),
    path('inscription/', CreateCompte, name='inscription'),
    path('deconnection/', deconnection, name='deconnexion'),
    # path('forgetemail/', forgetemail, name='forgetemail'),

]