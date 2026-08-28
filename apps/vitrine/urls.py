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
    path("agenda/<int:pk>/", views.detail_evenement, name="evenement"),
    path("agenda/<int:pk>/inscription/", views.inscription_evenement, name="inscription_evenement"),
    # Retrouvée par jeton et non par identifiant : le porteur n'a pas de
    # compte, et un identifiant de ligne se devine de proche en proche.
    path("reservation/<uuid:jeton>/", views.reservation, name="reservation"),
    path("galerie/", views.galerie, name="galerie"),
    path("association/", views.association, name="association"),
    path("membres/<int:pk>/", views.detail_membre, name="membre"),
    path("contact/", views.contact, name="contact"),
    path("contact/merci/", views.contact_merci, name="contact_merci"),
    path("confidentialite/", views.confidentialite, name="confidentialite"),
    path("robots.txt", views.robots_txt, name="robots"),
]
