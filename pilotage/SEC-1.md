---
chantier: SEC-1
statut: interrompu
---

# SEC-1 — consolidation après l'audit externe

**Arrêté sur** — lot 1 : pièces relues sous verrou avant toute transition, PDF figé à
l'émission, admin des factures aligné sur les écrans du bureau, suppression refusée aux
comptes sans fiche membre, plus les correctifs courts (calendrier borné, sauvegarde qui
sort en échec sans copie distante, erreurs de ligne affichées, arrondi du JS aligné sur
le serveur), commit `c71bf05`, 12 septembre.

## Reste

### Pièces émises
- [ ] Le reçu fiscal suit les mêmes règles que la facture : rien d'éditable ni de supprimable dans l'admin une fois émis, émetteur et signataire figés — les mêmes tests que pour la facture, transposés
- [ ] Une facture dont le PDF archivé a disparu se régénère à l'identique, et non depuis les données du jour : sans instantané des mentions et des identités, la pièce reconstruite n'est plus la pièce émise
- [ ] Un avoir dupliqué ne peut plus annuler plus que sa facture — `dupliquer_facture` retire volontairement `avoir_de`, ce qui sort la copie du contrôle « jamais plus que le reste à annuler »
- [ ] Télécharger ou prévisualiser une facture sans moteur PDF affiche un message, pas une erreur 500 — la vue du PV le fait déjà, les vues de facture non

### Saisie et parcours
- [ ] « Valider » ne porte plus que sur une version enregistrée : le bouton reste inactif tant que le brouillon porte des modifications non enregistrées, ou l'action enregistre avant de valider
- [ ] Un double clic sur « Valider » affiche un seul message, et non un succès suivi de « la facture n'est pas en brouillon »

### Concurrence éprouvée
- [ ] `TEST_POSTGRES=1 pytest` passe, test de double clic simultané compris — sous SQLite il se déclare « skipped » et ne prouve rien du verrou
- [ ] Le PDF rendu à la validation est éprouvé avec le vrai WeasyPrint : le fichier archivé s'ouvre et porte le bon numéro

### Livraison
- [ ] Une vérification distante sur PostgreSQL est la barrière avant `main` : un commit non validé ne part pas en déploiement — aujourd'hui le webhook se déclenche sur le push, et le hook local se contourne ou s'oublie à chaque clone

## Contexte

Un audit externe du dépôt (révision `8525e56`, daté du 11 septembre) a été relu constat par
constat contre le code. Le document lui-même ne vit pas dans le dépôt ; ce qui compte en a
été repris ici. Deux de ses constats ont été écartés :

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

**Décision d'arrondi (12 septembre)** : les montants sont arrondis au centime ligne par
ligne, au pair le plus proche — celui de `Decimal.quantize`, pas l'arrondi commercial au
demi supérieur. Aucun texte ne l'impose, changer toucherait tous les montants, et le
JavaScript reproduit désormais ce calcul à l'identique. Deux tests fixent la convention.

Hors périmètre tant que ce n'est pas demandé, et donc volontairement absent du `Reste`
ci-dessus : corbeille et journal des suppressions, quotas par membre, antivirus, MFA,
verrouillage optimiste des fiches, matrice de rôles fins. Ce sont des fonctionnalités v2,
pas des correctifs — cf. CLAUDE.md, « Périmètre v1 vs plus tard ».
