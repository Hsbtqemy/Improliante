# CLAUDE.md

Contexte et règles de travail pour Claude Code sur ce dépôt.
Ce fichier est court par nature : il **oriente**. Le détail fonctionnel complet
vit dans `docs/cahier-des-charges-asso.md` — s'y référer pour toute question métier.

> État du projet : **v1 fonctionnelle implémentée** (modèles, services, front
> public, espace membre, back-office). ~400 tests pytest verts, `ruff` propre,
> `manage.py check` et `check --deploy` passent. Carte détaillée des modules et
> des conventions transverses → `docs/etat-implementation.md`.
> **Reste à faire** : le déploiement VPS (fichiers prêts dans `deploiement/`).

---

## Le projet en bref

Application web pour une association de spectacle vivant, à trois faces partageant une base :
- **Front public** : présentation (asso, membres, spectacles/projets), agenda, galerie, contact.
- **Espace membre** (connecté) : statut d'adhésion, reçus fiscaux, documents, convocations, propositions.
- **Back-office** (rôles) : documents/GED, facturation, budget, gouvernance (AG).

Priorité du projet : **sur-mesure et flexible**. Détails → `docs/cahier-des-charges-asso.md`.

---

## Stack (décidée)

- **Backend** : Django + Django REST Framework
- **Base de données** : PostgreSQL
- **Front public** : rendu serveur privilégié (templates Django, ou Astro/Next.js SSR) — **pas** de SPA lourde (performance mobile + accessibilité)
- **PDF** : WeasyPrint (devis, factures, reçus fiscaux) · **Excel** : openpyxl
- **Arbres** (dossiers GED) : django-treebeard ou django-mptt
- **Permissions objet** (si besoin) : django-guardian
- **Dépôt** : monodépôt (back + front ensemble)

---

## Arborescence

```
/
├── config/                 # projet Django (settings, urls, wsgi)
├── apps/
│   ├── common/             # abstraits (Horodatage, Moderation) + services transverses :
│   │                       #   moderation.py, fichiers.py, stockage.py, pdf.py
│   ├── coeur/              # Utilisateur, Membre, Lieu, ParametresAssociation,
│   │                       #   Signataire ; roles.py (est_bureau, bureau_requis)
│   ├── spectacles/         # Spectacle, LigneDistribution, ImageSpectacle
│   ├── agenda/             # Evenement, Intervention, ImageEvenement
│   ├── medias/             # Media (alt obligatoire)
│   ├── documents/          # Dossier (arbre treebeard), Document ; services.py (versions)
│   ├── facturation/        # Client, Devis, Facture (+ avoir), lignes ; services.py
│   │                       #   (valider_facture, avoirs, PDF devis/facture)
│   ├── budget/             # Adhesion, Saison, Transaction, Categorie, RecuFiscal ;
│   │                       #   services.py (emettre_recu, bilan_par_categorie) ;
│   │                       #   graphiques.py (séries du tableau de bord, sans calcul)
│   ├── gouvernance/        # Sujet, Reunion, Resolution, Pouvoir, Presence, Parametres
│   │                       #   ; services.py (quorum, résolutions)
│   ├── vitrine/            # front public : vues + urls, calendrier/ical, contact
│   ├── espace_membre/      # espace connecté : projets, événements, documents,
│   │                       #   convocations, reçus (anti-IDOR)
│   └── backoffice/         # 3e face bureau : modération, facturation, GED, budget
│                           #   (pas de modèle propre ; migration groupe « Bureau »)
├── front/                  # templates & assets (front public, espace membre,
│                           #   backoffice, gabarits PDF facture/devis/recu)
├── docs/
│   ├── cahier-des-charges-asso.md   # cadrage fonctionnel (référence métier)
│   └── etat-implementation.md       # carte des modules + conventions transverses
├── deploiement/            # deploy.sh, webhook_receiver.py, *.service, nginx-*.conf, backup.sh
├── ruff.toml · pytest.ini · config/settings_test.py   # qualité & tests
├── requirements.txt
└── CLAUDE.md
```

Découpage en **apps Django par domaine métier** — une app par module du cahier des charges.
Chaque app vit sous `apps/` et déclare `name = "apps.<nom>"` dans son `AppConfig`
(avec un `verbose_name` en français). Le package projet s'appelle `config`
(imposé par `deploiement/asso.service` → `config.wsgi:application`).

---

## Conventions de nommage

**Métier en français, technique en anglais.**
- **Modèles, champs, choix métier → français** : `class Spectacle`, `class Adhesion`, champs `statut`, `date_debut`, `type_portage`, `montant_verse`. Les valeurs de choix métier en français (`"en_creation"`, `"a_l_affiche"`).
- **Noms d'apps → français métier**, choix assumé (`coeur`, `spectacles`, `agenda`, `facturation`, `budget`, `gouvernance`…).
- **Ossature technique → anglais** : méthodes, helpers, variables locales et fonctions non-métier (`get_queryset`, `save`, `is_valid`, `total`, `count`).
- **Pas d'accents ni d'espaces** dans les identifiants Python (`adhesion` et non `adhésion`).
- Cohérence avant tout : dans le doute, suivre le motif déjà présent dans le fichier voisin.

---

## Règles de vigilance NON NÉGOCIABLES

Ces règles découlent du cahier des charges et doivent être respectées dans tout code produit.

1. **Anti-IDOR (autorisation)** : dans l'espace membre, **toujours** filtrer les requêtes par l'utilisateur connecté (`.filter(membre=request.user.membre)`), jamais faire confiance à un ID d'URL sans revérifier la propriété. Vaut aussi pour l'édition d'un projet perso (le membre n'édite que *ses* spectacles).
2. **`alt` obligatoire sur les médias** : le modèle `Media` impose un texte alternatif à l'upload (accessibilité). Pas de média sans `alt`.
3. **Secrets hors Git** : `SECRET_KEY`, identifiants base, secret du webhook → variables d'environnement / fichiers `.env` non versionnés. Jamais en clair dans le code.
4. **Numérotation des factures** : séquentielle, continue, sans trou, attribuée **à la validation** (pas à la création du brouillon). Contrainte légale.
5. **Fichiers privés** (factures, reçus, docs membres) : servis via vue authentifiée contrôlant les droits (ou X-Accel-Redirect), jamais par URL publique devinable.
6. **`DEBUG = False`** en production ; `manage.py check --deploy` doit passer.
7. **Modération** : agenda, sujets de gouvernance et fiches de projets perso suivent le cycle `brouillon → proposé → publié/refusé`. Même logique réutilisée partout. **Nuance décidée** : une fiche **publiée reste éditable par son auteur** (un spectacle évolue) — la retouche part en ligne **immédiatement** et lève le drapeau `modifie_apres_publication` pour un **contrôle a posteriori** du bureau (file « à revoir »). Seul l'état **« proposé »** verrouille l'auteur, le temps du contrôle initial. La **visibilité** reste réglée par le bureau. Voir `apps/common/moderation.py` (`ETATS_MODIFIABLES_PAR_AUTEUR`, `signaler_modification_apres_publication`, `marquer_revu`).
8. **Règles statutaires paramétrables** (quorum, majorités, max pouvoirs, vote lié à la cotisation) : dans un objet de configuration éditable en admin, **jamais codées en dur**.
9. **Accessibilité (RGAA/WCAG AA)** et **responsive mobile-first** : HTML sémantique, unités relatives, contrastes AA. À garder présent dans tout code front.

---

## Périmètre v1 vs plus tard

- **v1** = tous les modules ci-dessus (voir cahier des charges §15).
- **v2/v3** (ne pas coder sans demande explicite) : relances auto, interfaces sur mesure (explorateur de fichiers, éditeur de facture), newsletter, billetterie, bénévoles.
- **Fait, sur demande** : le *tableau de bord budget* de cette liste (fiche `pilotage/BUD-1.md`). Le reste attend une demande.

Concevoir les modèles v1 en gardant v2/v3 possibles, mais **ne coder que la v1**.

---

## Déploiement (rappel)

- VPS Infomaniak · Nginx + Gunicorn (systemd) + PostgreSQL + Certbot.
- Déploiement auto : push sur `main` → webhook GitHub (signé HMAC) → `deploiement/deploy.sh` sur le VPS.
- Sauvegardes externalisées (Swiss Backup) dès le départ.
- Détails et fichiers → dossier `deploiement/` et cahier des charges §14.

---

## Commandes

> Dev : un `venv/` local (gitignoré). `django-admin` n'est pas sur le PATH →
> utiliser `python -m django`. En dev, définir `DJANGO_DEBUG=1` (sinon la
> `SECRET_KEY` est exigée). `makemigrations` et `check` marchent hors-ligne ;
> `migrate` / `runserver` exigent un PostgreSQL joignable.

```bash
# Environnement
python -m venv venv
source venv/bin/activate          # Windows : venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # renseigner DJANGO_SECRET_KEY / DB_* (ou DJANGO_DEBUG=1)

# Base & développement (PostgreSQL requis)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# Migrations
python manage.py makemigrations
python manage.py migrate

# Statiques (avant déploiement)
python manage.py collectstatic --noinput

# Vérification pré-déploiement
python manage.py check --deploy

# Tests (pytest + pytest-django ; base SQLite en mémoire, hors-ligne)
pytest -q

# Tests sur le MOTEUR DE PRODUCTION (PostgreSQL joignable requis).
# Seul moyen d'éprouver `select_for_update`, donc la numérotation légale sous
# concurrence : sous SQLite ce verrou ne fait rien et les deux tests dédiés
# se déclarent « skipped » plutôt que de passer sans rien prouver.
createdb asso_test && TEST_POSTGRES=1 pytest -q

# Garde de pré-push : à faire UNE FOIS par clone. Le hook (deploiement/hooks/pre-push)
# rejoue la suite sur PostgreSQL avant que le push ne parte — donc avant que le
# webhook ne déclenche le déploiement. Sans lui, les trois tests de concurrence
# ne tournent jamais et le push part quand même.
git config core.hooksPath deploiement/hooks

# Lint / format (ruff)
ruff check .
ruff format .
```

---

## Comment travailler ici

- Avant d'implémenter un module, **lire la section correspondante** du cahier des
  charges, et consulter `docs/etat-implementation.md` pour les conventions déjà en place.
- Respecter le découpage par apps métier ; ne pas mélanger les domaines.
- **Logique métier dans un `services.py`**, pas dans les vues/routes (les vues
  orchestrent et donnent le retour utilisateur). Zones à risque **test-first**
  (numérotation légale, quorum, versionnement, anti-IDOR).
- **Autorisation bureau** : toujours via `apps/coeur/roles.py` (`@bureau_requis`,
  `est_bureau`), jamais un `is_staff` brut dans une vue.
- Produire des migrations à chaque changement de modèle.
- Faire passer `pytest`, `ruff check` et `manage.py check` avant de committer.
- Signaler (sans le coder) tout écart ou décision manquante plutôt que de supposer en silence.

---

## Pilotage (journal de bord)

Le reste à faire vit dans `pilotage/`, confronté à ce que git montre par l'outil
`pilote`. Un chantier a un fichier `pilotage/<CODE>.md` ; une QA visuelle est une
passe rejouable dans `pilotage/qa/<nom>.md`. Le gabarit et le contrat de lecture sont
dans `pilotage/_TEMPLATE.md`, l'inventaire du dépôt dans `pilotage/journal.config.mjs`.

**Codes de chantier : `PREFIXE-N`, le préfixe nommant un domaine** — `DEP` (déploiement),
`VIT` (vitrine), `MEM` (espace membre), `BO` (back-office), `FAC` (facturation),
`GOU` (gouvernance), `GED` (documents/médias), `BUD` (budget), `SEC` (sécurité).
Un préfixe de 1 à 4 majuscules, un numéro de 1 à 3 chiffres, et rien d'autre : l'outil
ne reconnaît pas les autres formes.

IMPORTANT — respecter exactement `## Reste` et les H3 de zone : l'outil ne lit que
ces sections.

- Fin de session : mettre à jour le `Reste` du chantier travaillé.
- `statut:` se prend dans `à venir` · `interrompu` · `différé` · `clos` · `livré` ·
  `abandonné`, et rien d'autre — le contrôleur refuse le reste. `différé` = mis en
  attente exprès (autre chose doit aboutir d'abord), à distinguer d'`interrompu` =
  arrêté en plein travail. `abandonné` = décidé de ne pas le faire : fermé mais pas
  fait, et la fiche garde son `Reste` ouvert exprès plutôt que d'être supprimée avec
  son raisonnement. `livré` est démenti par l'écran si le dernier commit ne vit pas
  sur `origin/main`.
- **Le commit de code doit CITER le code du chantier**, dans son sujet ou son corps :
  `feat(deploiement): DEP-1 — unité systemd Gunicorn + socket`. Un chantier n'est daté
  que par les commits qui le citent ET qui touchent autre chose que `pilotage/` — les
  deux à la fois. Sans citation, la fiche affiche `0 commit`, aucune date, aucune barre
  sur la fresque, quel que soit le travail fait.
- Le commit de code d'abord, le commit de fiche ensuite, **séparément** : une fiche ne
  peut pas citer le commit qui la met à jour, et les commits qui ne touchent que
  `pilotage/` sont exclus du datage.
- Une case = une affirmation vérifiable, avec son attendu. « Vérifier le rendu » ne se
  coche pas ; « sur 375 px, la barre ne masque pas le geste » se coche.
- Avant de clore une session : `npx github:Hsbtqemy/pilote verifier` (code de retour
  non nul = l'outil lira mal le dossier ; `--strict` rend les avertissements bloquants).
- QA visuelle : écrire une passe dans `pilotage/qa/`, jamais dans le fil de
  conversation. Regrouper les points par zone en H3.
- Ne jamais cocher soi-même une case d'une passe de QA : l'agent la rédige, l'humain coche.
- Ne pas créer de fiche pour un point traité en un seul commit.

Le journal se lit avec `npx github:Hsbtqemy/pilote` puis `localhost:4123` — la commande
est idempotente, se retaper sans vérifier si un serveur tourne est le geste prévu
(`pilote arreter` ferme, `pilote aide` liste tout). Lecture seule sur le dépôt, sauf les
cases à cocher, dont l'écriture est bornée à `pilotage/`.
