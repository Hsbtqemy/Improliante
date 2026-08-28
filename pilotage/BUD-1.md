---
chantier: BUD-1
statut: clos
---

# BUD-1 — tableau de bord budget avec graphiques (v2)

**Arrêté sur** — tableau de bord posé sur l'écran Bilan (chiffres clés, réalisé face au
budget, répartition des dépenses), rendu en HTML/CSS, commit `bef0880`, 28 août.

## Reste

### Arbitrages
- [x] Trancher la technique de rendu des graphiques : SVG produit côté serveur, ou bibliothèque cliente — une bibliothèque de graphiques est le genre de dépendance qui contredit le « pas de SPA lourde » du cahier §2
- [x] Décider quelles séries méritent une courbe, et sur quelle maille de temps (saison, exercice, mois) — la `Saison` existe déjà comme découpage métier
- [x] Décider si le tableau de bord remplace l'export Excel ou le complète

### Vérifications
- [x] Chaque graphique porte son équivalent en tableau accessible, lisible au lecteur d'écran — règle 9 de CLAUDE.md ; un graphique seul n'est pas conforme AA
- [x] Les couleurs employées tiennent le contraste AA et ne portent jamais l'information à elles seules

## Contexte

Ni SVG ni bibliothèque cliente : **HTML/CSS**. Une barre est un `div` dont la largeur est
un pourcentage, un repère de cible un trait positionné. Le texte reste donc du texte —
il zoome, se lit au lecteur d'écran, s'imprime — et les modes sombre, contraste élevé et
`forced-colors` fonctionnent sans une ligne de code de rendu. Un SVG mis à l'échelle
aurait rétréci ses étiquettes avec lui sur mobile ; c'est ce qui a fait pencher la
balance, le cahier §2 étant satisfait dans les deux cas.

La maille de temps n'a pas été tranchée : elle a été **écartée**. Les trois vues retenues
(chiffres clés, réalisé face au budget par catégorie, répartition des dépenses) se
déduisent toutes de `bilan_par_categorie`, sans une seule agrégation temporelle nouvelle.
Une courbe d'évolution mensuelle reste possible — `Transaction.date` porte le jour — et
serait le contenu naturel d'un BUD-2 si le besoin se présente.

Le tableau de bord **complète** l'export Excel. Le `.xlsx` est un format d'échange pour
l'expert-comptable, pas un écran de lecture ; aucun graphique ne s'envoie à un comptable.

Un troisième arbitrage, que la fiche n'avait pas posé, a été tranché en cours de route :
les graphiques vivent sur l'écran **Bilan** plutôt que sur un cinquième onglet. Le tableau
détaillé y est alors le jumeau accessible exigé par la règle 9 — il était déjà là, il n'y
a rien à dupliquer ni à maintenir en double.

Deux décisions d'accessibilité méritent d'être retenues, parce qu'elles ne se devinent
pas à la relecture du code. D'abord, le budgété est un **repère** (un trait) quand le
réalisé est une **barre** : en thème sombre, le bordeaux éclairci et le gris de contexte
se retrouvent à luminance quasi égale (1,33:1), et aucun réglage de teinte ne rattrapait
ça — c'est la *forme* qui porte la distinction, pas la couleur. Ensuite, les parts
traversent le gabarit sous forme de **chaînes** à point décimal : le projet tourne en
`fr-fr`, et un nombre rendu « 12,5 » produirait `width: 12,5%`, donc une barre à zéro.
Un test de vue verrouille ce point sur le HTML rendu, pas seulement sur la fonction.

La palette a été validée mécaniquement (méthode dataviz) contre les surfaces **réelles**
du site — `#ffffff` en clair, `#211b28` en sombre — et non contre des surfaces par
défaut : bande de clarté, plancher de chroma, séparation sous protanopie et deutéranopie,
contraste. L'ordre des sept teintes de la répartition **est** le mécanisme de sécurité
daltonisme : il ne se réarrange pas, et une huitième catégorie ne prend pas une teinte de
plus — la traîne est regroupée sous « Autres catégories ».

Trois teintes (aqua, jaune, magenta) passent sous 3:1 sur fond blanc. C'est toléré par la
méthode à une condition non négociable : que la valeur soit lisible autrement. Elle l'est
deux fois — la légende sous la barre porte nom, montant et pourcentage, et le tableau
détaillé suit sur la même page.

Un débordement horizontal **préexistant** a été corrigé au passage :
`.espace-grille__contenu` est une colonne `1fr` dont le `min-width: auto` implicite
l'élargissait jusqu'à son contenu le plus large, si bien que l'`overflow-x` de
`.tableau-wrap` ne pouvait jamais s'activer. L'écran Bilan poussait la page 165 px hors
de l'écran en 1280. Le correctif (`min-width: 0`) vaut pour **tous** les écrans du
back-office à large tableau, pas seulement celui-ci.
