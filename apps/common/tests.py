"""Tests du service de modération partagé (`apps.common.moderation`).

On teste sur un modèle concret héritant du mixin `Moderation` — ici
`Spectacle` — puisque le service opère sur n'importe quelle fiche modérée.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.common.fichiers import reponse_fichier_prive
from apps.common.models import Moderation
from apps.common.moderation import (
    TransitionModerationInvalide,
    peut_etre_edite_par_auteur,
    soumettre_a_moderation,
)
from apps.documents.models import Document
from apps.spectacles.models import Spectacle

Statut = Moderation.StatutModeration


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


@pytest.mark.parametrize(
    ("statut", "attendu"),
    [
        (Statut.BROUILLON, True),
        (Statut.REFUSE, True),
        (Statut.PROPOSE, False),
        (Statut.PUBLIE, False),
    ],
)
def test_peut_etre_edite_par_auteur(db, statut, attendu):
    projet = Spectacle.objects.create(titre="X", statut_moderation=statut)
    assert peut_etre_edite_par_auteur(projet) is attendu


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
