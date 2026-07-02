"""Services métier du domaine « Spectacles / Projets ».

Gestion des images d'un spectacle — l'affiche (image principale) et la galerie
(plusieurs images ordonnées). Chaque image crée un `Media` du socle, avec un
`alt` OBLIGATOIRE (accessibilité, cf. CLAUDE.md règle 2). La logique vit ici,
pas dans les vues (les vues orchestrent et rendent le retour utilisateur).

Note : les `Media` sont un socle réutilisable ; retirer une image de la galerie
ou l'affiche détache le lien mais ne supprime pas le `Media` lui-même.
"""

from __future__ import annotations

from django.db.models import Max

from apps.medias.models import Media

from .models import ImageSpectacle, Spectacle


def definir_affiche(spectacle: Spectacle, fichier, alt: str, *, cree_par=None) -> Media:
    """Crée un `Media` image et le pose comme affiche du spectacle."""
    media = Media.objects.create(
        type_media=Media.TypeMedia.IMAGE,
        fichier=fichier,
        alt=alt,
        cree_par=cree_par,
    )
    spectacle.affiche = media
    spectacle.save(update_fields=["affiche", "date_modification"])
    return media


def retirer_affiche(spectacle: Spectacle) -> None:
    """Détache l'affiche du spectacle (le `Media` reste dans le socle)."""
    if spectacle.affiche_id is None:
        return
    spectacle.affiche = None
    spectacle.save(update_fields=["affiche", "date_modification"])


def ajouter_image_galerie(
    spectacle: Spectacle, fichier, alt: str, *, cree_par=None
) -> ImageSpectacle:
    """Ajoute une image à la galerie du spectacle, placée en fin d'ordre."""
    media = Media.objects.create(
        type_media=Media.TypeMedia.IMAGE,
        fichier=fichier,
        alt=alt,
        cree_par=cree_par,
    )
    dernier_ordre = spectacle.images.aggregate(max=Max("ordre"))["max"]
    return ImageSpectacle.objects.create(
        spectacle=spectacle,
        media=media,
        ordre=(dernier_ordre or 0) + 1,
    )


def retirer_images_galerie(spectacle: Spectacle, ids) -> int:
    """Retire de la galerie les images dont l'id est dans `ids`.

    Le queryset est BORNÉ au spectacle passé (anti-IDOR) : impossible de
    supprimer par id l'image d'un autre spectacle. Renvoie le nombre retiré.
    """
    qs = ImageSpectacle.objects.filter(spectacle=spectacle, pk__in=ids)
    nombre, _ = qs.delete()
    return nombre
