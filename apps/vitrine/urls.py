"""Routes du front public."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "vitrine"

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("spectacles/", views.liste_spectacles, name="spectacles"),
    path("spectacles/<int:pk>/", views.detail_spectacle, name="spectacle"),
    path("agenda/", views.agenda, name="agenda"),
    path("agenda/agenda.ics", views.agenda_ical, name="agenda_ical"),
    path("galerie/", views.galerie, name="galerie"),
    path("association/", views.association, name="association"),
    path("membres/<int:pk>/", views.detail_membre, name="membre"),
    path("contact/", views.contact, name="contact"),
    path("contact/merci/", views.contact_merci, name="contact_merci"),
    path("confidentialite/", views.confidentialite, name="confidentialite"),
]
