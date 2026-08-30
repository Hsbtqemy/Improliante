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
            for numero, ligne in enumerate(gabarit.read_text().splitlines(), 1):
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
            texte = gabarit.read_text()
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
            texte = gabarit.read_text()
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
    groupes = set(re.findall(r'<summary class="nav-espace__titre">([^<]+)</summary>', rail.read_text()))
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
            trouve = re.search(r'page-tete__eyebrow">([^<]*)</span>', gabarit.read_text())
            if not trouve:
                continue
            controlees += 1
            sur_titre = trouve.group(1)
            if gabarit.name == RACINE:
                if sur_titre != "Gestion":
                    fautifs.append(f"{gabarit.name} : racine, attendu « Gestion », lu « {sur_titre} »")
            elif not (
                sur_titre.startswith("Gestion · ") and sur_titre[len("Gestion · ") :] in groupes
            ):
                fautifs.append(f"{gabarit.name} : « {sur_titre} » n'est pas « Gestion · <groupe> »")

    assert controlees >= 30, f"{controlees} pages contrôlées : la boucle ne voit plus les gabarits"
    assert not fautifs, "sur-titre qui ne nomme pas son groupe de rail :\n  " + "\n  ".join(fautifs)
