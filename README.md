# Site & back-office — Association de spectacle vivant

Application web Django (front public + espace membre + back-office) pour une
association de spectacle vivant. Priorité : **sur-mesure et flexible**.

- Cadrage fonctionnel complet : [docs/cahier-des-charges-asso.md](docs/cahier-des-charges-asso.md)
- Carte de l'implémentation et conventions : [docs/etat-implementation.md](docs/etat-implementation.md)
- Règles de travail : [CLAUDE.md](CLAUDE.md)

> **État : v1 fonctionnelle implémentée** (front public, espace membre,
> back-office). ~168 tests pytest verts. Reste le déploiement VPS.

## Stack

Django 6 + Django REST Framework · PostgreSQL · templates Django (rendu
serveur) · WeasyPrint (PDF) · openpyxl (Excel) · django-treebeard (arbres GED).
Déploiement : VPS Infomaniak, Nginx + Gunicorn (systemd) + PostgreSQL,
déploiement auto par webhook GitHub.

## Arborescence

```
config/         projet Django (settings, urls, wsgi, asgi)
apps/           apps métier, une par domaine
  ├── common/         abstraits + services transverses (moderation, fichiers privés, pdf)
  ├── coeur/          Utilisateur, Membre, Lieu, ParametresAssociation, Signataire, rôles
  ├── spectacles/     Spectacle, LigneDistribution
  ├── agenda/         Evenement
  ├── medias/         Media (alt obligatoire)
  ├── documents/      Dossier (arbre), Document + versionnement
  ├── facturation/    Client, Devis, Facture, avoirs, lignes, numérotation légale
  ├── budget/         Adhesion, Saison, Transaction, Categorie, RecuFiscal, bilan
  ├── gouvernance/    Sujet, Reunion, Resolution, Pouvoir, Presence, Parametres
  ├── vitrine/        front public (vues, urls, agenda/ical, contact)
  ├── espace_membre/  espace connecté (anti-IDOR)
  └── backoffice/     3e face bureau (modération, facturation, GED, budget)
front/          templates & assets (front, espace membre, back-office, PDF)
docs/           cahier des charges + état d'implémentation
deploiement/    deploy.sh, webhook_receiver.py, *.service, nginx-*.conf, backup.sh
```

## Démarrage (développement)

Prérequis : Python 3.11+ et un serveur PostgreSQL local.

```bash
python -m venv venv
source venv/bin/activate          # Windows : venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # puis renseigner DB_PASSWORD, etc.

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver        # http://127.0.0.1:8000/admin/
```

## Vérification pré-déploiement

```bash
python manage.py check --deploy   # doit passer, DEBUG=False en production
```
