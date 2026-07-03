"""Services métier du domaine « Cœur associatif ».

Création de compte membre par le bureau : on crée l'`Utilisateur` (identifiant =
e-mail, mot de passe INUTILISABLE) et le `Membre` rattaché, en une transaction.
Le nouveau membre définit lui-même son mot de passe via un **lien d'activation**
(token signé, à durée de vie limitée) — le bureau ne manipule jamais de mot de
passe en clair. Tant que le SMTP n'est pas activé, le lien est affiché à l'écran
et transmis hors-outil ; il pourra être envoyé par e-mail sans autre changement.
"""

from __future__ import annotations

from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import Membre, Utilisateur

# Taille de la vedette (accordéon) sur la page association. L'accordéon ne scale
# pas au-delà de ~6-8 panneaux : on borne volontairement.
NB_VEDETTE = 6


def membres_en_vedette(nombre: int = NB_VEDETTE) -> list[Membre]:
    """Membres à afficher en vedette (accordéon) sur la page association.

    Les membres « à la une » visibles d'abord, complétés au hasard par d'autres
    membres visibles jusqu'à `nombre`, pour garder la vedette pleine et
    changeante même si peu de membres sont explicitement mis en avant. Bornée à
    `nombre` (l'accordéon ne scale pas au-delà de ~6-8)."""
    visibles = Membre.objects.filter(visible_sur_site=True).select_related("user", "photo")
    vedette = list(visibles.filter(mis_en_avant=True).order_by("?")[:nombre])
    manque = nombre - len(vedette)
    if manque > 0:
        deja = [m.pk for m in vedette]
        vedette += list(
            visibles.filter(mis_en_avant=False).exclude(pk__in=deja).order_by("?")[:manque]
        )
    return vedette


@transaction.atomic
def creer_compte_membre(
    *,
    first_name: str,
    last_name: str,
    email: str,
    role_public: str = "",
    telephone: str = "",
) -> Membre:
    """Crée l'utilisateur (mot de passe inutilisable) et sa fiche membre.

    L'identifiant de connexion est l'e-mail. Le compte est actif mais ne peut
    pas encore servir à se connecter tant que le membre n'a pas défini son mot
    de passe via le lien d'activation. L'unicité de l'e-mail doit être vérifiée
    en amont (formulaire)."""
    user = Utilisateur(
        username=email,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )
    user.set_unusable_password()
    user.save()
    return Membre.objects.create(user=user, role_public=role_public, telephone=telephone)


def jeton_activation(user: Utilisateur) -> tuple[str, str]:
    """Renvoie (uidb64, token) pour construire le lien d'activation d'un compte.

    Réutilise le générateur de token de Django (celui du « mot de passe
    oublié ») : le token devient caduc dès que le mot de passe est défini
    (usage unique) et expire selon `PASSWORD_RESET_TIMEOUT`."""
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    return uidb64, default_token_generator.make_token(user)


def definir_photo_membre(membre: Membre, fichier, alt: str, *, cree_par=None):
    """Crée un `Media` image et le pose comme photo (portrait) du membre."""
    from apps.medias.models import Media

    media = Media.objects.create(
        type_media=Media.TypeMedia.IMAGE,
        fichier=fichier,
        alt=alt,
        cree_par=cree_par,
    )
    membre.photo = media
    membre.save(update_fields=["photo", "date_modification"])
    return media


def retirer_photo_membre(membre: Membre) -> None:
    """Détache la photo du membre (le `Media` reste dans le socle)."""
    if membre.photo_id is None:
        return
    membre.photo = None
    membre.save(update_fields=["photo", "date_modification"])


def utilisateur_depuis_uidb64(uidb64: str) -> Utilisateur | None:
    """Décode un uidb64 en `Utilisateur`, ou None si invalide/introuvable."""
    try:
        pk = urlsafe_base64_decode(uidb64).decode()
        return Utilisateur.objects.get(pk=pk)
    except (TypeError, ValueError, OverflowError, Utilisateur.DoesNotExist):
        return None
