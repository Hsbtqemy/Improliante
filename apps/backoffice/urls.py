"""Routes du back-office (réservées au bureau)."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "backoffice"

urlpatterns = [
    path("bureau/moderation/", views.file_moderation, name="file_moderation"),
    path("bureau/moderation/projet/<int:pk>/", views.moderer_projet, name="moderer_projet"),
    path(
        "bureau/moderation/evenement/<int:pk>/",
        views.moderer_evenement,
        name="moderer_evenement",
    ),
    path("bureau/recus/", views.liste_recus, name="liste_recus"),
    path("bureau/recus/nouveau/", views.creer_recu, name="creer_recu"),
    path("bureau/recus/<int:pk>/telecharger/", views.telecharger_recu, name="telecharger_recu"),
    path("bureau/factures/", views.liste_factures, name="liste_factures"),
    path("bureau/factures/nouvelle/", views.creer_facture, name="creer_facture"),
    path("bureau/factures/<int:pk>/", views.editer_facture, name="editer_facture"),
    path("bureau/factures/<int:pk>/valider/", views.valider_facture_vue, name="valider_facture"),
    path(
        "bureau/factures/<int:pk>/telecharger/",
        views.telecharger_facture,
        name="telecharger_facture",
    ),
    path("bureau/factures/<int:pk>/apercu/", views.previsualiser_facture, name="apercu_facture"),
    path("bureau/clients/", views.liste_clients, name="liste_clients"),
    path("bureau/devis/", views.liste_devis, name="liste_devis"),
    path("bureau/devis/nouveau/", views.creer_devis, name="creer_devis"),
    path("bureau/devis/<int:pk>/", views.editer_devis, name="editer_devis"),
    path("bureau/devis/<int:pk>/statut/", views.changer_statut_devis, name="changer_statut_devis"),
    path("bureau/devis/<int:pk>/transformer/", views.transformer_devis, name="transformer_devis"),
    path("bureau/devis/<int:pk>/telecharger/", views.telecharger_devis, name="telecharger_devis"),
]
