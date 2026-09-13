"""Traitement des images téléversées : réduction et vignette.

Une photo de téléphone fait 4 000 px et quelques mégaoctets, et habillait telle
quelle une carte de 300 px. Chaque image est donc ramenée à une largeur de
travail (`LARGEUR_MAX`) et flanquée d'une **vignette** (`LARGEUR_VIGNETTE`) que
les gabarits proposent en `srcset` — le téléphone télécharge la petite. Les
dimensions sont conservées pour que chaque `<img>` réserve sa place.

Le format d'entrée est **conservé** (JPEG reste JPEG, PNG reste PNG) :
réencoder ailleurs obligerait à renommer le fichier, donc à changer son URL,
pour un gain marginal — et une image à fond transparent perdrait sa
transparence en JPEG.
"""

from __future__ import annotations

import io
from pathlib import PurePosixPath

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

from .models import Media

LARGEUR_MAX = 2000
LARGEUR_VIGNETTE = 600
QUALITE_JPEG = 82
# Formats que Pillow réécrit sans surprise. Un GIF (souvent animé) et tout le
# reste sont laissés INTACTS : réencoder un GIF animé le figerait.
FORMATS_TRAITES = {"JPEG", "PNG", "WEBP"}


def preparer_media(media: Media) -> bool:
    """Réduit l'image du média et produit sa vignette.

    Retourne True si quelque chose a changé (donc s'il faut ré-enregistrer).
    Silencieux quand le fichier est absent, illisible ou d'un format qu'on ne
    réécrit pas : ce traitement est un confort, il ne doit jamais faire échouer
    un téléversement. La validation du formulaire, elle, refuse déjà ce qui
    n'est pas une image.
    """
    if media.type_media != Media.TypeMedia.IMAGE or not media.fichier:
        return False
    if media.largeur and (media.vignette or media.largeur <= LARGEUR_VIGNETTE):
        return False  # déjà traité : on ne rouvre pas le fichier à chaque save
    image = _ouvrir(media)
    if image is None:
        return False
    with image:
        if image.format not in FORMATS_TRAITES:
            return False
        format_source = image.format
        # Redresse selon l'orientation EXIF : sans quoi une photo prise à la
        # verticale se retrouve couchée une fois réencodée.
        image = ImageOps.exif_transpose(image)

        if image.width > LARGEUR_MAX:
            image = _reduire(image, LARGEUR_MAX)
            _reecrire_en_place(media.fichier, _encoder(image, format_source))
        media.largeur, media.hauteur = image.size

        if image.width > LARGEUR_VIGNETTE:
            vignette = _reduire(image, LARGEUR_VIGNETTE)
            media.vignette.save(
                _nom_vignette(media.fichier.name),
                ContentFile(_encoder(vignette, format_source)),
                save=False,
            )
            media.vignette_largeur, media.vignette_hauteur = vignette.size
    return True


def _ouvrir(media: Media) -> Image.Image | None:
    """Ouvre l'image du média, ou None si le fichier est absent/illisible."""
    try:
        with media.fichier.open("rb") as source:
            image = Image.open(source)
            image.load()
        return image
    except Exception:  # noqa: BLE001 — fichier manquant, tronqué, non image…
        return None


def _reduire(image: Image.Image, largeur: int) -> Image.Image:
    """Copie réduite à `largeur`, hauteur proportionnelle (jamais agrandie)."""
    hauteur = round(image.height * largeur / image.width)
    return image.resize((largeur, hauteur), Image.LANCZOS)


def _encoder(image: Image.Image, format_source: str) -> bytes:
    """Encode l'image dans SON format d'origine, en aplatissant si besoin."""
    tampon = io.BytesIO()
    if format_source == "JPEG":
        # Le JPEG ne connaît pas la transparence : une image RGBA/P lèverait.
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.save(tampon, "JPEG", quality=QUALITE_JPEG, optimize=True, progressive=True)
    else:
        image.save(tampon, format_source, optimize=True)
    return tampon.getvalue()


def _reecrire_en_place(champ, octets: bytes) -> None:
    """Réécrit le fichier sous le MÊME nom.

    Passer par `champ.save()` ferait naître un second fichier — Django suffixe
    un nom déjà pris — et changerait l'URL en laissant l'original derrière.
    L'image vient d'être téléversée : personne ne l'a encore vue."""
    nom = champ.name
    champ.storage.delete(nom)
    champ.storage.save(nom, ContentFile(octets))


def _nom_vignette(nom_fichier: str) -> str:
    chemin = PurePosixPath(nom_fichier)
    return f"{chemin.stem}-vignette{chemin.suffix}"
