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
- [ ] Le lien de validation neutralisé se distingue **à l'œil**, et pas seulement pour un lecteur d'écran : il porte `aria-disabled` sans style associé

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
- [ ] PUB-01 : une limitation de débit protège contact et réservations — des envois répétés depuis la même origine sont ralentis ou refusés, et une jauge ne peut plus être saturée par des réservations successives
- [ ] PUB-02 est **différé** (12 septembre) : la page de confidentialité reste un modèle à compléter, et reste servie publiquement en l'état
- [ ] FRONT-03 est **écarté** (12 septembre) : le sélecteur de 18 palettes est offert au visiteur, pas oublié. Ce qu'il coûte est reporté sur FRONT-08 ci-dessous — le contraste se vérifie sur les 18
- [x] FRONT-07 : un membre qui a oublié son mot de passe le réinitialise depuis le site, cas du lien expiré compris — y compris celui qui n'en a jamais défini, que le défaut de Django laissait sans réponse
- [ ] Le parcours est éprouvé avec un VRAI serveur d'envoi : le courriel part, arrive, et son lien s'ouvre en `https` depuis une messagerie — le backend console prouve le parcours, pas la remise (DEP-1)
- [ ] FRONT-08, sans navigateur d'abord : HTML sémantique, libellés de champs, `aria`, ordre de tabulation, focus après erreur, et le contraste AA calculé sur les **18** palettes — ce qui échoue est corrigé ou fiché
- [ ] FRONT-08, passe QA ensuite : une passe rejouable dans `pilotage/qa/` couvre ce qui demande un vrai navigateur (375 px et bureau, zoom 200 %, clavier), et l'humain la coche
- [x] GOU-01 : une réunion close garde son résultat, et l'électorat n'est plus réduit aux présences enregistrées
- [ ] OPS-04 : les dépendances TRANSITIVES sont figées elles aussi — verrou produit sur Linux, avec la barrière d'intégration ; les directes le sont depuis le lot 5, et la documentation est à jour
- [ ] ARCH-01 : l'inventaire des règles métier qui n'existent que dans les vues est écrit, chacune avec ce qu'un accès admin ou shell pourrait faire malgré elle — la remontée se décide ensuite, tout n'a pas besoin de bouger
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
