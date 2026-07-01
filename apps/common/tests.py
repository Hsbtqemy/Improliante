"""Tests du service de modération partagé (`apps.common.moderation`).

On teste sur un modèle concret héritant du mixin `Moderation` — ici
`Spectacle` — puisque le service opère sur n'importe quelle fiche modérée.
"""

from __future__ import annotations

import pytest

from apps.common.models import Moderation
from apps.common.moderation import (
    TransitionModerationInvalide,
    peut_etre_edite_par_auteur,
    soumettre_a_moderation,
)
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
