"""Tests du front public : seules les fiches PUBLIÉES sont visibles (anti-fuite)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from django.utils.timezone import make_aware

from apps.agenda import services as agenda_services
from apps.agenda.models import Evenement, Inscription
from apps.coeur.models import LienReseau, Lieu, Membre, Utilisateur
from apps.medias.models import Media
from apps.spectacles.models import ImageSpectacle, LigneDistribution, Spectacle
from apps.vitrine.models import MessageContact
from apps.vitrine.views import handle_bluesky


def _bloc_json_ld(corps: str):
    """Contenu du premier <script type="application/ld+json"> d'une page, désérialisé."""
    motif = r'<script type="application/ld\+json">(.*?)</script>'
    trouve = re.search(motif, corps, re.DOTALL)
    return json.loads(trouve.group(1)) if trouve else None


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


# --- Association / membres ------------------------------------------------


def _membre(nom, *, visible=True):
    user = Utilisateur.objects.create(username=nom.lower(), last_name=nom)
    return Membre.objects.create(user=user, nom=nom, visible_sur_site=visible)


def test_association_montre_uniquement_les_membres_visibles(client, db):
    _membre("MembreVisible", visible=True)
    _membre("MembreCache", visible=False)
    corps = client.get("/association/").content.decode()
    assert "MembreVisible" in corps
    assert "MembreCache" not in corps


def test_association_affiche_vedette_et_grille(client, db):
    _membre("MembreA", visible=True)
    reponse = client.get("/association/")
    corps = reponse.content.decode()
    assert "À la une" in corps  # section vedette (accordéon)
    assert "Tous les membres" in corps  # grille exhaustive
    assert "MembreA" in corps
    assert all(m.visible_sur_site for m in reponse.context["vedette"])


def test_association_montre_les_projets_en_cours_des_membres(client, db):
    membre = _membre("MembrePorteur", visible=True)
    projet = Spectacle.objects.create(
        titre="MonProjetPerso",
        statut_moderation=Spectacle.StatutModeration.PUBLIE,
        type_portage=Spectacle.TypePortage.PERSONNEL,
        statut_projet=Spectacle.StatutProjet.EN_REPETITION,
    )
    projet.porteurs.add(membre)
    # Un projet archivé ou non publié ne doit PAS apparaître sur les cartes.
    archive = Spectacle.objects.create(
        titre="ProjetArchive",
        statut_moderation=Spectacle.StatutModeration.PUBLIE,
        statut_projet=Spectacle.StatutProjet.ARCHIVE,
    )
    archive.porteurs.add(membre)
    brouillon = Spectacle.objects.create(titre="ProjetBrouillon")  # non publié
    brouillon.porteurs.add(membre)

    corps = client.get("/association/").content.decode()
    assert "MonProjetPerso" in corps
    assert "carte-membre__tag--personnel" in corps  # étiquette « Projet perso »
    assert "ProjetArchive" not in corps
    assert "ProjetBrouillon" not in corps


def test_membre_detail_404_si_non_visible(client, db):
    membre = _membre("Secret", visible=False)
    assert client.get(f"/membres/{membre.pk}/").status_code == 404


def test_membre_detail_liste_ses_projets(client, db):
    membre = _membre("Porteuse", visible=True)
    spectacle = Spectacle.objects.create(
        titre="ProjetDuMembre", statut_moderation=Spectacle.StatutModeration.PUBLIE
    )
    spectacle.porteurs.add(membre)
    corps = client.get(f"/membres/{membre.pk}/").content.decode()
    assert "ProjetDuMembre" in corps


def test_membre_detail_separe_spectacles_et_collaborations(client, db):
    """Un spectacle porté va dans « Spectacles » ; une simple ligne de distribution
    (ex. mise en scène) sans être porteur va dans « Collaborations »."""
    membre = _membre("Artiste", visible=True)
    porte = Spectacle.objects.create(
        titre="SpectaclePorte", statut_moderation=Spectacle.StatutModeration.PUBLIE
    )
    porte.porteurs.add(membre)
    collab = Spectacle.objects.create(
        titre="SpectacleCollab",
        statut_moderation=Spectacle.StatutModeration.PUBLIE,
    )
    LigneDistribution.objects.create(spectacle=collab, membre=membre, role="Mise en scène")

    reponse = client.get(f"/membres/{membre.pk}/")
    corps = reponse.content.decode()
    assert "Spectacles" in corps and "Collaborations" in corps
    assert list(reponse.context["spectacles_portes"]) == [porte]
    assert list(reponse.context["collaborations"]) == [collab]


def test_handle_bluesky_extrait_le_handle():
    assert handle_bluesky("https://bsky.app/profile/alice.bsky.social") == "alice.bsky.social"
    assert handle_bluesky("https://bsky.app/profile/alice.bsky.social/") == "alice.bsky.social"
    assert handle_bluesky("@alice.bsky.social") == "alice.bsky.social"
    assert handle_bluesky("") == ""


def test_fiche_membre_propose_bluesky_au_clic(client, db):
    membre = _membre("AvecBsky", visible=True)
    LienReseau.objects.create(
        membre=membre,
        reseau=LienReseau.Reseau.BLUESKY,
        url="https://bsky.app/profile/artiste.bsky.social",
    )
    reponse = client.get(f"/membres/{membre.pk}/")
    corps = reponse.content.decode()
    assert reponse.context["bluesky_handle"] == "artiste.bsky.social"
    assert 'data-bluesky-handle="artiste.bsky.social"' in corps
    assert "Voir les derniers posts" in corps  # bouton click-to-load
    # RGPD : aucune requête vers Bluesky dans le HTML initial (chargement au clic).
    assert "public.api.bsky.app" not in corps


def test_fiche_membre_sans_bluesky_pas_d_encart(client, db):
    membre = _membre("SansBsky", visible=True)
    reponse = client.get(f"/membres/{membre.pk}/")
    assert reponse.context["bluesky_handle"] == ""
    assert "bluesky-feed" not in reponse.content.decode()


def test_accueil_affiche_instagram_si_configure(client, db):
    faux = [
        {
            "id": "1",
            "image": "https://cdn/x.jpg",
            "permalink": "https://insta/p/1",
            "legende": "Salut",
        }
    ]
    with patch("apps.vitrine.views.derniers_posts_instagram", return_value=faux):
        corps = client.get("/").content.decode()
    assert "Suivez-nous sur Instagram" in corps
    assert "https://insta/p/1" in corps


def test_accueil_sans_instagram_pas_de_section(client, db):
    with patch("apps.vitrine.views.derniers_posts_instagram", return_value=[]):
        corps = client.get("/").content.decode()
    assert "Suivez-nous sur Instagram" not in corps


def test_membre_detail_affiche_site_et_reseaux(client, db):
    membre = _membre("Reliee", visible=True)
    membre.site_web = "https://reliee.example"
    membre.save()
    LienReseau.objects.create(
        membre=membre, reseau=LienReseau.Reseau.INSTAGRAM, url="https://instagram.com/reliee"
    )
    corps = client.get(f"/membres/{membre.pk}/").content.decode()
    assert "https://reliee.example" in corps
    assert "https://instagram.com/reliee" in corps
    assert "Instagram" in corps


# --- Galerie --------------------------------------------------------------


def _media_video(alt):
    return Media.objects.create(
        alt=alt, type_media=Media.TypeMedia.VIDEO, url_externe="https://youtu.be/x"
    )


def test_galerie_montre_medias_des_spectacles_publies(client, db):
    publie = Spectacle.objects.create(
        titre="SpecPub", statut_moderation=Spectacle.StatutModeration.PUBLIE
    )
    brouillon = Spectacle.objects.create(titre="SpecBrouillon")
    ImageSpectacle.objects.create(spectacle=publie, media=_media_video("VideoPubliee"))
    ImageSpectacle.objects.create(spectacle=brouillon, media=_media_video("VideoBrouillon"))
    corps = client.get("/galerie/").content.decode()
    assert "VideoPubliee" in corps
    assert "VideoBrouillon" not in corps


# --- Contact --------------------------------------------------------------


def test_contact_get_affiche_le_formulaire(client, db):
    reponse = client.get("/contact/")
    assert reponse.status_code == 200
    assert "formulaire" in reponse.content.decode()


def test_contact_post_valide_enregistre_le_message(client, db):
    donnees = {
        "nom": "Alice",
        "email": "alice@example.org",
        "sujet": "Bonjour",
        "message": "Un message de test.",
        "consentement": "on",
        "site_web": "",
    }
    reponse = client.post("/contact/", donnees)
    assert reponse.status_code == 302  # PRG vers la page de remerciement
    message = MessageContact.objects.get()
    assert message.nom == "Alice"
    assert message.consentement is True
    assert message.date_consentement is not None


def test_contact_sans_consentement_est_rejete(client, db):
    donnees = {
        "nom": "Bob",
        "email": "bob@example.org",
        "message": "Coucou",
        "site_web": "",
    }
    reponse = client.post("/contact/", donnees)
    assert reponse.status_code == 200  # le formulaire est réaffiché
    assert MessageContact.objects.count() == 0


def test_contact_honeypot_bloque_le_spam(client, db):
    donnees = {
        "nom": "Spam",
        "email": "spam@example.org",
        "message": "Achetez ceci",
        "consentement": "on",
        "site_web": "http://spam.example",
    }
    reponse = client.post("/contact/", donnees)
    assert reponse.status_code == 200
    assert MessageContact.objects.count() == 0


# --- Accessibilité --------------------------------------------------------


def test_panneau_accessibilite_present(client, db):
    corps = client.get("/").content.decode()
    assert 'id="a11y-bouton"' in corps


def test_preferences_accessibilite_appliquees_via_cookie(client, db):
    client.cookies["a11y"] = "sombre txt-grand"
    corps = client.get("/").content.decode()
    assert 'class="sombre txt-grand"' in corps


# --- Détail d'un événement (page partageable) -----------------------------


def test_detail_evenement_public_accessible(client, db):
    evt = _evenement("SoireePublique")
    reponse = client.get(f"/agenda/{evt.pk}/")
    assert reponse.status_code == 200
    assert "SoireePublique" in reponse.content.decode()


def test_detail_evenement_interne_renvoie_404(client, db):
    evt = _evenement("HuisClos", visibilite=Evenement.Visibilite.INTERNE)
    assert client.get(f"/agenda/{evt.pk}/").status_code == 404


def test_detail_evenement_brouillon_renvoie_404(client, db):
    evt = _evenement("Ebauche", statut=Evenement.StatutModeration.BROUILLON)
    assert client.get(f"/agenda/{evt.pk}/").status_code == 404


def test_agenda_liste_lie_chaque_evenement_a_sa_fiche(client, db):
    evt = _evenement("ConcertLie")
    corps = client.get("/agenda/?vue=liste").content.decode()
    assert f'href="/agenda/{evt.pk}/"' in corps


# --- Métadonnées de partage (Open Graph) et données structurées (JSON-LD) --


def test_spectacle_expose_open_graph_et_canonical(client, publie):
    corps = client.get(f"/spectacles/{publie.pk}/").content.decode()
    assert '<meta property="og:type" content="article"' in corps
    assert '<meta property="og:title" content="SpectaclePublie"' in corps
    assert f'<link rel="canonical" href="http://testserver/spectacles/{publie.pk}/"' in corps


def test_spectacle_expose_json_ld_creativework(client, publie):
    corps = client.get(f"/spectacles/{publie.pk}/").content.decode()
    donnees = _bloc_json_ld(corps)
    assert donnees["@type"] == "CreativeWork"
    assert donnees["name"] == "SpectaclePublie"


def test_evenement_expose_json_ld_theaterevent(client, db):
    lieu = Lieu.objects.create(nom="Théâtre du Coin", ville="Lyon")
    evt = Evenement.objects.create(
        titre="Représentation",
        date_debut=timezone.now() + timedelta(days=3),
        lieu=lieu,
        statut_moderation=Evenement.StatutModeration.PUBLIE,
        visibilite=Evenement.Visibilite.PUBLIC,
    )
    donnees = _bloc_json_ld(client.get(f"/agenda/{evt.pk}/").content.decode())
    assert donnees["@type"] == "TheaterEvent"
    assert donnees["location"]["name"] == "Théâtre du Coin"
    assert donnees["startDate"].startswith(str(timezone.localtime(evt.date_debut).year))


def test_json_ld_neutralise_une_injection_de_script(client, db):
    """Un titre malicieux ne doit pas fermer prématurément la balise <script>."""
    evt = Evenement.objects.create(
        titre="Piège</script><img src=x>",
        date_debut=timezone.now() + timedelta(days=1),
        statut_moderation=Evenement.StatutModeration.PUBLIE,
        visibilite=Evenement.Visibilite.PUBLIC,
    )
    corps = client.get(f"/agenda/{evt.pk}/").content.decode()
    brut = re.search(r'<script type="application/ld\+json">(.*?)</script>', corps, re.DOTALL)
    # Le </script> injecté est échappé : le bloc capturé ne contient aucune
    # balise fermante brute, et reste un JSON valide portant le titre complet.
    assert "</script>" not in brut.group(1)
    assert "\\u003C/script\\u003E" in brut.group(1)
    assert json.loads(brut.group(1))["name"] == "Piège</script><img src=x>"


# --- Plan du site (sitemap.xml) et robots.txt -----------------------------


def test_sitemap_liste_le_publie_pas_le_brouillon(client, publie, brouillon):
    corps = client.get("/sitemap.xml").content.decode()
    assert client.get("/sitemap.xml").status_code == 200
    assert f"/spectacles/{publie.pk}/" in corps
    assert f"/spectacles/{brouillon.pk}/" not in corps


def test_sitemap_exclut_evenements_non_publics_et_membres_caches(client, db):
    public = _evenement("EvtPublicSitemap")
    interne = _evenement("EvtInterneSitemap", visibilite=Evenement.Visibilite.INTERNE)
    visible = _membre("MembreSitemapVisible", visible=True)
    cache = _membre("MembreSitemapCache", visible=False)
    corps = client.get("/sitemap.xml").content.decode()
    assert f"/agenda/{public.pk}/" in corps
    assert f"/agenda/{interne.pk}/" not in corps
    assert f"/membres/{visible.pk}/" in corps
    assert f"/membres/{cache.pk}/" not in corps


def test_robots_txt_pointe_le_sitemap_et_protege_le_prive(client, db):
    reponse = client.get("/robots.txt")
    assert reponse.status_code == 200
    assert reponse["Content-Type"].startswith("text/plain")
    corps = reponse.content.decode()
    assert "Sitemap: http://testserver/sitemap.xml" in corps
    assert "Disallow: /bureau/" in corps
    assert "Disallow: /espace/" in corps


# --- Page d'erreur 404 sur-mesure ------------------------------------------


@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
def test_page_404_personnalisee(client, db):
    """Hors DEBUG, une URL inconnue rend la 404 sur-mesure (pas la page Django brute)."""
    reponse = client.get("/une-page-qui-nexiste-pas/")
    assert reponse.status_code == 404
    corps = reponse.content.decode()
    assert "introuvable" in corps.lower()
    assert "Retour à l'accueil" in corps


# --- Inscription du public à un événement (VIT-2) ----------------------------


def _evenement_avec_jauge(places_max=10, **extra):
    donnees = {
        "titre": "Représentation",
        "date_debut": make_aware(datetime(2026, 11, 1, 20, 0)),
        "places_max": places_max,
        "statut_moderation": Evenement.StatutModeration.PUBLIE,
        "visibilite": Evenement.Visibilite.PUBLIC,
    }
    donnees.update(extra)
    return Evenement.objects.create(**donnees)


def _reservation_valide(places=2):
    return {
        "nom": "Camille Martin",
        "email": "camille@example.org",
        "places": places,
        "consentement": "on",
    }


def test_un_evenement_sans_jauge_n_ouvre_pas_d_inscription(client, db):
    evenement = _evenement_avec_jauge(places_max=None)
    assert client.get(f"/agenda/{evenement.pk}/inscription/").status_code == 404


def test_un_evenement_non_publie_n_accueille_personne(client, db):
    """La feuille d'inscription ne doit pas devenir une porte vers une fiche
    que la vitrine refuse d'afficher."""
    brouillon = _evenement_avec_jauge(statut_moderation=Evenement.StatutModeration.BROUILLON)
    interne = _evenement_avec_jauge(visibilite=Evenement.Visibilite.MEMBRES)

    assert client.get(f"/agenda/{brouillon.pk}/inscription/").status_code == 404
    assert client.get(f"/agenda/{interne.pk}/inscription/").status_code == 404


def test_le_public_reserve_et_recoit_son_lien(client, db):
    evenement = _evenement_avec_jauge(places_max=10)

    reponse = client.post(f"/agenda/{evenement.pk}/inscription/", _reservation_valide(places=2))

    inscription = Inscription.objects.get()
    assert reponse.status_code == 302
    assert reponse.url == f"/reservation/{inscription.jeton}/"
    assert inscription.places == 2


def test_la_reservation_se_retrouve_par_son_jeton_sans_compte(client, db):
    """Ce que la fiche VIT-2 demandait : consultable par son porteur sans
    compte, par un lien qu'aucun autre ne peut deviner."""
    evenement = _evenement_avec_jauge()
    client.post(f"/agenda/{evenement.pk}/inscription/", _reservation_valide())
    inscription = Inscription.objects.get()

    reponse = client.get(f"/reservation/{inscription.jeton}/")

    assert reponse.status_code == 200
    assert "Camille Martin" in reponse.content.decode()


def test_un_jeton_inconnu_ne_donne_rien(client, db):
    assert client.get("/reservation/11111111-1111-1111-1111-111111111111/").status_code == 404


def test_la_reservation_ne_s_atteint_pas_par_son_identifiant(client, db):
    """Le jeton n'est pas une commodité : c'est ce qui empêche de parcourir les
    réservations en incrémentant un nombre."""
    evenement = _evenement_avec_jauge()
    client.post(f"/agenda/{evenement.pk}/inscription/", _reservation_valide())
    inscription = Inscription.objects.get()

    assert client.get(f"/reservation/{inscription.pk}/").status_code == 404


def test_le_porteur_annule_sa_reservation_et_rend_les_places(client, db):
    evenement = _evenement_avec_jauge(places_max=5)
    client.post(f"/agenda/{evenement.pk}/inscription/", _reservation_valide(places=5))
    inscription = Inscription.objects.get()

    reponse = client.post(f"/reservation/{inscription.jeton}/")

    assert reponse.status_code == 302
    inscription.refresh_from_db()
    assert inscription.annulee is True
    assert agenda_services.places_restantes(evenement) == 5


def test_une_demande_qui_depasse_la_jauge_est_refusee_avec_un_message(client, db):
    """La jauge peut se remplir entre l'affichage et l'envoi : l'écran doit le
    dire, pas rendre une erreur serveur."""
    evenement = _evenement_avec_jauge(places_max=3)
    agenda_services.inscrire(evenement, nom="Déjà là", email="d@example.org", places=3)

    reponse = client.post(f"/agenda/{evenement.pk}/inscription/", _reservation_valide(places=1))

    assert reponse.status_code == 200
    assert "complet" in reponse.content.decode().lower()
    assert Inscription.objects.count() == 1


def test_le_consentement_est_obligatoire(client, db):
    evenement = _evenement_avec_jauge()
    donnees = _reservation_valide()
    del donnees["consentement"]

    reponse = client.post(f"/agenda/{evenement.pk}/inscription/", donnees)

    assert reponse.status_code == 200
    assert Inscription.objects.count() == 0


def test_le_piege_anti_spam_bloque_l_inscription(client, db):
    evenement = _evenement_avec_jauge()
    donnees = _reservation_valide() | {"site_web": "http://spam.example"}

    client.post(f"/agenda/{evenement.pk}/inscription/", donnees)

    assert Inscription.objects.count() == 0


def test_la_fiche_evenement_annonce_les_places_et_mene_a_la_reservation(client, db):
    evenement = _evenement_avec_jauge(places_max=12)

    corps = client.get(f"/agenda/{evenement.pk}/").content.decode()

    assert f"/agenda/{evenement.pk}/inscription/" in corps
    assert "12" in corps


def test_la_fiche_d_un_evenement_complet_le_dit_sans_proposer_de_reserver(client, db):
    evenement = _evenement_avec_jauge(places_max=2)
    agenda_services.inscrire(evenement, nom="Déjà là", email="d@example.org", places=2)

    corps = client.get(f"/agenda/{evenement.pk}/").content.decode()

    assert "Complet" in corps
    assert f"/agenda/{evenement.pk}/inscription/" not in corps


def test_un_evenement_sans_jauge_n_affiche_aucune_mention_de_place(client, db):
    evenement = _evenement_avec_jauge(places_max=None)

    corps = client.get(f"/agenda/{evenement.pk}/").content.decode()

    assert "Réserver ma place" not in corps
    assert "Complet" not in corps
