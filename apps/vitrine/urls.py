"""Routes du front public."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "vitrine"

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("spectacles/", views.liste_spectacles, name="spectacles"),
    path("spectacles/<int:pk>/", views.detail_spectacle, name="spectacle"),
]
