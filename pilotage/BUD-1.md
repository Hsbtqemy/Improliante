---
chantier: BUD-1
statut: à venir
---

# BUD-1 — tableau de bord budget avec graphiques (v2)

**Point de départ** — Rien n'est commencé. Les chiffres existent et sont déjà exposés :
`bilan_par_categorie` (`apps/budget/services.py`) et son export Excel openpyxl. Ce qui
manque est la mise en image, et le choix de la façon de la produire.

## Reste

### Arbitrages
- [ ] Trancher la technique de rendu des graphiques : SVG produit côté serveur, ou bibliothèque cliente — une bibliothèque de graphiques est le genre de dépendance qui contredit le « pas de SPA lourde » du cahier §2
- [ ] Décider quelles séries méritent une courbe, et sur quelle maille de temps (saison, exercice, mois) — la `Saison` existe déjà comme découpage métier
- [ ] Décider si le tableau de bord remplace l'export Excel ou le complète

### Vérifications
- [ ] Chaque graphique porte son équivalent en tableau accessible, lisible au lecteur d'écran — règle 9 de CLAUDE.md ; un graphique seul n'est pas conforme AA
- [ ] Les couleurs employées tiennent le contraste AA et ne portent jamais l'information à elles seules

## Contexte

**Hors périmètre tant qu'il n'est pas explicitement demandé** (CLAUDE.md, « Périmètre v1
vs plus tard »). Cette fiche cadre, elle n'autorise pas.

Les deux items de vérification ne sont pas des finitions : ce sont eux qui décident de la
technique. Un tableau de bord accessible se conçoit avec son équivalent textuel dès le
départ, pas ajouté après coup sur des images déjà produites.
