"""Instantané d'émission : figer ce qu'une pièce disait d'elle-même.

Le PDF archivé EST la pièce. Cet instantané existe pour le jour où ce fichier
disparaît — stockage restauré à moitié, fichier effacé par mégarde : il permet de
RECONSTRUIRE le document tel qu'il a été émis, au lieu de le recalculer depuis
les données du jour. Entre-temps l'association a pu déménager, le client changer
de nom, le signataire quitter le bureau ; rien de tout cela n'appartient à une
pièce déjà émise.

Le fac-similé de signature en fait partie, et ce n'est pas un luxe : le PDF de la
pièce est lui-même rendu depuis cet instantané, si bien que l'écarter reviendrait
à délivrer des documents non signés. Son poids n'est pas un argument — le PDF
embarque déjà la même image.
"""

from __future__ import annotations

from types import SimpleNamespace

# Tout ce que les gabarits PDF lisent des paramètres de l'association.
CHAMPS_EMETTEUR = (
    "nom",
    "adresse",
    "code_postal",
    "ville",
    "numero_rna",
    "numero_siret",
    "article_cgi",
    "iban",
    "bic",
    "mention_tva",
)
CHAMPS_SIGNATAIRE = ("nom", "qualite", "mention_delegation")


def emetteur(params) -> dict:
    """Fige l'association émettrice (`ParametresAssociation`)."""
    return {champ: getattr(params, champ) for champ in CHAMPS_EMETTEUR}


def signataire(signataire_) -> dict | None:
    """Fige l'identité du signataire et son fac-similé, ou None s'il n'y en a pas.

    L'image est figée telle qu'apposée : remplacer plus tard la signature d'un
    signataire ne doit pas changer une pièce déjà délivrée."""
    if signataire_ is None:
        return None
    fige = {champ: getattr(signataire_, champ) for champ in CHAMPS_SIGNATAIRE}
    # `image_base64` est une MÉTHODE : la figer sans l'appeler stockerait l'objet
    # méthode, que JSON refuse. Le gabarit, lui, reçoit ici une simple chaîne.
    fige["image_base64"] = signataire_.image_base64() or ""
    return fige


def en_objet(valeurs: dict | None):
    """Rend une part d'instantané lisible par un gabarit.

    Les gabarits PDF sont écrits pour des modèles — `asso.nom`,
    `facture.client.ville` — et un dictionnaire ne répond pas à cette syntaxe en
    profondeur. Leur passer des espaces de noms évite d'écrire une seconde
    version de chaque gabarit, qui finirait par diverger de la première."""
    return SimpleNamespace(**valeurs) if valeurs else None
