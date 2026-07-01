# CLAUDE.md

Contexte et règles de travail pour Claude Code sur ce dépôt.
Ce fichier est court par nature : il **oriente**. Le détail fonctionnel complet
vit dans `docs/cahier-des-charges-asso.md` — s'y référer pour toute question métier.

> État du projet : **squelette en place**. Projet Django `config` + 8 apps
> métier sous `apps/` créés ; `manage.py check` et `check --deploy` passent.
> **Les modèles ne sont pas encore codés** (`models.py` vides, placeholders).
> Prochaine étape : coder les modèles domaine par domaine (cf. cahier §17).

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

## Arborescence (en place, à étoffer au fil de l'eau)

```
/
├── config/                 # projet Django (settings, urls, wsgi)
├── apps/
│   ├── coeur/              # Membre, Lieu
│   ├── spectacles/         # Spectacle, LigneDistribution
│   ├── agenda/             # Evenement
│   ├── medias/             # Media (alt obligatoire)
│   ├── documents/          # Dossier (arbre), Document
│   ├── facturation/        # Client, Devis, Facture, lignes
│   ├── budget/             # Adhesion, Saison, Transaction, Categorie
│   └── gouvernance/        # Sujet, Reunion, Resolution, Pouvoir, Presence, Parametres
├── front/                  # templates / assets front public (ou app front dédiée)
├── docs/
│   └── cahier-des-charges-asso.md
├── deploiement/            # deploy.sh, webhook_receiver.py, *.service, backup.sh
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
7. **Modération** : agenda, sujets de gouvernance et fiches de projets perso suivent le cycle `brouillon → proposé → publié/refusé`. Même logique réutilisée partout.
8. **Règles statutaires paramétrables** (quorum, majorités, max pouvoirs, vote lié à la cotisation) : dans un objet de configuration éditable en admin, **jamais codées en dur**.
9. **Accessibilité (RGAA/WCAG AA)** et **responsive mobile-first** : HTML sémantique, unités relatives, contrastes AA. À garder présent dans tout code front.

---

## Périmètre v1 vs plus tard

- **v1** = tous les modules ci-dessus (voir cahier des charges §15).
- **v2/v3** (ne pas coder sans demande explicite) : relances auto, interfaces sur mesure (explorateur de fichiers, éditeur de facture, dashboard budget), newsletter, billetterie, bénévoles.

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

# Tests (à définir : pytest ou manage.py test)
# python manage.py test
```

---

## Comment travailler ici

- Avant d'implémenter un module, **lire la section correspondante** du cahier des charges.
- Respecter le découpage par apps métier ; ne pas mélanger les domaines.
- Produire des migrations à chaque changement de modèle.
- Signaler (sans le coder) tout écart ou décision manquante plutôt que de supposer en silence.
