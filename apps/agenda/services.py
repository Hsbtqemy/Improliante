"""Services métier du domaine « Agenda ».

Gestion des images d'un événement — l'affiche (image principale) et la galerie
(plusieurs images ordonnées). Miroir de `apps.spectacles.services` : chaque image
crée un `Media` du socle, avec un `alt` OBLIGATOIRE (accessibilité, cf. CLAUDE.md
règle 2). La logique vit ici, pas dans les vues.

Note : les `Media` sont un socle réutilisable ; retirer une image de la galerie
ou l'affiche détache le lien mais ne supprime pas le `Media` lui-même.
"""

from __future__ import annotations

from django.db.models import Max

from apps.medias.models import Media

from .models import Evenement, ImageEvenement


def definir_affiche(evenement: Evenement, fichier, alt: str, *, cree_par=None) -> Media:
    """Crée un `Media` image et le pose comme affiche de l'événement."""
    media = Media.objects.create(
        type_media=Media.TypeMedia.IMAGE,
        fichier=fichier,
        alt=alt,
        cree_par=cree_par,
    )
    evenement.affiche = media
    evenement.save(update_fields=["affiche", "date_modification"])
    return media


def retirer_affiche(evenement: Evenement) -> None:
    """Détache l'affiche de l'événement (le `Media` reste dans le socle)."""
    if evenement.affiche_id is None:
        return
    evenement.affiche = None
    evenement.save(update_fields=["affiche", "date_modification"])


def ajouter_image_galerie(
    evenement: Evenement, fichier, alt: str, *, cree_par=None
) -> ImageEvenement:
    """Ajoute une image à la galerie de l'événement, placée en fin d'ordre."""
    media = Media.objects.create(
        type_media=Media.TypeMedia.IMAGE,
        fichier=fichier,
        alt=alt,
        cree_par=cree_par,
    )
    dernier_ordre = evenement.images.aggregate(max=Max("ordre"))["max"]
    return ImageEvenement.objects.create(
        evenement=evenement,
        media=media,
        ordre=(dernier_ordre or 0) + 1,
    )


def retirer_images_galerie(evenement: Evenement, ids) -> int:
    """Retire de la galerie les images dont l'id est dans `ids`.

    Le queryset est BORNÉ à l'événement passé (anti-IDOR) : impossible de
    supprimer par id l'image d'un autre événement. Renvoie le nombre retiré.
    """
    qs = ImageEvenement.objects.filter(evenement=evenement, pk__in=ids)
    nombre, _ = qs.delete()
    return nombre
