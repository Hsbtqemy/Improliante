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


class DeplacementInterdit(Exception):
    """Levée quand un déplacement casserait un invariant de l'arbre.

    Trois cas : la cible est le dossier lui-même ou l'un de ses descendants
    (l'arbre y perdrait sa racine), elle vit dans un autre espace, ou — dans
    l'espace personnel — elle appartient à quelqu'un d'autre."""


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


@transaction.atomic
def creer_dossier_association(*, nom, description="", parent=None) -> Dossier:
    """Crée un dossier de l'espace ASSOCIATION (GED officielle du bureau), sans propriétaire."""
    donnees = {
        "nom": nom,
        "description": description,
        "espace": Dossier.Espace.ASSOCIATION,
        "proprietaire": None,
    }
    if parent is not None:
        return parent.add_child(**donnees)
    return Dossier.add_root(**donnees)


def televerser_fichier(
    dossier, *, titre, fichier, description="", par, confidentialite=None, date_validite=None
):
    """Dépose un fichier dans un dossier (personnel, commun ou association).

    L'audience est en général portée par le dossier ; pour l'espace ASSOCIATION,
    le bureau fixe la `confidentialite` (sinon le défaut du modèle) et une
    éventuelle `date_validite`."""
    donnees = {
        "titre": titre,
        "dossier": dossier,
        "fichier": fichier,
        "description": description,
        "cree_par": par,
    }
    if confidentialite is not None:
        donnees["confidentialite"] = confidentialite
    if date_validite is not None:
        donnees["date_validite"] = date_validite
    return Document.objects.create(**donnees)


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


@transaction.atomic
def deplacer_dossier(dossier: Dossier, *, nouveau_parent: Dossier | None) -> Dossier:
    """Déplace un dossier sous `nouveau_parent`, ou à la racine si None.

    Le déplacement respecte les deux invariants du modèle. Le premier tient à
    l'arbre : on ne descend pas un dossier dans son propre sous-arbre, sous
    peine de détacher toute la branche. Le second tient à la confidentialité,
    et c'est le vrai sujet — **la visibilité s'hérite du parent**. Déplacer un
    dossier « Privé » sous un dossier « Partagé » ouvrirait son contenu à toute
    la troupe ; l'alignement est donc explicite et PROPAGÉ à tout le sous-arbre,
    plutôt que laissé à un dossier qui afficherait « Privé » en vivant dans une
    branche partagée. L'appelant doit prévenir l'utilisateur de ce que ça change.

    Le changement d'espace est refusé net : rien ne justifie qu'un dossier
    personnel devienne un document officiel de l'association par glissement, et
    l'inverse ferait fuiter des pièces du bureau vers un membre.

    La vue appelante reste responsable de prouver la propriété (règle 1) : ce
    service maintient les invariants, il n'autorise pas.
    """
    # Rechargement OBLIGATOIRE, et ce n'est pas de la prudence décorative :
    # `node_order_by = ["nom"]` fait renuméroter les chemins matérialisés à
    # chaque création. Créer « Archives » après « Photos » renumérote les deux,
    # et l'instance « Photos » qu'on tenait garde un `path` périmé. `move`
    # travaille alors sur un chemin qui ne désigne plus le bon nœud, et ne
    # déplace rien — sans lever la moindre erreur.
    dossier = Dossier.objects.get(pk=dossier.pk)
    if nouveau_parent is not None:
        nouveau_parent = Dossier.objects.get(pk=nouveau_parent.pk)

    if nouveau_parent is not None:
        if nouveau_parent.pk == dossier.pk:
            raise DeplacementInterdit("Un dossier ne peut pas être déplacé dans lui-même.")
        if nouveau_parent.is_descendant_of(dossier):
            raise DeplacementInterdit(
                "Un dossier ne peut pas être déplacé dans l'un de ses sous-dossiers."
            )
        if nouveau_parent.espace != dossier.espace:
            raise DeplacementInterdit("Un dossier ne change pas d'espace en étant déplacé.")
        if (
            dossier.espace == Dossier.Espace.PERSO
            and nouveau_parent.proprietaire_id != dossier.proprietaire_id
        ):
            raise DeplacementInterdit("Un dossier personnel reste chez son propriétaire.")

    if nouveau_parent is None:
        racine = dossier.get_root()
        if racine.pk == dossier.pk:
            return dossier  # déjà à la racine : rien à faire
        # `sorted-sibling` est imposé par `node_order_by` : l'arbre se range
        # tout seul par nom, il n'y a pas de position à choisir.
        dossier.move(racine, "sorted-sibling")
    else:
        dossier.move(nouveau_parent, "sorted-child")
        _propager_visibilite(dossier.pk, nouveau_parent.visibilite)

    return Dossier.objects.get(pk=dossier.pk)


def _propager_visibilite(dossier_pk: int, visibilite: str) -> None:
    """Aligne un dossier et tout son sous-arbre sur une visibilité.

    Relu depuis la base : `move` a réécrit les chemins matérialisés, et
    l'instance qu'on tenait avant le déplacement ne connaît plus ses
    descendants."""
    dossier = Dossier.objects.get(pk=dossier_pk)
    if dossier.espace != Dossier.Espace.PERSO:
        return  # la visibilité ne s'applique qu'à l'espace personnel
    pks = [dossier.pk, *dossier.get_descendants().values_list("pk", flat=True)]
    Dossier.objects.filter(pk__in=pks).update(visibilite=visibilite)
