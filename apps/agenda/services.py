"""Services métier du domaine « Agenda ».

Gestion des images d'un événement — l'affiche (image principale) et la galerie
(plusieurs images ordonnées). Miroir de `apps.spectacles.services` : chaque image
crée un `Media` du socle, avec un `alt` OBLIGATOIRE (accessibilité, cf. CLAUDE.md
règle 2). La logique vit ici, pas dans les vues.

Note : les `Media` sont un socle réutilisable ; retirer une image de la galerie
ou l'affiche détache le lien mais ne supprime pas le `Media` lui-même.

Le module porte aussi les inscriptions (jauge relue sous verrou) et la lecture
des participations publiques d'un membre, servie à sa page publique.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.medias.models import Media

from .models import Evenement, ImageEvenement, Inscription, Intervention

# Dates montrées d'emblée sur une page publique ; au-delà, la page renvoie vers
# l'agenda plutôt que de dérouler une saison entière. Valeur de départ, à régler
# sur de vrais contenus — pas un seuil qui protège de quoi que ce soit.
PARTICIPATIONS_EN_PREMIERE_LISTE = 5


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


def prochaines_participations(membre, *, maintenant=None):
    """Participations publiques à venir d'un membre, de la plus proche à la plus lointaine.

    **Règle stricte** : seule une `Intervention` explicite sur l'événement
    compte. Figurer à la distribution d'un spectacle ne prouve pas la présence
    à chacune de ses dates — l'annoncer ferait déplacer quelqu'un pour rien.
    Une distribution permanente se recopie en interventions, elle ne s'hérite
    pas : c'est un geste du bureau, pas une déduction du code.

    Trois filtres, trois raisons distinctes :

    - `statut_moderation` publié : une date en brouillon n'est pas une date ;
    - `visibilite` publique : une soirée réservée aux membres ne fuit pas sur
      une page que tout le monde lit. Vaut aussi pour le **décompte** — d'où le
      fait que l'appelant compte ce que ce service retourne, et rien d'autre ;
    - `date_debut` à venir : même convention que l'agenda public, qui tient une
      date pour passée dès son début franchi (une soirée commencée n'est plus à
      annoncer).

    Aucun dédoublonnage : `Intervention` porte une contrainte d'unicité
    `(evenement, membre)`, un membre ne peut donc paraître deux fois sur la même
    date. Retourne un *queryset* — l'appelant en prend ce qu'il affiche, sans
    charger une saison pour en montrer cinq.
    """
    return (
        Intervention.objects.filter(
            membre=membre,
            evenement__statut_moderation=Evenement.StatutModeration.PUBLIE,
            evenement__visibilite=Evenement.Visibilite.PUBLIC,
            evenement__date_debut__gte=maintenant or timezone.now(),
        )
        .select_related(
            "evenement", "evenement__lieu", "evenement__spectacle", "evenement__affiche"
        )
        .order_by("evenement__date_debut")
    )
