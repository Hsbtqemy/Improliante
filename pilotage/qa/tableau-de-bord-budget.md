---
passe: Tableau de bord budget
chantier: BUD-1
duree: 15 min
derniere: 2026-08-28
---

# QA — tableau de bord de l'écran Bilan

Écran : **Bureau · Finances · Budget · Bilan** (`/bureau/budget/bilan/`), sur une saison
portant des mouvements dans plusieurs catégories, en recettes comme en dépenses.

Ce que la passe couvre : ce qu'aucune vérification mécanique n'atteint — la lisibilité
réelle, les collisions d'étiquettes, le comportement aux largeurs que le rendu en ligne
de commande ne sait pas produire. La palette, elle, est déjà validée par calcul (bande de
clarté, chroma, séparation daltonisme, contraste) et n'a pas à être jugée à l'œil.

Deux points appellent un vrai appareil plutôt qu'une fenêtre redimensionnée : **375 px**
(Chrome en ligne de commande plafonne son rendu à 500 px, ces largeurs n'ont donc jamais
été vues) et le **mode couleurs forcées**, qui n'existe pas sur macOS.

Pour peupler l'écran : créer une saison, puis des mouvements dans **plus de sept**
catégories de dépenses — c'est le seul moyen de déclencher le regroupement « Autres
catégories » et de juger la barre à sa densité maximale.

### Chiffres clés

- [ ] Les quatre tuiles tiennent leur montant sur une seule ligne, le « € » jamais seul en bas
- [ ] Un solde négatif affiche le mot « déficit » et se comprend sans regarder la couleur
- [ ] Les montants arrondis à l'euro ne choquent pas le trésorier, le tableau du bas portant le centime

### Réalisé face au budget

- [ ] Le repère « Budgété » reste visible quand il tombe AU MILIEU de la barre bordeaux, pas seulement à côté
- [ ] Sur une catégorie où le réalisé dépasse largement le budget, le repère ne sort pas de la piste
- [ ] Une catégorie à zéro réalisé montre une piste vide et son repère, pas une ligne blanche indéchiffrable
- [ ] Les noms longs (« Transport et défraiements ») ne poussent pas la valeur hors de sa colonne
- [ ] Recettes et dépenses se comparent à l'œil : la même longueur y vaut le même montant
- [ ] Quand une catégorie écrase l'échelle, les petites lignes restent compréhensibles — piste vide et montant lisible à droite, sans donner l'impression d'un affichage cassé

### Répartition des dépenses

- [ ] Avec plus de sept catégories, la dernière part s'appelle « Autres catégories » et la phrase au-dessus dit combien y sont regroupées
- [ ] Les parts de moins de 2 % restent visibles comme un trait, sans disparaître ni écraser leurs voisines
- [ ] Chaque part de la légende se relie sans hésitation à son segment dans la barre
- [ ] La légende reste lisible quand un nom de catégorie passe sur deux lignes
- [ ] Le total annoncé sous « Où partent les dépenses » égale celui de la tuile « Dépenses réalisées » — les deux ne divergent qu'avec un montant négatif saisi hors du formulaire

### Largeurs et appareils

- [ ] Sur 375 px réel, aucune barre de défilement horizontale sur la page entière
- [ ] Sur 375 px réel, la ligne se replie bien : nom et valeur en haut, barre pleine largeur dessous
- [ ] Sur 375 px réel, le tableau détaillé défile dans son cadre sans emporter la page
- [ ] En zoom navigateur à 200 %, rien ne se chevauche ni ne se coupe

### Thèmes et accessibilité

- [ ] En thème sombre, le repère gris se distingue franchement de la barre rose
- [ ] En mode contraste élevé, la piste reste visible sous une barre courte
- [ ] En couleurs forcées (Windows, contraste élevé), les barres gardent une forme lisible et la légende porte seule les valeurs
- [ ] Au lecteur d'écran, la page s'écoute sans buter sur les barres, et le tableau final redonne toutes les valeurs
- [ ] À l'impression (aperçu PDF), les barres et la barre de répartition sortent lisibles
