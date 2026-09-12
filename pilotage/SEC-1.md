---
chantier: SEC-1
statut: interrompu
audit: docs/audit-externe-2026-09-11-constats.md
---

# SEC-1 — consolidation après l'audit externe

**Arrêté sur** — lot 7 : FRONT-07, le parcours « mot de passe oublié », commit `6b86e3c`,
12 septembre. Avant lui, le lot 6 et sa relecture ont fermé l'impasse de l'avoir dupliqué,
posé la lecture seule après la fin d'adhésion et corrigé le niveau « Public ». Seize
constats sur trente sont clos.

## Reste

### Pièces émises
- [x] Le reçu fiscal suit les mêmes règles que la facture : rien d'éditable ni de supprimable dans l'admin une fois émis, PDF rendu dès l'émission
- [x] FIN-02 : une facture dont le PDF archivé a disparu se régénère à l'identique — instantané d'émission, dont le rendu part désormais
- [x] FIN-04 : un avoir dupliqué ne peut plus annuler plus que sa facture — détaché de son origine, il ne s'émet plus du tout
- [x] L'avoir dupliqué a une issue : la duplication d'un avoir disparaît, du bouton comme du service — il visait UNE facture, la copie ne pouvait pas rejouer ce lien
- [x] Télécharger ou prévisualiser une facture, un devis ou un reçu sans moteur PDF affiche un message, pas une erreur 500 — côté membre aussi

### Saisie et parcours
- [x] « Valider » ne porte plus que sur une version enregistrée : un écran de confirmation récapitule la pièce telle qu'elle est en base, et seul le POST émet
- [x] Un double clic sur « Valider » ne s'annonce plus comme une erreur : la seconde requête constate en information que la pièce est déjà émise
- [ ] Dans un navigateur : modifier un champ du brouillon révèle « Modifications non enregistrées » et le lien « Valider et numéroter… » cesse de mener au récapitulatif tant qu'on n'a pas enregistré — aucun test ne couvre ce geste, il demande un vrai navigateur
- [x] Le lien de validation neutralisé porte un style : fond neutre, curseur d'interdiction, et pas d'`opacity` qui l'effacerait à demi — un test retient la règle, la passe QA vérifie qu'elle se voit

### Concurrence éprouvée
- [x] `TEST_POSTGRES=1 pytest` passe, test de double clic simultané compris — rejoué à chaque commit par la vérification distante, et non plus seulement par un hook local contournable
- [ ] Le PDF rendu à l'émission est éprouvé avec le vrai WeasyPrint : le fichier archivé s'ouvre et porte le bon numéro. La vérification distante prouve désormais que le moteur CHARGE et rend sur Debian ; qu'une facture soit juste reste à voir à l'œil

### Livraison
- [x] OPS-01, la vérification : un workflow distant rejoue la suite sur PostgreSQL, le lint, les migrations et `check --deploy --fail-level WARNING` à chaque commit, et refuse un run où un test s'ignore — un « skipped » y signifie que la bascule n'a pas pris
- [ ] OPS-01, le branchement : le webhook écoute le succès de cette vérification et non le push — un commit non validé ne part pas en déploiement. Demande la machine, donc DEP-1

### Fin d'adhésion et audiences
- [x] SEC-05 : un membre dont l'adhésion a pris fin consulte encore ses reçus, ses documents et son historique, et ne dépose ni ne modifie plus rien — les boutons qui mèneraient à un refus ont disparu avec
- [x] FRONT-06 : le niveau de confidentialité le plus ouvert s'appelle « Tout compte connecté » — il ne met rien en ligne, et il est plus large que « Membres »

### Constats du rapport encore ouverts, à programmer
- [ ] PUB-01 : une limitation de débit protège contact, réservations **et « mot de passe oublié »** — des envois répétés depuis la même origine sont ralentis ou refusés, et une jauge ne peut plus être saturée par des réservations successives
- [ ] Le formulaire de « mot de passe oublié » ne permet pas de noyer la boîte d'un membre : c'est le seul formulaire public qui envoie un courriel à un TIERS choisi par le demandeur, donc le plus abusable des trois, et le lot 7 l'a ajouté sans rien pour le retenir — la réputation d'envoi de l'association s'y joue aussi
- [ ] PUB-02 est **différé** (12 septembre) : la page de confidentialité reste un modèle à compléter, et reste servie publiquement en l'état
- [ ] FRONT-03 est **écarté** (12 septembre) : le sélecteur de 18 palettes est offert au visiteur, pas oublié. Ce qu'il coûte est reporté sur FRONT-08 ci-dessous — le contraste se vérifie sur les 18
- [x] FRONT-07 : un membre qui a oublié son mot de passe le réinitialise depuis le site, cas du lien expiré compris — y compris celui qui n'en a jamais défini, que le défaut de Django laissait sans réponse
- [ ] Le parcours est éprouvé avec un VRAI serveur d'envoi : le courriel part, arrive, et son lien s'ouvre en `https` depuis une messagerie — le backend console prouve le parcours, pas la remise (DEP-1)
- [x] FRONT-08, sans navigateur : l'aide de chaque champ s'annonce (une convention au lieu de deux), aucun identifiant n'est rendu deux fois, aucune référence `aria-*` ne pend dans le vide, et trois invariants de balayage les retiennent sur 64 pages
- [ ] FRONT-08, passe QA : `pilotage/qa/accessibilite-front-08.md` est jouée et cochée par un humain — clavier réel, zoom 200 et 400 %, 375 px, et ce qu'un lecteur d'écran annonce sur un formulaire REFUSÉ, état qu'aucun balayage ne visite
- [ ] Les 25 gabarits qui rendent un champ à la main donnent un identifiant à leurs messages d'erreur, ou passent par `_champ.html` : la référence `<id>_error` de Django y pend dès qu'un formulaire est refusé — à trancher avec l'inventaire ARCH-01, dont c'est un cas d'école
- [x] GOU-01, les règles : une réunion close garde ses règles, et l'électorat n'est plus réduit aux présences enregistrées (lot 4) — le gel valant sur les TROIS chemins de clôture, création d'une séance déjà archivée comprise, où il manquait (relecture du lot 12)
- [x] GOU-01, le contenu : une réunion **archivée** refuse une résolution, un point d'ordre du jour, une présence, un pouvoir et une réécriture de compte rendu — une seule ligne (`contenu_scelle`), relue sous verrou par cinq services, lue par les écrans qui n'offrent plus les formulaires, et par l'admin (inlines en lecture seule, voix et notes figées). Le PV se régénère encore et la réunion se rouvre par son statut : exprès, et la réouverture s'annonce
- [ ] OPS-04 : les dépendances TRANSITIVES sont figées elles aussi — verrou produit sur Linux, avec la barrière d'intégration ; les directes le sont depuis le lot 5, et la documentation est à jour
- [x] ARCH-01 : l'inventaire est écrit — `docs/regles-hors-services.md`, sept points, chacun avec ce qu'un accès admin ou shell peut faire malgré la règle et une recommandation
- [x] Un devis déjà facturé ne se refacture pas : le garde-fou porte sur l'existence d'une facture liée — une seule lecture (`devis_deja_facture`), partagée par le service, l'écran d'édition du bureau, son changement de statut et l'admin, qui fige en plus le statut. Un devis dont la facture a été supprimée redevient pilotable À L'ÉCRAN au lieu de rester dans une impasse — les deux directions sont testées
- [x] Régénérer un compte rendu passe par `remplacer_document` : l'ancien PV garde sa version au lieu d'être supprimé du disque, comme une facture ne se réécrit pas en place — point 1. Et la réunion sert la version COURANTE de son PV : un PV corrigé depuis la GED laissait sa fiche et la convocation du membre sur celui d'avant
- [ ] `PouvoirInline` de l'admin ne crée plus de pouvoir sans passer par `donner_pouvoir` : le plafond statutaire vaut quel que soit le chemin, ce que le lot 4 avait annoncé à tort — point 4 de l'inventaire, et c'est tout ce qui reste de GOU-01 ; le sceau du lot 12 ne ferme que les séances CLOSES, ce contournement vaut sur une réunion ouverte
- [ ] Décidé, pour une adhésion portant un reçu émis : refus de suppression, ou suppression assumée et annoncée à l'écran — aujourd'hui le lien comptable se perd sans rien dire (point 6)
- [ ] SEC-04 et ARCH-02 sont **écartés** (12 septembre) : le bureau reste indivisible, `is_staff` compris ; l'écrasement concurrent des fiches part en v2 avec GED-02 et GED-03
- [ ] PERF-01 : la galerie et les listes d'affiches ne dégradent plus avec le contenu — N+1 mesuré supprimé, pagination posée, images servies à la taille affichée et non en pleine résolution
- [ ] SEC-03 et OPS-02 sont portés explicitement par DEP-1, où le report a été décidé — cette case tombe quand les cases de DEP-1 les citent
- [ ] FRONT-04 et FRONT-05 sont portés par VIT-4, à venir : cette case tombe quand VIT-4 les cite dans son propre `Reste`. GED-02 et GED-03 restent en v2 assumée, sans case ici

## Contexte

Un audit externe du dépôt (révision `8525e56`, daté du 11 septembre) a été relu constat par
constat contre le code. Il est versé tel quel dans `docs/audit-externe-2026-09-11.md` ;
l'en-tête `audit:` ci-dessus pointe son **index de constats**, écrit par le dépôt, qui donne
à chacun son état et laisse l'outil les compter — le rapport, lui, est en prose et n'a pas
de tableau. Deux de ses constats ont été écartés :

- **Les PV de bureau lisibles par les membres** ne sont pas une fuite mais la règle voulue —
  un compte rendu rend compte à toute l'association. Le cahier §233 et un test le disent
  maintenant explicitement.
- **Les briques de sécurité active commentées** (axes, OTP, CSP, historique) sont un report
  décidé jusqu'au déploiement, pas un oubli. Voir DEP-1.

Trois constats de l'audit étaient justes mais incomplets, et c'est la relecture qui a
trouvé le reste : la suppression atteignait aussi les documents **sans dossier** (donc les
PV) ; l'édition d'un brouillon pouvait effacer le numéro d'une facture validée entre-temps,
ce que l'audit évoquait sans l'avoir reproduit ; et `assurer_pdf_facture` portait le même
défaut d'instance périmée que les transitions, ce que personne n'avait vu — moi le premier,
puisque je venais de l'écrire.

Le **lot 2** a transposé tout cela aux reçus fiscaux, où le garde-fou « un versement = un
seul reçu » vivait dans la vue : ni l'admin, ni le shell, ni un double clic ne le voyaient.
Puis il a coupé la validation d'une facture en deux temps. Le récapitulatif n'est pas qu'un
confort : c'est **la** garantie du parcours sans JavaScript, où rien ne peut signaler un
brouillon non enregistré.

**Décision d'arrondi (12 septembre)** : les montants sont arrondis au centime ligne par
ligne, au pair le plus proche — celui de `Decimal.quantize`, pas l'arrondi commercial au
demi supérieur. Aucun texte ne l'impose, changer toucherait tous les montants, et le
JavaScript reproduit désormais ce calcul à l'identique. Deux tests fixent la convention.

**Douze décisions du 12 septembre.** Quatre constats se ferment sans une ligne de code —
SEC-04, FRONT-03, ARCH-02, PUB-02 — et ce n'est pas la même chose que quatre oublis.
Les deux premiers sont en mémoire de travail, parce qu'une relecture à froid les
reprendrait pour des défauts : le bureau indivisible (`is_staff` ouvre tout le
back-office, c'est voulu) et le sélecteur de palettes offert au visiteur.

FRONT-03 écarté a un coût que le constat ne portait pas : les 18 palettes restant
offertes, le contraste AA se vérifie sur les 18 et non sur une. C'est passé dans
FRONT-08, où ça se paiera.

**Le lot 6 en trois corrections.** L'avoir dupliqué avait une impasse ouverte depuis
FIN-04 : il se préparait puis refusait de s'émettre, sans qu'aucun écran ne dise quoi en
faire. Le geste lui-même n'avait pas de sens, il disparaît. La fin d'adhésion ne fermait
rien du tout : un ancien membre déposait encore des fichiers et se déclarait présent à
une AG où il n'est plus électeur. Et le niveau « Public » des documents n'a jamais rien
mis en ligne — il veut dire « tout compte connecté », et il est plus large que
« Membres » ; le mot disait l'inverse du contrôle, ce qui se paie en documents mal
classés.

Un détail du décorateur mérite d'être retenu : il n'intercepte **que** la fin
d'adhésion. Le compte sans fiche membre garde le 404 anti-énumération gagné en SEC-01,
qu'une redirection bavarde aurait affaibli — deux tests l'ont dit avant moi.

La relecture du lot 6 a trouvé le reste : masquer un lien ne ferme pas l'adresse. Six
écrans rendaient encore un formulaire complet à un ancien membre, qui l'aurait rempli
pour se voir refuser l'enregistrement à la fin. D'où deux gardes distinctes — un écran
qui MÊLE lecture et geste garde son GET, un écran qui n'est QUE le geste se ferme. Et une
régression de performance à moi : contrôler le bureau avant la fiche membre coûtait trois
requêtes de groupes par page servie.

**Le lot 13 — le PV régénéré, et un PV corrigé que personne ne voyait.** Régénérer un
compte rendu écrasait son fichier sur le disque : le PV que les membres avaient
téléchargé cessait d'exister, sans trace du changement, alors qu'il part en
confidentialité « Membres », donc à toute l'association. C'est l'invariant de FIN-02
sur les factures, et le remède — `remplacer_document` — était à côté depuis le lot 1.
Un test fixait le défaut à l'endroit du correctif (« même Document, fichier
remplacé ») ; il est remplacé, en gardant ce qu'il protégeait de juste : un seul
document COURANT, donc pas de doublon dans les listes.

Le plus gênant s'est trouvé en corrigeant. `reunion.compte_rendu` pointe une version
précise, et le bureau peut déposer un PV corrigé depuis les pièces de l'association —
cet écran couvre les documents non classés, donc les PV. La fiche de la réunion et la
convocation du membre servaient alors le fichier d'AVANT la correction pendant que la
GED montrait le bon, et une régénération repartait de la version périmée : deux
documents qui divergent, sans que rien ne le signale. Les deux écrans suivent
maintenant la version courante.

Détail de méthode qui a compté : le service lisait d'abord le document par la
relation portée par la réunion, donc depuis le cache de l'instance — il se croyait
courant. La relecture en base l'a corrigé. C'est la même règle que le sceau du lot 12
et que les pièces de facturation : on décide sur ce que dit la base, pas sur ce qu'on
tient en main.

**Le lot 12 — GOU-01, le contenu d'une séance close.** Le lot 4 avait figé les
RÈGLES d'une réunion archivée et la fiche s'était close là-dessus. Son CONTENU restait
ouvert : résolution, point d'ordre du jour, présence, pouvoir et compte rendu s'y
écrivaient encore, depuis le back-office et formulaires affichés. « Une réunion close
garde son résultat » n'était vrai que de ses seuils.

Le sceau est une ligne, dans le service, relue sous verrou — la séance peut être
archivée entre l'affichage de l'écran et l'envoi du formulaire. Cinq services nommés la
portent ; les deux vues qui lisaient `request.POST` en direct passent par un formulaire,
ce qui était le point 5 de l'inventaire et n'est pas un hasard : sans formulaire, il n'y
avait aucun endroit naturel pour poser la règle, et c'est ce qui a permis au défaut de
passer inaperçu.

Les deux moitiés du geste comptent, et c'est la leçon du lot 6 rejouée : refuser à
l'envoi sans retirer le formulaire fait remplir un écran pour rien ; retirer le
formulaire sans refuser laisse l'adresse ouverte. L'écran et la règle lisent donc la même
ligne, et cinq envois directs aux URL l'éprouvent. Le déroulé reste lisible sur une
séance close — masquer le formulaire ne doit pas escamoter le compte rendu, qui est
justement ce qu'on garde ; un seul fragment sert les deux états, pour que l'écran ne
montre jamais autre chose que ce que le PV assemble.

Deux gestes restent permis, assumés : le PV se régénère, parce qu'il ne fait que RENDRE
un contenu scellé et que le refuser enfermerait une séance sans son PV dans une impasse ;
et la réunion se rouvre par son statut, parce qu'une clôture par erreur doit se défaire.
Son en-tête, lui, est figé, et la réouverture s'annonce à l'écran.

La relecture a trouvé deux règles qui ne valaient pas partout. Le compte rendu en
portait deux au lieu d'une : une note absente de l'envoi était laissée telle quelle, une
synthèse absente était remise à blanc — la conclusion de séance s'effaçait sans qu'on la
demande, et l'encart de l'inventaire décrivait déjà la règle uniforme que le code
n'appliquait qu'à moitié. Et le gel des règles vivait sur le chemin de l'ÉDITION : une
réunion créée déjà archivée — une séance passée saisie après coup, ce que l'écran de
création permet — ne figeait rien, et ses seuils suivaient les paramètres pour toujours.
Les deux sont reproduites par sonde avant d'être corrigées.

Trouvaille de chemin : la fiche d'une réunion n'était dans aucun balayage
d'accessibilité, alors que c'est l'écran le plus dense du bureau. L'aide de son champ
« droit de vote » ne s'annonçait pas — le gabarit rendait le champ à la main, sans le
`<span>` que Django cite dans son `aria-describedby`. Le lot 9 avait corrigé la
convention, pas les gabarits qui ne l'empruntent pas. Cette page est maintenant balayée,
avec un point d'ordre du jour et un bloc de récit pour que ses champs existent.

**Le lot 11 — le devis refacturable, et ce que la relecture a dû aller chercher.** Le
garde-fou de `transformer_en_facture` portait sur l'étiquette « Facturé » du devis, que
l'admin remet en arrière ; il porte maintenant sur l'existence de la facture liée. Un
fait ne se remet pas à zéro depuis un formulaire d'admin, une étiquette si.

Corriger le service ne suffisait pas, et c'est la relecture qui l'a montré. Les deux
écrans du bureau gardaient leur lecture de l'étiquette : un devis marqué « Facturé »
dont la facture avait été supprimée depuis restait présenté en lecture seule, annonçant
une facture qu'il ne pouvait même plus lier, changement de statut refusé. Plus aucun
geste n'était offert, alors que le service, lui, acceptait de nouveau — la sortie
existait sans qu'aucun bouton n'y mène. Reproduit par sonde avant d'être corrigé. Les
quatre chemins lisent désormais la même ligne, ce qui est le fond d'ARCH-01 : la règle
à un seul endroit.

**Le lot 10 — l'inventaire ARCH-01, et deux constats à rouvrir.** L'inventaire
(`docs/regles-hors-services.md`) a trouvé trois choses qui pèsent plus que le constat
d'origine, et deux d'entre elles démentent des cases déjà cochées.

Un PV régénéré **supprime le fichier précédent du disque** : ni version, ni trace, alors
que `remplacer_document` est juste à côté depuis le lot 1. Un compte rendu part à toute
l'association ; celui que les membres ont téléchargé peut cesser d'exister.

Une réunion **archivée** accepte encore résolutions, sujets et compte rendu — depuis le
back-office, formulaires à l'écran, pas par contournement d'URL. Le lot 4 avait figé les
RÈGLES d'une réunion close, pas son CONTENU. GOU-01 est donc rouvert, sur ce point seul.

Un devis facturé peut redevenir « accepté » depuis l'admin, puis être refacturé :
`transformer_en_facture` se garde sur le statut, pas sur l'existence d'une facture liée.
Le verrou du lot 1 sérialise l'opération, il ne la rend pas idempotente.

Et une correction qui m'incombe : le lot 4 annonçait « un seul service pour les pouvoirs,
quel que soit le chemin ». Faux — `PouvoirInline` de l'admin écrit sans passer par
`donner_pouvoir`, donc sans le plafond statutaire. Je l'avais écrit sans ouvrir l'inline.
La leçon vaut au-delà : « quel que soit le chemin » est une affirmation qui se vérifie
chemin par chemin, l'admin compris.

**Le lot 9 — FRONT-08, et une panne qui ne faisait aucun bruit.** Django ≥ 5 relie
lui-même l'aide d'un champ à son widget par `aria-describedby`, vers `<id>_helptext`.
Le dépôt portait en plus un mixin maison qui visait `<id>_aide`. Les formulaires
passant par le mixin étaient corrects ; les autres pointaient vers un identifiant
inexistant — et une référence `aria` morte est **ignorée sans erreur**. L'aide
s'affichait à l'écran et ne s'annonçait jamais : inscription à un événement,
création d'une adhésion, fiche d'un membre. Le mixin a disparu ; il dupliquait une
fonction du cadre, et la duplication était la panne.

Un cas dépassait l'accessibilité : l'aide du champ « rôle » d'une ligne de
distribution n'était affichée **nulle part**, le gabarit de ligne rendant label et
champ sans elle. Le conseil était perdu pour l'œil autant que pour l'oreille.

Ce qui rend ces deux défauts intéressants, c'est qu'ils sont invisibles à la
relecture ET muets à l'exécution. Seul un balayage les trouve — d'où trois
invariants neufs, sur les 64 pages que le dépôt sait déjà rendre. Une sonde
signalait un troisième défaut : faux positif, le bouton du panneau
d'accessibilité porte un `aria-label` que mon filtre ne voyait pas.

**Le lot 8 — OPS-01, et ce qu'écrire une liste apt a révélé.** La vérification
distante existait déjà en intention dans le hook de pré-push, qui expliquait pourquoi
elle ne suffirait pas : le webhook se déclenche sur le push, donc une CI arrive après la
mise en ligne. C'est toujours vrai — le workflow constate, il ne retient rien, et la
barrière se ferme à DEP-1. Ce qu'il apporte tout de suite, c'est que les quatre tests de
concurrence tournent enfin ailleurs que sur une machine où l'on peut les contourner.

La trouvaille est ailleurs. En écrivant la liste des bibliothèques natives de WeasyPrint,
je l'ai lue dans `weasyprint/text/ffi.py` au lieu de la recopier : la v69 en ouvre six, et
NI cairo NI gdk-pixbuf n'en font partie. La liste qui vivait dans `requirements.txt` et
dans une case de DEP-1 — celle que quelqu'un aurait suivie sur le VPS — nommait deux
paquets inutiles et en oubliait trois nécessaires. Une étape du workflow la rend
exécutable : elle charge le moteur et produit un vrai PDF, ce qu'aucune machine du projet
n'avait jamais fait, la suite remplaçant `html_vers_pdf` partout et passant donc sur un
poste Windows sans GTK.

**Le lot 7 — FRONT-07.** L'essentiel n'est pas le branchement des quatre vues de Django
mais ce qu'il fallait lui retirer : son formulaire écarte les comptes au mot de passe
inutilisable, or c'est exactement ce que `ouvrir_compte` pose. Le membre invité il y a six
mois, lien d'activation perdu, recevait le silence sur une page lui affirmant qu'un
courriel était parti. C'est le cas le plus probable du parcours, et c'était le seul
non couvert.

Hors périmètre tant que ce n'est pas demandé, et donc volontairement absent du `Reste`
ci-dessus : corbeille et journal des suppressions, quotas par membre, antivirus, MFA,
matrice de rôles fins. Ce sont des fonctionnalités v2, pas des correctifs — cf.
CLAUDE.md, « Périmètre v1 vs plus tard ». Le verrouillage optimiste des fiches les
rejoint par décision (ARCH-02).
