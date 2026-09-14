"""Tests du front public : seules les fiches PUBLIÉES sont visibles (anti-fuite)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from django.utils.html import escape
from django.utils.timezone import make_aware

from apps.agenda import services as agenda_services
from apps.agenda.models import Evenement, Inscription, Intervention
from apps.coeur.models import (
    LienReseau,
    Lieu,
    Membre,
    ParametresAssociation,
    Utilisateur,
)
from apps.coeur.services import identifiant_youtube
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


@pytest.mark.parametrize("annee", ["0", "-3", "9999", "100000"])
def test_agenda_calendrier_annee_hors_plage_ne_plante_pas(client, db, annee):
    """Une année forgée dans l'URL faisait lever `date()` ou le calcul du mois
    voisin : erreur 500. On retombe sur le mois courant."""
    reponse = client.get(f"/agenda/?vue=calendrier&annee={annee}&mois=12")
    assert reponse.status_code == 200


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
    """Ni la nouvelle adresse ni l'ancienne ne doivent révéler une fiche cachée."""
    membre = _membre("Secret", visible=False)
    assert client.get(membre.get_absolute_url()).status_code == 404
    assert client.get(membre.get_absolute_url()).status_code == 404


def test_ancienne_adresse_membre_redirige_en_permanent(client, db):
    """`/membres/<id>/` a circulé : elle mène toujours à la fiche, en 301."""
    membre = _membre("Deplacee", visible=True)
    reponse = client.get(f"/membres/{membre.pk}/")
    assert reponse.status_code == 301
    assert reponse["Location"] == f"/@{membre.slug}/"
    assert client.get(reponse["Location"]).status_code == 200


def test_adresse_de_fiche_membre_est_un_arobase(client, db):
    membre = _membre("Publique", visible=True)
    assert membre.get_absolute_url() == "/@publique/"


def test_membre_detail_liste_ses_projets(client, db):
    membre = _membre("Porteuse", visible=True)
    spectacle = Spectacle.objects.create(
        titre="ProjetDuMembre", statut_moderation=Spectacle.StatutModeration.PUBLIE
    )
    spectacle.porteurs.add(membre)
    corps = client.get(membre.get_absolute_url()).content.decode()
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

    reponse = client.get(membre.get_absolute_url())
    corps = reponse.content.decode()
    assert "Spectacles" in corps and "Collaborations" in corps
    assert list(reponse.context["spectacles_portes"]) == [porte]
    assert list(reponse.context["collaborations"]) == [collab]


def test_handle_bluesky_extrait_le_handle():
    assert handle_bluesky("https://bsky.app/profile/alice.bsky.social") == "alice.bsky.social"
    assert handle_bluesky("https://bsky.app/profile/alice.bsky.social/") == "alice.bsky.social"
    assert handle_bluesky("@alice.bsky.social") == "alice.bsky.social"
    assert handle_bluesky("") == ""


# --- Vidéo au clic (VIT-4) --------------------------------------------------

# Les `rel` qui font PARTIR une requête au chargement. `noopener`, `noreferrer`
# ou `canonical` n'en font aucune : les confondre reviendrait à interdire un
# lien ordinaire.
_REL_QUI_CHARGE = frozenset(
    {"preconnect", "dns-prefetch", "preload", "prefetch", "stylesheet", "modulepreload"}
)
# « youtube » et non « youtube.com » : le domaine sans cookie s'appelle
# `youtube-nocookie.com`, et c'est justement celui qu'un lecteur intégré emploie.
# Écrite avec le point, la liste laissait passer le cadre qu'elle existe pour
# refuser — une sonde l'a montré.
_HOTES_DU_FOURNISSEUR = ("youtube", "youtu.be", "ytimg", "googlevideo")


def _ressources_distantes(html: str) -> list[str]:
    """Les adresses que le navigateur ira chercher SEUL en rendant cette page.

    On ne cherche pas « le mot youtube dans le HTML » : un `<a href>` vers
    YouTube ne déclenche aucune requête, et l'interdire retirerait le seul
    recours de qui n'a pas JavaScript. Ce qui part tout seul, c'est un `src`,
    un `srcset`, un `poster`, et les `<link>` qui préconnectent ou préchargent.
    """
    import re

    adresses = []
    for balise in re.findall(r"<[a-zA-Z][^>]*>", html):
        nom = re.match(r"<([a-zA-Z0-9]+)", balise).group(1).lower()
        if nom == "link":
            rel = re.search(r'\brel="([^"]*)"', balise)
            href = re.search(r'\bhref="([^"]*)"', balise)
            if rel and href and set(rel.group(1).lower().split()) & _REL_QUI_CHARGE:
                adresses.append(href.group(1))
            continue
        for attribut in ("src", "srcset", "poster"):
            trouve = re.search(rf'\b{attribut}="([^"]*)"', balise)
            if trouve:
                # `srcset` porte plusieurs candidats séparés par des virgules,
                # chacun suivi de son descripteur de largeur.
                adresses += [c.strip().split(" ")[0] for c in trouve.group(1).split(",")]
    return [a for a in adresses if a]


def _membre_avec_video(nom="AvecVideo", identifiant="dQw4w9WgXcQ"):
    membre = _membre(nom, visible=True)
    membre.video_youtube = identifiant
    membre.video_titre = "Extrait du spectacle"
    membre.video_texte = "Trois minutes de la création 2026."
    membre.save(update_fields=["video_youtube", "video_titre", "video_texte"])
    return membre


# --- Limitation de débit des formulaires publics (PUB-01) -------------------


def _message_de_contact(client, **extra):
    donnees = {
        "nom": "Camille",
        "email": "camille@example.org",
        "sujet": "Bonjour",
        "message": "Une question sur la saison.",
        "consentement": "on",
    }
    donnees.update(extra)
    return client.post("/contact/", donnees)


def test_le_contact_refuse_au_dela_de_la_limite(client, db, settings):
    """Le champ piège arrête un robot naïf ; il n'arrête pas la répétition."""
    from apps.vitrine.models import MessageContact

    settings.DEBIT_CONTACT = (3, 3600)

    for _ in range(3):
        assert _message_de_contact(client).status_code == 302  # accepté, redirigé

    refus = _message_de_contact(client)

    assert refus.status_code == 200  # réaffiché, pas redirigé
    assert escape("Trop d'envois depuis cette connexion") in refus.content.decode()
    assert MessageContact.objects.count() == 3


def test_un_en_tete_forge_ne_rouvre_pas_la_limite_du_contact(client, db, settings):
    """L'attaquant contrôle `X-Forwarded-For`. Sans relais déclaré, on l'ignore.

    C'est le contrôle qui donne son sens à tous les autres : une limite qu'un
    en-tête desserre n'est pas une limite.
    """
    from apps.vitrine.models import MessageContact

    settings.DEBIT_CONTACT = (2, 3600)
    settings.PROXIES_DE_CONFIANCE = 0

    _message_de_contact(client)
    _message_de_contact(client, HTTP_X_FORWARDED_FOR="198.51.100.1")
    refus = _message_de_contact(client, HTTP_X_FORWARDED_FOR="198.51.100.2")

    assert refus.status_code == 200
    assert MessageContact.objects.count() == 2


def test_une_saisie_ratee_ne_consomme_pas_la_part(client, db, settings):
    """On limite l'EFFET, pas la maladresse : six erreurs d'adresse d'affilée
    ne doivent pas fermer le formulaire à quelqu'un qui n'a rien envoyé."""
    from apps.vitrine.models import MessageContact

    settings.DEBIT_CONTACT = (2, 3600)

    for _ in range(6):
        _message_de_contact(client, email="pas-une-adresse")

    assert _message_de_contact(client).status_code == 302
    assert MessageContact.objects.count() == 1


def test_le_message_de_contact_est_borne(client, db):
    """Un champ sans borne est une zone de dépôt (constat PUB-01)."""
    # Le réglage est lu à l'import : le changer ici ne changerait rien, et la
    # ligne qui le faisait ne regardait rien. On éprouve la borne RÉELLEMENT
    # posée, quelle qu'elle soit.
    from apps.vitrine.forms import ContactForm
    from apps.vitrine.models import MessageContact

    borne = ContactForm().fields["message"].max_length
    assert borne, "aucune borne posée sur le message"

    reponse = _message_de_contact(client, message="x" * (borne + 1))

    assert reponse.status_code == 200
    assert MessageContact.objects.count() == 0


def test_identifiant_youtube_reconnait_les_formes_d_adresse():
    attendu = "dQw4w9WgXcQ"
    for saisie in (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?si=abc",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        "  dQw4w9WgXcQ  ",
    ):
        assert identifiant_youtube(saisie) == attendu, saisie


def test_identifiant_youtube_refuse_ce_qui_n_est_pas_une_video_youtube():
    for saisie in (
        "",
        "   ",
        "https://vimeo.com/76979871",
        # L'hôte se compare en ENTIER : ces deux-là contiennent « youtube.com »
        # et ne sont pas YouTube. Un contrôle par sous-chaîne les accepterait.
        "https://youtube.com.ailleurs.test/watch?v=dQw4w9WgXcQ",
        "https://ailleurs.test/watch?v=dQw4w9WgXcQ&h=youtube.com",
        # Sans hôte : leur laisser le bénéfice du doute mettrait du script
        # exécutable dans un attribut de lien.
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "//www.youtube.com/watch?v=dQw4w9WgXcQ",
        # Bonne maison, pas de vidéo.
        "https://www.youtube.com/",
        "https://www.youtube.com/watch?v=trop-court",
        "https://www.youtube.com/watch?v=beaucoup-trop-long-pour-un-id",
    ):
        assert identifiant_youtube(saisie) == "", saisie


def test_la_fiche_artiste_ne_demande_rien_a_youtube_avant_le_clic(client, db):
    """La façade est un LIEN, pas un cadre : la page ne charge rien du fournisseur.

    Le piège de ce motif est la vignette. Prise sur `i.ytimg.com`, comme le font
    la plupart des « lecteurs au clic », elle EST la requête qu'on prétend
    refuser — et elle part au chargement, avant tout clic. D'où un contrôle qui
    regarde les attributs qui déclenchent une requête, et non la présence du mot.
    """
    membre = _membre_avec_video()
    corps = client.get(membre.get_absolute_url()).content.decode()

    # Témoin : sans la façade rendue, tout ce qui suit passerait en ne regardant rien.
    assert "video-clic__facade" in corps, "la façade n'est pas rendue"

    fautives = [
        adresse
        for adresse in _ressources_distantes(corps)
        if any(hote in adresse for hote in _HOTES_DU_FOURNISSEUR)
    ]
    assert not fautives, "ressources chargées depuis le fournisseur : " + ", ".join(fautives)
    # Ces deux hôtes-là ne servent QUE des ressources : les voir où que ce soit
    # dans la page, fût-ce dans un attribut qu'on n'a pas prévu, est un défaut.
    assert "ytimg" not in corps
    assert "googlevideo" not in corps


def test_la_facade_video_reste_un_lien_quand_le_script_ne_tourne_pas(client, db):
    """Un `<button>` sans JavaScript est un bouton mort, et rien ne le dit.

    Le visiteur sans script doit pouvoir atteindre la vidéo : le lien l'y mène
    chez YouTube. C'est le script qui, s'il tourne, intercepte le clic.
    """
    membre = _membre_avec_video()
    corps = client.get(membre.get_absolute_url()).content.decode()
    assert 'href="https://www.youtube.com/watch?v=dQw4w9WgXcQ"' in corps
    # Le nom accessible du lien nomme la vidéo : « Lire la vidéo » seul ne dit
    # pas laquelle, et une page peut en porter plusieurs demain.
    assert "Lire la vidéo : Extrait du spectacle" in corps


def _image_temoin_vitrine(nom: str):
    """Une vraie image, assez large pour qu'une vignette et un `srcset` existent."""
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (1200, 800), (60, 90, 120)).save(tampon, "JPEG")
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type="image/jpeg")


def test_la_facade_video_porte_la_couverture_quand_il_y_en_a_une(client, db):
    """Et elle reste une façade : l'image est la NÔTRE, servie par nous.

    C'est tout l'intérêt d'une couverture choisie plutôt que de la vignette
    officielle : celle-ci vit sur `i.ytimg.com` et serait la requête que ce
    bloc existe pour refuser.
    """
    from apps.medias.models import Media

    membre = _membre_avec_video("AvecCouverture")
    membre.video_couverture = Media.objects.create(
        fichier=_image_temoin_vitrine("couv.jpg"), alt="Couverture témoin"
    )
    membre.save(update_fields=["video_couverture"])

    corps = client.get(membre.get_absolute_url()).content.decode()

    assert "video-clic__facade--couverte" in corps
    assert "Couverture témoin" in corps
    fautives = [
        adresse
        for adresse in _ressources_distantes(corps)
        if any(hote in adresse for hote in _HOTES_DU_FOURNISSEUR)
    ]
    assert not fautives, "la couverture a fait revenir une requête au fournisseur"


def test_sans_couverture_la_facade_reste_typographique(client, db):
    membre = _membre_avec_video("SansCouverture")
    corps = client.get(membre.get_absolute_url()).content.decode()
    assert "video-clic__facade" in corps
    assert "video-clic__facade--couverte" not in corps


def test_sans_video_la_fiche_ne_porte_pas_la_facade(client, db):
    membre = _membre("SansVideo", visible=True)
    corps = client.get(membre.get_absolute_url()).content.decode()
    assert "video-clic" not in corps


def test_fiche_membre_propose_bluesky_au_clic(client, db):
    membre = _membre("AvecBsky", visible=True)
    LienReseau.objects.create(
        membre=membre,
        reseau=LienReseau.Reseau.BLUESKY,
        url="https://bsky.app/profile/artiste.bsky.social",
    )
    reponse = client.get(membre.get_absolute_url())
    corps = reponse.content.decode()
    assert reponse.context["bluesky_handle"] == "artiste.bsky.social"
    assert 'data-bluesky-handle="artiste.bsky.social"' in corps
    assert "Voir les derniers posts" in corps  # bouton click-to-load
    # RGPD : aucune requête vers Bluesky dans le HTML initial (chargement au clic).
    assert "public.api.bsky.app" not in corps


def test_fiche_membre_sans_bluesky_pas_d_encart(client, db):
    membre = _membre("SansBsky", visible=True)
    reponse = client.get(membre.get_absolute_url())
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
    corps = client.get(membre.get_absolute_url()).content.decode()
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


# --- Budget de requêtes et volume des pages (PERF-01) ----------------------
#
# L'assertion porte sur la CROISSANCE, jamais sur un total : un total se périme
# au premier `select_related` ajouté ailleurs et ne dirait plus rien, alors que
# « le nombre de requêtes ne suit pas le nombre de spectacles » reste vrai quoi
# qu'on ajoute autour.


def _requetes(client, url) -> int:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as capture:
        client.get(url)
    return len(capture.captured_queries)


def _spectacles_affiches(nombre, debut=0):
    """`nombre` spectacles publiés, chacun avec son affiche (une carte = une image)."""
    for i in range(debut, debut + nombre):
        Spectacle.objects.create(
            titre=f"Spectacle {i}",
            statut_moderation=Spectacle.StatutModeration.PUBLIE,
            statut_projet=Spectacle.StatutProjet.A_L_AFFICHE,
            affiche=Media.objects.create(fichier=f"medias/aff{i}.jpg", alt=f"Affiche {i}"),
        )


def test_la_liste_des_spectacles_ne_suit_pas_le_nombre_d_affiches(client, db):
    """Le N+1 que l'audit avait mesuré : huit spectacles, neuf requêtes SQL —
    une pour la liste, une par affiche, parce que la carte montre l'image."""
    _spectacles_affiches(3)
    client.get("/spectacles/")  # 1re passe : cache des gabarits

    trois = _requetes(client, "/spectacles/")
    _spectacles_affiches(9, debut=3)
    douze = _requetes(client, "/spectacles/")

    assert douze == trois, f"{trois} requêtes pour 3 spectacles, {douze} pour 12"


def test_l_accueil_ne_suit_pas_le_nombre_de_spectacles(client, db):
    """Même motif sur la page la plus vue du site. Les deux listes y sont
    bornées à six, donc le défaut ne grossissait pas à l'infini — il coûtait
    quand même douze requêtes inutiles à chaque visite."""
    with patch("apps.vitrine.views.derniers_posts_instagram", return_value=[]):
        _spectacles_affiches(3)
        client.get("/")

        trois = _requetes(client, "/")
        _spectacles_affiches(9, debut=3)
        douze = _requetes(client, "/")

    assert douze <= trois, f"{trois} requêtes pour 3 spectacles, {douze} pour 12"


def test_la_page_association_ne_suit_pas_le_nombre_de_membres(client, db):
    """La vedette affiche les liens de réseaux de chaque membre : sans
    préchargement, l'accordéon en demandait un par personne."""
    for i in range(3):
        LienReseau.objects.create(
            membre=_membre(f"Membre{i}"),
            reseau=LienReseau.Reseau.INSTAGRAM,
            url="https://instagram.com/x",
        )
    client.get("/association/")

    trois = _requetes(client, "/association/")
    for i in range(3, 12):
        LienReseau.objects.create(
            membre=_membre(f"Membre{i}"),
            reseau=LienReseau.Reseau.INSTAGRAM,
            url="https://instagram.com/x",
        )
    douze = _requetes(client, "/association/")

    assert douze == trois, f"{trois} requêtes pour 3 membres, {douze} pour 12"


def test_une_carte_propose_la_vignette_et_reserve_sa_place(client, db):
    """La moitié « images » de PERF-01 : une affiche de 2 400 px habillait une
    carte de 300. Le gabarit propose désormais la vignette en `srcset` — avec
    `sizes`, sans quoi le navigateur suppose toute la largeur de l'écran et
    reprend la grande — et donne les dimensions intrinsèques, pour que la place
    soit réservée avant l'arrivée du fichier."""
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (2400, 3200), (10, 120, 200)).save(tampon, "JPEG")
    affiche = Media.objects.create(
        fichier=SimpleUploadedFile("aff.jpg", tampon.getvalue()), alt="Affiche du spectacle"
    )
    Spectacle.objects.create(
        titre="SpecPub",
        statut_moderation=Spectacle.StatutModeration.PUBLIE,
        affiche=affiche,
    )

    corps = client.get("/spectacles/").content.decode()

    affiche.refresh_from_db()
    assert f"{affiche.vignette.url} 600w" in corps
    assert f"{affiche.fichier.url} 2000w" in corps
    assert "sizes=" in corps
    assert 'width="2000" height="2667"' in corps
    assert 'loading="lazy"' in corps


def test_la_galerie_est_paginee(client, db):
    """Elle rassemble les images de TOUS les spectacles et événements publiés :
    sans pagination, une saison de plus et la page servait quelques centaines
    d'images d'un coup."""
    spectacle = Spectacle.objects.create(
        titre="SpecPub", statut_moderation=Spectacle.StatutModeration.PUBLIE
    )
    for i in range(30):
        ImageSpectacle.objects.create(
            spectacle=spectacle,
            media=Media.objects.create(fichier=f"medias/g{i}.jpg", alt=f"Image {i}"),
            ordre=i,
        )

    premiere = client.get("/galerie/")
    corps = premiere.content.decode()

    assert premiere.context["page"].paginator.num_pages == 2
    assert corps.count("<img") == 24
    assert 'class="pagination"' in corps
    assert client.get("/galerie/?page=2").content.decode().count("<img") == 6
    # Un numéro de page absurde ne doit pas casser la page publique.
    assert client.get("/galerie/?page=abc").status_code == 200


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
    assert f"/@{visible.slug}/" in corps
    assert f"/@{cache.slug}/" not in corps


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


def test_la_reservation_refuse_au_dela_de_la_limite(client, db, settings):
    """La jauge n'est plus le seul frein à une succession de réservations.

    Elle reste ce qui fait autorité — le dépôt a écarté un plafond par adresse,
    qui se contourne en changeant d'adresse et gêne un foyer légitime. La
    limite de débit, elle, porte sur l'origine : elle ne rend pas la saturation
    impossible, elle la rend lente.
    """
    evenement = _evenement_avec_jauge(places_max=200)
    settings.DEBIT_RESERVATION = (2, 3600)

    for _ in range(2):
        assert (
            client.post(
                f"/agenda/{evenement.pk}/inscription/", _reservation_valide(places=1)
            ).status_code
            == 302
        )

    refus = client.post(f"/agenda/{evenement.pk}/inscription/", _reservation_valide(places=1))

    assert refus.status_code == 200
    assert escape("Trop d'envois depuis cette connexion") in refus.content.decode()
    assert Inscription.objects.count() == 2


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


def test_le_champ_piege_ne_s_affiche_pas_comme_un_champ_ordinaire(client, db):
    """Rendu dans la boucle des champs, le piège apparaissait à l'écran avec
    son label « Ne pas remplir » — au milieu d'un formulaire public."""
    evenement = _evenement_avec_jauge()

    corps = client.get(f"/agenda/{evenement.pk}/inscription/").content.decode()

    assert 'class="pot-de-miel"' in corps  # conteneur masqué (display: none)
    assert '<p class="champ">\n  <label for="id_site_web"' not in corps


def test_l_ecran_ne_promet_pas_un_e_mail_qui_n_est_pas_envoye(client, db):
    """Aucun envoi n'est implémenté : annoncer « vous recevrez un lien » ferait
    attendre un message qui ne viendrait jamais — et perdre le lien."""
    evenement = _evenement_avec_jauge()

    corps = client.get(f"/agenda/{evenement.pk}/inscription/").content.decode()

    assert "vous recevrez" not in corps.lower()
    assert "renvoyer le lien" not in corps.lower()
    assert "conservez le lien affiché" in corps.lower()


def test_la_reservation_est_confirmee_explicitement(client, db):
    evenement = _evenement_avec_jauge()

    reponse = client.post(
        f"/agenda/{evenement.pk}/inscription/", _reservation_valide(places=2), follow=True
    )

    assert "réservation est confirmée" in reponse.content.decode()


# --- Cohérence des en-têtes de page -----------------------------------------
#
# Trois règles, tenues par les deux tests qui suivent :
#   1. toute page porte un et un seul `<header class="page-tete">` — c'est lui
#      qui fixe la taille du titre, sa place et le filet qui le souligne ;
#   2. le sur-titre nomme la SECTION PARENTE, jamais le site ni la page
#      elle-même (« L'Improliante » au-dessus de « Agenda » ne disait rien que
#      le logo et la navigation ne disent déjà) ;
#   3. une page de premier niveau, présente dans la navigation, n'en porte pas.


def _gabarits_vitrine():
    import pathlib

    from django.conf import settings

    racine = pathlib.Path(settings.TEMPLATES[0]["DIRS"][0]) / "vitrine"
    # Les fragments (préfixe `_`) sont inclus dans une page, ils n'ont pas de titre.
    return [g for g in sorted(racine.glob("*.html")) if not g.name.startswith("_")]


def test_chaque_page_de_la_vitrine_a_un_seul_en_tete_de_page():
    """Un `<h1>` nu et un `.page-tete` ne se ressemblent pas : espacement,
    filet et emplacement du sous-titre diffèrent. C'est ce mélange qui donnait
    l'impression que les titres n'étaient « pas à la même place »."""
    # L'accueil fait exception, assumée : son titre est le hero pleine largeur.
    exceptions = {"accueil.html"}

    fautifs = []
    for gabarit in _gabarits_vitrine():
        if gabarit.name in exceptions:
            continue
        texte = gabarit.read_text(encoding="utf-8")
        if texte.count("<h1") != 1 or texte.count('class="page-tete"') != 1:
            fautifs.append(gabarit.name)

    assert not fautifs, "en-tête absent ou dupliqué : " + ", ".join(fautifs)


def test_aucun_sur_titre_ne_repete_le_nom_du_site():
    """Le sur-titre sert à situer une page dans une section. Y mettre le nom de
    l'association le vide de son rôle et double le logo."""
    fautifs = [
        g.name for g in _gabarits_vitrine() if "Improliante</span>" in g.read_text(encoding="utf-8")
    ]

    assert not fautifs, "sur-titre répétant le nom du site : " + ", ".join(fautifs)


# --- Contraste des palettes -------------------------------------------------
#
# La règle 9 du CLAUDE.md exige AA. Sans mesure, « AA » est une intention : deux
# palettes (E nuit bleue, F charbon/corail) peignaient l'item courant du rail à
# 4,05 et 4,29 pour un seuil de 4,5, et rien ne le signalait. Ce test rend la
# règle mécanique et couvre AUTOMATIQUEMENT toute palette ajoutée ensuite.
#
# Il suit les `var()` jusqu'au bout plutôt que de nommer des couleurs en dur :
# une première version citait `--couleur-lien` directement et restait verte quand
# on rebranchait le rail sur `--couleur-primaire`, c'est-à-dire quand on remettait
# le défaut qu'elle était censée interdire.


def _luminance(canaux):
    lineaires = []
    for v in canaux:
        v /= 255
        lineaires.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lineaires[0] + 0.7152 * lineaires[1] + 0.0722 * lineaires[2]


def _contraste(avant_plan, arriere_plan):
    a, b = _luminance(avant_plan), _luminance(arriere_plan)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _resoudre(jetons, valeur, profondeur=0):
    """Suit les `var(--x)` en chaîne jusqu'à une valeur littérale."""
    import re

    if profondeur > 10 or valeur is None:
        return None
    valeur = valeur.strip()
    reference = re.fullmatch(r"var\((--[\w-]+)\)", valeur)
    if reference:
        return _resoudre(jetons, jetons.get(reference.group(1)), profondeur + 1)
    if valeur.startswith("--"):  # un nom de jeton nu se résout comme un var()
        return _resoudre(jetons, jetons.get(valeur), profondeur + 1)
    return valeur


def _couleur(jetons, valeur, fond=None):
    """Rend un triplet RVB. Une couleur translucide est composée sur `fond` —
    l'item actif du rail sombre est un blanc à 10 % posé sur l'encre."""
    import re

    valeur = _resoudre(jetons, valeur)
    if valeur is None:
        return None
    if valeur.startswith("#"):
        h = valeur.lstrip("#").split()[0]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    rgba = re.fullmatch(r"rgba?\(([^)]+)\)", valeur)
    if rgba:
        parties = [p.strip() for p in rgba.group(1).replace("/", ",").split(",")]
        canaux = [float(x) for x in parties[:3]]
        alpha = float(parties[3]) if len(parties) > 3 else 1.0
        if alpha >= 1.0:
            return tuple(round(c) for c in canaux)
        if fond is None:
            return None
        return tuple(round(c * alpha + f * (1 - alpha)) for c, f in zip(canaux, fond, strict=True))
    return None


# Chaque paire est un texte réellement peint sur un fond réellement peint, et
# désigne des JETONS : si le CSS rebranche un jeton, la mesure suit.
# 3.0 pour l'accent : il ne sert qu'en gros titre dans le hero (AA gros texte).
_PAIRES_AA = [
    ("lien sur carte", "--couleur-lien", "--surface", None, 4.5),
    ("lien sur canvas", "--couleur-lien", "--canvas", None, 4.5),
    ("lien sur surface alternée", "--couleur-lien", "--surface-alt", None, 4.5),
    ("blanc sur bouton primaire", "#ffffff", "--couleur-primaire", None, 4.5),
    ("blanc sur en-tête", "#ffffff", "--ink", None, 4.5),
    ("texte sur teinte claire", "--couleur-texte", "--couleur-primaire-clair", None, 4.5),
    ("item courant du rail", "--rail-actif-texte", "--rail-actif-bg", "--rail-bg", 4.5),
    # Le rail était hors mesure : ses titres de groupe tombaient à 4,37 sur les
    # palettes à rail sombre. Ils portent la position depuis que le rail se
    # replie — c'est le repère principal, pas un ornement.
    ("titre de groupe du rail", "--rail-titre", "--rail-bg", "--rail-bg", 4.5),
    ("entrée du rail", "--rail-texte", "--rail-bg", "--rail-bg", 4.5),
    ("entrée survolée du rail", "--rail-texte-fort", "--rail-hover", "--rail-bg", 4.5),
    ("accent sur en-tête (gros titre)", "--accent", "--ink", None, 3.0),
    ("encre sur bouton accent", "--ink", "--accent", None, 4.5),
    ("texte muet sur canvas", "--couleur-muet", "--canvas", None, 4.5),
    # Ajoutée au lot 9 avec la règle du lien neutralisé : elle peint une paire
    # que rien ne mesurait, sur les dix-huit palettes et dans les deux modes. Un
    # bouton neutralisé reste à LIRE — il dit pourquoi on ne peut pas cliquer —
    # donc il tient le même seuil que le texte courant, pas celui d'un ornement.
    ("texte sur bouton neutralisé", "--couleur-texte", "--surface-alt", None, 4.5),
]


def _jetons_du_theme(css, selecteur):
    """Fusionne, dans l'ordre du document, toute règle dont la LISTE de
    sélecteurs contient celui-ci : une palette hérite du groupe « rail clair »
    autant que de son propre bloc."""
    import re

    jetons = {}
    # Retirer les commentaires D'ABORD : le grand en-tête « THÈMES DE TEST » cite
    # `data-theme="a"`, et une de ses lignes se faisait prendre pour un sélecteur
    # — la règle « rail clair » qui suivait était alors avalée, et les palettes
    # claires mesuraient le rail sombre de `:root`. Un test peut être vert et
    # mesurer autre chose que ce qu'il annonce.
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for liste, corps in re.findall(r"(?m)^([^{}@/\n][^{}]*?)\{([^{}]*)\}", css):
        if selecteur in [s.strip() for s in liste.split(",")]:
            jetons.update(
                (cle, valeur.strip())
                for cle, valeur in re.findall(r"(--[\w-]+):\s*([^;]+);", corps)
            )
    return jetons


def test_les_palettes_respectent_le_contraste_AA():
    import pathlib
    import re

    from django.conf import settings

    css = (pathlib.Path(settings.BASE_DIR) / "front/static/css/site.css").read_text(
        encoding="utf-8"
    )
    racine = _jetons_du_theme(css, ":root")
    palettes = sorted(set(re.findall(r'html\[data-theme="(\w+)"\]', css)))
    assert len(palettes) >= 7, f"palettes introuvables dans le CSS : {palettes}"

    fautifs = []
    for lettre in palettes:
        # Les deux modes, dans l'ordre de la cascade. En sombre, `html.sombre`
        # et `html[data-theme=N]` pèsent la même spécificité (0,1,1) : la
        # palette, écrite plus bas, l'emportait et posait ses couleurs de
        # papier kraft sur un fond noir. `html.sombre[data-theme=N]` pèse
        # (0,2,1) et tranche. Ne mesurer que le mode clair laissait passer
        # quinze palettes sur dix-huit sous AA.
        for mode, selecteurs in (
            ("clair", [f'html[data-theme="{lettre}"]']),
            (
                "sombre",
                [
                    "html.sombre",
                    f'html[data-theme="{lettre}"]',
                    f'html.sombre[data-theme="{lettre}"]',
                ],
            ),
        ):
            _mesurer(css, racine, selecteurs, lettre, mode, fautifs)

    assert not fautifs, "contraste sous le seuil AA :\n  " + "\n  ".join(fautifs)


def _mesurer(css, racine, selecteurs, lettre, mode, fautifs):
    jetons = dict(racine)
    for selecteur in selecteurs:
        jetons.update(_jetons_du_theme(css, selecteur))
    mesurees = 0
    for label, avant, arriere, derriere, seuil in _PAIRES_AA:
        fond = _couleur(jetons, derriere) if derriere else None
        texte, support = _couleur(jetons, avant, fond), _couleur(jetons, arriere, fond)
        if texte is None or support is None:
            continue
        mesurees += 1
        rapport = _contraste(texte, support)
        if rapport < seuil:
            fautifs.append(f"{lettre} ({mode}) · {label} : {rapport:.2f} < {seuil}")
    # Un jeton renommé ferait passer le test en ne mesurant plus rien :
    # exiger le compte plein est ce qui empêche ce faux vert.
    assert mesurees == len(_PAIRES_AA), (
        f"palette {lettre} ({mode}) : {mesurees} paires mesurées sur "
        f"{len(_PAIRES_AA)} — un jeton a changé de nom, le test ne prouve plus rien"
    )


# --- Présentation de l'association ------------------------------------------
#
# L'accroche et la présentation vivaient en dur dans deux gabarits : le bureau
# ne pouvait pas retoucher ce que dit sa propre page d'accueil, et le même texte
# était écrit deux fois. Les deux pages tirent maintenant du même enregistrement.


def test_l_accueil_porte_sur_l_association(client, db):
    """Le hero affiche le nom, l'accroche et la présentation de l'association —
    et il suit quand le bureau les modifie."""
    parametres = ParametresAssociation.load()
    parametres.nom = "Compagnie du Tréteau"
    parametres.accroche = "on joue, on rate, on recommence."
    parametres.presentation = "Une troupe née en 2019 dans une salle des fêtes."
    parametres.save()

    corps = client.get("/").content.decode()

    assert "Compagnie du Tréteau" in corps
    assert "on joue, on rate, on recommence." in corps
    assert "Une troupe née en 2019 dans une salle des fêtes." in corps


def test_la_presentation_n_est_ecrite_qu_a_un_endroit(client, db):
    """Accueil et page « L'association » servent le MÊME texte : le doublon en
    dur d'avant se serait désynchronisé à la première retouche."""
    parametres = ParametresAssociation.load()
    parametres.presentation = "Texte de présentation unique et reconnaissable."
    parametres.save()

    accueil = client.get("/").content.decode()
    association = client.get("/association/").content.decode()

    assert "Texte de présentation unique et reconnaissable." in accueil
    assert "Texte de présentation unique et reconnaissable." in association


def test_le_hero_nomme_l_association_sur_une_installation_neuve(client, db):
    """Sans aucune saisie, le titre doit porter le nom — pas commencer par un
    saut de ligne orphelin. Mes deux scripts de rendu remplissaient `nom` avant
    de capturer : la capture était juste, l'installation neuve ne l'était pas."""
    import re

    from django.utils.html import escape

    parametres = ParametresAssociation.load()  # rien n'a été saisi

    html = client.get("/").content.decode()
    titre = re.search(r'<h1 class="hero__titre">(.*?)</h1>', html, re.S).group(1)

    assert parametres.nom, "le nom par défaut est vide"
    # `escape` : l'apostrophe de « L'Improliante » sort en `&#x27;` dans le HTML.
    assert titre.strip().startswith(escape(parametres.nom)), titre.strip()[:80]


def test_un_nom_vide_ne_laisse_pas_de_saut_de_ligne_orphelin(client, db):
    """Le champ reste effaçable : le titre doit alors se réduire à l'accroche."""
    import re

    parametres = ParametresAssociation.load()
    parametres.nom = ""
    parametres.save()

    html = client.get("/").content.decode()
    titre = re.search(r'<h1 class="hero__titre">(.*?)</h1>', html, re.S).group(1)

    assert "<br />" not in titre, titre.strip()[:80]


def test_l_accroche_vide_ne_casse_pas_le_hero(client, db):
    """Champs facultatifs : une association qui les vide doit garder une page
    d'accueil valide, sans paragraphe fantôme."""
    parametres = ParametresAssociation.load()
    parametres.accroche = ""
    parametres.presentation = ""
    parametres.save()

    reponse = client.get("/")

    assert reponse.status_code == 200
    assert 'class="hero__intro"' not in reponse.content.decode()


# --- Coordonnées publiques ---------------------------------------------------
#
# La page de contact n'offrait qu'un formulaire : aucune adresse, aucun nom,
# aucun moyen de joindre l'association autrement. Le bureau les saisit
# maintenant dans les paramètres. Le point sensible est l'adresse : celle du
# modèle est l'adresse DÉCLARÉE, très souvent le domicile d'un membre — elle ne
# doit sortir que sur demande explicite.


def test_les_coordonnees_saisies_apparaissent_sur_la_page_contact(client, db):
    parametres = ParametresAssociation.load()
    parametres.email_public = "bonjour@improliante.test"
    parametres.telephone_public = "01 23 45 67 89"
    parametres.save()

    corps = client.get("/contact/").content.decode()

    assert "bonjour@improliante.test" in corps
    assert "01 23 45 67 89" in corps
    assert 'href="tel:0123456789"' in corps  # espaces retirés dans le lien


def test_la_page_contact_ne_montre_rien_quand_rien_n_est_saisi(client, db):
    """Champs vides = pas de bloc vide : une association qui ne publie pas de
    coordonnées garde la page telle qu'elle était."""
    ParametresAssociation.load()

    corps = client.get("/contact/").content.decode()

    assert "Nous joindre directement" not in corps


def test_l_adresse_postale_reste_privee_sans_demande_explicite(client, db):
    """L'adresse déclarée est souvent un domicile. La renseigner pour les reçus
    fiscaux ne doit JAMAIS suffire à la publier."""
    parametres = ParametresAssociation.load()
    parametres.adresse = "12 rue des Lilas"
    parametres.code_postal = "75011"
    parametres.ville = "Paris"
    parametres.save()  # la case n'est pas cochée

    corps = client.get("/contact/").content.decode()

    assert "12 rue des Lilas" not in corps
    assert parametres.adresse_affichable() == ""

    parametres.afficher_adresse_postale = True
    parametres.save()

    corps = client.get("/contact/").content.decode()

    assert "12 rue des Lilas" in corps
    assert "75011 Paris" in corps


def test_les_interlocuteurs_publics_apparaissent(client, db):
    from apps.coeur.models import ContactPublic

    parametres = ParametresAssociation.load()
    ContactPublic.objects.create(
        parametres=parametres,
        role="Réservations",
        nom="Camille Roux",
        email="resa@improliante.test",
        ordre=1,
    )
    # Une fonction peut être publiée sans nommer personne.
    ContactPublic.objects.create(
        parametres=parametres, role="Presse", telephone="0600000000", ordre=2
    )

    corps = client.get("/contact/").content.decode()

    assert "Réservations" in corps
    assert "Camille Roux" in corps
    assert "resa@improliante.test" in corps
    assert "Presse" in corps


def test_l_entete_public_garde_sa_navigation(client, db):
    """Le repli de l'en-tête ne vaut QUE dans l'espace connecté : sur la vitrine,
    la navigation complète reste en place."""
    entete = client.get("/").content.decode().split("<header", 1)[1].split("</header>", 1)[0]

    for lien in ("Accueil", "L'association", "Spectacles", "Agenda", "Galerie", "Contact"):
        assert lien in entete, lien
    assert "Voir le site" not in entete


def test_un_lien_neutralise_se_distingue_a_l_oeil():
    """`aria-disabled` n'a AUCUN effet visuel par lui-même.

    Le lien « Valider et numéroter… » le reçoit dès qu'un brouillon de facture
    porte des modifications non enregistrées (`facturation.js`). Sans règle CSS,
    l'œil voyait un bouton d'apparence normale qui ne mène nulle part — annoncé
    au lecteur d'écran, invisible pour tous les autres.

    La règle vit dans la feuille, pas dans un gabarit : seul un test de son
    existence la retient d'être perdue à la prochaine refonte. La contrepartie
    est assumée — il vérifie qu'elle EST là, pas qu'elle se voit. C'est la passe
    QA qui regarde (`pilotage/qa/accessibilite-front-08.md`)."""
    from pathlib import Path

    from django.conf import settings

    css = Path(settings.BASE_DIR, "front", "static", "css", "site.css").read_text(encoding="utf-8")
    regle = '.lien-bouton[aria-disabled="true"]'
    assert regle in css, "aucun style ne distingue un lien neutralisé"
    bloc = css.split(regle, 1)[1].split("}", 1)[0]
    assert "cursor" in bloc, "la couleur porterait seule l'information (WCAG 1.4.1)"
    assert "opacity" not in bloc, (
        "une opacité effacerait le texte à demi : un bouton neutralisé reste à lire"
    )


# --- VIT-4 : prochaines participations, et fuites par une date --------------


def _date_publique(*, dans_jours=7, titre="SoireePublique", **champs):
    champs.setdefault("statut_moderation", Evenement.StatutModeration.PUBLIE)
    champs.setdefault("visibilite", Evenement.Visibilite.PUBLIC)
    return Evenement.objects.create(
        titre=titre,
        date_debut=timezone.now() + timedelta(days=dans_jours),
        **champs,
    )


def test_fiche_membre_annonce_ses_prochaines_participations(client, db):
    membre = _membre("Joueuse", visible=True)
    evenement = _date_publique(titre="SoireeImpro")
    Intervention.objects.create(evenement=evenement, membre=membre, role="Comédienne")

    corps = client.get(membre.get_absolute_url()).content.decode()

    assert "Prochaines participations" in corps
    assert "SoireeImpro" in corps
    assert "Comédienne" in corps
    assert f"/agenda/{evenement.pk}/" in corps


def test_fiche_membre_sans_date_le_dit_au_lieu_de_se_taire(client, db):
    """Un visiteur vient souvent pour savoir si la personne joue bientôt. Ne
    rien afficher le laisse chercher ; trois mots répondent."""
    membre = _membre("SansDate", visible=True)
    corps = client.get(membre.get_absolute_url()).content.decode()
    assert "Aucune prochaine date annoncée" in corps


def test_fiche_membre_ne_laisse_pas_fuiter_une_date_reservee_aux_membres(client, db):
    membre = _membre("Discrete", visible=True)
    interne = _date_publique(titre="ReunionInterne", visibilite=Evenement.Visibilite.MEMBRES)
    Intervention.objects.create(evenement=interne, membre=membre)

    reponse = client.get(membre.get_absolute_url())
    corps = reponse.content.decode()

    assert "ReunionInterne" not in corps
    # Le décompte lit la même liste : il ne peut pas annoncer une date que la
    # page ne montre pas.
    assert list(reponse.context["participations"]) == []
    assert reponse.context["autres_participations"] is False
    assert "Aucune prochaine date annoncée" in corps


def test_fiche_membre_ne_deroule_pas_une_saison_entiere(client, db):
    """Au-delà de la première liste, la page renvoie à l'agenda."""
    from apps.agenda.services import PARTICIPATIONS_EN_PREMIERE_LISTE as LIMITE

    membre = _membre("TresDemandee", visible=True)
    for i in range(LIMITE + 3):
        evenement = _date_publique(dans_jours=i + 1, titre=f"Date{i}")
        Intervention.objects.create(evenement=evenement, membre=membre)

    reponse = client.get(membre.get_absolute_url())

    assert len(reponse.context["participations"]) == LIMITE
    assert reponse.context["autres_participations"] is True
    assert "Toutes les dates à l'agenda" in reponse.content.decode()


def test_une_date_publique_ne_devoile_pas_un_spectacle_en_brouillon(client, db):
    """Deux publications, deux interrupteurs. Le bureau annonce une date avant
    d'avoir fini la fiche de l'œuvre : le titre, l'affiche et le lien de ce
    spectacle restent dedans — y compris dans les données structurées et
    l'image de partage, que personne ne relit à l'œil."""
    affiche_secrete = Media.objects.create(fichier="medias/secrete.jpg", alt="Affiche secrète")
    brouillon = Spectacle.objects.create(
        titre="OeuvreSecrete",
        statut_moderation=Spectacle.StatutModeration.BROUILLON,
        affiche=affiche_secrete,
    )
    evenement = _date_publique(titre="SoireeAnnoncee", spectacle=brouillon)

    agenda = client.get("/agenda/").content.decode()
    assert "SoireeAnnoncee" in agenda  # la date, elle, est bien publique
    assert "OeuvreSecrete" not in agenda

    fiche = client.get(f"/agenda/{evenement.pk}/")
    corps = fiche.content.decode()
    assert "OeuvreSecrete" not in corps
    assert "medias/secrete.jpg" not in corps  # ni en image de partage
    assert fiche.context["spectacle"] is None
    assert "workPerformed" not in _bloc_json_ld(corps)


def test_une_date_publique_montre_un_spectacle_publie(client, db):
    """Le revers : fermer la fuite ne doit pas fermer le cas normal."""
    spectacle = Spectacle.objects.create(
        titre="OeuvrePubliee", statut_moderation=Spectacle.StatutModeration.PUBLIE
    )
    evenement = _date_publique(titre="SoireeDeCreation", spectacle=spectacle)

    corps = client.get(f"/agenda/{evenement.pk}/").content.decode()

    assert "OeuvrePubliee" in corps
    assert f"/spectacles/{spectacle.pk}/" in corps
    assert _bloc_json_ld(corps)["workPerformed"]["name"] == "OeuvrePubliee"


def test_la_fiche_d_un_membre_ne_suit_pas_le_nombre_de_participations(client, db):
    """La carte de date montre le lieu, l'affiche et le spectacle rattaché :
    sans préchargement, chaque date en réclamait trois de plus. Le contrôle
    porte sur la CROISSANCE, pas sur un total — un total se périme au premier
    préchargement ajouté ailleurs."""
    membre = _membre("Mesuree", visible=True)

    def poser(debut, nombre):
        for i in range(debut, debut + nombre):
            evenement = _date_publique(dans_jours=i + 1, titre=f"Date{i}")
            Intervention.objects.create(evenement=evenement, membre=membre, role="Jeu")

    poser(0, 3)
    client.get(membre.get_absolute_url())  # amorce (gabarits, session)
    trois = _requetes(client, membre.get_absolute_url())
    poser(3, 9)
    douze = _requetes(client, membre.get_absolute_url())

    assert douze == trois, f"{trois} requêtes pour 3 participations, {douze} pour 12"


def test_la_fiche_d_un_spectacle_n_annonce_pas_une_date_passee(client, db):
    """« Prochaines dates » borne aussi le temps. La liste montrait toutes les
    représentations publiques, passées comprises : une tournée finie en février
    s'annonçait encore en septembre, sous ce titre-là."""
    spectacle = Spectacle.objects.create(
        titre="TourneeFinie", statut_moderation=Spectacle.StatutModeration.PUBLIE
    )
    for dans_jours, titre in ((-200, "DateDeLaSaisonDerniere"), (10, "DateAVenir")):
        _date_publique(dans_jours=dans_jours, titre=titre, spectacle=spectacle)

    corps = client.get(f"/spectacles/{spectacle.pk}/").content.decode()

    assert "DateAVenir" in corps
    assert "DateDeLaSaisonDerniere" not in corps
