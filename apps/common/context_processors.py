"""Contexte de gabarit transverse : les préférences de confort du visiteur.

Le panneau d'accessibilité mémorise ses réglages dans le cookie `a11y`, que le
serveur rend sur `<html>` dès la première réponse — sans quoi la page
s'afficherait une fraction de seconde dans les réglages par défaut avant que le
script ne la corrige.

Un cookie se fabrique à la main : ce qu'il contient est donc relu contre une
**liste fermée** plutôt que recopié. L'auto-échappement de Django empêche déjà
de sortir de l'attribut `class`, il n'y a donc pas d'injection à la clé ; ce qui
reste sans la liste, c'est la possibilité de poser n'importe quelle classe du
site sur `<html>` — et de faire porter à un réglage de confort une classe qui ne
lui appartient pas.
"""

from __future__ import annotations

# Les seules classes que le panneau de confort pose sur <html>. Tout ce qui est
# porté par <html> en dehors de cette liste appartient à quelqu'un d'autre et ne
# doit survivre ni à un réglage ni à une remise à zéro.
#
# `front/static/js/accessibilite.js` tient la même liste, côté navigateur ; un
# test refuse qu'elles divergent, parce qu'une divergence ne se verrait pas :
# la page continuerait de s'afficher, simplement en perdant un réglage.
CLASSES_CONFORT = (
    "txt-grand",
    "txt-max",
    "contraste",
    "sombre",
    "espacement",
    "dyslexie",
    "anim-reduites",
)


def confort(request):
    """Les classes de confort demandées par le cookie, connues et dédoublonnées.

    L'ordre du cookie est conservé : il ne change rien au rendu, et le garder
    évite de faire mentir le script, qui relit ensuite l'attribut tel quel.
    """
    retenues = []
    for classe in (request.COOKIES.get("a11y") or "").split():
        if classe in CLASSES_CONFORT and classe not in retenues:
            retenues.append(classe)
    return {"classes_confort": " ".join(retenues)}
