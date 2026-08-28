"""Contexte de gabarit commun au back-office."""

from __future__ import annotations

from apps.coeur.roles import est_bureau

# Espaces applicatifs : à l'intérieur, le rail latéral porte la navigation et
# l'en-tête publique n'a plus lieu d'être déployée.
ESPACES_CONNECTES = frozenset({"espace_membre", "backoffice"})


def roles(request):
    """Expose `est_bureau` et `dans_espace_connecte` aux gabarits.

    `dans_espace_connecte` était calculé en gabarit par un
    `namespace in 'espace_membre backoffice'` — un test de SOUS-CHAÎNE, donc vrai
    pour un futur namespace « espace » ou « back ». Ici c'est une appartenance à
    un ensemble, et le test est écrit une fois.
    """
    correspondance = getattr(request, "resolver_match", None)
    return {
        "est_bureau": est_bureau(request.user),
        "dans_espace_connecte": bool(
            request.user.is_authenticated
            and correspondance
            and correspondance.namespace in ESPACES_CONNECTES
        ),
    }
