"""Contexte de gabarit commun au back-office."""

from __future__ import annotations

from apps.coeur.roles import est_bureau, peut_ecrire_espace_membre

# Espaces applicatifs : à l'intérieur, le rail latéral porte la navigation et
# l'en-tête publique n'a plus lieu d'être déployée.
ESPACES_CONNECTES = frozenset({"espace_membre", "backoffice"})


def roles(request):
    """Expose `est_bureau`, `peut_ecrire_espace` et `dans_espace_connecte`.

    `dans_espace_connecte` était calculé en gabarit par un
    `namespace in 'espace_membre backoffice'` — un test de SOUS-CHAÎNE, donc vrai
    pour un futur namespace « espace » ou « back ». Ici c'est une appartenance à
    un ensemble, et le test est écrit une fois.

    `peut_ecrire_espace` passe par le contexte plutôt que par chaque vue : une
    douzaine d'écrans offrent un geste d'écriture, et un drapeau oublié dans
    l'un d'eux redonnerait un bouton qui mène à un refus.
    """
    correspondance = getattr(request, "resolver_match", None)
    return {
        "est_bureau": est_bureau(request.user),
        "peut_ecrire_espace": peut_ecrire_espace_membre(request.user),
        "dans_espace_connecte": bool(
            request.user.is_authenticated
            and correspondance
            and correspondance.namespace in ESPACES_CONNECTES
        ),
    }
