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


def peut_ecrire_espace_membre(user) -> bool:
    """Vrai si l'utilisateur peut DÉPOSER ou MODIFIER dans l'espace membre.

    Une adhésion qui prend fin (`Membre.actif = False`) ferme l'écriture, pas la
    lecture : l'ancien membre garde ses reçus fiscaux, ses documents et son
    historique — un reçu fiscal sert plusieurs années, et le lui retirer
    obligerait le bureau à rouvrir un compte à chaque demande.

    Le bureau n'est pas concerné : il administre l'association, pas sa propre
    adhésion. Un trésorier dont la fiche est inactive doit continuer à gérer.
    """
    if not user.is_authenticated or not user.is_active:
        return False
    # La fiche membre AVANT le bureau, et l'ordre n'est pas cosmétique : la
    # relation est mise en cache sur l'utilisateur au premier accès, alors que
    # `est_bureau` retourne en base à chaque appel. Dans l'autre sens, le cas
    # courant — un membre à jour — payait une requête de groupes par appel, et
    # cette fonction est appelée sur chaque page servie.
    membre = getattr(user, "membre", None)
    if membre is not None and membre.actif:
        return True
    return est_bureau(user)


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
