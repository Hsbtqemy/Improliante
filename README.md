# Site & back-office — Association de spectacle vivant

Application web Django (front public + espace membre + back-office) pour une
association de spectacle vivant. Priorité : **sur-mesure et flexible**.

- Cadrage fonctionnel complet : [docs/cahier-des-charges-asso.md](docs/cahier-des-charges-asso.md)
- Règles de travail et conventions : [CLAUDE.md](CLAUDE.md)

> **État : amorçage.** La structure Django est en place ; les modèles ne sont
> pas encore codés.

## Stack

Django 6 + Django REST Framework · PostgreSQL · templates Django (rendu
serveur) · WeasyPrint (PDF) · openpyxl (Excel). Déploiement : VPS Infomaniak,
Nginx + Gunicorn (systemd) + PostgreSQL, déploiement auto par webhook GitHub.

## Arborescence

```
config/         projet Django (settings, urls, wsgi, asgi)
apps/           apps métier, une par domaine
  ├── coeur/          Membre, Lieu
  ├── spectacles/     Spectacle, LigneDistribution
  ├── agenda/         Evenement
  ├── medias/         Media (alt obligatoire)
  ├── documents/      Dossier (arbre), Document
  ├── facturation/    Client, Devis, Facture, lignes
  ├── budget/         Adhesion, Saison, Transaction, Categorie
  └── gouvernance/    Sujet, Reunion, Resolution, Pouvoir, Presence, Parametres
front/          templates & assets du front public
docs/           cahier des charges
deploiement/    deploy.sh, webhook_receiver.py, *.service, backup.sh
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
