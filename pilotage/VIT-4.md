---
chantier: VIT-4
statut: interrompu
---

# VIT-4 — pages artistes expressives : identité commune et page éditée par l'artiste

**Ouvert le 13 septembre 2026** sur cinq arbitrages tranchés. Un guide externe daté du
12 septembre cadre le sujet (`docs/guide-refonte-pages-artistes.md`) : une identité
Improliante commune, des pages artistes personnalisables dans des bornes, un brouillon
séparé de la version publique. Le dépôt lui donne raison sur les faits — ses dix
références au code ont été vérifiées une à une — mais il ignore quatre briques déjà en
place, et deux de ses préconditions ont été construites ailleurs depuis. Le périmètre
retenu est plus étroit que le guide, et c'est écrit ci-dessous.

## Reste

### Arbitrages
- [x] **Circuit de publication : brouillon séparé, sans historique.** L'artiste
  enregistre un brouillon, vérifie un aperçu, publie explicitement ; le public garde la
  version publiée jusque-là. Ni révision immuable ni restauration d'une version
  antérieure — voir « Pourquoi pas le cycle de modération » plus bas
- [x] **Les dérivés d'images sont faits** — ce n'est plus un arbitrage : le lot 17 de
  SEC-1 a construit le pipeline que le guide mettait en précondition de sa fondation
  technique (2 000 px, vignette de 600, `srcset`, dimensions stockées, `manage.py
  preparer_medias`). GED-03 ne garde que les quotas
- [x] **Une dizaine de fiches, éditées une ou deux fois l'an.** Le conflit d'onglets, le
  verrou de version et la restauration de révision du guide ne se déclencheraient jamais
  à cette échelle : ils ne sont pas construits
- [x] **Le bureau publie**, SEC-04 ayant été écarté le 12 septembre. Pas de capacité de
  publication déléguée à construire ; la première activation et les suivantes passent par
  le même geste
- [x] **Les deux compositions d'entrée du guide** sont retenues : portrait éditorial et
  visuel de création. Chacune se recette entièrement — mobile, clavier, 400 %, sans
  image, nom long — et la recette en tient compte

### Préalables
- [ ] VIT-3 est clos : fond et police arrêtés, panneau DEV retiré — on ne peut pas juger
  « accueil, artiste et spectacle forment un seul site » tant que l'identité n'est pas
  arrêtée. **Seule la moitié identité attend** : la moitié données avance sans
- [x] Le périmètre est réduit à ce qui est décidé ci-dessus et réécrit dans cette fiche

### Lecture publique
- [x] Un artiste porté à la distribution d'un spectacle mais absent d'une représentation
  ne voit pas cette date annoncée comme sa participation — seule une `Intervention`
  explicite sur un événement publié et public la produit
- [x] Un événement lié à l'artiste mais en visibilité « membres » n'apparaît pas sur sa
  page publique, ni dans le compte des prochaines dates — le décompte lit la liste
  affichée, pas une seconde requête qui pourrait filtrer autrement
- [x] Un événement public rattaché à un spectacle non publié n'en révèle rien : ni titre
  sur l'agenda, ni titre et lien sur la fiche de la date, ni `workPerformed` dans le
  JSON-LD, ni affiche reprise en image de partage
- [x] La fiche d'un spectacle n'annonce comme « prochaine » qu'une date encore à
  venir — elle listait toutes ses représentations publiques sous ce titre, passées
  comprises
- [x] Le nombre de requêtes de la fiche d'un artiste ne suit pas son nombre de dates :
  même compte à 3 participations et à 12
- [ ] Les deux compositions d'entrée rendent une page soignée sans portrait et sans
  spectacle mis en avant : pas de rectangle vide, pas de photographie générique imposée
- [ ] La couleur d'accent d'un artiste est validée côté serveur (`#RRGGBB` opaque) et le
  serveur en dérive les couples lisibles — une teinte inutilisable est corrigée ou
  refusée avant publication, pas rendue telle quelle
- [ ] Aucune requête ne part vers YouTube avant que le visiteur ait cliqué — le même
  geste que le flux Bluesky de la fiche membre, qui ne charge rien avant le clic

### Brouillon et publication
- [ ] La page publique lit le contenu **publié** ; le brouillon n'est lu que par son
  propriétaire et par le bureau, dans l'aperçu
- [ ] Les points d'écriture des champs publics de `Membre` passent tous par le même
  chemin de publication : `espace_membre/forms.py`, `backoffice/forms.py` et sa vue, les
  deux constructeurs de `coeur/services.py`, le geste photo, et `MembreAdmin` qui n'a
  aujourd'hui aucun `fields` restreint
- [ ] Le JSON-LD de `vitrine/seo.py` lit la même source que la page artiste : il ne
  publie pas une biographie que la page n'affiche pas
- [ ] Une image de brouillon n'est pas lisible sans session : elle vit sous
  `MEDIA_PRIVE_ROOT` et se sert par une vue qui contrôle les droits, comme les reçus et
  les documents
- [ ] L'aperçu est authentifié, réservé au propriétaire et au bureau, et servi avec des
  en-têtes qui interdisent l'indexation et la mise en cache partagée — un `noindex` seul
  ne protège pas un accès
- [ ] Un échec de publication laisse la version publique précédente intacte, et une
  publication change tous les contenus éditoriaux d'un coup ou aucun

### Confort de lecture
- [x] Un réglage du panneau de confort ne fait plus disparaître les autres classes de
  `<html>` : `accessibilite.js` ne bascule que les sept classes qui lui appartiennent, et
  le cookie `a11y` est relu contre la même liste fermée côté serveur

## Contexte

**Mis de côté le 12 septembre 2026**, le jour où le guide est entré au dépôt, puis
**ouvert le 13** après cinq arbitrages. Deux d'entre eux n'en étaient déjà plus : le
pipeline d'images a été construit entre-temps par SEC-1, et SEC-04 a été écarté, ce qui
répond à « qui publie ». Les trois autres ont été tranchés par l'association, et le
périmètre ci-dessus est plus étroit que le guide — qui prévient lui-même qu'il couvre
plus large que ce qui sera fait.

**Le chantier est entré par la moitié données**, celle qui ne dépend ni du fond ni de la
police, donc pas de VIT-3. Deux lots le 13 septembre :

- **Les prochaines participations** d'un artiste, à la règle stricte du guide (§5.4) :
  seule une `Intervention` explicite annonce une date. La carte de date de l'agenda est
  devenue `_carte_agenda.html`, servie telle quelle par la fiche artiste — c'est le
  premier risque du guide (« pages perçues comme des sites différents ») traité par la
  construction plutôt que par la recette.
- **Le confort de lecture**, dont le défaut latent est corrigé avant qu'un thème posé en
  classe ne le réveille.

**Ce que la relecture a trouvé.** Le même défaut que le lot venait de fermer sur la
fiche d'un artiste vivait sur la fiche d'un **spectacle** : « Prochaines dates » listait
toutes les représentations publiques, passées comprises — une tournée finie en février
s'annonçait encore en septembre. Fermer une règle sur une page ne la ferme pas sur sa
voisine : c'est la deuxième fois en une journée sur ce chantier, après la fuite du
spectacle en brouillon, et la même leçon que l'inventaire ARCH-01 de SEC-1 avait tirée
sur les gestes d'écriture. Deux autres points :
le préchargement du service était porteur sans être épinglé (sans lui, sept requêtes
fixes deviennent douze pour douze dates), et le balayage ne voyait de la carte de
participation que son **état vide**, le membre témoin n'intervenant nulle part.

**Une fuite trouvée en chemin, et fermée.** Un événement public rattaché à un spectacle
en brouillon publiait le titre de ce spectacle sur l'agenda, sur la fiche de la date et
dans le JSON-LD, et son affiche partait en image de partage — quatre chemins, dont deux
que personne ne relit à l'œil. Le lien menait en plus à une page introuvable, le
spectacle n'étant pas publié. `Evenement.spectacle_public` tient la règle à un seul
endroit : deux publications, deux interrupteurs.

### Pourquoi pas le cycle de modération

`apps/common/moderation.py` fait déjà `brouillon → proposé → publié/refusé` pour l'agenda,
les spectacles et la gouvernance. L'étendre à `Membre` était l'option la moins chère, et
cette fiche l'a longtemps présentée comme ne manquant que la restauration d'une version
antérieure. C'est inexact : sur une fiche **publiée**, `ETATS_MODIFIABLES_PAR_AUTEUR`
laisse l'auteur retoucher, et la retouche part en ligne **immédiatement**, avec
`modifie_apres_publication` levé pour un contrôle a posteriori. C'est voulu — un spectacle
évolue — mais ce n'est pas un brouillon. Le cycle ne pouvait donc pas tenir la promesse du
guide, quel que soit le besoin de restauration.

### Ce que le guide ignore, à son avantage

Quatre briques existent déjà et allègent son plan :

- **Le stockage privé tourne.** `StockagePrive`, `MEDIA_PRIVE_ROOT` et
  `reponse_fichier_prive` (X-Accel-Redirect en production) servent déjà les reçus, les
  factures, les documents et les signatures. Le guide classe « confidentialité illusoire
  des brouillons » en risque **critique** et met la construction d'un stockage privé en
  précondition de sa fondation technique : c'est un branchement, pas une construction.
- **Le chargement au clic a un précédent qui marche.** Le flux Bluesky de
  `membre_detail.html` et `bluesky.js` ne fait aucune requête tierce avant le clic, sur
  cette page précise. Le lecteur YouTube du guide est le même geste.
- **Les variables sémantiques existent.** Quarante-neuf tokens dans `site.css`
  (`--couleur-texte`, `--surface`, `--bordure`, `--rayon`, `--espace`, `--largeur-texte`…).
  Le guide propose de les créer sous d'autres noms (`--public-surface`…) : les renommer
  coûterait cher pour rien, mieux vaut étendre la convention en place.
- **Les polices sont auto-hébergées.** Quatre `.woff2` dans `front/static/fonts/`,
  décision non négociable de VIT-3. Le guide le demande comme un souhait.

### Ce qui reste vrai quoi qu'il arrive

Les champs publics de `Membre` s'écrivent depuis cinq endroits, dont l'admin sans `fields`
restreints, et se lisent depuis un sixième que le guide oublie : `vitrine/seo.py` fabrique
le JSON-LD depuis `bio` et `role_public`. Toute séparation brouillon/public qui en manque
un se contourne par ce chemin-là. C'est la case la plus fastidieuse de la zone
« Brouillon et publication », et celle qui décide si la promesse tient.

`Intervention` portait déjà un `role` et une contrainte d'unicité `(evenement, membre)`,
et `Evenement` sa visibilité à trois niveaux plus la modération : la règle stricte du
guide était écrivable sur le modèle actuel, sans rien ajouter. Elle l'a été.

### Collisions connues

- **VIT-3** reste le préalable de la moitié identité, et le chantier hérite de son CSS :
  `site.css` fait 103 ko en un seul fichier, et `base.html` est étendu par trente-sept
  gabarits backoffice contre quatorze vitrine. Toute variable touchée se propage aux trois
  faces.
- **GED-03** (quotas et cycle de vie des fichiers, v2 assumée) : le traitement des images,
  lui, est fait.
- **ARCH-02** (modifications concurrentes qui se perdent, v2 assumée) portait le verrou de
  version, écarté avec elle par le dimensionnement.
