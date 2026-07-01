"""Routes de l'espace membre (connecté)."""

from __future__ import annotations

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "espace_membre"

urlpatterns = [
    path(
        "connexion/",
        auth_views.LoginView.as_view(template_name="espace_membre/connexion.html"),
        name="connexion",
    ),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="deconnexion"),
    path("espace/", views.tableau_de_bord, name="tableau_de_bord"),
]
