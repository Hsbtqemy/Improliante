# Inventaire — les règles métier qui ne vivent pas dans un service

**Constat ARCH-01 de l'audit du 11 septembre 2026** · inventaire du 12 septembre 2026.

Document de décision : il ne corrige rien. Pour chaque point, ce qu'un accès
**admin Django** ou **shell** peut faire malgré la règle, et ce que je
recommande. C'est à l'association de trancher — tout n'a pas besoin de bouger.

## Méthode et limites

J'ai relu les trois faces (`apps/vitrine/views.py`, `apps/espace_membre/views.py`,
`apps/backoffice/views.py` — environ 3 900 lignes), en partant des écritures de
modèle faites hors service (`objects.create`, `save`, `delete`, `update`), puis
les classes d'admin qui exposent les mêmes modèles.

**Ce que l'inventaire ne couvre pas** : le JavaScript (une règle qui n'existe
qu'au navigateur est déjà couverte par FRONT-01 et FRONT-02), et les règles
portées par un **formulaire** plutôt qu'une vue — elles sont mentionnées quand
elles pèsent, mais un formulaire est au moins partagé entre les écrans, ce qu'une
vue n'est pas.

**Deux points ont été éprouvés, pas déduits** : le n° 2 et le n° 3 ci-dessous ont
été reproduits par une sonde jetable. Les autres sont établis par lecture.

---

## 1. Le PV régénéré détruit le précédent — *hors ARCH-01, trouvé en chemin*

**Où** : `apps/gouvernance/services.py::generer_compte_rendu`.

Ce point n'est pas une règle mal placée : elle est dans un service. Je le mets en
tête parce que c'est ce que l'inventaire a trouvé de plus lourd.

```python
if reunion.compte_rendu_id:
    doc = reunion.compte_rendu
    doc.fichier.delete(save=False)
    doc.fichier.save(nom, ContentFile(octets), save=True)
```

Régénérer un compte rendu **supprime le fichier précédent du disque**. Aucune
version n'est conservée : `Document.version` reste à 1, `remplace` reste vide, et
la mécanique de versionnement corrigée au lot 1 (GED-01, `remplacer_document`,
`courant`) n'est pas appelée sur ce chemin.

**Ce qui peut arriver** : le bureau génère le PV d'une AG. Il part en
confidentialité « Membres », donc à toute l'association (décision de
septembre 2026). Quelqu'un corrige une coquille, régénère — et le PV que les
membres ont téléchargé n'existe plus nulle part, sans trace du changement.
Combiné au point 2, un décompte de voix peut avoir changé entre les deux
fichiers.

**Recommandation : à corriger.** C'est le même invariant que FIN-02 sur les
factures, que l'audit classait P0 : une pièce distribuée ne se réécrit pas en
place. Le remède existe déjà à côté — passer par `remplacer_document`, qui garde
l'ancienne version et marque la nouvelle `courante`.

> **Corrigé le 12 septembre 2026** (lot 13). Régénérer crée une nouvelle version
> et la réunion pointe dessus ; l'ancienne est conservée, avec son fichier. Les
> écrans ne listent que la version courante — c'était déjà le cas partout —,
> donc rien ne se dédouble à l'affichage : c'est ce que l'ancien test protégeait
> de juste, et cette moitié-là est gardée.
>
> **Trouvé en corrigeant, et c'est le plus gênant des deux.** `reunion.compte_rendu`
> pointe une version PRÉCISE, et le bureau peut déposer un PV corrigé depuis les
> pièces de l'association — cet écran couvre les documents non classés, donc les
> PV. La fiche de la réunion et la convocation du membre servaient alors le
> fichier d'AVANT la correction pendant que la GED montrait le bon, et une
> régénération repartait de la version périmée : deux documents qui divergent.
> Les deux écrans suivent désormais la version courante, et la régénération
> repart de la correction. Reproduit par sonde, puis retenu par un test par
> écran — les deux échouent contre l'ancien code, vérifié en le remettant.

## 2. Une réunion archivée accepte encore du contenu — **éprouvé**

**Où** : `apps/backoffice/views.py::gouvernance_ajouter_resolution`,
`gouvernance_ajouter_sujet`, `gouvernance_notes`, `gouvernance_ajouter_bloc` ;
et `apps/gouvernance/admin.py::ResolutionInline`.

Le lot 4 a figé les **règles** d'une réunion close (`figer_les_regles` : quorum,
majorités, plafond de pouvoirs). Il n'a pas figé son **contenu**. Aucune de ces
quatre vues ne regarde `reunion.statut`, et les formulaires non plus.

**Ce qui peut arriver** — reproduit : sur une réunion `ARCHIVEE`, un POST depuis
le back-office ajoute une résolution avec 99 voix pour, et un sujet à l'ordre du
jour. Les deux atterrissent en base, et **les formulaires sont toujours affichés
à l'écran** : ce n'est pas un contournement d'URL, c'est le parcours normal.
Le décompte des voix est par ailleurs modifiable via l'admin sur n'importe quelle
réunion (`ResolutionAdmin` ne rend en lecture seule que les dates).

**Recommandation : à corriger.** C'est le constat GOU-01 que le lot 4 croyait
clos — « une réunion close garde son résultat » n'est vrai que de ses règles. Le
geste juste est celui déjà employé pour les factures : une transition relue sous
verrou dans un service, qui refuse d'écrire sur une réunion archivée, et un écran
qui n'offre plus le formulaire.

> **Corrigé le 12 septembre 2026** (lot 12, avec le n° 5). Le sceau vit dans le
> service et se relit sous verrou : `contenu_scelle` dit la règle, un
> gestionnaire de contexte privé la fait respecter, et cinq services nommés la
> portent — point d'ordre du jour, résolution, présence, bloc de récit, compte
> rendu. Le pouvoir du bureau passait déjà par `donner_pouvoir`, qui relit sous
> verrou : le sceau s'y est posé sans rien ajouter.
>
> L'écran lit la MÊME ligne et n'offre plus les formulaires. Les deux moitiés
> comptent : refuser à l'envoi sans retirer le formulaire fait remplir un écran
> pour rien, et retirer le formulaire sans refuser laisse l'adresse ouverte —
> c'est la leçon du lot 6, éprouvée ici par cinq envois directs aux URL. Le
> déroulé, lui, reste lisible : masquer le formulaire ne doit pas escamoter le
> compte rendu de la séance, qui est justement ce qu'on garde.
>
> Côté admin : les trois inlines de la réunion passent en lecture seule, le
> décompte des voix et les notes d'un point sont figés, et un formulaire refuse
> de rattacher une résolution ou un point à une séance close — c'est le
> `ResolutionInline` que ce point nomme, et le rattachement par liste déroulante
> est le geste le plus facile à faire sans y penser.
>
> **Deux gestes restent permis, et c'est voulu.** Le PV se régénère : il ne fait
> que RENDRE un contenu scellé, et le refuser enfermerait une séance archivée
> sans son PV dans une impasse. Et la réunion se rouvre par son statut — une
> clôture par erreur doit se défaire — mais son en-tête est figé, la réouverture
> s'annonce dans un bandeau, et les règles figées à la clôture ne se refigent
> pas.

## 3. Un devis facturé peut redevenir « accepté », puis être refacturé — **éprouvé par lecture croisée**

**Où** : la règle vit dans `apps/backoffice/views.py::changer_statut_devis` :

```python
if nouveau is None or devis.statut == Devis.Statut.FACTURE:
    messages.error(request, "Changement de statut impossible.")
```

Or `transformer_en_facture` se garde sur **le statut**, pas sur l'existence d'une
facture liée :

```python
if courant.statut == Devis.Statut.FACTURE:
    raise DevisDejaFacture(...)
```

**Ce qui peut arriver** : `DevisAdmin` ne rend en lecture seule que les dates. Un
compte bureau remet le statut à « Accepté » depuis l'admin, puis reclique
« Transformer en facture » : **une seconde facture naît du même devis**, et deux
factures pointent `devis_origine` vers lui. Le verrou posé au lot 1 (FIN-03)
sérialise l'opération, il ne la rend pas idempotente.

**Recommandation : à corriger, et c'est le moins coûteux des trois.** Le garde-fou
doit porter sur le fait, pas sur l'étiquette : `Facture.objects.filter(
devis_origine=courant).exists()`. Un fait ne se remet pas à zéro depuis un
formulaire d'admin.

> **Corrigé le 12 septembre 2026** (`c1aac59`, complété par la relecture). Le
> garde-fou porte sur l'existence de la facture, et c'est une seule ligne —
> `devis_deja_facture`, dans le service — que lisent les quatre chemins
> concernés : la transformation, l'écran d'édition du bureau, son changement de
> statut, et `DevisAdmin`, qui fige en plus le statut d'un devis déjà facturé.
>
> La relecture a trouvé que corriger le service ne suffisait pas. Les deux
> écrans gardaient leur lecture de l'étiquette : un devis marqué « Facturé »
> dont la facture avait été supprimée depuis restait présenté en lecture seule,
> en annonçant une facture qu'il ne pouvait même plus lier, changement de statut
> refusé — plus aucun geste offert, alors que le service acceptait de nouveau.
> Reproduit par sonde, puis retenu par deux tests d'écran.
>
> **Résidu assumé** : sur une facture en brouillon, `devis_origine` reste
> modifiable dans l'admin. L'effacer à la main détache la facture de son devis,
> qui redevient transformable. Ce n'est pas le geste que cet inventaire traque —
> trois clics dans une liste de statuts, qu'on fait sans y penser — et le bureau
> a le droit de rattacher une pièce à son devis. Non verrouillé, donc, et dit
> ici plutôt que passé sous silence.

## 4. Le plafond statutaire de pouvoirs est contourné par l'admin

**Où** : `apps/gouvernance/admin.py::PouvoirInline` — quatre lignes, aucune
validation.

`donner_pouvoir` vérifie trois choses : mandataire différent du mandant, plafond
`max_pouvoirs_par_personne` (règle 8 de CLAUDE.md : statutaire, paramétrable,
jamais codée en dur), et réunion encore ouverte aux réponses. L'inline d'admin
écrit des `Pouvoir` en base sans aucune de ces vérifications.

**Correction du dossier** : le message de commit du lot 4 annonçait « un seul
service pour les pouvoirs — plafond statutaire compris, **quel que soit le
chemin** ». C'était exact pour les trois chemins du back-office sur mesure, et
faux pour l'admin Django. Je l'avais écrit sans vérifier l'inline.

**Recommandation : à corriger, petit.** Soit l'inline passe en lecture seule
(le bureau saisit un pouvoir papier depuis l'écran de la réunion, qui appelle le
service avec `par_le_bureau=True`), soit il valide par le service. La première
option est plus sûre et tient en trois lignes.

## 5. Le compte rendu s'écrit sans formulaire ni service

**Où** : `apps/backoffice/views.py::gouvernance_notes` et
`gouvernance_ajouter_bloc`.

Ces deux vues lisent `request.POST.get(...)` directement, sans formulaire : pas de
validation, pas de longueur maximale, pas de contrôle de statut (cf. point 2), et
la synthèse comme les blocs de récit s'écrivent en base tels quels.

**Ce qui peut arriver** : rien de dangereux en soi — le texte est échappé au
rendu. Mais c'est le seul endroit du dépôt où une saisie utilisateur contourne
la couche formulaire, et c'est ce qui a permis au point 2 de passer inaperçu :
sans formulaire, il n'y a pas d'endroit naturel pour poser la règle.

**Recommandation : à faire quand on corrigera le point 2**, pas avant. Seul, le
gain est de la propreté ; avec le point 2, c'est l'endroit où la règle se pose.

> **Corrigé le 12 septembre 2026** (lot 12, avec le n° 2 — dans cet ordre, comme
> prévu). `CompteRenduForm` porte un champ par point de l'ordre du jour et trois
> par bloc de récit, construits depuis LA réunion : une clé qui désigne le point
> d'une autre séance n'écrit plus rien. Un champ absent de l'envoi est laissé
> tel quel plutôt que vidé — la page peut avoir été rendue avant qu'un point
> n'existe, et ce qu'elle n'a pas montré ne s'écrase pas.
>
> `BlocCompteRenduForm` refuse un bloc sans texte, que l'écran écrivait sans
> broncher, et un intertitre trop long est refusé au lieu de partir en base —
> PostgreSQL l'y rejetterait, donc en erreur 500. Effet de bord utile : ces
> champs passent par la couche de rendu commune, donc leurs messages d'erreur
> portent l'identifiant que Django cite dans leur `aria-describedby`. Et la
> fiche d'une réunion entre dans le balayage d'accessibilité, où elle n'était
> pas — c'est l'écran le plus dense du bureau, et l'aide de son champ « droit de
> vote » ne s'annonçait pas.

## 6. Suppression d'une adhésion qui porte un reçu fiscal émis

**Où** : nulle part — aucune règle, ni en vue ni en service.
`apps/backoffice/views.py::supprimer_adhesion` appelle `delete()` directement.

Les `RecuFiscal` et `Transaction` liés sont en `on_delete=SET_NULL` : rien n'est
détruit, le reçu survit et son PDF reste reproductible depuis l'instantané posé
au lot 2. Mais le lien comptable — quelle adhésion ce reçu couvre — est perdu
silencieusement.

**Recommandation : à trancher, sans urgence.** Deux options : refuser la
suppression d'une adhésion dont un reçu a été émis (cohérent avec le traitement
des factures), ou l'assumer et le dire à l'écran. L'état actuel ne dit rien.

## 7. Un membre ne peut pas estampiller son projet « production de l'association »

**Où** : `apps/espace_membre/forms.py::ProjetMembreForm.__init__`, qui restreint
`type_portage` à « personnel » / « collectif ».

Contournable depuis l'admin — mais l'admin, c'est le bureau, qui a le droit de
poser ce portage. Il n'y a pas d'élévation de privilège.

**Recommandation : ne rien faire.** La règle est au bon endroit (un formulaire
est partagé par tous les écrans qui l'emploient) et son contournement est
légitime.

---

## Ce qui est déjà à sa place

À noter, parce que l'inventaire n'a pas vocation à ne montrer que le creux :

- **La jauge d'un événement** : `agenda_services.inscrire` relit l'événement sous
  verrou et refuse le dépassement. La vue ne fait qu'afficher le refus. C'est le
  motif à reproduire ailleurs.
- **Le consentement du formulaire de contact** : la vue écrit `consentement=True`,
  ce qui a l'air d'un aveu — mais `ContactForm` porte une case **obligatoire**.
  La valeur écrite est donc vraie. Vérifié, pas supposé.
- **Factures et reçus** : après les lots 1 à 3, les transitions relisent sous
  verrou, l'admin obéit aux mêmes règles, et l'instantané d'émission rend la
  pièce reproductible. C'est l'état de référence du dépôt.
- **La fin d'adhésion** : `peut_ecrire_espace_membre` vit dans
  `apps/coeur/roles.py`, pas dans les vues (lot 6).

## Ce que je ferais, dans cet ordre

1. ✅ **Le point 3** — le moins coûteux, et il évite une double facturation d'un
   même devis. Une ligne de garde, un test. *Fait le 12 septembre (lot 11).*
2. ✅ **Le point 2 avec le point 5** — c'est le plus lourd, et c'est GOU-01 qui
   n'était pas clos. Il demande un service de transition et trois écrans à
   ajuster. *Fait le 12 septembre (lot 12) : le sceau, cinq services, deux
   formulaires, l'admin et le balayage.*
3. ✅ **Le point 1** — même famille que FIN-02, remède déjà présent dans le
   dépôt. *Fait le 12 septembre (lot 13), avec une divergence trouvée en chemin
   entre le PV que sert la réunion et celui que montre la GED.*
4. **Le point 4** — trois lignes. C'est ce qui reste de GOU-01 : le plafond
   statutaire de pouvoirs se contourne encore sur une réunion OUVERTE, le sceau
   du lot 12 ne fermant que les séances closes.
5. **Le point 6** — quand la question sera posée par l'usage.

Les points 5 (seul) et 7 ne valent pas d'être remontés.
