# Audit externe du 11 septembre 2026 — index des constats

Document **du dépôt**, écrit après coup. Le rapport lui-même est
[`audit-externe-2026-09-11.md`](audit-externe-2026-09-11.md), versé tel qu'il a été reçu et
**non modifié**. Cet index existe parce que le rapport est en prose : sans tableau, l'outil
`pilote` ne sait pas compter les constats ouverts ni les rattacher au chantier SEC-1.

Lecture des pastilles : 🔴 🟠 🟡 = **ouvert**, du plus urgent au moins ; ✅ = **clos dans le
dépôt**, corrigé ou écarté par décision — la colonne d'état dit laquelle des deux. La
priorité d'origine du rapport (P0, P1, P2) est rappelée dans la colonne « Constat », parce
qu'elle ne dit pas la même chose que ce qui reste à faire aujourd'hui.

| Code | Sév. | Constat | État dans le dépôt |
|---|---|---|---|
| SEC-01 | ✅ | P0 — suppression de documents officiels par un compte sans fiche membre | Corrigé, lot 1 (`2dd86ef`). Couvre aussi les documents **sans dossier**, donc les PV, que le rapport n'avait pas vus |
| SEC-02 | ✅ | P0 — les PV de bureau deviennent accessibles aux membres | **Écarté** : c'est la règle voulue. Un compte rendu rend compte à toute l'association (cahier §233, test dédié) |
| FIN-01 | ✅ | P0 — une même facture peut être renumérotée | Corrigé, lot 1 (`cc4b384`) : relecture sous verrou avant contrôle, édition périmée bloquée |
| FIN-02 | ✅ | P0 — l'immuabilité des factures n'est pas assurée sur tous les parcours | Corrigé, lots 2 et 3 (`566b9cd`) : PDF figé à l'émission, aperçu servi depuis l'archive, admin aligné, et instantané d'émission (émetteur, client, signataire, lignes, totaux) d'où le PDF se reconstruit à l'identique. Vaut aussi pour le reçu |
| SEC-03 | 🟠 | P1 — les protections installées ne sont pas toutes actives | Report **décidé** jusqu'au déploiement (axes, OTP, CSP, historique) — voir DEP-1 |
| SEC-04 | 🟡 | P1 — le rôle Bureau est trop large pour une délégation fine | Décision métier à prendre ; `is_staff` valant bureau reste à trancher |
| SEC-05 | 🟡 | P1 — distinguer fin d'adhésion, statut du membre et accès au compte | Décision métier à prendre |
| GED-01 | ✅ | P1 — le versionnement peut produire deux versions courantes | Corrigé, lot 1 (`2dd86ef`) : version relue sous verrou, `VersionPerimee` |
| GED-02 | 🟡 | P1 — suppression immédiate, absence de corbeille, fichiers orphelins | v2 assumée (CLAUDE.md, « Périmètre v1 vs plus tard ») |
| GED-03 | 🟡 | P1/P2 — quotas globaux et traitement des fichiers | v2 assumée |
| PUB-01 | 🟠 | P1 — les formulaires publics restent exposés aux abus | Ouvert : limitation de débit à poser, côté Nginx au déploiement |
| PUB-02 | 🟠 | P1 — documentation de confidentialité incomplète | Ouvert : la page reste un modèle à compléter, et l'inventaire des traitements à écrire |
| FIN-03 | ✅ | P1 — transformation devis → facture non idempotente | Corrigé, lot 1 : devis relu sous verrou. La limite de numérotation des devis est désormais documentée, pas niée |
| FIN-04 | ✅ | P1 — invariants des pièces et des montants | Corrigé, lots 2 et 3 (`93a9fe3`) : un seul avoir en préparation, jamais plus que le reste à annuler, ligne obligatoire dans le service, signe de la pièce contrôlé (une remise reste possible), avoir détaché non émissible, taux de TVA borné en base |
| GOU-01 | 🟠 | P1 — le résultat d'une réunion doit être figé avec ses règles | Ouvert : électorat, instantané des règles, gel à la clôture |
| ARCH-01 | 🟡 | P1 — les règles centrales restent trop dépendantes des vues | Ouvert |
| ARCH-02 | 🟡 | P2 — les modifications concurrentes des fiches peuvent se perdre | Ouvert |
| PERF-01 | 🟡 | P2 — quelques requêtes et médias croîtront avec le contenu | Ouvert : N+1 des affiches, images non redimensionnées |
| FRONT-01 | ✅ | P1 — fiabiliser d'abord la saisie des factures | Corrigé, lot 1 : arrondi JavaScript aligné sur le serveur (aucun écart sur 5 009 cas), erreurs affichées champ par champ |
| FRONT-02 | ✅ | P1 — éviter de valider une ancienne version du brouillon | Corrigé, lot 2 (`6236e67`) : écran de confirmation sur la version enregistrée |
| FRONT-03 | 🟠 | P1/P2 — achever l'amélioration progressive, retirer les outils de développement | Ouvert : le sélecteur de 18 palettes attend le choix d'une palette |
| FRONT-04 | 🟡 | P2 — transformer la fiche spectacle en vraie page de présentation | Ouvert (proposition produit) |
| FRONT-05 | 🟡 | P2 — donner plus d'autonomie aux auteurs | Ouvert (proposition produit) |
| FRONT-06 | 🟡 | P1/P2 — clarifier les audiences et sécuriser les gestes de fichiers | Ouvert : le niveau « PUBLIC » veut dire « tout compte connecté » |
| FRONT-07 | 🟠 | P1/P2 — finir les parcours d'accès et de réservation | Ouvert : aucun parcours « mot de passe oublié », lié aux e-mails transactionnels |
| FRONT-08 | 🟠 | P1/P2 — corriger les entrées invalides et vérifier l'accessibilité réelle | **Partiel** : l'erreur 500 du calendrier est corrigée (lot 1). La campagne d'accessibilité reste entière |
| OPS-01 | 🟠 | P1 — le déploiement n'attend pas une validation distante du commit | Ouvert — case « Livraison » de SEC-1 |
| OPS-02 | 🟠 | P1 — déploiement en place et dernier push potentiellement perdu | Ouvert — DEP-1 |
| OPS-03 | ✅ | P1 — la sauvegarde peut réussir sans copie distante | Corrigé, lot 1 (`c71bf05`) : sortie en code 1. Éprouver la restauration reste une case de DEP-1 |
| OPS-04 | 🟠 | P1/P2 — dépendances non verrouillées et documentation vieillissante | Ouvert : pas de lockfile ; le README annonce Python 3.11+ et ~168 tests |
