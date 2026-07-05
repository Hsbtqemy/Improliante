"""Services du domaine « Documents / GED ».

Le versionnement conserve l'historique : une nouvelle version devient la version
courante, l'ancienne est gardée (`courant=False`) et reliée par `remplace`.

Les fonctions `*_membre` gèrent l'espace « Mes fichiers » : elles supposent que
la vue appelante a **déjà prouvé la propriété** (filtre `proprietaire=membre`) ;
leur rôle est de maintenir l'invariant d'arbre (un sous-arbre = un seul
propriétaire) et de centraliser la logique hors des vues.
"""

from __future__ import annotations

from django.db import transaction

from .models import Document, Dossier


class DossierNonVide(Exception):
    """Levée lors d'une tentative de suppression d'un dossier non vide."""


@transaction.atomic
def creer_dossier_membre(membre, *, nom, description="", visibilite=None, parent=None) -> Dossier:
    """Crée un dossier PERSONNEL appartenant à `membre` (racine ou sous-dossier).

    Invariant de branche : un sous-dossier hérite de la **visibilité** (et donc
    de la branche Perso/Bureau) de son parent ; `visibilite` n'est requis que
    pour une racine."""
    if parent is not None:
        visibilite = parent.visibilite
    donnees = {
        "nom": nom,
        "description": description,
        "espace": Dossier.Espace.PERSO,
        "visibilite": visibilite,
        "proprietaire": membre,
    }
    if parent is not None:
        return parent.add_child(**donnees)
    return Dossier.add_root(**donnees)


@transaction.atomic
def creer_dossier_commun(*, nom, description="", parent=None) -> Dossier:
    """Crée un dossier de l'espace COMMUN (troupe collaborative), sans propriétaire."""
    donnees = {
        "nom": nom,
        "description": description,
        "espace": Dossier.Espace.COMMUN,
        "proprietaire": None,
    }
    if parent is not None:
        return parent.add_child(**donnees)
    return Dossier.add_root(**donnees)


def televerser_fichier(dossier, *, titre, fichier, description="", par) -> Document:
    """Dépose un fichier dans un dossier (personnel ou commun).

    L'audience est portée par le dossier ; la `confidentialite` du Document n'est
    pas consultée hors espace association."""
    return Document.objects.create(
        titre=titre,
        dossier=dossier,
        fichier=fichier,
        description=description,
        cree_par=par,
    )


# Rétro-compatibilité : ancien nom explicite « membre » (mêmes effets).
def televerser_fichier_membre(membre, dossier, *, titre, fichier, description="", par) -> Document:
    """Dépose un fichier dans un dossier de `membre` (cf. `televerser_fichier`)."""
    return televerser_fichier(
        dossier, titre=titre, fichier=fichier, description=description, par=par
    )


def modifier_dossier_membre(dossier, *, nom, description, visibilite) -> Dossier:
    """Renomme / redécrit / change la visibilité d'un dossier de membre."""
    dossier.nom = nom
    dossier.description = description
    dossier.visibilite = visibilite
    dossier.save(update_fields=["nom", "description", "visibilite"])
    return dossier


def renommer_dossier(dossier, *, nom, description) -> Dossier:
    """Renomme / redécrit un dossier (espace commun : pas de visibilité)."""
    dossier.nom = nom
    dossier.description = description
    dossier.save(update_fields=["nom", "description"])
    return dossier


def supprimer_dossier_membre(dossier) -> None:
    """Supprime un dossier de membre **vide** (sans sous-dossier ni document).

    Lève `DossierNonVide` sinon (on ne supprime jamais en cascade des fichiers
    sans le vouloir explicitement)."""
    if dossier.get_children().exists() or dossier.documents.exists():
        raise DossierNonVide("Le dossier doit être vide pour être supprimé.")
    dossier.delete()


def supprimer_document_membre(document) -> None:
    """Supprime un fichier de membre : efface aussi le fichier physique."""
    document.fichier.delete(save=False)
    document.delete()


@transaction.atomic
def remplacer_document(ancien: Document, *, fichier, par=None) -> Document:
    """Crée une nouvelle version d'un document.

    Le nouveau document reprend les métadonnées de l'ancien (titre, dossier,
    confidentialité…), incrémente la version et devient courant ; l'ancien est
    conservé mais n'est plus courant (historique consultable)."""
    nouveau = Document.objects.create(
        titre=ancien.titre,
        dossier=ancien.dossier,
        fichier=fichier,
        description=ancien.description,
        confidentialite=ancien.confidentialite,
        version=ancien.version + 1,
        remplace=ancien,
        courant=True,
        date_validite=ancien.date_validite,
        cree_par=par,
    )
    ancien.courant = False
    ancien.save(update_fields=["courant"])
    return nouveau
