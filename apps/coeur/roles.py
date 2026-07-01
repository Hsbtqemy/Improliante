"""Rôles applicatifs et contrôle d'accès du bureau.

Le « bureau » est le groupe qui administre l'association (validation de la
modération, GED, facturation…). On le matérialise par un groupe Django nommé
`Bureau`, complété par les comptes techniques d'administration (`is_staff` /
superutilisateur). Centraliser la définition ici évite de disperser des
`user.is_staff` en dur dans les vues et permet d'ajuster la règle à un seul
endroit (CLAUDE.md règle 8 : rôles paramétrables, pas codés en dur partout).
"""

from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

NOM_GROUPE_BUREAU = "Bureau"


def est_bureau(user) -> bool:
    """Vrai si l'utilisateur fait partie du bureau (accès back-office)."""
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name=NOM_GROUPE_BUREAU).exists()


def bureau_requis(view):
    """Réserve une vue au bureau.

    - visiteur anonyme → redirection vers la connexion (`login_required`) ;
    - connecté hors bureau → 403 (`PermissionDenied`), sans redirection en
      boucle vers la connexion.
    """

    @wraps(view)
    def _verifie_bureau(request, *args, **kwargs):
        if not est_bureau(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return login_required(_verifie_bureau)
