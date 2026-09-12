---
passe: Accessibilité — campagne FRONT-08
chantier: SEC-1
duree: 45 min
derniere: —
---

# QA — accessibilité réelle (constat FRONT-08 de l'audit)

L'audit externe du 11 septembre 2026 demandait une campagne d'accessibilité. Le
lot 9 a corrigé ce qui se vérifie dans le code ; cette passe couvre le reste,
c'est-à-dire ce qu'aucune mesure n'atteint.

**Ce que la passe NE couvre PAS**, parce qu'un test échoue si on le casse — y
revenir à l'œil ferait perdre du temps :

- le contraste AA des **dix-huit** palettes, en clair et en sombre (dix paires
  réellement peintes mesurées par palette) — `test_les_palettes_respectent_le_contraste_AA` ;
- le plan des titres sur les 64 pages rendues (aucun niveau sauté) ;
- le nom accessible de chaque champ, bouton et lien de `<main>` ;
- l'absence de référence `aria-*` vers un id inexistant, et l'absence d'id rendu
  deux fois sur une même page ;
- l'existence de la règle qui distingue un lien neutralisé.

Ce qu'elle couvre : la lisibilité vécue, le clavier réel, les largeurs réelles,
et la justesse de ce qui est annoncé.

**Trois réserves de méthode.** Les points à **375 px** demandent un vrai
téléphone : le rendu en ligne de commande plafonne plus haut. Les points au
**lecteur d'écran** demandent NVDA ou VoiceOver ; « le code est correct » n'est
pas une réponse à « qu'entend-on ». Et le panneau de réglages (Palette / Fond /
Titres) recouvre le bas de l'écran en position fixe : ce chevauchement est
attendu, ne pas le remonter comme défaut.

## Reste

### Clavier seul — parcours complet
- [ ] Depuis la page d'accueil, `Tab` atteint le lien d'évitement en premier, et l'activer place le focus dans `<main>` — le lien suivant tabulé appartient au contenu, pas à l'en-tête
- [ ] Sur 375 px, le menu replié s'ouvre au clavier (`Entrée` sur « Menu ») et `Tab` reste PIÉGÉ dans le menu ouvert jusqu'à `Échap`, qui referme et rend le focus au bouton
- [ ] Le panneau d'accessibilité s'ouvre, se parcourt et se ferme au clavier, et `Échap` rend le focus au bouton « Options d'accessibilité »
- [ ] Chaque élément atteint au clavier porte un contour de focus VISIBLE sur la palette retenue, y compris les liens sur fond sombre du hero et les boutons du panneau de réglages
- [ ] Aucun élément ne reçoit le focus alors qu'il est masqué : tabuler de bout en bout ne fait jamais disparaître le curseur de l'écran

### Formulaires refusés — ce que le lot 9 n'a pas pu mesurer
- [ ] Envoyer le formulaire de contact vide : le focus se porte sur le premier champ fautif ou sur le résumé d'erreurs, sans avoir à re-tabuler depuis le haut
- [ ] Au lecteur d'écran, atteindre un champ refusé annonce le libellé, l'erreur ET l'aide — pas seulement « zone de saisie, invalide »
- [ ] Sur une ligne de facture refusée, l'erreur est annoncée en désignant SA ligne : un « Quantité invalide » sans numéro de ligne ne suffit pas sur une pièce de dix lignes
- [ ] Le message « Modifications non enregistrées » d'un brouillon de facture est annoncé quand il apparaît, sans avoir à le chercher
- [ ] Le lien « Valider et numéroter… » neutralisé se distingue **à l'œil** du même lien actif, sur la palette retenue, en clair et en sombre — la règle existe, reste à voir si elle se voit

### Zoom et largeurs réelles
- [ ] À **zoom 200 %** sur bureau, aucune page ne réclame de défilement horizontal, et aucun texte n'est coupé ou recouvert
- [ ] À **zoom 400 %**, la page se réorganise en une colonne : le rail de gestion devient atteignable, il ne recouvre pas le contenu
- [ ] Sur **375 px**, le tableau des lignes de facture reste utilisable : soit il défile horizontalement dans son propre conteneur, soit il se replie en fiches — la page, elle, ne défile pas latéralement
- [ ] Sur **375 px**, l'aide neuve des lignes de distribution (« Ex. comédien·ne, mise en scène… ») ne casse pas la mise en page de la ligne : elle passe sous le champ sans déborder ni écraser le bouton « × »
- [ ] Sur **375 px**, les quatre formulaires « Nouveau dossier » de la page Fichiers s'ouvrent et se remplissent sans que deux sections se chevauchent

### Ce que le lecteur d'écran annonce vraiment
- [ ] Sur l'écran d'un dossier, les deux formulaires (« Nouveau dossier » et « Téléverser ») s'annoncent comme deux groupes distincts : leurs champs « Description » ne se confondent plus
- [ ] Cliquer le libellé « Nom » d'une branche de la page Fichiers place le focus dans le champ de CETTE branche, pas dans celui de la première
- [ ] Sur la page d'inscription à un événement, l'aide du champ « places » est annoncée à l'arrivée dans le champ — c'est le défaut corrigé au lot 9, il se vérifie à l'oreille
- [ ] Le tableau des lignes de facture s'annonce comme un tableau, avec l'en-tête de colonne repris à chaque cellule
- [ ] Une pastille d'état (brouillon / proposé / publié) est annoncée, et pas seulement colorée

### Mouvement et préférences système
- [ ] Avec « réduire les animations » activé dans le système, le fond animé (mesh) cesse de bouger et les transitions de boutons ne sautent plus
- [ ] Le panneau d'accessibilité et le choix de palette survivent à un rechargement, et le choix de palette ne réinitialise pas les autres réglages de confort

## Contexte

**Écrite le 12 septembre 2026, après le lot 9.** Elle n'est pas rejouable à
l'identique d'une session à l'autre : plusieurs de ses points portent sur des
correctifs précis de ce lot, et deviendront des non-événements une fois vérifiés.
Trois points sont à garder au-delà, parce qu'ils reviennent à chaque évolution du
front : le contour de focus sur la palette retenue, le zoom 200 %, et le tableau
des lignes de facture sur 375 px.

**Pourquoi ces points-là.** Le lot 9 a trouvé deux défauts par balayage — une
aide de champ affichée sans jamais être annoncée, et des identifiants rendus deux
fois sur une même page. Les deux étaient invisibles à la relecture et muets à
l'exécution. Ce qu'un balayage ne peut PAS trouver, en revanche, c'est si le
contour de focus se voit, si l'erreur annoncée désigne la bonne ligne, et si une
aide ajoutée casse une mise en page à 375 px. D'où cette passe, et d'où le fait
qu'elle insiste sur les formulaires refusés : le balayage ne charge que des pages
saines.

**Un point reste ouvert côté code, et il est ici exprès** : vingt-cinq gabarits
rendent un champ à la main au lieu de passer par `_champ.html`. Leurs messages
d'erreur n'ont pas d'identifiant, donc la référence `aria-describedby` que Django
pose vers `<id>_error` pend dès qu'un formulaire est refusé — état qu'aucun
balayage ne visite. Deux des cases « Formulaires refusés » ci-dessus le
constateront à l'oreille. Le remède de fond est l'inventaire ARCH-01, où cette
duplication a sa place.
