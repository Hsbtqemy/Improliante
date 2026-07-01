"""Tests du front public : seules les fiches PUBLIÉES sont visibles (anti-fuite)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.agenda.models import Evenement
from apps.spectacles.models import Spectacle


@pytest.fixture
def publie(db):
    return Spectacle.objects.create(
        titre="SpectaclePublie",
        statut_moderation=Spectacle.StatutModeration.PUBLIE,
    )


@pytest.fixture
def brouillon(db):
    return Spectacle.objects.create(titre="SpectacleBrouillon")


def test_accueil_repond(client, db):
    assert client.get("/").status_code == 200


def test_liste_montre_uniquement_les_publies(client, publie, brouillon):
    reponse = client.get("/spectacles/")
    assert reponse.status_code == 200
    corps = reponse.content.decode()
    assert "SpectaclePublie" in corps
    assert "SpectacleBrouillon" not in corps


def test_detail_publie_accessible(client, publie):
    assert client.get(f"/spectacles/{publie.pk}/").status_code == 200


def test_detail_brouillon_renvoie_404(client, brouillon):
    assert client.get(f"/spectacles/{brouillon.pk}/").status_code == 404


def test_filtre_par_statut_de_projet(client, db):
    Spectacle.objects.create(
        titre="AlphaAffiche",
        statut_moderation=Spectacle.StatutModeration.PUBLIE,
        statut_projet=Spectacle.StatutProjet.A_L_AFFICHE,
    )
    Spectacle.objects.create(
        titre="BetaCreation",
        statut_moderation=Spectacle.StatutModeration.PUBLIE,
        statut_projet=Spectacle.StatutProjet.EN_CREATION,
    )
    corps = client.get("/spectacles/?statut=a_l_affiche").content.decode()
    assert "AlphaAffiche" in corps
    assert "BetaCreation" not in corps


# --- Agenda ---------------------------------------------------------------


def _evenement(titre, *, statut=None, visibilite=None, dans_jours=7):
    return Evenement.objects.create(
        titre=titre,
        date_debut=timezone.now() + timedelta(days=dans_jours),
        statut_moderation=statut or Evenement.StatutModeration.PUBLIE,
        visibilite=visibilite or Evenement.Visibilite.PUBLIC,
    )


def test_agenda_liste_montre_publics_futurs(client, db):
    _evenement("ConcertPublic")
    _evenement("ReunionInterne", visibilite=Evenement.Visibilite.INTERNE)
    _evenement("EvenementBrouillon", statut=Evenement.StatutModeration.BROUILLON)
    corps = client.get("/agenda/?vue=liste").content.decode()
    assert "ConcertPublic" in corps
    assert "ReunionInterne" not in corps
    assert "EvenementBrouillon" not in corps


def test_agenda_calendrier_repond(client, db):
    assert client.get("/agenda/?vue=calendrier").status_code == 200


def test_agenda_memorise_la_vue(client, db):
    reponse = client.get("/agenda/?vue=calendrier")
    assert reponse.cookies["agenda_vue"].value == "calendrier"


def test_export_ical(client, db):
    _evenement("Fête, musique")
    reponse = client.get("/agenda/agenda.ics")
    assert reponse.status_code == 200
    assert reponse["Content-Type"].startswith("text/calendar")
    corps = reponse.content.decode()
    assert "BEGIN:VCALENDAR" in corps
    assert "BEGIN:VEVENT" in corps
    assert "SUMMARY:Fête\\, musique" in corps


def test_ical_exclut_les_non_publics(client, db):
    _evenement("PublicOui")
    _evenement("InterneNon", visibilite=Evenement.Visibilite.INTERNE)
    corps = client.get("/agenda/agenda.ics").content.decode()
    assert "PublicOui" in corps
    assert "InterneNon" not in corps
