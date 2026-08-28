"""Préparation des séries du tableau de bord budgétaire.

Ce module ne calcule **aucun** montant : il consomme la sortie de
`services.bilan_par_categorie` / `services.tresorerie` et la met en forme pour
l'affichage (tri, parts, écarts, regroupement de la traîne). La logique métier
reste dans `services.py` ; ici, seulement de la présentation.

Les parts sont renvoyées en **chaînes** à point décimal (« 12.5 »), jamais en
nombres : le projet tourne en `LANGUAGE_CODE = "fr-fr"`, et un flottant rendu
par un gabarit Django y sortirait « 12,5 » — ce qui casserait la largeur CSS
dans laquelle la valeur est injectée.

Les graphiques sont dessinés en HTML/CSS (pas de SVG, pas de bibliothèque
cliente) : le texte reste du texte redimensionnable, et les modes contraste
élevé, couleurs forcées et impression fonctionnent sans code supplémentaire.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_ZERO = Decimal("0.00")
_CENT = Decimal("100")
_DIXIEME = Decimal("0.1")

# Au-delà, les segments deviennent indiscernables : la traîne est regroupée.
# (8 teintes catégorielles existent ; on s'arrête à 7 pour garder une marge.)
MAX_SEGMENTS = 7

ETIQUETTE_AUTRES = "Autres catégories"


def _part(montant: Decimal, total: Decimal) -> str:
    """Part de `montant` dans `total`, en pourcentage, prête pour un `style=`.

    Renvoie « 0 » quand le total est nul — un budget vide ne divise pas."""
    if total <= _ZERO:
        return "0"
    part = (montant / total * _CENT).quantize(_DIXIEME, rounding=ROUND_HALF_UP)
    return str(part)


def _part_lisible(part: str) -> str:
    """La même part, écrite pour un lecteur français (« 12,5 »).

    Le point sert la feuille de style, la virgule sert l'œil : les deux formes
    coexistent parce qu'aucune ne peut faire le travail de l'autre."""
    return part.replace(".", ",")


def tuiles(bilan: dict, treso: dict) -> list[dict]:
    """Les quatre chiffres clés en tête d'écran.

    `sens` porte le signe du solde **en mot** : la couleur seule ne doit jamais
    dire si l'exercice est excédentaire (règle 9 de CLAUDE.md).

    Les montants sortent en `Decimal`, jamais en chaîne : c'est le gabarit qui
    les met en forme (`floatformat`), pour que la virgule française soit posée
    par la localisation Django et non ici."""
    totaux = bilan["totaux"]
    solde = totaux["solde_realise"]
    if solde > _ZERO:
        sens, mot = "positif", "excédent"
    elif solde < _ZERO:
        sens, mot = "negatif", "déficit"
    else:
        sens, mot = "nul", "à l'équilibre"

    return [
        {
            "label": "Recettes réalisées",
            "valeur": totaux["recette_realise"],
            "detail": "budgétées :",
            "detail_montant": totaux["recette_prevu"],
        },
        {
            "label": "Dépenses réalisées",
            "valeur": totaux["depense_realise"],
            "detail": "budgétées :",
            "detail_montant": totaux["depense_prevu"],
        },
        {
            "label": "Solde réalisé",
            "valeur": solde,
            "sens": sens,
            "detail": f"{mot} — budgété :",
            "detail_montant": totaux["solde_prevu"],
        },
        {
            "label": "Trésorerie prévisionnelle",
            "valeur": treso["previsionnelle"],
            "detail": "dernier pointage :",
            "detail_montant": treso["solde_pointe"],
        },
    ]


def _lignes_dun_flux(bilan: dict, flux: str, echelle: Decimal) -> list[dict]:
    """Lignes « réalisé vs budgété » d'un flux, les plus grosses d'abord."""
    lignes = []
    for ligne in bilan["lignes"]:
        realise = ligne[f"{flux}_realise"]
        prevu = ligne[f"{flux}_prevu"]
        # Une catégorie sans rien de budgété ni de réalisé sur ce flux n'a pas
        # de barre à montrer : elle occuperait une ligne vide.
        if realise == _ZERO and prevu == _ZERO:
            continue
        ecart = realise - prevu
        if ecart > _ZERO:
            sens = "au-dessus"
        elif ecart < _ZERO:
            sens = "en dessous"
        else:
            sens = "conforme"
        lignes.append(
            {
                "categorie": ligne["categorie"],
                "realise": realise,
                "prevu": prevu,
                "ecart": ecart,
                # Le signe est déjà porté par `sens` en toutes lettres : le
                # gabarit affiche une valeur absolue et le mot qui la qualifie,
                # plutôt qu'un « -150 € » que le lecteur doit interpréter.
                "ecart_absolu": abs(ecart),
                "sens": sens,
                "part_realise": _part(realise, echelle),
                "part_prevu": _part(prevu, echelle),
            }
        )
    lignes.sort(key=lambda ligne: (ligne["realise"], ligne["prevu"]), reverse=True)
    return lignes


def comparaison_au_budget(bilan: dict) -> dict:
    """Réalisé (barre) face au budgété (repère de cible), par catégorie.

    Les deux flux partagent **une seule échelle** — celle du plus gros montant
    de l'écran. Deux échelles rendraient une dépense de 500 € aussi longue
    qu'une recette de 50 000 €, ce qu'aucun lecteur ne rattrape."""
    montants = [
        ligne[cle]
        for ligne in bilan["lignes"]
        for cle in ("recette_prevu", "recette_realise", "depense_prevu", "depense_realise")
    ]
    echelle = max(montants) if montants else _ZERO

    flux = [
        {
            "titre": "Recettes",
            "cle": "recette",
            "lignes": _lignes_dun_flux(bilan, "recette", echelle),
        },
        {
            "titre": "Dépenses",
            "cle": "depense",
            "lignes": _lignes_dun_flux(bilan, "depense", echelle),
        },
    ]
    return {"echelle": echelle, "flux": [f for f in flux if f["lignes"]]}


def repartition_depenses(bilan: dict, maximum: int = MAX_SEGMENTS) -> dict:
    """Part de chaque catégorie dans les dépenses réalisées de la saison.

    Au-delà de `maximum` segments, la traîne est regroupée sous « Autres
    catégories » : une teinte de plus ne serait plus distinguable de ses
    voisines, et la barre cesserait d'être lisible."""
    depenses = [
        (ligne["categorie"], ligne["depense_realise"])
        for ligne in bilan["lignes"]
        if ligne["depense_realise"] > _ZERO
    ]
    depenses.sort(key=lambda couple: couple[1], reverse=True)
    total = sum((montant for _, montant in depenses), _ZERO)

    if len(depenses) > maximum:
        tete = depenses[: maximum - 1]
        traine = depenses[maximum - 1 :]
        reste = sum((montant for _, montant in traine), _ZERO)
        tete.append((ETIQUETTE_AUTRES, reste))
        depenses, regroupees = tete, len(traine)
    else:
        regroupees = 0

    segments = []
    for index, (nom, montant) in enumerate(depenses, start=1):
        part = _part(montant, total)
        segments.append(
            {
                "categorie": nom,
                "montant": montant,
                "part": part,
                "part_lisible": _part_lisible(part),
                # Rang de 1 à MAX_SEGMENTS : sert de numéro de teinte côté CSS.
                "rang": index,
            }
        )
    return {"total": total, "segments": segments, "regroupees": regroupees}
