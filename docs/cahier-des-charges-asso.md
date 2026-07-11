# Cahier des charges — Site & back-office de l'association

*Récapitulatif des décisions de cadrage (v1)*

---

## 1. Vision générale

Application web à deux faces partageant une même base de données :

- **Front public** : site de présentation de l'association (membres, spectacles, agenda, galerie, contact).
- **Espace membre** : zone connectée où chaque adhérent retrouve ce qui le concerne.
- **Back-office** : administration réservée, avec rôles, pour gérer documents, facturation, budget et gouvernance.

**Priorité affichée du projet : sur-mesure et flexible.** L'équipe dispose de compétences de développement.

---

## 2. Stack technique retenue

| Élément | Choix |
|---|---|
| Backend | **Django + Django REST Framework** (Python) |
| Base de données | **PostgreSQL** |
| Back-office | **Admin Django** (point de départ), interfaces sur mesure ajoutées progressivement |
| Front public | Rendu serveur privilégié (**Astro**, **Next.js SSR**, ou **templates Django**) — pas une application monopage lourde, pour la performance mobile et l'accessibilité |
| Génération PDF | **WeasyPrint** (HTML/CSS → PDF) pour devis, factures, reçus fiscaux |
| Export Excel | **openpyxl** |
| Arborescence de dossiers | **django-treebeard** ou **django-mptt** |
| Permissions par objet | **django-guardian** (si besoin de finesse au niveau objet) |

**Principe de mise en œuvre** : démarrer toute la logique sur l'admin Django, valider les modèles, puis construire les interfaces soignées uniquement pour les écrans utilisés au quotidien (explorateur de fichiers, éditeur de facture, tableau de bord budget).

---

## 3. Périmètre fonctionnel

### 3.1 Front public

- Présentation de l'association
- Présentation des membres
- **Spectacles / projets** : page filtrable (à l'affiche / en création / archives ; productions asso vs projets de membres), fiches projet avec équipe, affiche, galerie, prochaines dates
- **Agenda** : deux vues disponibles (**liste** + **calendrier mensuel**), **au choix du visiteur**, préférence mémorisée
- **Galerie** photo / vidéo (vidéo via liens YouTube/Vimeo plutôt qu'hébergement lourd)
- **Formulaire de contact** (avec anti-spam et consentement RGPD)

### 3.2 Espace membre (connecté)

- Statut d'adhésion personnel
- Téléchargement des reçus fiscaux
- Consultation des documents qui concernent le membre
- Convocations aux AG + ordres du jour
- Comptes-rendus
- **Proposer un événement** (entre en modération)
- **Proposer un sujet** à discuter (entre en modération)
- **Créer / éditer la fiche de son propre projet** (perso ou collectif), puis la soumettre (entre en modération)

> **Règle de sécurité clé (IDOR)** : chaque écran de l'espace membre filtre **toujours** selon l'utilisateur connecté, jamais selon un identifiant fourni dans l'URL sans revérifier la propriété.

### 3.3 Back-office (selon rôles)

- **Cœur associatif** : membres, lieux
- **Spectacles / projets** : fiches (portage asso/perso/collectif, statut projet, distribution membres + extérieurs) + file de modération des propositions de membres
- **Agenda** + file de modération des propositions
- **Médias** (avec texte alternatif obligatoire)
- **GED** : documents / dossiers (y compris vie associative : statuts, PV d'AG, déclarations préfecture)
- **Facturation** : devis, factures, lignes
- **Budget** : adhésions, transactions
- **Exports comptables** + bilan annuel
- **Gouvernance** : carnet de sujets, réunions/AG, ordres du jour, présences, pouvoirs, résolutions, quorum

---

## 4. Module Facturation

- Éditeur sous forme de **formulaire** : client, date, lignes (désignation / quantité / prix unitaire / TVA) → calcul automatique HT / TVA / TTC.
- **Lignes en ligne** (inline) dans le formulaire de la facture.
- Un **devis transformable en facture** d'un clic.
- **Numérotation des factures** : séquentielle, continue, sans trou, attribuée **à la validation** (pas au brouillon) — contrainte légale.
- Mentions légales obligatoires (identité, dates, TVA le cas échéant).
- Export **PDF** via WeasyPrint.

---

## 5. Module Budget

### Adhésions
- Relie un **Membre** à une **Saison** / année.
- Statut : **payé / exonéré / en attente**.
- Montant attendu **et** montant réellement versé (gère ceux qui donnent plus).
- Date.

### Transactions
- Type : **recette / dépense**.
- Statut : **prévu / réalisé** (→ budget prévisionnel vs réel).
- Montant, catégorie, date.
- Lien optionnel vers une **facture** ou une **adhésion**.

### Sorties
- Total recettes, total dépenses, solde, reste à encaisser, écart prévu/réel.
- **Export CSV / Excel** pour le trésorier / l'expert-comptable.
- **Bilan financier annuel** par catégorie (PDF et/ou Excel), pour l'AG.
- **Reçus fiscaux** pour les dons (Cerfa 11580) si l'association est d'intérêt général.

---

## 6. Module Spectacle / Projet

### Distinction de fond : l'œuvre vs ses représentations
- Le **Spectacle / Projet** = l'œuvre elle-même (titre, synopsis, équipe, affiche), **existe indépendamment des dates**.
- La **représentation** = une occurrence datée → c'est un `Evenement` de l'agenda, relié au spectacle.
- Un spectacle a **0..n représentations** (0 si en création).

### Type de portage
- Champ `type_portage` : **association / personnel / collectif**.
- `porteurs` → Membres (surtout pour perso/collectif).
- Permet de distinguer à l'affichage « production de la compagnie » et « projet porté par [membre] ».

### Cycle de vie du projet (découplé des dates)
- `statut_projet` : **en création / en répétition / à l'affiche / archivé**.
- Un spectacle **peut exister sans aucune représentation** → rubrique front « nos créations en cours » distincte de « à l'affiche ».
- Projet archivé → bascule vers galerie souvenir / historique.

### Modération (même logique que l'agenda)
- `statut_modération` : `brouillon → proposé → publié` (ou `refusé`).
- Un **membre porteur** peut **créer et éditer** la fiche de **son** projet perso/collectif, puis la soumet ; le bureau valide la mise en ligne.
- Un membre ne peut éditer **que ses propres projets** (vérification d'autorisation par objet, anti-IDOR) — pas les productions de l'asso ni les projets des autres.
- Le bureau crée directement et peut tout éditer.
- `créé_par` / `validé_par`.

### Distribution / équipe — **membres + intervenants extérieurs**
- **Décision : pas de socle Personne** (on garde simple). Modèle `Membre` inchangé.
- Chaque ligne de distribution est **soit un Membre** (fiche réutilisable), **soit un nom libre** (intervenant extérieur, texte).

```
LigneDistribution
├── spectacle   → Spectacle
├── membre      → Membre    (optionnel)
├── nom_externe : texte     (optionnel, si pas membre)
├── rôle        : comédien / mise en scène / technique / musique…
└── règle : soit membre, soit nom_externe
```

- Compromis assumé : un intervenant extérieur récurrent est ressaisi à chaque fois (pas de fiche). Migration vers un socle Personne possible plus tard si besoin.

### Structure consolidée

```
Spectacle / Projet
├── titre, synopsis, note d'intention
├── type_portage      : association / personnel / collectif
├── porteurs          → Membres
├── statut_projet     : en création / en répétition / à l'affiche / archivé
├── statut_modération : brouillon / proposé / publié / refusé
├── créé_par / validé_par
├── distribution      → LigneDistribution (membre OU nom externe, avec rôle)
│                       la mise en scène est une ligne comme une autre
│                       (rôle « Mise en scène ») — pas de champ dédié
├── affiche           → Media (alt obligatoire)
├── galerie           → Media (plusieurs)
├── durée, genre, public visé
└── représentations   → Evenement (0..n)
```

### Front public
- Page « nos spectacles / projets » **filtrable** : à l'affiche / en création / archives ; productions asso vs projets de membres.
- Fiche projet : synopsis, note d'intention, équipe (liens vers fiches membres), affiche, galerie, **prochaines dates** (tirées des représentations), + lien inscription/billetterie le moment venu.
- Circularité : membre → ses projets ; projet → son équipe + ses dates ; date d'agenda → sa fiche spectacle.

### Pistes v2/v3 (à garder en tête, ne pas coder)
- Autour des projets en création : appel à bénévoles, à soutien, carnet de création.

---

## 7. Module Agenda — décisions

| Question | Décision |
|---|---|
| Qui crée un événement ? | **Membres proposent, bureau valide** (modération) |
| Événements privés ? | **Oui** : trois niveaux — **public / membres / interne** |
| Affichage par défaut | **Les deux vues au choix** du visiteur (défaut adapté selon l'écran : liste sur mobile) |

### Cycle de vie
`brouillon → proposé → publié` (ou `refusé` + motif)

### Données de l'événement
- Titre, description
- Date début / fin, heure
- Lieu (texte ou modèle `Lieu`)
- Statut, visibilité
- **Affiche** → Media (alt obligatoire)
- **Galerie** d'images → Media (plusieurs)
- **Spectacle** lié (optionnel) — l'événement est alors une **représentation** du spectacle et hérite de sa description, ses photos, sa distribution
- **Intervenants** → Membres (rôles : organisateur, participant…)
- `créé_par` (qui propose) / `validé_par` (qui modère)
- Date de publication
- Export **iCal / .ics**

### Règles
- Le **membre propose**, le **bureau fixe la visibilité** à la validation.
- **Notifications par e-mail** : au bureau à chaque proposition, au membre à la décision (pas de temps réel au départ).
- Événements simples (une date = une entrée) en v1 ; récurrence = raffinement ultérieur.

---

## 8. Module Gouvernance

### 8.1 Carnet de sujets (continu)

- Qui dépose ? **Membres proposent, bureau trie** (même logique que l'agenda).
- Statut : `proposé → ouvert → à l'ordre du jour → traité`, ou `reporté` (revient « ouvert »), ou `refusé` (+ motif).
- Champs : titre, description, proposé_par, date, priorité, catégorie, documents liés (→ GED), réunion liée.
- Le bureau peut retenir, refuser, ou **fusionner** avec un sujet existant.

### 8.2 Réunions / AG (événementiel)

- Type : **AG ordinaire / AG extraordinaire / réunion de bureau**.
- Statut : préparation / convoquée / tenue / archivée.
- **Ordre du jour** = sujets piochés dans le carnet (ordonnés).
- **Documents joints** → GED (communiqués avec la convocation).
- Convocation (texte + date d'envoi).
- **Compte-rendu** (PV) → GED.
- Une réunion **peut être** un `Evenement` de l'agenda (visibilité membres/interne) — pas de duplication.

### 8.3 Votes / pouvoirs / quorum — **dès la v1**

**Résolutions**
- Vote résolution par résolution.
- Type de majorité : simple / qualifiée (ex. 2/3) / unanimité.
- Résultat (pour / contre / abstention), adoptée oui/non (calculé).
- Lien optionnel vers le sujet dont découle la résolution.

**Pouvoirs / procurations**
- Mandant (absent) → mandataire (présent).
- **Contrôle du nombre max de pouvoirs par personne** (selon statuts).

**Présences / quorum**
- Statut par membre : présent / excusé / représenté / absent.
- **Calcul automatique du quorum** (décision : **oui, important**).
- Quorum atteint = (présents + représentés) ≥ seuil statutaire.

### 8.4 Paramètres de gouvernance (configurables dans l'admin)

Aucune règle statutaire codée en dur. Objet de configuration éditable :

- `vote_réservé_aux_membres_à_jour` : **à paramétrer selon les statuts** (valeur par défaut prudente en attendant)
- `max_pouvoirs_par_personne` (ex. 2)
- `quorum_AG_ordinaire` (ex. 1/3)
- `quorum_AG_extraordinaire` (ex. 1/2)
- `majorité_simple` (> 50 %)
- `majorité_qualifiée` (ex. 2/3)

**Règle de cohérence** : le droit de vote est **figé à la date de l'AG** (état enregistré au moment de la tenue), jamais recalculé rétroactivement.

**Lien inter-modules** : le droit de vote peut croiser automatiquement l'**adhésion à jour** (module budget), selon le paramètre ci-dessus.

---

## 9. Module Documents / GED

- Arborescence **dossiers / sous-dossiers** infinie (modèle `Dossier` auto-référent + `Document`).
- Gérée via django-treebeard / django-mptt.
- Sert aussi à la **vie associative** : statuts, PV d'AG, déclarations préfecture, récépissés.
- **Versionnement** souhaitable (conserver les anciennes versions, ex. des statuts) + date de validité.
- Une vraie interface « explorateur de fichiers » (glisser-déposer) prévue à terme ; l'admin suffit au démarrage.
- **Sécurité** : documents privés servis par une vue authentifiée qui vérifie les droits — jamais d'URL publique devinable ; stockage hors racine web publique.

---

## 10. Sécurité (dès le départ)

**Acquis Django par défaut** : protections CSRF, XSS, injection SQL (via l'ORM et les templates).

**À verrouiller activement :**
- Mots de passe : validation de robustesse + hachage **Argon2**.
- **2FA** (django-otp) au moins pour admin/bureau.
- Sessions : expiration, déconnexion sur inactivité, cookies `Secure` + `HttpOnly` + `SameSite`.
- Anti-brute-force : **django-axes**.
- **Autorisation stricte / anti-IDOR** : filtrer chaque requête par l'utilisateur connecté.
- **HTTPS** partout + HSTS + redirection HTTP→HTTPS.
- En-têtes : CSP, X-Content-Type-Options, Referrer-Policy (django-csp).
- `DEBUG = False` en prod ; `SECRET_KEY` et identifiants en **variables d'environnement**, jamais dans Git.
- **Fichiers uploadés** : validation type réel + taille ; service via vue authentifiée ; stockage hors racine publique.
- **Sauvegardes** chiffrées et testées (base + fichiers, stockées ailleurs).
- Mises à jour des dépendances ; **pip-audit**.
- **Journal d'audit** (qui a fait quoi) — django-simple-history ou LogEntry.

---

## 11. Accessibilité (cible : RGAA / WCAG 2.1 AA)

**Accessibilité de fond (priorité) :**
- HTML sémantique (`<nav>`, `<main>`, `<button>`, titres hiérarchisés).
- Navigation clavier complète, focus visible, pas de piège clavier.
- **Textes alternatifs** : `alt` obligatoire à l'upload (imposé dans le modèle `Media`).
- Formulaires accessibles (labels liés, erreurs explicites annoncées).
- Contrastes WCAG AA (4,5:1 texte normal).
- ARIA uniquement quand nécessaire, avec parcimonie.

**Options d'affichage (panneau d'accessibilité, icône flottante) :**
- Taille du texte (plusieurs niveaux, en `rem`).
- Mode fort contraste / mode sombre.
- Espacement augmenté (interlignage, lettres).
- Police adaptée (option lisible / dyslexie).
- Réduction des animations (+ respect automatique de `prefers-reduced-motion`).
- Liens d'évitement (« aller au contenu principal »).

Gestion via **variables CSS** basculées par une classe sur `<html>`, préférences mémorisées.

**Méthode** : tester tôt avec NVDA / VoiceOver + axe DevTools / Lighthouse.

---

## 12. Responsive & mobile

- **Mobile-first** : concevoir d'abord pour petit écran, enrichir ensuite.
- Une seule base de code (pas de site mobile séparé).
- **Unités relatives** partout (`rem`, `%`) — cohérent avec le réglage de taille de texte.
- Points de bascule indicatifs : téléphone <640 px, tablette 640–1024, ordinateur >1024.
- **Zones tactiles** ≥ ~44×44 px, espacées.
- Contenu reformaté en **une colonne** au zoom 200 % sans débordement.
- Actions importantes atteignables au pouce (zone basse).
- Tester sur **VoiceOver (iOS)** et **TalkBack (Android)**, sur de vrais téléphones.

**Écrans à traiter spécifiquement :**
- Agenda : **vue liste par défaut sur mobile**, vue mois simplifiée et tactile.
- Tableaux denses (budget, factures) : lignes en **cartes empilées** ou défilement horizontal avec 1re colonne figée (surtout back-office, compromis acceptable).
- Formulaires : un champ par ligne, claviers adaptés, labels visibles, formulaires longs découpés en étapes.
- Panneau d'accessibilité atteignable au pouce, plein écran sur mobile.

---

## 13. Conformité RGPD

- Page **politique de confidentialité**.
- **Consentement** explicite et horodaté sur les formulaires.
- **Durées de conservation** définies.
- **Droit d'accès** : export de toutes les données d'une personne.
- **Droit à l'effacement** : anonymisation/suppression — avec articulation aux **obligations comptables** (conservation des pièces : anonymiser plutôt que supprimer quand nécessaire).
- Registre des traitements.

---

## 14. Infrastructure & déploiement

### Hébergement
- **VPS Infomaniak** (gamme **VPS Cloud** recommandée, ex. VPS Cloud S : 4 vCPU / 12 Go / 250 Go NVMe).
- Distribution : **Ubuntu LTS** ou **Debian stable**.
- Datacenters en Suisse (nLPD, hors Cloud Act) — atout RGPD/souveraineté.
- IPv4 + IPv6 dédiées, bande passante illimitée, SLA 99,99 %.
- Ressources ajustables à la demande (démarrer petit, monter si besoin).

### Stack serveur
```
Internet → Nginx (HTTPS, statiques, reverse proxy)
         → Gunicorn (socket Unix) → Django
         → PostgreSQL (même machine au départ)
```
- **Nginx** : terminaison HTTPS, service des fichiers statiques et médias publics, reverse proxy vers Gunicorn.
- **Gunicorn** : serveur d'application, géré par **systemd** (`asso.service`), redémarrage auto.
- **PostgreSQL** : sur la même machine en v1.
- **Certbot / Let's Encrypt** : certificat HTTPS gratuit, renouvellement automatique.
- **Pare-feu** : ouvrir 80, 443, 22 uniquement.
- **WeasyPrint** : installer les dépendances système (Pango, etc.).

### Fichiers privés
- Documents sensibles (factures, reçus fiscaux, pièces membres) servis via **X-Accel-Redirect** (Nginx) ou une vue Django contrôlant les droits — jamais d'URL publique devinable, stockage hors racine web.

### Déploiement automatique — **webhook + script sur le VPS** (dépôt sur **GitHub**)
- À chaque push sur `main`, GitHub appelle un **webhook** exposé en HTTPS par Nginx (`/webhook`).
- Un **récepteur** (`webhook_receiver.py`, service `asso-webhook.service`) vérifie la **signature HMAC-SHA256** (secret partagé) avant tout traitement, puis lance `deploy.sh`.
- `deploy.sh` : `git reset --hard origin/main` → dépendances (si `requirements.txt` changé) → `migrate` → `collectstatic` → `check --deploy` → redémarrage de Gunicorn, le tout **journalisé**.
- Le secret du webhook et les variables d'app (`SECRET_KEY`, base, `DEBUG=False`) sont dans des **fichiers d'environnement protégés** (chmod 600), **jamais dans Git**.
- `systemctl restart` autorisé au compte `deploy` via une **règle sudoers restreinte** (uniquement ce service).

> Fichiers fournis : `deploy.sh`, `webhook_receiver.py`, `asso.service`, `asso-webhook.service`, `backup.sh`.

### Sauvegardes — **externalisées dès le départ**
- `backup.sh` planifié par **cron** (quotidien) : `pg_dump` compressé + archive des médias.
- **Copie hors VPS obligatoire** : envoi vers **Swiss Backup** (ou autre stockage distinct), p. ex. via `rclone`. Un snapshot Infomaniak ne remplace pas une sauvegarde externalisée.
- Rétention locale limitée (purge auto) + rétention distante.
- **Tester la restauration** régulièrement (une sauvegarde jamais restaurée n'en est pas une).

### Maintenance (responsabilité de l'équipe — un VPS n'est pas managé)
- Mises à jour de sécurité du système et des dépendances (`pip-audit`).
- Surveillance des logs (déploiement, Gunicorn, Nginx, webhook).
- Renouvellement des certificats (auto via Certbot, à vérifier).

---

## 15. Découpage en versions

**v1 (cœur)**
Front public + espace membre + admin avec : cœur associatif, agenda (modération + visibilités), médias (alt obligatoire), GED (+ statuts), facturation, budget + adhésions, exports compta + bilan, gouvernance complète (carnet, réunions, présences, pouvoirs, résolutions, quorum auto paramétrable), reçus fiscaux, permissions fines, RGPD, sécurité, sauvegardes, accessibilité, responsive mobile-first.

**v2 (ultérieur)**
Espace membre enrichi, relances automatiques (adhésions/factures en retard), interfaces sur mesure (explorateur de fichiers, éditeur de facture, tableau de bord budget avec graphiques).

**v3 (plus tard)**
Newsletter / envoi groupé, billetterie / inscription aux spectacles, gestion des bénévoles / plannings.

> Concevoir les modèles v1 en gardant v2/v3 en tête, mais ne coder que la v1 d'abord.

---

## 16. Domaines de données (vue d'ensemble)

| Domaine | Modèles principaux |
|---|---|
| Cœur | Membre, Lieu |
| Spectacle / Projet | Spectacle (type_portage, statut_projet, statut_modération), LigneDistribution |
| Agenda | Evenement (statut, visibilité, affiche, galerie, intervenants, spectacle) |
| Médias | Media (alt obligatoire) |
| GED | Dossier (auto-référent), Document (versionné) |
| Facturation | Client, Devis, LigneDevis, Facture, LigneFacture |
| Budget | Adhesion, Saison, Transaction, Categorie |
| Gouvernance | Sujet, Reunion, Resolution, Pouvoir, Presence, ParamètresGouvernance |

> Liens inter-modules : agenda ↔ médias ↔ spectacles ; gouvernance ↔ GED ↔ adhésions ; espace membre agrège ce qui concerne chaque personne, sans duplication.

---

## 17. Prochaine étape

Génération du **`models.py` de la v1**, structuré par domaines, prêt à `migrate`, pour obtenir un back-office Django fonctionnel et itérer dessus.
