---
chantier: SEC-1
statut: interrompu
audit: docs/audit-externe-2026-09-11-constats.md
---

# SEC-1 — consolidation après l'audit externe

**Arrêté sur** — lot 4 : gouvernance (GOU-01) — un seul service pour les pouvoirs avec le
plafond statutaire, registre électoral complet (le quorum se calcule enfin sur l'électorat,
absents compris) et règles figées à la clôture, commit `d1ba3a5`, 12 septembre.

## Reste

### Pièces émises
- [x] Le reçu fiscal suit les mêmes règles que la facture : rien d'éditable ni de supprimable dans l'admin une fois émis, PDF rendu dès l'émission
- [x] FIN-02 : une facture dont le PDF archivé a disparu se régénère à l'identique — instantané d'émission, dont le rendu part désormais
- [x] FIN-04 : un avoir dupliqué ne peut plus annuler plus que sa facture — détaché de son origine, il ne s'émet plus du tout
- [ ] L'avoir dupliqué a une issue : soit un écran pour le rattacher à une facture, soit la duplication d'un avoir disparaît — aujourd'hui il se prépare et reste bloqué là
- [ ] Télécharger ou prévisualiser une facture sans moteur PDF affiche un message, pas une erreur 500 — la vue du PV le fait déjà, les vues de facture non

### Saisie et parcours
- [x] « Valider » ne porte plus que sur une version enregistrée : un écran de confirmation récapitule la pièce telle qu'elle est en base, et seul le POST émet
- [x] Un double clic sur « Valider » ne s'annonce plus comme une erreur : la seconde requête constate en information que la pièce est déjà émise
- [ ] Dans un navigateur : modifier un champ du brouillon révèle « Modifications non enregistrées » et le lien « Valider et numéroter… » cesse de mener au récapitulatif tant qu'on n'a pas enregistré — aucun test ne couvre ce geste, il demande un vrai navigateur
- [ ] Le lien de validation neutralisé se distingue **à l'œil**, et pas seulement pour un lecteur d'écran : il porte `aria-disabled` sans style associé

### Concurrence éprouvée
- [ ] `TEST_POSTGRES=1 pytest` passe, test de double clic simultané compris — sous SQLite il se déclare « skipped » et ne prouve rien du verrou
- [ ] Le PDF rendu à l'émission est éprouvé avec le vrai WeasyPrint : le fichier archivé s'ouvre et porte le bon numéro

### Livraison
- [ ] OPS-01 : une vérification distante sur PostgreSQL est la barrière avant `main` : un commit non validé ne part pas en déploiement — aujourd'hui le webhook se déclenche sur le push, et le hook local se contourne ou s'oublie à chaque clone

### Constats du rapport encore ouverts, à programmer
- [ ] PUB-01 : une limitation de débit protège contact et réservations — des envois répétés depuis la même origine sont ralentis ou refusés, et une jauge ne peut plus être saturée par des réservations successives
- [ ] PUB-02 : la page de confidentialité décrit les traitements réels (comptes, adhésions, réservations, documents, photos, gouvernance) et leurs durées, au lieu de se présenter comme un modèle à compléter
- [ ] FRONT-03 : le sélecteur de 18 palettes a disparu des pages servies, une palette ayant été choisie — il s'affiche aujourd'hui sans condition `DEBUG`
- [ ] FRONT-07 : un membre qui a oublié son mot de passe le réinitialise depuis le site, cas du lien expiré compris — aucune route ne le permet aujourd'hui
- [ ] FRONT-08 : une campagne d'accessibilité a été menée (375 px et bureau, zoom 200 %, clavier, focus après erreur, contraste de la palette retenue) et ce qu'elle trouve est corrigé ou fiché
- [x] GOU-01 : une réunion close garde son résultat, et l'électorat n'est plus réduit aux présences enregistrées
- [ ] OPS-04 : l'environnement testé est verrouillé (lockfile), et le README annonce la bonne version de Python et un compte de tests exact
- [ ] SEC-03 et OPS-02 sont portés explicitement par DEP-1, où le report a été décidé — cette case tombe quand les cases de DEP-1 les citent

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

Hors périmètre tant que ce n'est pas demandé, et donc volontairement absent du `Reste`
ci-dessus : corbeille et journal des suppressions, quotas par membre, antivirus, MFA,
verrouillage optimiste des fiches, matrice de rôles fins. Ce sont des fonctionnalités v2,
pas des correctifs — cf. CLAUDE.md, « Périmètre v1 vs plus tard ».
