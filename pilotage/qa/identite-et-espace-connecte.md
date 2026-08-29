---
passe: Identité visuelle et espace connecté
chantier: —
duree: 30 min
derniere: 2026-08-29
---

# QA — identité visuelle, page d'accueil, espace connecté

Couvre les vingt-et-un commits du 28-29 août 2026, de `c6b85e5` à `a34343a` :
harmonisation des en-têtes de la vitrine, sélecteur de police, dix-huit palettes,
mode sombre par palette, hero portant sur l'association, coordonnées publiques,
désaturation de l'espace connecté, empreinte des fichiers statiques, renommage
« Bureau » → « Gestion ».

**Ce que la passe NE couvre PAS**, parce que c'est déjà tenu par la mesure et
qu'y revenir à l'œil ferait perdre du temps : le contraste AA des dix-huit
palettes dans les deux modes (treize paires mesurées par palette), l'existence
des fichiers statiques référencés, et la présence d'un repère de position sur
chaque destination du rail. Ces trois points ont un test qui échoue si on les
casse.

Ce qu'elle couvre : ce qu'aucune mesure n'atteint — la lisibilité vécue, le
comportement au clavier, les largeurs réelles, et la justesse des mots.

**Deux réserves de méthode.** Chrome en ligne de commande plafonne son rendu à
500 px : les points à **375 px** n'ont jamais été vus, ils demandent un vrai
téléphone. Et le panneau de réglages (Palette / Fond / Titres) recouvre le bas de
l'écran en position fixe : ce chevauchement est attendu, il disparaîtra avec le
panneau — ne pas le remonter comme défaut.

Pour peupler : une association avec accroche et présentation renseignées, un
e-mail et un téléphone publics, trois interlocuteurs, deux ou trois fiches
proposées, et quelques dates à venir.

### Vitrine — en-têtes de page

- [ ] Sur les treize pages publiques, le titre commence à la même hauteur et porte le même filet en dessous — l'accueil excepté, qui garde son hero
- [ ] Aucune page de premier niveau n'affiche de sur-titre ; seules les pages imbriquées en portent un (fiche spectacle, fiche événement, fiche membre, réservation)
- [ ] Sur une fiche spectacle avec affiche, le titre passe pleine largeur AU-DESSUS des deux colonnes, et non à côté de l'affiche
- [ ] Un titre de spectacle de plus de soixante caractères ne chevauche pas l'affiche et ne déborde pas à droite
- [ ] Sur 375 px, l'en-tête d'une fiche membre reste lisible : rôle sous le nom, pas de chevauchement avec la photo

### Page d'accueil

- [ ] Le hero affiche le nom de l'association, puis l'accroche en couleur d'accent et plus petite, puis la présentation
- [ ] Modifier l'accroche dans Gestion → Paramètres change le hero au rechargement suivant
- [ ] Une accroche de dix mots se replie sans écraser le nom ni sortir de l'encadré
- [ ] Vider accroche et présentation laisse une page d'accueil valide : ni bloc vide, ni ligne orpheline sous le nom
- [ ] Les trois boutons (L'association / Les spectacles / L'agenda) tiennent sur 375 px sans se chevaucher ni déborder

### Page Contact

- [ ] Sans aucune coordonnée saisie, la page ne montre aucun encadré : elle est identique à ce qu'elle était
- [ ] Avec e-mail et téléphone saisis, l'encadré apparaît au-dessus du formulaire, étiquette à gauche et valeur à droite sur écran large, empilées sur mobile
- [ ] Le lien du téléphone compose le numéro sans ses espaces (survol pour lire l'URL, ou clic sur mobile)
- [ ] L'adresse n'apparaît PAS tant que la case « Afficher l'adresse postale » n'est pas cochée, même adresse complète renseignée
- [ ] Une fois la case cochée, l'adresse apparaît sur une ligne, code postal et ville ensemble
- [ ] Trois interlocuteurs s'affichent dans l'ordre de leur champ « ordre d'affichage », et pas dans l'ordre de saisie
- [ ] Un interlocuteur sans nom — une fonction seule, « Réservations » — s'affiche sans laisser de vide gênant

### Espace connecté — navigation

- [ ] En arrivant sur un écran, un seul groupe du rail est déplié : celui de la page affichée
- [ ] Cliquer le titre d'un autre groupe le déplie, et le premier reste ouvert : on peut en tenir plusieurs ouverts à la main
- [ ] Au clavier seul : Tab atteint un titre de groupe, Entrée le déplie, Tab continue dans ses entrées
- [ ] Le rail entier tient au-dessus du pli sur ton écran, sans faire défiler la page
- [ ] Dans l'espace connecté, l'en-tête ne montre que « Voir le site » et « Déconnexion »
- [ ] Sur la vitrine, l'en-tête montre bien les six liens publics
- [ ] Sur un vrai téléphone, le burger ouvre le tiroir, et le groupe « Le site » y donne accès aux pages publiques et à la déconnexion
- [ ] JavaScript désactivé : tous les groupes sont ouverts et rien n'est inatteignable

### Tableau de bord de gestion

- [ ] La grille « Modules » a disparu ; restent les tuiles, « En attente d'une décision » et « Ce qui arrive »
- [ ] Avec des fiches proposées, elles sont nommées et datées, et « Ouvrir la file de modération » y mène
- [ ] Sans rien en attente, la page dit « Rien n'attend de décision » et ne paraît pas cassée pour autant
- [ ] Le titre « Tableau de bord » paraît proportionné à sa colonne, comme un titre de la vitrine l'est à la sienne
- [ ] Les quatre tuiles restent alignées sur une largeur de 1024 px sans qu'une seule passe à la ligne

### Messages reçus et signaux du tableau de bord

- [ ] Un message déposé par le formulaire public apparaît dans Gestion → Vie associative → Messages reçus, sans passer par l'admin Django
- [ ] « Marquer comme traité » le sort de la liste par défaut, et « Tous » le retrouve
- [ ] Le lien sur l'adresse ouvre le client mail avec le sujet du message pré-rempli
- [ ] Une facture validée dont l'échéance est passée fait monter le compteur « facture(s) échue(s) », et le clic mène à l'onglet Factures
- [ ] Les compteurs à zéro sont visiblement en retrait des autres, sans que leur texte devienne difficile à lire
- [ ] Sur 1024 px, les huit tuiles se répartissent sans qu'une seule dépasse en hauteur de sa rangée
- [ ] Une facture validée impayée figure dans « En retard », nommée, avec son ancienneté en jours, et le lien mène à la facture
- [ ] Une réunion convoquée dont la date est passée y figure aussi, avec « tenue, mais sans compte-rendu »
- [ ] Une réunion convoquée à VENIR n'y figure pas — elle reste dans « Ce qui arrive »
- [ ] Le motif ne répète pas la date affichée à droite : il apporte autre chose

### Vocabulaire

- [ ] Aucun écran de gestion n'affiche « Bureau » comme nom de section, ni « Back-office » : le sur-titre dit « Gestion »
- [ ] Là où il s'agit des personnes, le mot reste : « Équipe du bureau », « transmis au bureau », « validation du bureau »
- [ ] Le groupe du rail s'appelle « Gestion » — dépend du commit en cours sur `_nav_espace.html`, non livré par l'agent
- [ ] La branche « Bureau » de l'explorateur de fichiers garde son nom : elle désigne bien les élus

### Palettes et mode sombre

- [ ] Les dix-huit palettes se choisissent depuis le panneau et s'appliquent sans rechargement
- [ ] En mode sombre, chaque palette garde SA teinte : les liens de la 13 restent magenta, ceux de la 17 verts
- [ ] En mode sombre, l'item courant du rail se lit sans effort sur les palettes 2, 4 et 7
- [ ] Les titres de groupe du rail se lisent sans effort sur les palettes à rail sombre, tout en restant visiblement secondaires par rapport aux entrées
- [ ] Au survol, le bouton principal du hero s'éclaircit dans SA couleur et ne vire pas à l'ambre
- [ ] Sur un écran dense (facturation, budget), aucune palette ne rend un texte pénible à lire

### Polices de titre

- [ ] Les cinq choix s'appliquent aux titres ET au logo « L'Improliante »
- [ ] Instrument Serif ne paraît pas faussement graissé — ses pleins et déliés restent fins
- [ ] Sur « Politique de confidentialité » à 375 px, la police retenue reste lisible et ne déborde pas
- [ ] Au premier chargement, le passage de la police de repli à la police web ne fait pas sauter la mise en page

### Fichiers statiques

- [ ] Le code source d'une page servie en production porte un CSS empreinté (`site.<empreinte>.css`), pas `site.css`
- [ ] Après un déploiement, un rechargement SIMPLE — sans vidage de cache — montre bien les modifications
