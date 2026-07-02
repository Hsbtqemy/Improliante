"""Routes du back-office (réservées au bureau)."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "backoffice"

urlpatterns = [
    path("bureau/", views.tableau_de_bord, name="tableau_de_bord"),
    path("bureau/parametres/", views.parametres_association, name="parametres_association"),
    path("bureau/equipe/", views.equipe_bureau, name="equipe_bureau"),
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
    path("bureau/factures/<int:pk>/avoir/", views.creer_avoir_vue, name="creer_avoir"),
    path("bureau/clients/", views.liste_clients, name="liste_clients"),
    path("bureau/devis/", views.liste_devis, name="liste_devis"),
    path("bureau/devis/nouveau/", views.creer_devis, name="creer_devis"),
    path("bureau/devis/<int:pk>/", views.editer_devis, name="editer_devis"),
    path("bureau/devis/<int:pk>/statut/", views.changer_statut_devis, name="changer_statut_devis"),
    path("bureau/devis/<int:pk>/transformer/", views.transformer_devis, name="transformer_devis"),
    path("bureau/devis/<int:pk>/telecharger/", views.telecharger_devis, name="telecharger_devis"),
    path("bureau/documents/", views.ged_racine, name="ged_racine"),
    path("bureau/documents/dossier/<int:pk>/", views.ged_dossier, name="ged_dossier"),
    path(
        "bureau/documents/<int:pk>/nouvelle-version/",
        views.ged_nouvelle_version,
        name="ged_nouvelle_version",
    ),
    path("bureau/budget/", views.budget_transactions, name="budget_transactions"),
    path(
        "bureau/budget/transaction/nouvelle/",
        views.budget_creer_transaction,
        name="budget_creer_transaction",
    ),
    path(
        "bureau/budget/transaction/<int:pk>/",
        views.budget_editer_transaction,
        name="budget_editer_transaction",
    ),
    path(
        "bureau/budget/transaction/<int:pk>/supprimer/",
        views.budget_supprimer_transaction,
        name="budget_supprimer_transaction",
    ),
    path("bureau/budget/bilan/", views.budget_bilan, name="budget_bilan"),
    path("bureau/budget/bilan/excel/", views.budget_bilan_excel, name="budget_bilan_excel"),
    path("bureau/budget/saisons/", views.budget_saisons, name="budget_saisons"),
    path("bureau/budget/categories/", views.budget_categories, name="budget_categories"),
]
