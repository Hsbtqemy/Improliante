"""Tests du module de rôles (`apps.coeur.roles`)."""

from __future__ import annotations

from django.contrib.auth.models import Group

from apps.coeur.models import Utilisateur
from apps.coeur.roles import NOM_GROUPE_BUREAU, est_bureau


def test_utilisateur_lambda_n_est_pas_bureau(db):
    user = Utilisateur.objects.create_user(username="lambda", password="x")
    assert est_bureau(user) is False


def test_membre_du_groupe_bureau_est_bureau(db):
    user = Utilisateur.objects.create_user(username="secretaire", password="x")
    groupe, _ = Group.objects.get_or_create(name=NOM_GROUPE_BUREAU)
    user.groups.add(groupe)
    assert est_bureau(user) is True


def test_staff_est_bureau(db):
    user = Utilisateur.objects.create_user(username="admin", password="x", is_staff=True)
    assert est_bureau(user) is True


def test_compte_inactif_n_est_pas_bureau(db):
    user = Utilisateur.objects.create_user(
        username="ancien", password="x", is_staff=True, is_active=False
    )
    assert est_bureau(user) is False
