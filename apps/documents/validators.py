"""Validation des fichiers téléversés dans la GED (cahier §10 : type + taille).

On reste volontairement sans dépendance native (pas de python-magic/libmagic) :
la vérification du « type réel » par sniffing des octets nécessiterait une lib
système. On combine donc un **plafond de taille** et une **liste noire
d'extensions exécutables/scripts**, ce qui reste fidèle à « tout type de fichier »
tout en écartant les binaires manifestement dangereux. Les fichiers sont par
ailleurs servis en pièce jointe (``attachment``), jamais rendus inline.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from django import forms

# 20 Mio : large pour des PDF/images/scans, raisonnable pour du stockage privé.
TAILLE_MAX_DOCUMENT = 20 * 1024 * 1024

# Extensions d'exécutables / scripts refusées (défense simple, sans sniffing).
EXTENSIONS_INTERDITES = frozenset(
    {
        ".exe",
        ".msi",
        ".bat",
        ".cmd",
        ".com",
        ".scr",
        ".pif",
        ".dll",
        ".js",
        ".jse",
        ".vbs",
        ".vbe",
        ".ps1",
        ".psm1",
        ".sh",
        ".jar",
        ".apk",
        ".app",
        ".hta",
        ".cpl",
        ".msc",
        ".reg",
        ".wsf",
        ".gadget",
    }
)


def valider_fichier_document(fichier):
    """Valide un fichier téléversé : taille plafonnée + extension non exécutable.

    Renvoie le fichier tel quel (pour un usage direct en ``clean_fichier``).
    Lève ``forms.ValidationError`` si le fichier est trop volumineux ou porte une
    extension interdite. ``None`` (aucun fichier) passe sans erreur : l'obligation
    du champ est gérée par le formulaire.
    """
    if not fichier:
        return fichier
    if fichier.size > TAILLE_MAX_DOCUMENT:
        limite = TAILLE_MAX_DOCUMENT // (1024 * 1024)
        raise forms.ValidationError(f"Fichier trop volumineux ({limite} Mio maximum).")
    extension = PurePosixPath(fichier.name).suffix.lower()
    if extension in EXTENSIONS_INTERDITES:
        raise forms.ValidationError("Ce type de fichier n'est pas autorisé.")
    return fichier
