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


def utilisateur_depuis_uidb64(uidb64: str) -> Utilisateur | None:
    """Décode un uidb64 en `Utilisateur`, ou None si invalide/introuvable."""
    try:
        pk = urlsafe_base64_decode(uidb64).decode()
        return Utilisateur.objects.get(pk=pk)
    except (TypeError, ValueError, OverflowError, Utilisateur.DoesNotExist):
        return None
