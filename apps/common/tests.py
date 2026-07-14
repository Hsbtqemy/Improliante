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
