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
    path("activation/<uidb64>/<token>/", views.activer_compte, name="activer_compte"),
    path("espace/", views.tableau_de_bord, name="tableau_de_bord"),
    path("espace/profil/", views.mon_profil, name="mon_profil"),
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
    path("espace/fichiers/", views.mes_fichiers, name="mes_fichiers"),
    path("espace/fichiers/<int:pk>/", views.dossier_membre, name="dossier_membre"),
    path(
        "espace/fichiers/<int:pk>/editer/",
        views.editer_dossier_membre,
        name="editer_dossier_membre",
    ),
    path(
        "espace/fichiers/<int:pk>/supprimer/",
        views.supprimer_dossier_membre,
        name="supprimer_dossier_membre",
    ),
    path(
        "espace/fichiers/doc/<int:pk>/supprimer/",
        views.supprimer_document_membre,
        name="supprimer_document_membre",
    ),
    path("espace/commun/<int:pk>/", views.dossier_commun, name="dossier_commun"),
    path(
        "espace/commun/<int:pk>/editer/",
        views.editer_dossier_commun,
        name="editer_dossier_commun",
    ),
    path(
        "espace/commun/<int:pk>/supprimer/",
        views.supprimer_dossier_commun,
        name="supprimer_dossier_commun",
    ),
    path(
        "espace/commun/doc/<int:pk>/supprimer/",
        views.supprimer_document_commun,
        name="supprimer_document_commun",
    ),
    path("espace/convocations/", views.mes_convocations, name="mes_convocations"),
    path("espace/convocations/<int:pk>/", views.detail_convocation, name="detail_convocation"),
    path("espace/recus/", views.mes_recus, name="mes_recus"),
    path("espace/recus/<int:pk>/telecharger/", views.telecharger_recu, name="telecharger_recu"),
]
