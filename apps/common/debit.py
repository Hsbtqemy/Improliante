"""Limitation de débit des formulaires publics — constat PUB-01 de l'audit.

Trois formulaires écrivent en base, ou envoient un courriel, sans compte ni
session : contact, réservation d'un événement, et « mot de passe oublié ». Un
champ piège arrête un robot naïf ; il n'arrête pas quelqu'un qui renvoie le
formulaire en boucle.

Le compteur vit dans le cache `debit`, et non dans le cache par défaut : celui-ci
est un cache de confort que chaque worker Gunicorn peut dupliquer sans dommage,
alors qu'un compteur dupliqué multiplie la limite par le nombre de workers.

Ce module ne porte QUE la question « trop de fois, depuis la même origine ».
Les deux autres bornes que l'audit demande vivent là où elles ont du sens :
le plafond de places par personne est une règle métier (`agenda/services.py`),
et la longueur d'un message est une borne de formulaire.
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.cache import caches


def origine(requete) -> str:
    """L'adresse à laquelle imputer une tentative.

    Derrière Nginx, `REMOTE_ADDR` est celle de Nginx : toutes les tentatives du
    monde s'imputeraient à une seule origine, et la limite fermerait le site à
    tout le monde au premier abus. `X-Forwarded-For` porte la vraie adresse —
    mais le CLIENT l'écrit lui-même, et un attaquant qui en change à chaque
    envoi ne rencontrerait jamais la limite.

    On ne lit donc pas l'en-tête, on COMPTE. `PROXIES_DE_CONFIANCE` dit combien
    de relais sont devant l'application ; on prend l'entrée à cette distance de
    la DROITE, la seule que le client ne puisse pas avoir écrite puisque c'est
    notre propre relais qui l'a ajoutée. Tout ce qui est à sa gauche peut être
    inventé, et n'est jamais lu.

    À zéro — développement, tests, et tant que le VPS n'existe pas — l'en-tête
    est ignoré entièrement. C'est le bon défaut : se tromper vers `REMOTE_ADDR`
    imputait trop large, se tromper vers l'en-tête n'impute plus rien.
    """
    relais = getattr(settings, "PROXIES_DE_CONFIANCE", 0)
    if relais > 0:
        chaine = requete.META.get("HTTP_X_FORWARDED_FOR", "")
        maillons = [m.strip() for m in chaine.split(",") if m.strip()]
        if len(maillons) >= relais:
            return maillons[-relais]
    return requete.META.get("REMOTE_ADDR", "") or "origine-inconnue"


def tentative_de_trop(cle: str, *, limite: int, fenetre: int) -> bool:
    """Compte une tentative et dit si elle DÉPASSE la limite.

    La clé est hachée avant d'entrer dans le cache : elle porte souvent une
    adresse électronique, et le cache est une table de la base. Stocker en
    clair une adresse qu'on n'a pas demandé à conserver serait la conserver
    quand même, sous un autre nom.

    La fenêtre est FIXE et non glissante : le compteur expire `fenetre`
    secondes après la PREMIÈRE tentative, pas après la dernière. Une fenêtre
    glissante demanderait de garder chaque horodatage ; à cette échelle, elle
    achèterait de la précision contre de la complexité, et ce qu'on veut
    arrêter, c'est la rafale.

    La course entre `add` et `incr` laisse au pire passer une tentative de plus
    lorsque deux requêtes arrivent exactement ensemble. On l'assume : le but
    est de tarir une rafale, pas de compter juste.
    """
    empreinte = "debit:" + hashlib.sha256(cle.encode("utf-8")).hexdigest()[:32]
    magasin = caches["debit"]
    magasin.add(empreinte, 0, fenetre)
    try:
        compte = magasin.incr(empreinte)
    except ValueError:
        # L'entrée a expiré entre les deux appels : la fenêtre vient de se
        # rouvrir, et cette tentative est la première de la suivante.
        magasin.set(empreinte, 1, fenetre)
        compte = 1
    return compte > limite


def oublier(cle: str) -> None:
    """Efface le compteur d'une clé — pour les tests, et pour un déblocage."""
    caches["debit"].delete("debit:" + hashlib.sha256(cle.encode("utf-8")).hexdigest()[:32])
