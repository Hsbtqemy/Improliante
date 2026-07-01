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
]
