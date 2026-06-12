from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required


# Create your views here.

# Page d'accueil
def home(request):
    return render(request, 'index.html')


# Page de connexion
def connexion(request):
    # Si l'utilisateur est déjà connecté, rediriger vers l'accueil
    if request.user.is_authenticated:
        return redirect('accueil')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, "✅ Connexion réussie ! Bienvenue.")
            return redirect('accueil')
        else:
            messages.error(request, "❌ Nom d'utilisateur ou mot de passe incorrect.")
    
    return render(request, 'login.html')


# Page d'inscription
def CreateCompte(request):
    # Si l'utilisateur est déjà connecté, rediriger vers l'accueil
    if request.user.is_authenticated:
        return redirect('accueil')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        terms = request.POST.get('terms')  # 🔥 Récupération des conditions d'utilisation

        # # 🔥 VÉRIFICATION DES CONDITIONS D'UTILISATION
        # if not terms:
        #     messages.error(request, "❌ Vous devez accepter les conditions d'utilisation pour créer un compte.")
        #     return render(request, "register.html")

        # Vérification confirmation mot de passe
        if password != password_confirm:
            messages.error(request, "❌ Les mots de passe ne sont pas identiques.")
            return render(request, "register.html")
        
        # Vérification longueur du mot de passe
        if len(password) < 8:
            messages.error(request, "❌ Le mot de passe doit contenir au moins 8 caractères.")
            return render(request, "register.html")
        
        # Vérification si mot de passe uniquement chiffres
        if password.isdigit():
            messages.error(request, "❌ Le mot de passe ne peut pas contenir uniquement des chiffres.")
            return render(request, "register.html")

        # Vérification email valide
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "❌ Adresse email invalide.")
            return render(request, "register.html")
        
        # Vérification si username existe déjà
        if User.objects.filter(username=username).exists():
            messages.error(request, "❌ Ce nom d'utilisateur existe déjà.")
            return render(request, "register.html")
        
        # Vérification si email existe déjà
        if User.objects.filter(email=email).exists():
            messages.error(request, "❌ Cette adresse email est déjà utilisée.")
            return render(request, "register.html")
        
        # ✅ TOUTES LES VALIDATIONS SONT PASSÉES → CRÉATION DU COMPTE
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )
            messages.success(request, "✅ Votre compte a été créé avec succès ! Vous pouvez maintenant vous connecter.")
            return redirect('connexion')
        except Exception as e:
            messages.error(request, f"❌ Erreur lors de la création du compte : {str(e)}")
            return render(request, "register.html")
    
    return render(request, "register.html")


# Déconnexion
def deconnection(request):
    logout(request)
    messages.info(request, "🔓 Vous avez été déconnecté.")
    return redirect('connexion')


# # Page d'accueil après connexion (dashboard)
# @login_required(login_url='connexion')
# def accueil(request):
#     """Page d'accueil après connexion - Dashboard principal"""
#     return render(request, 'dashboard.html')


# Mot de passe oublié (à décommenter et compléter plus tard)
# def forget_password(request):
#     if request.method == 'POST':
#         email = request.POST.get('email')
#         if not email:
#             messages.error(request, "❌ Veuillez saisir votre adresse email.")
#             return render(request, 'forget_password.html')
#         
#         user = User.objects.filter(email=email).first()
#         if not user:
#             messages.error(request, "❌ Cet email n'existe pas.")
#             return render(request, 'forget_password.html')
#         
#         # Logique d'envoi d'email de réinitialisation
#         messages.success(request, "📧 Un email vous a été envoyé pour réinitialiser votre mot de passe.")
#         return redirect('connexion')
#     
#     return render(request, 'forget_password.html')