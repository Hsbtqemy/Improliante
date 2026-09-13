"""Tests du service de modération partagé (`apps.common.moderation`).

On teste sur un modèle concret héritant du mixin `Moderation` — ici
`Spectacle` — puisque le service opère sur n'importe quelle fiche modérée.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.coeur.models import Utilisateur
from apps.common.fichiers import reponse_fichier_prive
from apps.common.models import Moderation
from apps.common.moderation import (
    TransitionModerationInvalide,
    marquer_revu,
    peut_etre_edite_par_auteur,
    peut_etre_soumis,
    refuser,
    signaler_modification_apres_publication,
    soumettre_a_moderation,
    valider,
)
from apps.documents.models import Document
from apps.spectacles.models import Spectacle

Statut = Moderation.StatutModeration


# --- Flux Instagram de l'asso (rendu serveur, dégradation) -----------------


def test_instagram_vide_sans_jeton():
    from django.core.cache import cache
    from django.test import override_settings

    from apps.common.instagram import derniers_posts_instagram

    cache.clear()
    with override_settings(INSTAGRAM_TOKEN=""):
        assert derniers_posts_instagram() == []


def test_instagram_renvoie_les_posts_en_cache():
    from unittest.mock import patch

    from django.core.cache import cache
    from django.test import override_settings

    from apps.common.instagram import derniers_posts_instagram

    cache.clear()
    faux = [{"id": "1", "image": "https://cdn/x.jpg", "permalink": "https://insta/p/1"}]
    with override_settings(INSTAGRAM_TOKEN="jeton-factice"):
        with patch("apps.common.instagram._recuperer", return_value=faux) as mock:
            assert derniers_posts_instagram(8) == faux
            derniers_posts_instagram(8)  # 2e appel : servi par le cache
    assert mock.call_count == 1  # une seule requête réseau


def test_instagram_sert_le_dernier_flux_connu_quand_l_api_tombe():
    """Le flux est récupéré dans le fil de la requête : quand Meta ne répond
    plus, la section d'accueil se vidait pour tout le monde jusqu'au retour de
    l'API. Une copie de la dernière réponse valide, gardée bien plus longtemps
    que le cache courant, fait qu'on montre le flux d'hier plutôt qu'un trou."""
    from unittest.mock import patch

    from django.core.cache import cache
    from django.test import override_settings

    from apps.common.instagram import CLE_CACHE, derniers_posts_instagram

    cache.clear()
    faux = [{"id": "1", "image": "https://cdn/x.jpg", "permalink": "https://insta/p/1"}]
    with override_settings(INSTAGRAM_TOKEN="jeton-factice"):
        with patch("apps.common.instagram._recuperer", return_value=faux):
            assert derniers_posts_instagram(8) == faux

        cache.delete(CLE_CACHE)  # le cache courant expire ; l'API, elle, est tombée
        with patch("apps.common.instagram._recuperer", return_value=[]) as panne:
            assert derniers_posts_instagram(8) == faux

        # Et la panne ne se redemande pas à chaque visiteur : elle est en cache.
        with patch("apps.common.instagram._recuperer", return_value=[]) as encore:
            assert derniers_posts_instagram(8) == faux

    assert panne.call_count == 1
    assert encore.call_count == 0


def test_instagram_normalise_video_utilise_thumbnail():
    from apps.common.instagram import _normaliser

    n = _normaliser(
        {
            "id": "2",
            "media_type": "VIDEO",
            "media_url": "video.mp4",
            "thumbnail_url": "miniature.jpg",
            "permalink": "https://insta/p/2",
            "caption": "Vidéo de répétition",
        }
    )
    assert n["image"] == "miniature.jpg"
    assert n["permalink"] == "https://insta/p/2"
    assert n["legende"] == "Vidéo de répétition"


def test_soumettre_un_brouillon_le_passe_en_propose(db):
    projet = Spectacle.objects.create(titre="Nouveau", statut_moderation=Statut.BROUILLON)
    soumettre_a_moderation(projet)
    projet.refresh_from_db()
    assert projet.statut_moderation == Statut.PROPOSE


def test_soumettre_un_refuse_efface_le_motif(db):
    projet = Spectacle.objects.create(
        titre="À corriger",
        statut_moderation=Statut.REFUSE,
        motif_refus="Titre trop vague.",
    )
    soumettre_a_moderation(projet)
    projet.refresh_from_db()
    assert projet.statut_moderation == Statut.PROPOSE
    assert projet.motif_refus == ""


def test_soumettre_un_propose_est_refuse(db):
    projet = Spectacle.objects.create(titre="En attente", statut_moderation=Statut.PROPOSE)
    with pytest.raises(TransitionModerationInvalide):
        soumettre_a_moderation(projet)


def test_soumettre_un_publie_est_refuse(db):
    projet = Spectacle.objects.create(titre="En ligne", statut_moderation=Statut.PUBLIE)
    with pytest.raises(TransitionModerationInvalide):
        soumettre_a_moderation(projet)


def test_valider_publie_et_trace_le_valideur(db):
    bureau = Utilisateur.objects.create_user(username="bureau", password="x")
    projet = Spectacle.objects.create(titre="À publier", statut_moderation=Statut.PROPOSE)
    valider(projet, par=bureau)
    projet.refresh_from_db()
    assert projet.statut_moderation == Statut.PUBLIE
    assert projet.valide_par == bureau
    assert projet.date_publication is not None


def test_valider_une_fiche_non_proposee_est_refuse(db):
    projet = Spectacle.objects.create(titre="Brouillon", statut_moderation=Statut.BROUILLON)
    with pytest.raises(TransitionModerationInvalide):
        valider(projet, par=None)


def test_refuser_enregistre_le_motif_et_le_valideur(db):
    bureau = Utilisateur.objects.create_user(username="bureau", password="x")
    projet = Spectacle.objects.create(titre="Incomplet", statut_moderation=Statut.PROPOSE)
    refuser(projet, par=bureau, motif="Synopsis manquant.")
    projet.refresh_from_db()
    assert projet.statut_moderation == Statut.REFUSE
    assert projet.motif_refus == "Synopsis manquant."
    assert projet.valide_par == bureau


def test_refuser_sans_motif_leve_une_erreur(db):
    projet = Spectacle.objects.create(titre="Incomplet", statut_moderation=Statut.PROPOSE)
    with pytest.raises(ValueError):
        refuser(projet, par=None, motif="   ")


@pytest.mark.parametrize(
    ("statut", "attendu"),
    [
        (Statut.BROUILLON, True),
        (Statut.REFUSE, True),
        (Statut.PROPOSE, False),  # verrouillé le temps du contrôle initial
        (Statut.PUBLIE, True),  # publié : l'auteur peut encore faire évoluer sa fiche
    ],
)
def test_peut_etre_edite_par_auteur(db, statut, attendu):
    projet = Spectacle.objects.create(titre="X", statut_moderation=statut)
    assert peut_etre_edite_par_auteur(projet) is attendu


@pytest.mark.parametrize(
    ("statut", "attendu"),
    [
        (Statut.BROUILLON, True),
        (Statut.REFUSE, True),
        (Statut.PROPOSE, False),
        (Statut.PUBLIE, False),  # publié : éditable mais pas re-soumissible
    ],
)
def test_peut_etre_soumis(db, statut, attendu):
    projet = Spectacle.objects.create(titre="X", statut_moderation=statut)
    assert peut_etre_soumis(projet) is attendu


def test_signaler_modification_apres_publication_leve_le_drapeau(db):
    projet = Spectacle.objects.create(titre="En ligne", statut_moderation=Statut.PUBLIE)
    signaler_modification_apres_publication(projet)
    projet.refresh_from_db()
    assert projet.modifie_apres_publication is True
    assert projet.statut_moderation == Statut.PUBLIE  # reste publié


def test_signaler_sans_effet_si_non_publie(db):
    projet = Spectacle.objects.create(titre="Brouillon", statut_moderation=Statut.BROUILLON)
    signaler_modification_apres_publication(projet)
    projet.refresh_from_db()
    assert projet.modifie_apres_publication is False


def test_marquer_revu_efface_le_drapeau(db):
    bureau = Utilisateur.objects.create(username="bureau")
    projet = Spectacle.objects.create(
        titre="Revu", statut_moderation=Statut.PUBLIE, modifie_apres_publication=True
    )
    marquer_revu(projet, par=bureau)
    projet.refresh_from_db()
    assert projet.modifie_apres_publication is False
    assert projet.valide_par == bureau


# --- Service de fichier privé ----------------------------------------------


def _document_pdf():
    return Document.objects.create(
        titre="Reçu",
        confidentialite=Document.Confidentialite.PRIVE,
        fichier=SimpleUploadedFile("recu.pdf", b"%PDF-1.4 data", content_type="application/pdf"),
    )


def test_reponse_fichier_prive_sert_le_contenu_en_dev(db):
    """Mode dev (UTILISER_X_ACCEL=False) : Django sert lui-même le flux."""
    document = _document_pdf()
    reponse = reponse_fichier_prive(document.fichier)
    assert b"".join(reponse.streaming_content) == b"%PDF-1.4 data"
    assert reponse["Content-Type"] == "application/pdf"


def test_reponse_fichier_prive_delegue_a_nginx_en_prod(db, settings):
    """Mode prod : réponse vide + en-tête X-Accel-Redirect, le fichier ne
    transite pas par Python (c'est Nginx qui le sert)."""
    settings.UTILISER_X_ACCEL = True
    settings.X_ACCEL_PREFIXE = "/media-prive/"
    document = _document_pdf()
    reponse = reponse_fichier_prive(document.fichier)
    assert reponse.status_code == 200
    assert reponse["X-Accel-Redirect"] == "/media-prive/" + document.fichier.name
    assert reponse.content == b""  # pas de corps : Nginx s'en charge
    assert "attachment" in reponse["Content-Disposition"]


# --- Garde-fou sur les commentaires de gabarit ------------------------------


def test_aucun_gabarit_n_utilise_un_commentaire_court_multiligne():
    """`{# … #}` est MONO-LIGNE. Étalé sur plusieurs lignes, il cesse d'être un
    commentaire : son texte s'affiche en clair, et Django exécute les tags qu'il
    contient. C'est ce qui rendait `500.html` impossible à afficher — la page
    d'erreur elle-même levait une TemplateSyntaxError, en production, au pire
    moment. Le commentaire multi-ligne s'écrit `{% comment %} … {% endcomment %}`.
    """
    import pathlib

    from django.conf import settings

    fautifs = []
    for dossier in settings.TEMPLATES[0]["DIRS"]:
        for gabarit in sorted(pathlib.Path(dossier).rglob("*.html")):
            for numero, ligne in enumerate(gabarit.read_text(encoding="utf-8").splitlines(), 1):
                depart = ligne.find("{#")
                if depart != -1 and "#}" not in ligne[depart:]:
                    fautifs.append(f"{gabarit}:{numero}")

    assert not fautifs, "commentaires courts non fermés sur leur ligne : " + ", ".join(fautifs)


def test_la_page_d_erreur_500_se_rend_sans_contexte():
    """Un 500 survient quand une brique a lâché : la page doit s'afficher avec
    un contexte vide, sans context processor, sans variable. La rendre ici est
    le seul moyen de s'en assurer — aucune vue ne l'appelle en temps normal."""
    from django.template.loader import render_to_string

    html = render_to_string("500.html", {})

    assert "{#" not in html and "{%" not in html  # rien de non interprété
    assert "<html" in html


def test_chaque_reference_static_des_gabarits_pointe_vers_un_fichier_existant():
    """Avec `ManifestStaticFilesStorage`, un `{% static %}` visant un fichier
    absent ne produit plus un lien mort : il lève une erreur AU RENDU, donc un
    500 en production. Le défaut ne se voit qu'en prod, et sur la page qui
    porte la référence — ce test le ramène ici.

    On passe par les finders de Django plutôt que par un chemin en dur : un
    asset peut venir d'une app (admin, treebeard) et pas seulement de
    `front/static`.
    """
    import pathlib
    import re

    from django.conf import settings
    from django.contrib.staticfiles import finders

    fautifs = []
    trouvees = 0
    for dossier in settings.TEMPLATES[0]["DIRS"]:
        for gabarit in sorted(pathlib.Path(dossier).rglob("*.html")):
            texte = gabarit.read_text(encoding="utf-8")
            for reference in re.findall(r"""\{%\s*static\s+["']([^"']+)["']""", texte):
                trouvees += 1
                if finders.find(reference) is None:
                    fautifs.append(f"{gabarit.name} → {reference}")

    assert trouvees >= 8, f"{trouvees} références trouvées : le balayage ne voit plus rien"
    assert not fautifs, "fichiers statiques référencés mais absents : " + ", ".join(fautifs)


def test_le_mot_bureau_ne_designe_jamais_l_espace_d_administration():
    """Dans une association, « le bureau » est un ORGANE — les personnes élues —
    pas un lieu. L'employer comme nom de section faisait lire « Bureau ·
    Finances » comme « les élus · finances ». L'espace s'appelle « Gestion » ;
    « bureau » reste réservé aux personnes (« Équipe du bureau », « transmis au
    bureau », le groupe de permission).

    « Back-office » est écarté pour une autre raison : c'est un anglicisme, et
    la convention du projet est le métier en français. Il désignait d'ailleurs
    le MÊME espace que « Bureau », qui avait donc deux noms.
    """
    import pathlib
    import re

    from django.conf import settings

    fautifs = []
    for dossier in settings.TEMPLATES[0]["DIRS"]:
        for gabarit in sorted(pathlib.Path(dossier).rglob("*.html")):
            texte = gabarit.read_text(encoding="utf-8")
            for numero, ligne in enumerate(texte.splitlines(), 1):
                if re.search(r'page-tete__eyebrow">Bureau\b', ligne):
                    fautifs.append(f"{gabarit.name}:{numero} sur-titre « Bureau »")
                if "Back-office" in ligne:
                    fautifs.append(f"{gabarit.name}:{numero} « Back-office »")
                if re.search(r'<summary class="nav-espace__titre">Bureau<', ligne):
                    fautifs.append(f"{gabarit.name}:{numero} groupe de nav « Bureau »")

    assert not fautifs, "« bureau » employé pour l'ESPACE et non pour l'organe :\n  " + "\n  ".join(
        fautifs
    )


def test_le_sur_titre_d_une_page_de_gestion_nomme_son_groupe_de_rail():
    """Le sur-titre est le fil d'Ariane : il doit dire dans quel groupe du rail
    on se trouve, donc porter exactement « Gestion · <groupe> ».

    Il n'en était rien. Trois dérives cohabitaient : douze pages s'arrêtaient à
    « Gestion » sans dire lequel des quatre domaines ; « Gestion · Gouvernance »
    et « Gestion · Documents » nommaient des groupes inexistants (ce sont des
    ENTRÉES de « Vie associative ») ; les quatre écrans de réglages disaient
    « Réglages » tout court, comme s'ils vivaient hors de l'espace de gestion.

    Les groupes se lisent DANS le gabarit du rail, pas dans une liste recopiée
    ici : renommer un groupe fait tomber ce test au lieu de laisser vingt et une
    pages désigner un groupe disparu.
    """
    import pathlib
    import re

    from django.conf import settings

    dossiers = [pathlib.Path(d) for d in settings.TEMPLATES[0]["DIRS"]]
    rail = next(d / "_nav_espace.html" for d in dossiers if (d / "_nav_espace.html").exists())
    groupes = set(
        re.findall(
            r'<summary class="nav-espace__titre">([^<]+)</summary>',
            rail.read_text(encoding="utf-8"),
        )
    )
    groupes -= {"Le site", "Mon espace"}  # ni l'un ni l'autre n'est un domaine de gestion
    assert len(groupes) >= 4, f"groupes lus dans le rail : {sorted(groupes)}"

    # « Vue d'ensemble » est la racine de l'espace et vit hors groupe, dans le
    # rail comme ici : son sur-titre n'a pas de domaine à nommer. Exception
    # nommée, et une seule — la même que celle du test de position du rail.
    RACINE = "tableau_de_bord.html"

    fautifs = []
    controlees = 0
    for dossier in dossiers:
        for gabarit in sorted((dossier / "backoffice").glob("*.html")):
            trouve = re.search(
                r'page-tete__eyebrow">([^<]*)</span>', gabarit.read_text(encoding="utf-8")
            )
            if not trouve:
                continue
            controlees += 1
            sur_titre = trouve.group(1)
            if gabarit.name == RACINE:
                if sur_titre != "Gestion":
                    fautifs.append(
                        f"{gabarit.name} : racine, attendu « Gestion », lu « {sur_titre} »"
                    )
            elif not (
                sur_titre.startswith("Gestion · ") and sur_titre[len("Gestion · ") :] in groupes
            ):
                fautifs.append(f"{gabarit.name} : « {sur_titre} » n'est pas « Gestion · <groupe> »")

    assert controlees >= 30, f"{controlees} pages contrôlées : la boucle ne voit plus les gabarits"
    assert not fautifs, "sur-titre qui ne nomme pas son groupe de rail :\n  " + "\n  ".join(fautifs)


def test_aucun_ecran_de_gestion_ne_refait_un_lien_vers_la_racine():
    """Neuf écrans de gestion portaient « ← Gestion » vers le tableau de bord.
    Onze écrans comparables n'en portaient pas : ce n'était pas une convention,
    c'était du résidu.

    Le lien est devenu faux le jour où la racine a pris le nom « Vue d'ensemble »,
    et redondant le même jour : sortie des groupes, cette entrée est la seule du
    rail qui ne se replie jamais. C'est le même raisonnement qui a vidé la grille
    « Modules » du tableau de bord et les raccourcis de celui du membre.

    Ce qui reste autorisé, et qui n'est pas la même chose : le retour d'un
    formulaire vers SA liste (« ← Membres », « ← Signataires »). Le rail marque la
    liste, jamais le formulaire — sans ce lien, il n'y a pas de chemin de retour.
    """
    import pathlib
    import re

    from django.conf import settings

    fautifs = []
    for dossier in settings.TEMPLATES[0]["DIRS"]:
        for gabarit in sorted((pathlib.Path(dossier) / "backoffice").glob("*.html")):
            for numero, ligne in enumerate(gabarit.read_text(encoding="utf-8").splitlines(), 1):
                if "←" in ligne and re.search(r"url '(backoffice:tableau_de_bord)'", ligne):
                    fautifs.append(f"{gabarit.name}:{numero} {ligne.strip()[:70]}")

    assert not fautifs, (
        "lien de retour vers la racine, que le rail porte déjà hors groupe :\n  "
        + "\n  ".join(fautifs)
    )


# --- Accessibilité : balayage de toutes les pages sans paramètre -------------
#
# La règle 9 du dépôt (RGAA/WCAG AA) n'avait jamais été mesurée ailleurs qu'à
# l'œil, écran par écran. Ces deux tests parcourent toutes les URL appelables
# sans identifiant — 46 pages pour un membre du bureau — et vérifient deux
# choses qu'un humain ne peut pas tenir à jour de tête.


def _image_temoin(nom: str):
    """Une vraie image JPEG, assez large pour qu'une vignette en soit tirée."""
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (700, 500), (120, 40, 60)).save(tampon, "JPEG")
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type="image/jpeg")


def _ecrans_a_identifiant(membre):
    """Un objet de chaque sorte, et les URL de détail qu'ils ouvrent.

    Sans eux, le balayage ne voyait que les écrans appelables à l'aveugle : 67
    gabarits sur 98. Les fiches publiques — spectacle, événement, membre,
    réservation — n'étaient mesurées par aucun des deux contrôles, alors que ce
    sont les pages qu'un visiteur atteint après les listes.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.agenda.models import Evenement
    from apps.budget.models import Adhesion, Saison
    from apps.coeur.models import Membre
    from apps.common.models import Moderation
    from apps.documents.models import Dossier
    from apps.facturation.models import Client as ClientFacturation
    from apps.facturation.models import Devis, Facture
    from apps.gouvernance.models import BlocCompteRendu, Reunion, Sujet
    from apps.gouvernance.services import donner_pouvoir
    from apps.medias.models import Media
    from apps.spectacles.models import ImageSpectacle, Spectacle

    publie = Moderation.StatutModeration.PUBLIE
    aujourdhui = timezone.now()

    # De vraies images, et pas des chemins de fantaisie : sans elles, les pages
    # sont rendues SANS aucun `<img>`, et les invariants qui portent dessus —
    # texte alternatif, identifiants — passeraient en ne regardant rien. Assez
    # large pour qu'une vignette en soit tirée, donc pour que le `srcset` existe.
    affiche = Media.objects.create(fichier=_image_temoin("affiche.jpg"), alt="Affiche témoin")
    spectacle = Spectacle.objects.create(
        titre="Spectacle témoin", statut_moderation=publie, affiche=affiche
    )
    spectacle.porteurs.add(membre)
    ImageSpectacle.objects.create(
        spectacle=spectacle,
        media=Media.objects.create(fichier=_image_temoin("galerie.jpg"), alt="Image de galerie"),
    )
    membre.photo = Media.objects.create(fichier=_image_temoin("photo.jpg"), alt="Portrait témoin")
    membre.save(update_fields=["photo"])
    evenement = Evenement.objects.create(
        titre="Événement témoin",
        date_debut=aujourdhui + timedelta(days=5),
        statut_moderation=publie,
        cree_par=membre.user,
        places_max=20,  # sans jauge, la feuille d'inscription publique n'existe pas
        affiche=Media.objects.create(fichier=_image_temoin("evt.jpg"), alt="Affiche d'événement"),
    )
    reunion = Reunion.objects.create(
        titre="AG témoin",
        date=aujourdhui,
        type_reunion=Reunion.TypeReunion.AG_ORDINAIRE,
        statut=Reunion.Statut.CONVOQUEE,
    )
    # La fiche d'une réunion porte un champ PAR point d'ordre du jour et trois
    # par bloc de récit : sans un point et un bloc, le balayage passerait sur
    # l'écran le plus dense du bureau sans en voir les champs. Un pouvoir, de
    # même, pour que sa ligne et son bouton de retrait existent.
    Sujet.objects.create(titre="Point témoin", reunion=reunion, statut=Sujet.Statut.ORDRE_DU_JOUR)
    BlocCompteRendu.objects.create(reunion=reunion, texte="Récit témoin")
    donner_pouvoir(
        reunion,
        Membre.objects.create(user=Utilisateur.objects.create(username="mandant-temoin")),
        membre,
        par_le_bureau=True,
    )
    client_fact = ClientFacturation.objects.create(nom="Client témoin")
    facture = Facture.objects.create(client=client_fact, date=aujourdhui.date())
    devis = Devis.objects.create(client=client_fact, date=aujourdhui.date())
    dossier = Dossier.add_root(
        nom="Dossier témoin", proprietaire=membre, espace=Dossier.Espace.PERSO
    )
    saison = Saison.objects.create(nom="2026", date_debut="2026-01-01", date_fin="2026-12-31")
    adhesion = Adhesion.objects.create(membre=membre, saison=saison, montant_verse=10)

    return [
        f"/spectacles/{spectacle.pk}/",
        f"/agenda/{evenement.pk}/",
        f"/agenda/{evenement.pk}/inscription/",
        f"/@{membre.slug}/",
        f"/espace/projets/{spectacle.pk}/",
        f"/espace/evenements/{evenement.pk}/",
        f"/espace/convocations/{reunion.pk}/",
        f"/bureau/gouvernance/reunion/{reunion.pk}/",
        f"/espace/fichiers/{dossier.pk}/",
        f"/bureau/factures/{facture.pk}/",
        f"/bureau/devis/{devis.pk}/",
        f"/bureau/membres/{membre.pk}/",
        f"/bureau/adhesions/{adhesion.pk}/",
        f"/bureau/evenements/{evenement.pk}/inscriptions/",
        # La page d'erreur est vue par de vrais visiteurs et n'était mesurée par
        # rien. Elle répond 404 : la boucle ne retient que les 200, on la traite
        # donc à part, ci-dessous.
    ]


def _pages_sans_parametre(client):
    """Rend chaque page du site et renvoie (url, html) pour celles qui répondent
    200 en HTML : les URL appelables sans identifiant, PLUS les écrans de détail
    ouverts par `_ecrans_a_identifiant`."""
    from django.contrib.auth.models import Group
    from django.urls import get_resolver

    from apps.coeur.models import Membre, ParametresAssociation, Utilisateur

    ParametresAssociation.objects.get_or_create(pk=1, defaults={"nom": "L'Improliante"})
    utilisateur = Utilisateur.objects.create_user(username="a11y", password="x", is_staff=True)
    membre = Membre.objects.create(
        user=utilisateur, nom="Test", prenom="A11y", visible_sur_site=True
    )
    groupe, _ = Group.objects.get_or_create(name="Bureau")
    utilisateur.groups.add(groupe)
    client.force_login(utilisateur)

    urls = set()
    for motif in get_resolver().url_patterns:
        for sous_motif in getattr(motif, "url_patterns", [motif]):
            chemin = str(getattr(sous_motif, "pattern", ""))
            if "<" in chemin:
                continue
            # Le chemin VIDE est la page d'accueil. Le test l'écartait avec un
            # `if chemin` : la page la plus vue du site n'était mesurée par
            # aucun des deux contrôles, et rien ne le disait.
            urls.add("/" + chemin.lstrip("/"))
    urls |= set(_ecrans_a_identifiant(membre))

    pages = []
    for url in sorted(urls):
        reponse = client.get(url)
        if reponse.status_code == 200 and "html" in reponse.headers.get("Content-Type", ""):
            pages.append((url, reponse.content.decode(errors="replace")))
    erreur = client.get("/url-qui-n-existe-pas/")
    if erreur.status_code == 404 and "html" in erreur.headers.get("Content-Type", ""):
        pages.append(("404", erreur.content.decode(errors="replace")))

    assert len(pages) >= 55, f"{len(pages)} pages rendues : le balayage ne voit plus le site"
    # Un compte global ne dit pas QUOI manque : perdre une page sur quarante-sept
    # passe sous le seuil sans rien déclencher. On nomme donc la page dont
    # l'absence était justement passée inaperçue.
    assert "/" in {url for url, _ in pages}, "la page d'accueil n'est pas dans le balayage"
    return pages


def test_aucune_page_ne_saute_un_niveau_de_titre(client, db):
    """Un lecteur d'écran navigue de titre en titre : un h1 suivi d'un h3 lui
    présente un plan troué.

    Quatre formulaires de fiche étaient dans ce cas. Leurs sections « Affiche »
    et « Galerie » étaient des h3, et le seul h2 de la page était le panneau
    d'accessibilité du châssis — hors <main>, donc au-dessus du formulaire dans
    le plan. Le `<legend>Images</legend>` qui les groupe ne compense pas : un
    legend nomme un groupe de champs, il n'entre pas dans le plan du document.
    """
    import re

    fautives = []
    for url, html in _pages_sans_parametre(client):
        niveaux = [int(n) for n in re.findall(r"<h([1-6])\b", html)]
        for avant, apres in zip(niveaux, niveaux[1:], strict=False):
            if apres > avant + 1:
                fautives.append(f"{url} → h{avant} suivi de h{apres}")
                break

    assert not fautives, "plan de titres troué :\n  " + "\n  ".join(fautives)


def test_chaque_champ_de_formulaire_a_un_nom_accessible(client, db):
    """Un champ sans label s'annonce « zone de saisie, vide ».

    Les quatre champs d'une ligne de facture étaient dans ce cas : l'en-tête de
    colonne renseigne l'œil, jamais le lecteur d'écran. C'était sur l'écran qui
    porte la contrainte légale de numérotation.

    Trois formes de nom sont acceptées, et la deuxième avait d'abord manqué à ce
    contrôle — un `<label>` qui ENVELOPPE son champ est valide et n'a pas de
    `for` : sans elle, la mesure inventait des fautes là où il n'y en avait pas.
    """
    import re

    fautives = []
    for url, html in _pages_sans_parametre(client):
        corps = html.split('<main id="contenu"', 1)[-1].split("</main>", 1)[0]
        explicites = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', html))
        enveloppants = set()
        for bloc in re.findall(r"<label\b(?![^>]*\bfor=)[^>]*>(.*?)</label>", html, re.S):
            enveloppants |= set(re.findall(r'\bid="([^"]+)"', bloc))

        nus = []
        for champ in re.findall(r"<(?:input|select|textarea)\b[^>]*>", corps):
            if re.search(r'type="(hidden|submit|button|image)"', champ):
                continue
            if re.search(r"aria-label", champ):
                continue
            identifiant = re.search(r'\bid="([^"]+)"', champ)
            if identifiant and (
                identifiant.group(1) in explicites or identifiant.group(1) in enveloppants
            ):
                continue
            nus.append(identifiant.group(1) if identifiant else champ[:50])
        if nus:
            fautives.append(f"{url} → {', '.join(nus[:4])}")

    assert not fautives, "champ sans nom accessible :\n  " + "\n  ".join(fautives)


def test_aucune_reference_aria_ne_pointe_dans_le_vide(client, db):
    """Un `aria-describedby` vers un id absent est ignoré SANS BRUIT : l'aide
    s'affiche à l'écran et ne s'annonce jamais. Rien ne casse, rien ne prévient.

    Le dépôt portait deux conventions concurrentes. Django ≥ 5 pose lui-même
    l'attribut vers `<id>_helptext`, et vers `<id>_error` dès qu'un champ est en
    erreur ; un mixin maison le posait vers `<id>_aide`. Les formulaires qui
    passaient par le mixin étaient corrects, les autres pointaient dans le vide —
    dont l'inscription à un événement, publique, et la création d'une adhésion.
    Et personne ne rendait d'id sur les messages d'erreur, donc l'association
    manquait précisément là où elle sert : après un refus de validation.
    """
    import re

    pendantes = []
    for url, html in _pages_sans_parametre(client):
        presents = set(re.findall(r'\bid="([^"]+)"', html))
        for attribut in ("aria-describedby", "aria-labelledby", "aria-controls"):
            for valeur in re.findall(rf'{attribut}="([^"]+)"', html):
                for cible in valeur.split():
                    if cible not in presents:
                        pendantes.append(f"{url} → {attribut}={cible}")

    assert not pendantes, "référence aria dans le vide :\n  " + "\n  ".join(
        sorted(set(pendantes))[:15]
    )


def test_aucune_page_ne_porte_deux_fois_le_meme_identifiant(client, db):
    """Un id dupliqué casse `label for` — le clic met le focus dans le premier
    champ portant l'id, pas celui qu'on visait — et rend toute référence aria
    ambiguë.

    La page « Fichiers » était dans ce cas : elle inclut le même formulaire de
    création de dossier une fois par branche, et chaque copie rendait les mêmes
    `id_nom` et `id_description`.
    """
    import re
    from collections import Counter

    fautives = []
    for url, html in _pages_sans_parametre(client):
        # Aucune exception, y compris pour les gabarits `__prefix__` des
        # formsets : j'en avais posé une par précaution, et le test passe sans
        # elle. Elle écartait du calcul toute balise contenant `__prefix__`,
        # donc une vraie duplication qui s'y trouverait serait passée
        # inaperçue — pour couvrir un cas que le dépôt ne produit pas.
        doubles = [i for i, n in Counter(re.findall(r'\bid="([^"]+)"', html)).items() if n > 1]
        if doubles:
            fautives.append(f"{url} → {', '.join(sorted(doubles)[:4])}")

    assert not fautives, "identifiant rendu deux fois :\n  " + "\n  ".join(fautives)


def test_chaque_bouton_et_lien_a_un_nom_accessible(client, db):
    """Un contrôle réduit à une icône s'annonce « bouton » : un lecteur d'écran
    ne lit pas un pictogramme. Le nom peut venir du texte, d'un `aria-label` ou
    d'un `title` — l'`<svg aria-hidden>` du dépôt, lui, est muet par construction.
    """
    import re

    muets = []
    for url, html in _pages_sans_parametre(client):
        corps = html.split('<main id="contenu"', 1)[-1].split("</main>", 1)[0]
        for balise, contenu in re.findall(
            r"<(?:button|a)\b([^>]*)>(.*?)</(?:button|a)>", corps, re.S
        ):
            texte = re.sub(r"<[^>]+>", "", contenu).strip()
            if texte or re.search(r'aria-label(?:ledby)?="[^"]+"|title="[^"]+"', balise):
                continue
            muets.append(f"{url} → {balise.strip()[:60]}")

    assert not muets, "contrôle sans nom accessible :\n  " + "\n  ".join(sorted(set(muets))[:10])


def test_chaque_image_rendue_porte_un_texte_alternatif(client, db):
    """Règle 2 du dépôt : « pas de média sans alt ».

    Le modèle l'impose à l'envoi, mais rien ne garantissait que le GABARIT le
    rende : un `<img>` sans attribut `alt` du tout est annoncé par son nom de
    fichier, ce qui est pire que rien. Un `alt=""` reste valide et voulu — une
    image redondante avec le texte voisin ne doit PAS être annoncée deux fois —,
    donc le contrôle porte sur la présence de l'attribut, pas sur son contenu."""
    import re

    sans_alt = []
    for url, html in _pages_sans_parametre(client):
        corps = html.split('<main id="contenu"', 1)[-1].split("</main>", 1)[0]
        for balise in re.findall(r"<img\b[^>]*>", corps):
            if not re.search(r"\balt=", balise):
                sans_alt.append(f"{url} → {balise[:70]}")

    assert not sans_alt, "image sans attribut alt :\n  " + "\n  ".join(sorted(set(sans_alt))[:10])


def test_un_champ_refuse_relie_ses_messages_sans_dupliquer_d_identifiant():
    """L'état que le balayage ne visite PAS : un formulaire refusé.

    Django référence `<id>_error` dès qu'un champ porte une erreur. Le gabarit
    doit donc rendre cet id, UNE seule fois quel que soit le nombre de messages
    — deux spans le portant chacun rendraient la référence ambiguë — et laisser
    les messages s'empiler plutôt que se lire comme une seule phrase.
    """
    import re

    from django import forms
    from django.template.loader import render_to_string

    class FormulaireEprouve(forms.Form):
        code = forms.CharField(help_text="Trois lettres.")

        def clean_code(self):
            raise forms.ValidationError(["Première raison.", "Seconde raison."])

    formulaire = FormulaireEprouve(data={"code": "x"})
    assert not formulaire.is_valid()
    html = render_to_string("_champ.html", {"field": formulaire["code"]})

    cibles = set()
    for valeur in re.findall(r'aria-describedby="([^"]+)"', html):
        cibles |= set(valeur.split())
    assert "id_code_error" in cibles, f"l'erreur n'est pas reliée au champ : {cibles}"
    assert "id_code_helptext" in cibles, "l'aide cesse d'être reliée quand le champ est refusé"

    ids = re.findall(r'\bid="([^"]+)"', html)
    assert ids.count("id_code_error") == 1, f"id d'erreur rendu {ids.count('id_code_error')} fois"
    for cible in cibles:
        assert cible in ids, f"référence dans le vide : {cible}"

    assert html.count('class="champ__erreur"') == 2, "les deux messages ne sont plus deux blocs"
