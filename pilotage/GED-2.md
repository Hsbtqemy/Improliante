---
chantier: GED-2
statut: à venir
---

# GED-2 — les images des fiches non publiées sont servies publiquement

**Trouvé le 13 septembre 2026**, en relisant le lot qui venait de protéger la photo d'un
brouillon de page artiste (VIT-4). Le même défaut vit une app plus loin, et il n'y a
aucune raison qu'il s'arrête à la page artiste.

> À ne pas confondre avec **GED-03**, un constat de l'audit externe du 11 septembre
> (quotas et traitement des fichiers, v2 assumée). Celui-ci est un chantier, trouvé dans
> le dépôt, et il porte sur la confidentialité — pas sur les quotas.

**Le fait, mesuré.** Un membre propose un projet ; sa fiche reste en `brouillon` tant que
le bureau ne l'a pas publiée. Son affiche, elle, est écrite dans `MEDIA_ROOT` dès le
téléversement :

```
statut de moderation : brouillon
fichier              : medias/2026/09/affiche-secrete.jpg
URL publique         : /media/medias/2026/09/affiche-secrete.jpg
servie par Nginx     : oui
```

Le nom vient du fichier téléversé, donc il n'est pas même difficile à deviner. Vaut pour
`Spectacle.affiche`, `ImageSpectacle`, `Evenement.affiche` et `ImageEvenement` — l'affiche
comme la galerie, les projets comme les événements.

## Reste

### Arbitrages
- [ ] Décider **qui** a le droit de voir l'image d'une fiche non publiée : ses porteurs
  seuls, tout compte connecté, ou les porteurs plus le bureau — un spectacle a plusieurs
  porteurs, un événement a un seul `cree_par`, et les deux règles ne s'écrivent pas
  pareil
- [ ] Décider du sort des fichiers **déjà exposés** : les laisser où ils sont (ils le sont
  déjà, les déplacer ne les dé-publie pas rétroactivement) ou les reprendre par une
  migration de données — le guide de refonte dit la première moitié, pas la seconde
- [ ] Arrêter le périmètre : l'affiche seule, ou l'affiche et la galerie — la galerie
  multiplie les objets à déplacer au moment de la publication, et c'est là que le geste
  cesse d'être atomique

### Ce que le motif de VIT-4 donne déjà
- [ ] `Media.fichier_prive` + `StockagePrive` existent et servent la photo d'un brouillon
  de page artiste : le stockage n'est pas à construire, seulement à brancher
- [ ] Le déplacement à la publication est écrit (`coeur/services.py::publier_photo_de_brouillon`)
  et sait qu'il ne doit pas échouer sur un nettoyage — reste à l'appeler depuis les
  transitions de `apps/common/moderation.py`, qui sont le vrai moment de publication
- [ ] Aucune vignette ne doit être produite tant que l'image est privée : elle partirait
  dans le stockage public, et une miniature d'une image protégée est une fuite de cette
  image

### Vérifications
- [ ] L'affiche d'un spectacle en brouillon n'est pas lisible sans session, et pas
  lisible par un membre qui n'en est pas porteur
- [ ] Publier la fiche fait passer l'affiche ET les images de galerie dans la racine web,
  et la page publique les sert depuis là
- [ ] Dépublier une fiche déjà publiée ne reclasse PAS ses images en privé : elles ont
  été publiques, les rendre privées ne les reprend pas — le dire plutôt que le promettre
- [ ] Les écrans qui ont le droit de montrer une image non publiée — édition du membre,
  file de modération du bureau — testent `media.a_une_image` et non `media.fichier`, sans
  quoi la fiche s'affiche sans son affiche
- [ ] Un média partagé par deux fiches, l'une publiée et l'autre non, reste lisible : le
  déplacement suit la première publication, pas la dernière

## Contexte

**Pas ouvert, et pas codé sans décision.** Les trois arbitrages ci-dessus changent le
coût du chantier, et le premier est une vraie question de produit : « tout compte
connecté » est la réponse la plus simple, « les porteurs seuls » la plus juste, et les
deux se défendent pour une association de cette taille.

**Ce qui rend ce défaut différent de celui de VIT-4.** La page artiste avait un moment de
publication explicite — un bouton, un service, une copie. Une fiche de spectacle, elle,
est publiée par une **transition de modération** (`brouillon → proposé → publié`), qui
vit dans `apps/common/moderation.py` et sert trois domaines. Y accrocher un déplacement
de fichiers, c'est toucher le chemin le plus partagé du dépôt — et la règle 7 de
CLAUDE.md dit qu'une fiche publiée reste éditable par son auteur, donc une image peut
arriver APRÈS la publication. Le déplacement ne peut pas être un geste unique à la
transition ; il doit aussi valoir au téléversement sur une fiche déjà publiée.

**Ce qui est vrai quoi qu'il arrive.** Une URL difficile à deviner n'est pas un contrôle
d'accès, et celle-ci n'est même pas difficile à deviner : elle reprend le nom du fichier
téléversé. C'est le risque que le guide de refonte classe en critique, et il ne concerne
pas que les pages artistes.
