"""Services métier du domaine « Agenda ».

Gestion des images d'un événement — l'affiche (image principale) et la galerie
(plusieurs images ordonnées). Miroir de `apps.spectacles.services` : chaque image
crée un `Media` du socle, avec un `alt` OBLIGATOIRE (accessibilité, cf. CLAUDE.md
règle 2). La logique vit ici, pas dans les vues.

Note : les `Media` sont un socle réutilisable ; retirer une image de la galerie
ou l'affiche détache le lien mais ne supprime pas le `Media` lui-même.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Max, Sum

from apps.medias.models import Media

from .models import Evenement, ImageEvenement, Inscription


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


# --- Inscriptions du public (VIT-2) -----------------------------------------


class InscriptionFermee(Exception):
    """L'événement n'accueille pas d'inscription (pas de jauge renseignée)."""


class PlusAssezDePlaces(Exception):
    """La demande dépasse ce qu'il reste — la jauge fait foi."""


def places_prises(evenement: Evenement) -> int:
    """Places déjà réservées, annulations exclues."""
    total = evenement.inscriptions.filter(annulee=False).aggregate(total=Sum("places"))
    return total["total"] or 0


def places_restantes(evenement: Evenement) -> int | None:
    """Places encore disponibles, ou None si l'événement n'ouvre pas d'inscription."""
    if evenement.places_max is None:
        return None
    return max(0, evenement.places_max - places_prises(evenement))


@transaction.atomic
def inscrire(evenement: Evenement, *, nom: str, email: str, places: int = 1) -> Inscription:
    """Réserve des places, sous verrou, ou refuse.

    Le verrou n'est pas décoratif : c'est TOUT le sujet de cette fonction. Lire
    les places restantes puis écrire l'inscription sans sérialiser laisse deux
    demandes concurrentes lire le même « il reste une place » et la réserver
    chacune — la jauge est alors dépassée et quelqu'un se présente le soir sans
    siège. `select_for_update` sur l'événement fait attendre la seconde demande
    jusqu'à ce que la première ait écrit.

    Le verrou porte sur l'ÉVÉNEMENT et non sur les inscriptions : c'est lui la
    ressource disputée, et il existe déjà quand la première réservation arrive.
    """
    verrouille = Evenement.objects.select_for_update().get(pk=evenement.pk)

    if verrouille.places_max is None:
        raise InscriptionFermee("Cet événement n'accueille pas d'inscription.")
    if places < 1:
        raise PlusAssezDePlaces("Il faut réserver au moins une place.")

    restantes = verrouille.places_max - places_prises(verrouille)
    if places > restantes:
        raise PlusAssezDePlaces(
            f"Il ne reste que {restantes} place(s) pour cet événement."
            if restantes
            else "Cet événement est complet."
        )

    return Inscription.objects.create(evenement=verrouille, nom=nom, email=email, places=places)


def annuler_inscription(inscription: Inscription) -> Inscription:
    """Annule une réservation et rend ses places à la jauge.

    L'inscription est marquée plutôt que supprimée : le bureau doit pouvoir
    lire l'historique d'une soirée, et un porteur qui revient sur son lien doit
    trouver une annulation confirmée plutôt qu'une page introuvable."""
    if not inscription.annulee:
        inscription.annulee = True
        inscription.save(update_fields=["annulee", "date_modification"])
    return inscription
