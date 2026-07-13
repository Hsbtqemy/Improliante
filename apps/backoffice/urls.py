"""Routes du back-office (réservées au bureau)."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "backoffice"

urlpatterns = [
    path("bureau/", views.tableau_de_bord, name="tableau_de_bord"),
    path("bureau/finances/", views.finances, name="finances"),
    path("bureau/parametres/", views.parametres_association, name="parametres_association"),
    path("bureau/equipe/", views.equipe_bureau, name="equipe_bureau"),
    path("bureau/membres/", views.liste_membres, name="liste_membres"),
    path("bureau/membres/nouveau/", views.creer_membre, name="creer_membre"),
    path("bureau/membres/<int:pk>/", views.editer_membre, name="editer_membre"),
    path(
        "bureau/membres/<int:pk>/ouvrir-acces/",
        views.ouvrir_acces_membre,
        name="ouvrir_acces_membre",
    ),
    path(
        "bureau/membres/<int:pk>/visibilite/",
        views.basculer_visibilite_membre,
        name="basculer_visibilite_membre",
    ),
    path(
        "bureau/membres/<int:pk>/a-la-une/",
        views.basculer_mise_en_avant_membre,
        name="basculer_mise_en_avant_membre",
    ),
    path("bureau/adhesions/", views.liste_adhesions, name="liste_adhesions"),
    path("bureau/adhesions/nouvelle/", views.creer_adhesion, name="creer_adhesion"),
    path("bureau/adhesions/<int:pk>/", views.editer_adhesion, name="editer_adhesion"),
    path(
        "bureau/adhesions/<int:pk>/supprimer/",
        views.supprimer_adhesion,
        name="supprimer_adhesion",
    ),
    path("bureau/moderation/", views.file_moderation, name="file_moderation"),
    path("bureau/moderation/projet/<int:pk>/", views.moderer_projet, name="moderer_projet"),
    path(
        "bureau/moderation/evenement/<int:pk>/",
        views.moderer_evenement,
        name="moderer_evenement",
    ),
    path("bureau/evenements/", views.liste_evenements, name="liste_evenements"),
    path("bureau/evenements/nouveau/", views.creer_evenement, name="creer_evenement"),
    path("bureau/evenements/<int:pk>/", views.editer_evenement, name="editer_evenement"),
    path(
        "bureau/evenements/<int:pk>/supprimer/",
        views.supprimer_evenement,
        name="supprimer_evenement",
    ),
    path("bureau/projets/", views.liste_projets, name="liste_projets"),
    path("bureau/projets/nouveau/", views.creer_projet, name="creer_projet"),
    path("bureau/projets/<int:pk>/", views.editer_projet, name="editer_projet"),
    path("bureau/projets/<int:pk>/supprimer/", views.supprimer_projet, name="supprimer_projet"),
    path("bureau/recus/", views.liste_recus, name="liste_recus"),
    path("bureau/recus/nouveau/", views.creer_recu, name="creer_recu"),
    path("bureau/recus/<int:pk>/telecharger/", views.telecharger_recu, name="telecharger_recu"),
    path("bureau/facturation/", views.facturation, name="facturation"),
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
    path("bureau/fichiers-transmis/", views.fichiers_membres, name="fichiers_membres"),
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
    path("bureau/gouvernance/", views.gouvernance_reunions, name="gouvernance_reunions"),
    path(
        "bureau/gouvernance/reunion/<int:pk>/",
        views.gouvernance_reunion,
        name="gouvernance_reunion",
    ),
    path(
        "bureau/gouvernance/reunion/<int:pk>/modifier/",
        views.gouvernance_editer_reunion,
        name="gouvernance_editer_reunion",
    ),
    path(
        "bureau/gouvernance/reunion/<int:pk>/sujet/",
        views.gouvernance_ajouter_sujet,
        name="gouvernance_ajouter_sujet",
    ),
    path(
        "bureau/gouvernance/reunion/<int:pk>/presence/",
        views.gouvernance_saisir_presence,
        name="gouvernance_saisir_presence",
    ),
    path(
        "bureau/gouvernance/reunion/<int:pk>/preremplir-votes/",
        views.gouvernance_preremplir_votes,
        name="gouvernance_preremplir_votes",
    ),
    path(
        "bureau/gouvernance/reunion/<int:pk>/pouvoir/",
        views.gouvernance_ajouter_pouvoir,
        name="gouvernance_ajouter_pouvoir",
    ),
    path(
        "bureau/gouvernance/reunion/<int:pk>/resolution/",
        views.gouvernance_ajouter_resolution,
        name="gouvernance_ajouter_resolution",
    ),
    path(
        "bureau/gouvernance/reunion/<int:pk>/notes/",
        views.gouvernance_notes,
        name="gouvernance_notes",
    ),
    path(
        "bureau/gouvernance/reunion/<int:pk>/bloc/",
        views.gouvernance_ajouter_bloc,
        name="gouvernance_ajouter_bloc",
    ),
    path(
        "bureau/gouvernance/reunion/<int:pk>/pv/",
        views.gouvernance_generer_pv,
        name="gouvernance_generer_pv",
    ),
    path(
        "bureau/gouvernance/reunion/<int:pk>/pv/telecharger/",
        views.gouvernance_telecharger_pv,
        name="gouvernance_telecharger_pv",
    ),
]
