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
    path("espace/projets/", views.mes_projets, name="mes_projets"),
    path("espace/projets/nouveau/", views.creer_projet, name="creer_projet"),
    path("espace/projets/<int:pk>/", views.editer_projet, name="editer_projet"),
    path("espace/evenements/", views.mes_evenements, name="mes_evenements"),
    path("espace/evenements/nouveau/", views.creer_evenement, name="creer_evenement"),
    path("espace/evenements/<int:pk>/", views.editer_evenement, name="editer_evenement"),
    path("espace/documents/", views.mes_documents, name="mes_documents"),
    path(
        "espace/documents/<int:pk>/telecharger/",
        views.telecharger_document,
        name="telecharger_document",
    ),
    path("espace/convocations/", views.mes_convocations, name="mes_convocations"),
    path("espace/convocations/<int:pk>/", views.detail_convocation, name="detail_convocation"),
]
