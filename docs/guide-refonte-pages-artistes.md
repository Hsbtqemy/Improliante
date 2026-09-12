# Improliante — Guide de transformation des pages publiques et des pages artistes

**Version 1.0 · 12 septembre 2026**  
**Destinataires :** responsable de l’association, designer, développeur et personnes chargées des contenus.  
**Nature :** proposition de spécifications et guide de réalisation. Ce document n’atteste pas d’une implémentation ni d’une conformité acquise.

## 1. Décision de conception

Concevoir **un seul site Improliante, avec des pages artistes expressives à l’intérieur d’une identité commune**. Le visiteur doit reconnaître le collectif, comprendre qui crée quoi, retrouver les dates et accéder aux réservations sans réapprendre l’interface.

L’artiste personnalise ses contenus, ses images, une couleur d’accent et la composition de son introduction. L’association conserve la maîtrise des boutons, encadrés, traits, espacements, polices de lecture et composants pratiques. Les préférences d’affichage du visiteur priment sur la personnalisation artistique.

Les trois univers montrés dans l’exemple précédent — papier, nocturne et végétal — sont à considérer comme des **pistes de direction artistique globale**. Ils ne constituent pas trois sites indépendants à laisser choisir à chaque membre.

### Ce que cette approche apporte

- **Identité collective reconnaissable :** accueil, agenda, spectacle et artiste partagent la même grammaire graphique.
- **Personnalité artistique :** les œuvres, photographies, affiches et textes structurent chaque page.
- **Informations fiables :** un spectacle et une représentation conservent une fiche de référence unique.
- **Autonomie des artistes :** l’espace membre permet d’éditer une page sans connaître le code.
- **Accessibilité durable :** les améliorations des composants et des réglages profitent à toutes les pages.
- **Maintenance maîtrisée :** Django et les données métier sont conservés ; les variantes restent limitées et testables.

### Comment lire ce guide

**Existant vérifié** décrit le code du dépôt au commit `8525e563fd61e8bb3b707e2a30ac3215a8993b99`. Les références [C1–C10] renvoient à cet état précis. Aucun contrôle du déploiement actuel n’est supposé.

**Cible proposée** décrit le comportement à réaliser. Les limites numériques de contenu, les budgets de poids et les dimensions de design sont des valeurs de départ configurables, distinctes des seuils normatifs d’accessibilité.

Le présent guide complète l’audit précédent. Il porte sur cette transformation et ne constitue pas une nouvelle vérification de l’ensemble du backend.

## 2. Périmètre et première version

### Inclus dans la première version

1. Une identité publique commune appliquée à la navigation et aux composants réutilisés.
2. Deux compositions d’introduction de page artiste : **portrait éditorial** et **visuel de création**.
3. Une couleur d’accent personnalisable, avec combinaisons de rendu validées.
4. Une présentation publique, une démarche, un portrait, une bannière et une galerie.
5. Un spectacle mis en avant, les créations portées et les collaborations.
6. Les prochaines participations publiques de l’artiste, explicitement rattachées aux événements.
7. Une vidéo YouTube facultative, chargée à la demande.
8. Un espace « Ma page artiste » avec brouillon, aperçu et publication contrôlée.
9. L’évolution du panneau de confort existant, sans compte requis pour le visiteur.
10. La reprise des pages existantes, de leurs adresses et de leurs contenus.

### À prévoir ensuite

Une troisième composition, plusieurs vidéos, des pages de démarche plus longues, une médiathèque partagée avec autorisations explicites et une délégation d’édition à un autre membre pourront être ajoutées après usage réel de la première version.

### Hors périmètre initial

Éditeur de page libre, CSS ou HTML saisi par les artistes, téléversement de polices, positionnement au pixel, glisser-déposer obligatoire, hébergement de fichiers vidéo, nouvelle billetterie payante et refonte des fonctions comptables ou documentaires.

La cohérence exige d’adapter au minimum l’en-tête, le pied de page, les cartes de spectacles et les lignes de dates sur les autres pages publiques. Elle n’impose pas de reconstruire immédiatement chaque écran administratif.

## 3. Socle existant : réutilisation et écarts

| Domaine | Existant vérifié | Transformation nécessaire |
|---|---|---|
| Identité | `Membre` possède biographie, rôle public, site, portrait et visibilité publique. Le compte associé est facultatif. [C1] | Ajouter la présentation éditoriale et sa publication, sans mêler les données publiques aux coordonnées administratives. |
| Adresse | `/@slug` ; ancienne adresse numérique redirigée en 301. [C2] | Conserver les adresses. Ne pas régénérer les slugs lors d’une refonte ou d’un changement de nom public. |
| Spectacles | La vue distingue spectacles portés et collaborations publiés. [C2] | Conserver cette distinction et ajouter une mise en avant éditoriale contrôlée. |
| Dates | `Intervention` rattache un membre à un événement avec son rôle. [C3] | Construire la liste des participations publiques à venir ; expliciter les distributions permanentes. |
| Profil membre | `mon_profil` édite le membre connecté ; formulaire pour bio, rôle, site et portrait. [C4] | Étendre ce parcours et séparer « enregistrer un brouillon » de « rendre public ». |
| Images | `Media`, portrait, galeries de spectacles/événements ; limite d’import de 5 Mio dans les formulaires communs. [C5, C6] | Ajouter la galerie artiste, les cadrages, les dérivés optimisés et une gestion des médias privés de brouillon. |
| Vidéo | `Media` accepte déjà `VIDEO` et une URL externe ; la galerie publique prévoit un lien externe. [C5, C10] | Ajouter saisie dédiée, validation du fournisseur et lecteur au clic. Un champ URL existant ne garantit pas une intégration sécurisée. |
| Confort de lecture | Script et cookie `a11y` déjà présents ; options et taille du texte. [C7] | Réutiliser ce mécanisme, vérifier son application aux nouveaux composants et compléter l’affichage épuré. |
| Technique | Templates Django, CSS et JavaScript ciblés. [C8] | Introduire des composants et styles publics cohérents, sans migration imposée vers une application React. |

**Point concret à traiter :** les images de `MEDIA_ROOT` sont décrites comme servies publiquement par Nginx dans les réglages. Une future image de brouillon déposée à cet emplacement ne devient pas privée parce que la page est cachée. Le stockage et la distribution des nouveaux médias privés doivent être conçus avant de promettre des aperçus confidentiels. [C9]

## 4. Identité graphique : règles communes et liberté artistique

### 4.1. Une direction globale

Point de départ recommandé : une composition de programme culturel contemporain, avec une typographie de titre expressive, du texte courant sobre, des filets fins, des dates lisibles et une place généreuse aux images. Le choix final doit être évalué sur l’accueil, une page artiste et une page spectacle ensemble, avec de vrais contenus.

Éviter l’uniformité d’une succession de cartes identiques. Utiliser une ouverture éditoriale, des listes de rendez-vous, des affiches et des sections de texte selon la nature du contenu.

### 4.2. Matrice de personnalisation

| Élément | Maîtrise | Règle de réalisation |
|---|---|---|
| Logo, navigation, pied de page | Association | Identiques sur toutes les pages publiques. |
| Boutons, champs et messages | Association | Mêmes formes, libellés usuels, hauteurs minimales et états. |
| Encadrés et filets | Association | Un petit vocabulaire commun : filet de section, cadre de média et message fonctionnel. |
| Arrondis et ombres | Association | Valeurs communes ; aucune commande par artiste. |
| Espacement et largeur de lecture | Association | Grille et échelle cohérentes ; aucune valeur libre. |
| Police de lecture, titres de sections | Association | Même hiérarchie ; polices chargées localement si possible. |
| Grand titre d’entrée | Association, via la composition | Deux traitements compatibles au maximum ; pas de police importée par l’artiste. |
| Couleur d’accent | Artiste | Une valeur contrôlée ; le système en dérive les usages lisibles. |
| Fonds et couleurs de statut | Association / visiteur | L’artiste ne redéfinit ni les erreurs ni la confirmation ni le focus. |
| Portrait, bannière, galerie | Artiste | Cadres prévus, cadrage non destructif et légendes. |
| Texte et création mise en avant | Artiste | Champs structurés ; seules les relations autorisées sont proposées. |
| Ordre des sections | Association, puis choix limité | Introduction et dates stables ; déplacement des blocs éditoriaux optionnels seulement en évolution. |
| Réglages de confort | Visiteur | Prioritaires sur les couleurs et traitements artistiques. |

### 4.3. Valeurs de design à formaliser

Créer des variables sémantiques pour les fonds, textes, accents, bordures, erreurs, focus, espacements et rayons. Par exemple : `--public-surface`, `--public-text`, `--artist-accent`, `--public-border`, `--public-focus`.

Valeurs de départ pour le travail graphique : filets de 1 px ; arrondi discret commun aux commandes ; échelle d’espacement de 4, 8, 12, 16, 24, 32, 48 et 64 px ; texte courant de 1 rem au minimum avec interligne autour de 1,5 ; paragraphes de l’ordre de 60 à 75 caractères de largeur. Ce sont des choix de conception à éprouver, pas des critères suffisants de conformité.

Ne pas rendre les bordures fonctionnelles trop pâles. Un filet décoratif n’a pas la même fonction que la bordure permettant d’identifier un champ.

### 4.4. Couleur choisie et couleurs réellement utilisées

L’interface propose quelques accents prêts à l’emploi et un sélecteur de couleur. En première version, accepter un format canonique opaque, par exemple `#RRGGBB`, sans transparence ni expression CSS.

Le serveur valide la valeur et calcule les couples utiles : texte sur fond, texte du bouton sur son fond, lien sur surface, états interactifs et variantes de thème. Le navigateur donne un retour immédiat, mais ne constitue pas le seul contrôle.

Si la couleur est inutilisable dans un contexte, afficher une correction compréhensible : « Cette teinte sera assombrie pour les liens afin de rester lisible ». Montrer le résultat avant publication. Conserver au besoin la couleur originale dans les zones purement décoratives.

Ne pas appliquer aveuglément l’accent à tous les textes et traits. Ne pas considérer un simple choix automatique noir/blanc comme une vérification complète de tous les composants.

### 4.5. Deux compositions compatibles

**Portrait éditorial :** nom, accroche et démarche courte à côté d’un portrait ou d’une photographie de travail. Convient à un artiste présentant plusieurs projets.

**Visuel de création :** introduction associée à l’affiche ou à l’image d’un spectacle mis en avant. Le nom de l’artiste reste le titre principal de la page. Convient à une création en tournée ou en lancement.

Les deux variantes réutilisent ensuite les mêmes dates, listes de spectacles, légendes, boutons et liens. Sur mobile, elles se réorganisent dans un ordre de lecture logique. Une page sans visuel reste soignée, sans rectangle vide ni photographie générique imposée.

## 5. Contenus, navigation et règles métier

### 5.1. Structure de la page artiste

1. Navigation commune et retour vers le collectif.
2. Nom public en titre principal, disciplines ou rôle, accroche, visuel facultatif.
3. Lien vers les prochains rendez-vous lorsque des dates existent.
4. Prochaines participations publiques.
5. Spectacles portés ; mise en avant d’une création possible.
6. Collaborations, avec le rôle de l’artiste.
7. Démarche, galerie et vidéo si renseignées.
8. Liens publics choisis et pied de page commun.

La biographie complète peut être placée après les créations. Les informations pratiques ne doivent pas être repoussées sous une longue biographie ou une galerie.

### 5.2. Champs éditoriaux proposés

| Champ | Limite initiale proposée | Comportement |
|---|---|---|
| Nom public | 150 caractères | Distinct du nom administratif si nécessaire ; ne modifie pas le slug. |
| Disciplines / rôle public | Réutiliser les 200 caractères existants | Libellé textuel lisible, sans multiplication obligatoire de badges. |
| Accroche | 180 caractères | Une phrase, facultative. |
| Introduction | 600 caractères | Résumé visible dès l’entrée. |
| Biographie / démarche | 6 000 caractères | Paragraphes ; mise en forme limitée et sûre. |
| Création mise en avant | Une relation vers un spectacle | Sélection parmi les spectacles autorisés ; publication du spectacle contrôlée à l’affichage. |
| Galerie | 8 images maximum | Ordre modifiable par boutons monter/descendre. |
| Vidéo | Une URL YouTube | Titre, couverture et complément textuel associés. |

Les limites se configurent côté serveur et s’affichent dans le formulaire. Les textes trop longs ne doivent jamais être perdus ou tronqués silencieusement à l’enregistrement.

### 5.3. Une source de référence pour chaque information

Le titre, le synopsis et les dates d’un spectacle restent dans leurs modèles métier. La page artiste référence ces objets. Elle peut ajouter un texte personnel présentant le travail, sans créer une deuxième fiche de spectacle divergente.

Une collaboration doit préciser le rôle connu : interprétation, écriture, mise en scène, musique, etc. Ne pas inventer un rôle lorsqu’il n’est pas renseigné.

Le spectacle mis en avant peut apparaître à nouveau dans la liste exhaustive, mais avec un traitement discret ou une déduplication dans cette même section. Préserver l’accès à tous les projets.

### 5.4. « Mes prochaines participations » : règle stricte

En première version, afficher les événements à venir explicitement reliés à l’artiste par `Intervention`, à condition qu’ils soient **publiés et publics**. Dédupliquer par événement, trier chronologiquement, utiliser le fuseau de l’association et proposer une liste étendue si nécessaire.

Une présence dans la distribution générale du spectacle ne prouve pas une participation à chaque date. De plus, une intervention peut concerner l’organisation plutôt que le jeu : le titre neutre « Prochaines participations » évite d’annoncer systématiquement « Sur scène ».

Pour une distribution permanente, proposer ultérieurement au responsable d’événement de **copier puis confirmer** les participants du spectacle. Ne pas introduire un héritage implicite qui rendrait les dates individuelles trompeuses.

Un événement public lié à un spectacle non publié ne doit pas révéler les champs de ce spectacle. Selon la règle métier retenue pour l’événement, afficher seulement ses propres informations publiques ou exclure le lien au spectacle.

### 5.5. États à dessiner

| Situation | Affichage attendu |
|---|---|
| Aucune date future | « Aucune prochaine date annoncée » ; créations et liens restent accessibles. |
| Aucun spectacle publié | Présentation et médias conservés ; pas de fausse carte de démonstration. |
| Aucune image | Composition textuelle prévue. |
| Spectacle retiré de publication | Retrait immédiat des références publiques qui exposeraient son contenu. |
| Réservation indisponible | Lien « Voir les informations », selon le fonctionnement réel de l’événement. |
| Jauge atteinte | État « Complet » et accès aux informations, sans bouton de réservation trompeur. |
| Vidéo inaccessible | Message court et lien externe conservé. |
| Page artiste masquée | Aucun contenu public, ni dans les résultats internes, les métadonnées ou le plan du site. |
| Artiste inactif dans l’association | Ne pas dépublier automatiquement : `actif` et `visible_sur_site` ont des fonctions différentes. |

Les annulations et reports devront réutiliser un statut métier fiable, ou être ajoutés explicitement si le modèle actuel ne les représente pas. Ne pas déduire « annulé » d’un titre ou d’une date passée.

## 6. Images, affiches et galeries

### Parcours utilisateur

Importer → voir l’image → choisir un cadrage → renseigner description, légende et crédit → enregistrer le brouillon → vérifier l’aperçu.

Distinguer **retirer de cette page**, **remplacer** et **supprimer définitivement**. Un média réutilisé par un spectacle ou une révision publiée ne doit pas être détruit par une simple suppression dans une galerie.

### Affichage

- Portrait : cadre stable, position du point focal enregistrée.
- Bannière : cadrage souple, vérifié sur mobile ; aucune hauteur fixe qui coupe le texte.
- Affiche : montrer l’œuvre entière dans un cadre adapté ; ne pas couper ses mentions par défaut.
- Galerie : images responsives, légendes accessibles, ordre identique pour la lecture et le clavier.
- Agrandissement : une page image ou un dialogue accessible ; Échap ferme le dialogue, puis le focus revient à la commande d’ouverture.

Le point focal est une donnée de présentation, par exemple deux coordonnées normalisées entre 0 et 1. Conserver l’original et produire des dérivés plutôt que recadrer destructivement le fichier source.

### Import et stockage

Conserver initialement la limite existante de **5 Mio par image**. Limiter aussi les dimensions décodées, par exemple à 25 mégapixels, ainsi que le nombre d’images et le quota total par compte. Ces limites sont à centraliser et à ajuster sur des photos réelles.

Accepter une liste réduite de formats décodables, par exemple JPEG, PNG et WebP. Valider le contenu réel, réencoder les images, utiliser des noms de stockage générés et supprimer les métadonnées sensibles des dérivés publics. Exclure les SVG et fichiers animés des imports membres dans cette première version. Protéger les imports par authentification, autorisation et limites de ressources. [S8, S9]

Prévoir un stockage privé pour les nouveaux originaux et médias de brouillon, puis des dérivés publics des seuls médias publiés. Une URL difficile à deviner n’est pas un contrôle d’accès. Si un média a déjà été publié ailleurs, son retrait d’un brouillon ne le rend pas confidentiel rétroactivement.

Une sauvegarde de la base ne sauvegarde pas les fichiers : inclure les médias privés et publics dans la stratégie de restauration. La suppression différée doit respecter les références des pages et révisions conservées.

### Alternatives textuelles et droits de publication

Conserver l’exigence actuelle de description pour les images importées informatives. Expliquer avec un exemple : « Camille et deux partenaires improvisent autour d’une table » est plus utile que « photo 3 ».

Les crédits et les légendes sont distincts du texte alternatif. Les décorations créées par le design n’ont pas à être annoncées ; elles doivent rester réellement décoratives. L’éventuel support d’un `alt` vide pour un média importé exige une règle explicite compatible avec les validations existantes.

Les informations d’une affiche — titre, date, lieu et accès — doivent aussi exister sous forme de texte dans la page. Prévoir un champ de crédit et une confirmation éditoriale de l’autorisation d’usage des visuels, sans prétendre automatiser la vérification des droits.

## 7. Vidéo YouTube

Le modèle `Media` prévoit déjà une URL vidéo. La cible ajoute une utilisation encadrée à la page artiste, sans importer le fichier vidéo sur le serveur d’Improliante.

### Saisie et validation

L’artiste colle une URL YouTube. Le serveur reconnaît des formes autorisées, comme `watch?v=`, `youtu.be/`, `shorts/` et `embed/`, puis extrait et stocke un identifiant canonique. Vérifier exactement le nom d’hôte et le format de l’identifiant ; refuser un domaine ressemblant à YouTube, du HTML fourni par l’utilisateur ou une URL arbitraire. Ne pas récupérer automatiquement le contenu de toute URL saisie.

En première version, ignorer ou refuser clairement les playlists et paramètres non pris en charge. Ne pas promettre une validation de la disponibilité distante si aucun contrôle distant n’est effectué.

### Lecture et confidentialité

Afficher une couverture hébergée par Improliante et une commande « Charger la vidéo YouTube ». Avant ce choix, ne charger ni lecteur, ni miniature distante, ni script, ni connexion anticipée vers YouTube. Après activation, construire le lecteur à partir de l’identifiant validé ; le domaine de confidentialité avancée documenté est `youtube-nocookie.com`. Ce mode ne signifie pas absence de toute communication avec Google. [S10]

Aucune lecture automatique à l’arrivée sur la page. Conserver les commandes de lecture et le plein écran. Proposer un lien « Ouvrir sur YouTube » et informer que le lecteur est un service externe. Le mécanisme doit s’intégrer aux choix de confidentialité du site ; un bouton au clic n’est pas à lui seul une attestation de conformité juridique.

Tester sur le véritable domaine de préproduction : la lecture dépend notamment de l’autorisation d’intégration de la vidéo et de la transmission d’un référent HTTP compatible. YouTube documente une erreur 153 en son absence. Ne pas appliquer aveuglément une politique `no-referrer` au lecteur. [S10]

### Accessibilité et défaillances

Associer au lecteur un titre explicite. Prévoir des sous-titres relus, un complément textuel et, lorsque les informations visuelles le nécessitent pour la cible d’accessibilité, une audiodescription. Une transcription ne remplace pas automatiquement toutes les exigences applicables à une vidéo. [S6]

Le chargement ou l’échec ne déplace pas arbitrairement le focus. Une vidéo supprimée, privée, bloquée ou non intégrable laisse la page utilisable. La galerie et les informations pratiques restent disponibles indépendamment de YouTube.

## 8. Accessibilité : socle obligatoire et confort facultatif

### 8.1. Objectif

Viser **WCAG 2.2 niveau AA** pour les parcours transformés, y compris leur édition. La sélection ci-dessous sert au développement et ne remplace pas la vérification de tous les critères applicables. Ne publier aucune affirmation de conformité sans évaluation correspondante. Les éventuelles obligations réglementaires propres à l’association relèvent d’une vérification distincte. [S1]

Chaque variante doit être accessible dans son état initial. Le mode de confort est une préférence supplémentaire ; il ne doit pas servir à tolérer une page artistique illisible.

### 8.2. Exigences de réalisation

| Sujet | Exigence et contrôle |
|---|---|
| Texte | Contraste d’au moins 4,5:1 pour le texte courant et 3:1 pour les grands caractères au sens WCAG. Vérifier les fonds et états réellement rendus. [S2] |
| Contrôles | Contraste non textuel suffisant pour les éléments nécessaires à l’identification des commandes, selon le critère 1.4.11. Le focus reste visible et non entièrement masqué. [S1] |
| Agrandissement | Texte agrandi à 200 % sans perte de contenu ou de fonction, sous réserve des exceptions du critère 1.4.4. [S3] |
| Redistribution | Lecture à 320 pixels CSS de largeur sans défilement dans les deux dimensions, hors contenus nécessitant intrinsèquement deux dimensions. Tester aussi le zoom à 400 % depuis 1 280 pixels de large. [S4] |
| Espacement utilisateur | Supporter sans perte un interligne de 1,5 fois la taille du texte, un espacement de paragraphes de 2 fois, de lettres de 0,12 fois et de mots de 0,16 fois. Ce sont des conditions de test, pas un style à imposer partout. [S5] |
| Clavier | Tous les liens, commandes, formulaires et lecteurs utilisables au clavier, dans un ordre logique ; aucun piège hors dialogue correctement géré. |
| Structure | Un titre principal par page ; sous-titres hiérarchisés ; régions et liens clairement nommés ; lien d’accès direct au contenu. |
| Actions | Viser des cibles tactiles de 44 × 44 pixels CSS comme choix de confort du projet ; ne pas confondre cette cible avec le seuil AA de 24 × 24 et ses exceptions. [S1] |
| Erreurs | Résumé des erreurs, messages associés aux champs, conservation des données et confirmation d’enregistrement perceptible. |
| Information | Aucun statut communiqué uniquement par couleur, icône, survol ou affiche. |
| Mouvement | Respect de la préférence système de réduction du mouvement ; aucun carrousel automatique ni animation indispensable à la compréhension. |
| Réorganisation | Boutons monter/descendre disponibles même si un glisser-déposer est ajouté. |

### 8.3. Réglages du visiteur

Faire évoluer le panneau existant vers des choix compréhensibles : taille du texte, espacement, thème de lecture, contraste renforcé, affichage épuré et réduction du mouvement. Une préférence n’implique pas automatiquement les autres : certaines personnes préfèrent un fond clair, d’autres un fond sombre.

En première livraison, prioriser la bonne conservation des options déjà présentes et l’ajout d’un affichage épuré. Ce dernier réduit les décorations et les compositions complexes, conserve les images porteuses de sens et garde toutes les fonctions.

Ordre d’application : **styles de base → variante artiste → préférences explicites de lecture**. En l’absence de choix explicite, respecter les préférences du système. Ne jamais neutraliser les mécanismes natifs de couleurs forcées ou de zoom pour maintenir une esthétique.

Conserver le cookie `a11y` et son rendu initial côté serveur s’ils conviennent après vérification. Éviter un second stockage concurrent. Valider les valeurs reçues par une liste fermée ; les préférences ne contiennent aucune information médicale.

**Attention au code actuel :** `reinitialiser()` réécrit toutes les classes de l’élément `html`. Si les thèmes utilisent aussi cet élément, une remise à zéro pourrait les supprimer. Limiter les modifications aux classes appartenant au confort, ou placer le thème artiste sur un conteneur distinct. Le changement d’un réglage ne doit pas effacer les autres classes de l’application. [C7]

Le cache doit tenir compte des préférences réellement rendues par le serveur, ou cacher seulement les fragments indépendants de celles-ci. Un visiteur ne doit pas recevoir les options d’un autre.

## 9. Espace membre : « Ma page artiste »

### Organisation de l’interface

Prévoir cinq sections successives, navigables au clavier : **Présentation**, **Apparence**, **Images**, **Vidéo**, **Aperçu et publication**. Un formulaire simple et des sous-sections accessibles suffisent ; aucun éditeur de site complet n’est nécessaire.

Chaque section explique seulement les choix utiles à l’artiste. Ne pas exposer les noms de modèles, les identifiants internes ou les réglages CSS.

Commandes principales : **Enregistrer le brouillon**, **Voir l’aperçu**, puis **Publier les modifications** lorsque l’autorisation existe. Afficher « Dernier enregistrement… » et « Version publique… » pour lever toute ambiguïté. Une prévisualisation ne doit pas publier.

### Aperçu

Utiliser les mêmes composants et le même rendu serveur que la page publique, avec un contexte de brouillon. Prévoir une largeur ordinateur/mobile et la possibilité d’appliquer les préférences de confort à l’aperçu. Ne pas maintenir une maquette JavaScript indépendante qui pourrait diverger de la production.

L’aperçu est authentifié, réservé au propriétaire et au bureau autorisé, et envoyé avec des directives empêchant sa mise en cache partagée et son indexation. Un `noindex` seul n’est pas une protection d’accès. Ne pas ajouter de lien d’aperçu partageable dans la première version.

### Cas à gérer

- Compte connecté sans fiche membre : explication et retour vers l’espace personnel, sans page créée automatiquement.
- Fiche membre sans compte : gestion possible par le bureau, sans fabrication d’un compte de connexion.
- Nouvelle image invalide : conserver les autres champs et la version précédente ; expliquer si le fichier doit être sélectionné de nouveau.
- Fermeture avec modifications non enregistrées : avertissement discret et pertinent.
- Deux éditeurs ou onglets simultanés : conflit signalé avant écrasement d’une version plus récente.
- Import en cours : état visible ; la publication attend la fin du traitement du média.
- Échec de publication : la version publique précédente reste intacte.

## 10. Droits et publication

### 10.1. Matrice cible

Les noms de capacités ci-dessous sont des propositions, pas des permissions supposées déjà implémentées.

| Action | Visiteur | Compte sans membre | Artiste propriétaire | Autre artiste | Bureau autorisé |
|---|---|---|---|---|---|
| Lire une page publique | Oui | Oui | Oui | Oui | Oui |
| Modifier la page artiste | Non | Non | Sa page | Non | Pages relevant de sa fonction |
| Lire un brouillon / aperçu | Non | Non | Le sien | Non | Oui |
| Ajouter ou retirer un média de la page | Non | Non | Dans son périmètre | Non | Oui |
| Activer la première publication | Non | Non | Demander | Non | Oui |
| Publier une nouvelle révision | Non | Non | Si capacité accordée | Non | Oui |
| Modifier visibilité / mise en avant collective | Non | Non | Demander | Non | Oui |
| Choisir son confort de lecture | Oui | Oui | Oui | Oui | Oui |

Le fait d’être `staff` ou connecté ne doit pas ouvrir implicitement toutes les opérations. Le contrôle s’effectue pour chaque objet et chaque action, y compris les identifiants de médias envoyés dans un formulaire. Refus par défaut lorsqu’un rattachement ou une autorisation manque. [S7]

`Media.cree_par` décrit l’auteur de l’import ; ce champ nullable ne doit pas devenir à lui seul toute la politique de propriété. Un import réalisé par le bureau pour un artiste doit avoir un rattachement métier explicite.

### 10.2. Circuit recommandé

1. L’artiste enregistre une révision de travail ; le public voit toujours l’ancienne version publiée.
2. Il vérifie l’aperçu.
3. Pour la première activation, le bureau valide la page et sa visibilité.
4. Pour les changements suivants, l’artiste disposant de la capacité dédiée publie explicitement sa révision. Les changements sont tracés et consultables par le bureau.
5. Le bureau peut suspendre la visibilité ou restaurer une révision antérieure.

Ce circuit est une **évolution proposée** : actuellement, l’enregistrement du profil modifie directement `Membre`. Il faut implémenter une véritable séparation brouillon/public pour respecter cette promesse. [C4]

La capacité de publier sa page n’autorise pas à publier un spectacle ou un événement en attente. Leurs règles de modération restent indépendantes.

### 10.3. Invariants de publication

- La visibilité décidée par le bureau reste prioritaire sur une révision publiée.
- Une publication change l’ensemble des contenus éditoriaux et références médias de la révision de manière atomique.
- La publication d’une ancienne révision ne ressuscite ni un événement privé ni un spectacle retiré : les relations métier sont filtrées au moment de la lecture.
- Une révision rejetée ou remplacée ne laisse pas de média privé accessible publiquement.
- Les journaux conservent auteur, date et action ; les changements sensibles sont attribuables.

## 11. Architecture Django proposée

### 11.1. Modèles et responsabilités

Les noms sont indicatifs ; adapter les migrations aux conventions du dépôt.

| Objet | Responsabilité proposée |
|---|---|
| `Membre` | Identité associative, compte facultatif, slug et contrôle de visibilité ; conservation des données privées. |
| `PageArtiste` | Relation unique vers `Membre`, pointeur vers révision de travail et révision publiée, version de concurrence. |
| `RevisionPageArtiste` | Contenu public éditorial, variante, accent, référence de création mise en avant, auteur et horodatage. Révision publiée immuable. |
| `Media` | Réutiliser l’identité du média ; étendre son traitement et les métadonnées nécessaires. |
| `MediaPageArtiste` | Relation à la révision, rôle du média, ordre, cadrage et description contextuelle éventuelle. |
| `Spectacle`, `Evenement`, `Intervention` | Sources métier inchangées pour œuvres, dates et participations ; ajouts ciblés seulement si nécessaires. |

Le nom public, la biographie, le portrait et les liens affichés doivent avoir **une source éditoriale faisant autorité** après migration. Si leur publication est différée, le rendu doit lire la révision publique, et non les champs de `Membre` en cours de modification. Les données privées restent dans `Membre`.

Décider champ par champ lesquels migrent vers la révision. Mettre à jour aussi les anciennes vues d’édition et le backoffice : aucun formulaire historique ne doit permettre de contourner involontairement la publication. Ne pas garder deux biographies éditables indépendamment.

Les références à spectacles et événements restent dynamiques. Une révision est un instantané éditorial, pas une copie de l’agenda ni une sauvegarde complète du système.

### 11.2. Services

Centraliser les opérations suivantes : déterminer les droits ; construire le contexte public ; récupérer les participations publiques ; normaliser les couleurs ; valider les vidéos ; traiter les images ; enregistrer une révision ; publier ; restaurer ; retirer une association à un média.

Utiliser des transactions pour les changements de références en base, et un contrôle de version pour les éditions concurrentes. Un verrou ou une transaction SQL ne remet pas automatiquement en état un stockage de fichiers : préparer les dérivés, puis basculer les références et nettoyer les fichiers orphelins de façon maîtrisée.

Une validation de formulaire ne couvre pas les imports, l’admin et les services. Les invariants essentiels doivent être partagés et complétés par les contraintes de base appropriées.

### 11.3. Templates, CSS et scripts

- Conserver un squelette public commun et des inclusions pour en-tête artiste, ligne de date, aperçu spectacle, galerie et vidéo.
- Transformer `membre_detail.html` en composition de ces briques plutôt qu’ajouter un deuxième site parallèle.
- Organiser le CSS public en fondations, composants, variantes et préférences ; préserver les composants administratifs tant qu’ils ne sont pas migrés.
- Limiter les scripts aux interactions : aperçu, confort, cadrage, réorganisation et chargement vidéo.
- Garder le contenu et les liens essentiels disponibles sans JavaScript. Un formulaire d’enregistrement classique reste fonctionnel ; le confort peut prévoir un enregistrement serveur si nécessaire.
- Ne jamais injecter du HTML utilisateur marqué arbitrairement comme sûr. Préférer texte échappé et balisage limité explicitement nettoyé. [S9]

Pour les accents personnalisés, émettre uniquement des valeurs CSS validées via un mécanisme compatible avec la politique de sécurité du contenu retenue : feuille générée ou bloc autorisé avec nonce, par exemple. Ne pas ouvrir globalement `unsafe-inline` pour contourner une difficulté d’intégration. Les changements d’en-têtes de sécurité doivent être vérifiés avec le lecteur vidéo et les scripts du site.

### 11.4. Carte des interventions dans le dépôt

| Emplacement existant | Travail attendu |
|---|---|
| `apps/coeur/models.py`, `services.py` | Articulation entre identité du membre et données publiques ; réutilisation du portrait. |
| `apps/vitrine/models.py` ou module de présentation dédié | Modèles de page/révision et règles éditoriales, selon le découpage choisi. |
| `apps/vitrine/views.py` | Rendu de la révision publique et liste des participations filtrées. |
| `apps/espace_membre/forms.py`, `views.py` | Extension du parcours d’édition, brouillon, aperçu et commandes autorisées. |
| `apps/medias/models.py` et services à créer si utiles | Rattachement et droits explicites, vidéo normalisée, images et cycle de vie. |
| `apps/common/fiches.py` | Réutilisation des validations d’images sans coupler abusivement les droits artiste/spectacle/événement. |
| `front/templates/vitrine/` | Page artiste et composants communs aux autres pages publiques. |
| `front/templates/espace_membre/profil_form.html` | Nouveau parcours, ou séparation claire entre profil administratif et page publique. |
| `front/static/css/site.css` | Extraction progressive de styles publics et gestion des variables. |
| `front/static/js/accessibilite.js` | Préférences conservées, réinitialisation limitée et compatibilité des variantes. |
| `config/settings.py` et configuration du serveur | Stockage privé/public, limites d’import, cache et sécurité du lecteur. |
| SEO existant, plan du site et recherche interne | Données publiées seulement, même nom public et mêmes visuels que la page. |

## 12. Performance, référencement et fiabilité

**Images :** générer des tailles adaptées à plusieurs largeurs, annoncer dimensions ou ratio pour éviter les sauts de page, charger paresseusement les médias situés plus bas. L’image principale utile au premier écran ne doit pas être retardée mécaniquement. Ne pas envoyer systématiquement l’original de 5 Mio.

**Budget de départ à mesurer :** viser environ 1,5 Mo au maximum de ressources transférées au chargement initial d’une page artiste riche, hors vidéo déclenchée volontairement ; viser moins de 300 Ko pour son image principale lorsque la qualité le permet. Ces budgets sont des cibles du projet, à ajuster par mesure, pas des résultats observés ni des garanties.

**Base de données :** utiliser les chargements groupés appropriés aux médias et relations ; éviter une requête par spectacle ou image ; limiter la première liste de dates et prévoir son extension. Fixer un budget de requêtes à partir d’une mesure avant/après sur le même jeu de données.

**Cache :** séparer public et privé. Invalider les pages concernées lors d’une publication, dépublication ou modification d’événement. Ne pas mettre en cache publiquement un aperçu ou une réponse personnalisée de l’espace membre.

**Référencement :** préserver les URLs et redirections existantes, produire titre et description issus du contenu public, conserver des métadonnées de partage cohérentes. Adapter les données structurées existantes au nom public et aux médias publiés ; ne pas annoncer des informations absentes de la page. Exclure les brouillons des index, recherches et métadonnées.

**Défaillances :** une préférence inconnue revient à un défaut lisible ; une variante retirée dispose d’un repli prévu ; l’échec d’un tiers ne bloque pas la page ; une image absente ne casse pas sa composition.

## 13. Risques à suivre pendant le chantier

| Risque | Importance | Mesure concrète |
|---|---|---|
| Pages perçues comme des sites différents | Forte | Valider accueil, artiste et spectacle côte à côte ; figer boutons, cadres, traits et rythme communs. |
| Résultat encore générique | Forte | Travailler avec de vrais visuels et textes ; varier les formats de contenu, pas seulement la couleur. |
| Confidentialité illusoire des brouillons | Critique | Protéger aussi les fichiers et aperçus ; tester l’accès direct sans session. |
| Modification d’une autre page ou d’un autre média | Critique | Contrôles objet par objet et tests avec deux artistes et un compte sans membre. |
| Révision publique modifiée indirectement | Forte | Contenus/références immuables après publication ; remplacement de média par nouvelle identité. |
| Présence annoncée à tort | Forte | Participation explicite à l’événement ; rôle affiché ; distribution permanente confirmée. |
| Couleurs ou cadrages illisibles | Forte | Validation de tous les états et vérification sur mobile/zoom. |
| Publication contournée par un ancien formulaire | Forte | Identifier et adapter tous les points d’écriture des champs publics. |
| Médias trop lourds ou malveillants | Forte | Quotas, validation réelle, dérivés, noms générés et ressources bornées. |
| Régression du backoffice par CSS global | Forte | Périmètre public explicite et contrôle des écrans partagés. |
| Vidéo bloquée ou chargement tiers prématuré | Moyenne | Lecteur au clic, couverture locale et test sur préproduction. |
| Conflit entre réglages de confort et thème | Forte | Propriété claire des classes/variables et tests de réinitialisation. |
| Perte des fichiers lors d’une restauration | Forte | Sauvegarde et essai de restauration des données et médias ensemble. |
| Maintenance des variantes qui explose | Moyenne | Deux compositions en première version et catalogue de cas testables. |

## 14. Plan de transformation par lots

Chaque lot livre un résultat vérifiable. Les travaux de stockage privé et de publication doivent précéder l’ouverture des brouillons aux utilisateurs.

| Lot | Travail | Résultat attendu / condition de passage |
|---|---|---|
| 0 — Référence | Inventorier champs publics, écritures existantes, règles d’accès et contenus de trois artistes volontaires. | Liste des données faisant autorité, périmètre et jeu de contenus réalistes établis. |
| 1 — Identité commune | Dessiner accueil, artiste et spectacle ; définir les composants et deux introductions. | Ensemble reconnu comme un seul site, dans les états mobile et lecture agrandie. |
| 2 — Fondation technique | Modèles éditoriaux, droits, médias privés/publics, migrations et reprise des profils. | Une page reprise reste publique ; son nouveau brouillon et ses médias restent privés. |
| 3 — Lecture publique | Brancher créations, collaborations, participations et composants communs. | Aucune donnée privée exposée ; informations cohérentes avec les fiches métier. |
| 4 — Édition | Formulaires, couleurs, images, vidéo, aperçu, conflit de version et publication. | Un artiste prépare et publie une évolution complète dans son périmètre. |
| 5 — Confort et qualité | Finaliser préférences, navigation clavier, alternatives médias et optimisation. | Recette fonctionnelle et accessible du périmètre ; défauts bloquants corrigés. |
| 6 — Déploiement progressif | Activer pour quelques pages, recueillir les retours et généraliser. | Aucun recul sur les accès, la lisibilité, les adresses ou les réservations. |

### Migration et retour arrière

Créer les structures sans supprimer immédiatement les champs historiques. Reprendre les pages visibles dans une révision publique initiale, en conservant leurs adresses et visuels. Les pages cachées restent cachées. Pour les données manquantes, appliquer des valeurs de présentation neutres.

Avant activation, vérifier les comptes sans membre, membres sans compte, profils sans image, collaborations multiples et médias déjà partagés. Faire une simulation de migration sur une copie des données avec contrôles de comptage et d’échantillons.

Prévoir un indicateur d’activation permettant le retour au rendu précédent **sur les données publiques faisant autorité**. Le retour arrière ne doit pas faire réapparaître des champs historiques obsolètes. Conserver les nouvelles révisions pendant ce retour et prévoir une procédure distincte si une restauration de données est nécessaire.

### Charge de travail

Le choix de couleur et l’ajout d’un champ YouTube sont relativement limités. La confidentialité réelle des médias, la publication versionnée, le cadrage, les droits et la recette de toutes les variantes concentrent la charge.

L’estimation orale initiale de 8 à 15 jours concernait une première version plus simple. Elle ne doit pas être utilisée comme engagement pour tout ce guide. Chiffrer chaque lot après le lot 0, en distinguant design, développement, reprise des données, contenus et tests utilisateurs. Réduire d’abord le nombre de variantes et d’options si le budget est limité ; préserver les contrôles d’accès et le socle d’accessibilité.

## 15. Recette : critères vérifiables avant généralisation

Préparer au minimum : deux artistes avec compte, un membre sans compte, un compte technique sans membre, un compte bureau, une page cachée, un spectacle publié, un spectacle en brouillon, un événement public, un événement réservé aux membres, une date passée, une galerie complète et une vidéo non intégrable.

| ID | Scénario | Résultat attendu |
|---|---|---|
| R01 | Passer de l’accueil à un artiste, puis à un spectacle. | Même navigation, mêmes boutons et mêmes lignes de dates ; identité artistique perceptible dans les contenus. |
| R02 | Afficher les deux compositions avec nom long, texte maximum et aucun portrait. | Aucune superposition ou section artificiellement vide. |
| R03 | Choisir une couleur très claire puis publier. | Correction ou rejet explicite ; aucun état illisible publié. |
| R04 | Activer le confort, changer de page, recharger et réinitialiser. | Préférences conservées puis réinitialisées ; autres classes et thème préservés. |
| R05 | Parcourir les pages au clavier et ouvrir galerie, panneau et aperçu. | Toutes les actions accessibles ; fermeture et retour de focus cohérents. |
| R06 | Tester largeur 320 px, texte 200 %, zoom 400 % et espacement utilisateur. | Informations et commandes présentes ; redistribution conforme aux cas applicables. |
| R07 | Utiliser un lecteur d’écran sur page publique et formulaire. | Titres, contrôles, erreurs, états et descriptions compréhensibles. |
| R08 | Visiter sans JavaScript ou avec vidéo bloquée. | Contenus, liens et parcours essentiels disponibles ; aucun écran vide. |
| R09 | Artiste A envoie l’identifiant de la page ou d’un média privé de B. | Accès refusé, aucune modification ni divulgation. |
| R10 | Compte sans membre appelle directement une route d’édition. | Refus contrôlé ; aucun élargissement involontaire du périmètre. |
| R11 | Lire une URL de brouillon ou de fichier privé sans session. | Contenu inaccessible ; absence dans recherche, métadonnées et cache public. |
| R12 | Modifier biographie, portrait et accent sans publier. | La page publique reste identique ; seul l’aperçu change. |
| R13 | Publier puis restaurer une révision. | Bascule complète ; auteur tracé ; aucune récupération de contenu métier devenu privé. |
| R14 | Deux onglets enregistrent des versions concurrentes. | Conflit détecté ; aucun écrasement silencieux. |
| R15 | Retirer une image utilisée ailleurs. | Seule l’association visée disparaît ; les autres usages restent intacts. |
| R16 | Importer fichier trop gros, dimensions excessives ou faux format image. | Rejet explicite, sans saturation ni perte des autres données du formulaire. |
| R17 | Artiste dans un spectacle mais absent d’une représentation. | Cette représentation n’est pas annoncée comme sa participation personnelle. |
| R18 | Événement lié à l’artiste mais réservé aux membres. | Absent de sa page publique, y compris des compteurs. |
| R19 | Dépublier un spectacle ou masquer une page artiste. | Disparition cohérente dans les pages, métadonnées et caches concernés. |
| R20 | Visiter une page avec vidéo sans l’activer, puis l’activer. | Aucun appel YouTube avant activation ; lecteur ou solution de repli après activation. |
| R21 | Ouvrir les anciens liens numériques et les URLs `/@slug`. | Redirection historique et adresse canonique conservées. |
| R22 | Comparer chargement et requêtes sur les mêmes contenus avant/après. | Budget documenté ; absence d’originaux inutilement lourds et de requêtes par élément. |
| R23 | Restaurer la base et les médias sur un environnement de test. | Pages et références de fichiers cohérentes, médias privés toujours protégés. |
| R24 | Ouvrir les écrans de profil, spectacle, événement et backoffice affectés. | Aucune régression fonctionnelle ou graphique des composants partagés. |

Automatiser surtout les permissions, filtres de visibilité, validations, transitions de publication et migrations. Compléter les contrôles automatiques d’accessibilité par une recette manuelle au clavier, avec NVDA/Firefox sous Windows et VoiceOver/Safari sur appareil Apple lorsque disponible. Faire intervenir des personnes malvoyantes et des utilisateurs de lecteurs d’écran sur les parcours réels.

### Définition de terminé

- Les règles de personnalisation et les composants communs sont documentés et utilisés sur le périmètre public retenu.
- Les données réelles ont été reprises sans perte d’adresse, de visibilité ou de relation métier.
- L’artiste distingue clairement brouillon, aperçu et version publique.
- Tous les scénarios d’accès et de confidentialité critiques passent.
- Les défauts d’accessibilité bloquant les parcours sont corrigés ; les limites restantes sont décrites sans déclaration de conformité prématurée.
- Les responsables savent publier, suspendre, restaurer et retirer un média sans dommage collatéral.
- Le retour arrière et la restauration sont documentés et éprouvés sur le périmètre concerné.

## 16. Fiche de démarrage pour l’équipe

**Décisions de départ recommandées :** une identité Improliante ; deux compositions d’entrée ; un accent personnel ; styles de boutons, cadres et filets communs ; huit images de galerie ; une vidéo YouTube ; reprise du panneau de confort existant ; brouillon privé et publication explicite ; premières dates issues des interventions confirmées.

**Livrables de réalisation :** catalogue de composants, écrans publics et d’édition, migrations, services de publication et de traitement des médias, tests ciblés, procédure de déploiement/retour arrière et courte aide à destination des artistes.

**À préciser pendant le lot 0 sans réinventer le périmètre :** responsable de la première validation, détenteurs de la capacité de publication, volume de médias disponible, politique de conservation des révisions, champs publics exacts et exhaustivité actuelle des participations aux événements.

**Règle d’arbitrage :** si une option augmente fortement le nombre de variantes, fragilise la lisibilité ou rend le contrôle des contenus incertain, la reporter. La singularité d’une page doit d’abord venir de ce que l’artiste donne à voir et à lire.

## 17. Références et points de code

Références consultées le 12 septembre 2026. Les sources externes précisent les critères et mécanismes cités ; les choix de produit, limites de contenu, modèles et lots restent des recommandations propres à ce guide.

### Code du dépôt — version figée

- **[C1]** [Identité, membres et liens publics](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/coeur/models.py) — `Membre`, `LienReseau`, visibilité et slug.
- **[C2]** [Vues publiques](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/vitrine/views.py) — `detail_membre`, ancienne adresse, filtres de publication.
- **[C3]** [Modèles agenda](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/agenda/models.py) et [modèles spectacles](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/spectacles/models.py) — événements, interventions et distribution.
- **[C4]** [Vues de l’espace membre](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/views.py) et [formulaires](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/espace_membre/forms.py) — `mon_profil`, `ProfilMembreForm`.
- **[C5]** [Modèle Media](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/medias/models.py) — image, vidéo, description et auteur d’import.
- **[C6]** [Gestion partagée des images](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/apps/common/fiches.py) — limite de poids, validation et opérations de fiche.
- **[C7]** [Préférences d’accessibilité](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/static/js/accessibilite.js) — cookie `a11y`, classes et réinitialisation.
- **[C8]** [Page membre](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/templates/vitrine/membre_detail.html) et [CSS actuel](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/static/css/site.css).
- **[C9]** [Configuration](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/config/settings.py) — emplacement et exposition prévue des médias.
- **[C10]** [Galerie publique](https://github.com/Hsbtqemy/Improliante/blob/8525e563fd61e8bb3b707e2a30ac3215a8993b99/front/templates/vitrine/galerie.html) — traitement actuel des vidéos par lien externe.

### Références officielles

- **[S1]** W3C, [WCAG 2.2](https://www.w3.org/TR/WCAG22/) — référentiel, navigation, focus et taille des cibles.
- **[S2]** W3C, [Understanding Contrast (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) — contrastes de texte.
- **[S3]** W3C, [Understanding Resize Text](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html) — agrandissement du texte.
- **[S4]** W3C, [Understanding Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) — redistribution et zoom.
- **[S5]** W3C, [Understanding Text Spacing](https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html) — espacements personnalisés.
- **[S6]** W3C, [Making Audio and Video Media Accessible](https://www.w3.org/WAI/media/av/) — sous-titres, descriptions et transcriptions.
- **[S7]** OWASP, [Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — autorisations au niveau des opérations et objets.
- **[S8]** OWASP, [File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) — validation et traitement des fichiers importés.
- **[S9]** Django 6.0, [Security in Django](https://docs.djangoproject.com/en/6.0/topics/security/) — contenus utilisateurs et fichiers téléversés.
- **[S10]** YouTube, [Intégrer des vidéos et des playlists](https://support.google.com/youtube/answer/171780?hl=fr) — lecteur intégré, confidentialité avancée, sous-titres et référent HTTP.
