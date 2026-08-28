"""Tests du domaine « Documents / GED » : versionnement et déplacement.

Le déplacement est une zone à risque : il touche à la confidentialité (la
visibilité s'hérite du parent) et à l'intégrité de l'arbre. Traité test-first,
comme le demande CLAUDE.md pour ces zones-là.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.coeur.models import Membre, Utilisateur
from apps.documents.models import Document, Dossier
from apps.documents.services import (
    DeplacementInterdit,
    creer_dossier_association,
    creer_dossier_membre,
    deplacer_dossier,
    remplacer_document,
)


def _document(**extra):
    donnees = {
        "titre": "Statuts",
        "confidentialite": Document.Confidentialite.MEMBRES,
        "fichier": SimpleUploadedFile("statuts.pdf", b"v1", content_type="application/pdf"),
    }
    donnees.update(extra)
    return Document.objects.create(**donnees)


def test_remplacer_document_cree_une_nouvelle_version_courante(db):
    ancien = _document()
    nouveau = remplacer_document(
        ancien,
        fichier=SimpleUploadedFile("statuts-v2.pdf", b"v2", content_type="application/pdf"),
    )
    ancien.refresh_from_db()
    assert nouveau.version == 2
    assert nouveau.courant is True
    assert nouveau.remplace == ancien
    assert nouveau.titre == ancien.titre
    assert nouveau.confidentialite == ancien.confidentialite
    # L'ancienne version est conservée mais n'est plus courante.
    assert ancien.courant is False


def test_versions_successives_incrementent(db):
    v1 = _document()
    v2 = remplacer_document(v1, fichier=SimpleUploadedFile("v2.pdf", b"v2"))
    v3 = remplacer_document(v2, fichier=SimpleUploadedFile("v3.pdf", b"v3"))
    assert [v1.version, v2.version, v3.version] == [1, 2, 3]
    assert Document.objects.filter(courant=True).count() == 1  # seule v3 est courante


# --- Déplacement de dossier -------------------------------------------------


def _membre(username="alice"):
    return Membre.objects.create(
        user=Utilisateur.objects.create_user(username=username, password="x")
    )


def test_deplacer_un_dossier_le_range_sous_sa_nouvelle_cible(db):
    membre = _membre()
    source = creer_dossier_membre(membre, nom="Photos", visibilite=Dossier.Visibilite.PRIVE)
    cible = creer_dossier_membre(membre, nom="Archives", visibilite=Dossier.Visibilite.PRIVE)

    deplace = deplacer_dossier(source, nouveau_parent=cible)

    assert deplace.get_parent().pk == cible.pk
    assert deplace.is_descendant_of(cible)


def test_deplacer_vers_la_racine_detache_le_dossier(db):
    membre = _membre()
    racine = creer_dossier_membre(membre, nom="Archives", visibilite=Dossier.Visibilite.PRIVE)
    enfant = creer_dossier_membre(membre, nom="2025", parent=racine)

    deplace = deplacer_dossier(enfant, nouveau_parent=None)

    assert deplace.get_parent() is None
    assert deplace.get_depth() == 1


def test_un_dossier_ne_se_deplace_pas_dans_lui_meme(db):
    membre = _membre()
    dossier = creer_dossier_membre(membre, nom="Photos", visibilite=Dossier.Visibilite.PRIVE)

    with pytest.raises(DeplacementInterdit):
        deplacer_dossier(dossier, nouveau_parent=dossier)


def test_un_dossier_ne_se_deplace_pas_dans_son_propre_sous_dossier(db):
    """Le cas qui détacherait toute la branche de l'arbre."""
    membre = _membre()
    parent = creer_dossier_membre(membre, nom="Photos", visibilite=Dossier.Visibilite.PRIVE)
    enfant = creer_dossier_membre(membre, nom="2025", parent=parent)

    with pytest.raises(DeplacementInterdit):
        deplacer_dossier(parent, nouveau_parent=enfant)


def test_un_dossier_ne_change_pas_d_espace_en_etant_deplace(db):
    """Sinon un dossier personnel deviendrait un document officiel, et une
    pièce du bureau atterrirait chez un membre."""
    membre = _membre()
    perso = creer_dossier_membre(membre, nom="Photos", visibilite=Dossier.Visibilite.PRIVE)
    officiel = creer_dossier_association(nom="Statuts")

    with pytest.raises(DeplacementInterdit):
        deplacer_dossier(perso, nouveau_parent=officiel)
    with pytest.raises(DeplacementInterdit):
        deplacer_dossier(officiel, nouveau_parent=perso)


def test_un_dossier_personnel_reste_chez_son_proprietaire(db):
    """Règle 1 : le déplacement ne doit pas servir de passe-droit vers l'espace
    d'un autre membre."""
    alice = _membre("alice")
    bob = _membre("bob")
    a_alice = creer_dossier_membre(alice, nom="Photos", visibilite=Dossier.Visibilite.PRIVE)
    a_bob = creer_dossier_membre(bob, nom="Archives", visibilite=Dossier.Visibilite.PRIVE)

    with pytest.raises(DeplacementInterdit):
        deplacer_dossier(a_alice, nouveau_parent=a_bob)


def test_le_deplacement_aligne_la_visibilite_sur_le_nouveau_parent(db):
    """Un dossier « Privé » rangé sous un dossier « Partagé » ne peut pas
    rester privé : il vivrait dans une branche partagée en prétendant le
    contraire."""
    membre = _membre()
    prive = creer_dossier_membre(membre, nom="Brouillons", visibilite=Dossier.Visibilite.PRIVE)
    partage = creer_dossier_membre(membre, nom="Troupe", visibilite=Dossier.Visibilite.PARTAGE)

    deplace = deplacer_dossier(prive, nouveau_parent=partage)

    assert deplace.visibilite == Dossier.Visibilite.PARTAGE


def test_le_deplacement_propage_la_visibilite_a_tout_le_sous_arbre(db):
    """Le point qui coûte cher s'il est raté : déplacer un dossier expose AUSSI
    ce qu'il contient, aussi profond soit-il."""
    membre = _membre()
    prive = creer_dossier_membre(membre, nom="Brouillons", visibilite=Dossier.Visibilite.PRIVE)
    enfant = creer_dossier_membre(membre, nom="2025", parent=prive)
    petit_enfant = creer_dossier_membre(membre, nom="Janvier", parent=enfant)
    partage = creer_dossier_membre(membre, nom="Troupe", visibilite=Dossier.Visibilite.PARTAGE)

    deplacer_dossier(prive, nouveau_parent=partage)

    enfant.refresh_from_db()
    petit_enfant.refresh_from_db()
    assert enfant.visibilite == Dossier.Visibilite.PARTAGE
    assert petit_enfant.visibilite == Dossier.Visibilite.PARTAGE


def test_le_deplacement_emmene_les_documents_du_sous_arbre(db):
    """Les documents suivent leur dossier : ils ne sont pas rattachés à un
    chemin, mais au dossier lui-même."""
    membre = _membre()
    source = creer_dossier_membre(membre, nom="Photos", visibilite=Dossier.Visibilite.PRIVE)
    cible = creer_dossier_membre(membre, nom="Archives", visibilite=Dossier.Visibilite.PRIVE)
    doc = _document(dossier=source)

    deplacer_dossier(source, nouveau_parent=cible)

    doc.refresh_from_db()
    assert doc.dossier.pk == source.pk
    assert doc.dossier.get_parent().pk == cible.pk
