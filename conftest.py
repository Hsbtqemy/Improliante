"""Utilitaires de test partagés entre les apps.

`liens_nus_rouvrant_le_rail` vit ici parce qu'elle porte un invariant valable
sur les DEUX tableaux de bord — celui de la gestion et celui du membre. Écrite
dans l'un des deux modules de test, elle aurait dû être importée par l'autre,
ou recopiée : deux formulations d'une même règle finissent par diverger.
"""

from __future__ import annotations

import re


def liens_nus_rouvrant_le_rail(html: str) -> list[str]:
    """Liens du contenu qui rouvrent une entrée du rail SANS rien apprendre.

    L'invariant n'est pas « aucune destination partagée » : une tuile qui
    affiche un nombre et mène à son écran est un indicateur, pas un doublon de
    menu. Ce qu'on traque, c'est le libellé nu — une carte « Fichiers » posée à
    côté d'un rail qui porte déjà « Fichiers ».

    Le chiffre sert de marqueur : il distingue « 3 factures échues → » d'un
    simple raccourci. Un lien de suivi qui n'en porte pas (« Ouvrir la file de
    modération ») reste toléré par le seuil, côté appelant.
    """
    rail = html.split('<nav id="nav-espace"', 1)[1].split("</nav>", 1)[0]
    contenu = html.split('<main id="contenu"', 1)[1].split("</main>", 1)[0]
    destinations = set(re.findall(r'href="(/[^"#?]*)"', rail))

    nus = []
    for lien in re.findall(r"<a\b[^>]*>.*?</a>", contenu, re.S):
        cible = re.search(r'href="(/[^"#?]*)"', lien)
        if not cible or cible.group(1) not in destinations:
            continue
        texte = " ".join(re.sub(r"<[^>]+>", " ", lien).split())
        if not re.search(r"\d", texte):
            nus.append(f"{cible.group(1)} → {texte[:40]}")
    return nus
