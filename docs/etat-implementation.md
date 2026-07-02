# État d'implémentation

Carte des modules livrés et des **conventions transverses** à respecter pour
toute nouvelle contribution. Le cadrage fonctionnel de référence reste
`docs/cahier-des-charges-asso.md` ; ce document décrit ce qui *existe* et *comment
c'est structuré*.

> État : **v1 fonctionnelle complète**, ~168 tests pytest. Reste le déploiement
> VPS (fichiers dans `deploiement/`).

---

## Les trois faces

### Front public (`apps/vitrine`)
Accueil, spectacles (liste filtrable + détail), agenda (liste + calendrier +
export iCal), galerie, page association + fiches membres visibles, contact
(honeypot anti-spam + consentement RGPD ; envoi e-mail **non activé**, messages
persistés en base). Panneau d'accessibilité (préférences en cookie, classes
appliquées sur `<html>`, JS externe sans inline).

### Espace membre (`apps/espace_membre`) — connecté
Tableau de bord (adhésions), **proposer/éditer son projet** (spectacle),
**proposer/éditer un événement**, consulter ses **documents**, ses
**convocations/CR d'AG**, ses **reçus fiscaux**. Tout est filtré par le membre
connecté (voir *Anti-IDOR*).

### Back-office (`apps/backoffice`) — bureau
3ᵉ app métier (sans modèle propre), **interface sur-mesure** (templates sur
`base.html`, pas l'admin Django) : **tableau de bord** (compteurs + accès
rapides), **modération** (valider/refuser projets et événements, fixer la
visibilité), **devis** (→ transformation en facture), **factures** (brouillon →
validation numérotée → PDF ; **aperçu** brouillon ; **avoir**), **reçus
fiscaux** (Cerfa, aperçu avant émission), **GED** (arbre de dossiers, dépôt,
versionnement), **budget** (mouvements + bilan par catégorie + export Excel),
**gouvernance** (réunions/AG : quorum, ordre du jour, présences avec
préremplissage des droits de vote, pouvoirs, résolutions avec résultat),
**réglages** (paramètres de l'association, équipe = groupe « Bureau »). Listes
filtrables et paginées.

> L'admin Django (`/admin/`) reste disponible en parallèle pour la config rare
> et les CRUD techniques non couverts par un écran sur-mesure.

---

## Conventions transverses (à suivre absolument)

### Couche services
La logique métier vit dans un `services.py`, **pas dans les vues** (qui
orchestrent et rendent le retour utilisateur). Points d'entrée notables :
- `apps/common/moderation.py` : `soumettre_a_moderation`, `valider`, `refuser`.
- `apps/facturation/services.py` : `valider_facture` (numéro légal),
  `creer_avoir`, `transformer_en_facture`, `numeroter_devis`, rendus PDF.
- `apps/budget/services.py` : `emettre_recu`, `bilan_par_categorie`, PDF Cerfa.
- `apps/documents/services.py` : `remplacer_document` (versionnement).

### Rôles & autorisation bureau
`apps/coeur/roles.py` est la **seule** porte : `est_bureau(user)` (groupe Django
« Bureau » **ou** `is_staff`/superuser, compte actif) et le décorateur
`@bureau_requis`. Ne jamais remettre un `is_staff` brut dans une vue. Le groupe
« Bureau » est créé par `apps/backoffice/migrations/0001`. `est_bureau` est
exposé aux gabarits par `apps.backoffice.context_processors.roles`.

### Anti-IDOR (espace membre)
Propriété vérifiée **par objet**, jamais par id d'URL nu :
- projets : `get_object_or_404(Spectacle, pk=pk, porteurs=membre)` ;
- événements / documents / reçus : filtre `cree_par=request.user` ou `membre=`.
- Ressource interdite → **404** (pas 403), pour ne pas révéler son existence.
- Champs sensibles verrouillés dans les formulaires membres (`type_portage`
  restreint, `visibilite` non exposée, `spectacle` limité aux projets du membre).

### Fichiers privés
Hors racine web (`apps/common/stockage.py::StockagePrive` →
`settings.MEDIA_PRIVE_ROOT`), servis uniquement par une vue authentifiée
contrôlant les droits, via `apps/common/fichiers.py::reponse_fichier_prive`
(X-Accel-Redirect en prod — cf. `deploiement/nginx-improliante.conf` ;
`FileResponse` en dev). Concerne documents, reçus, factures, images de signature.

### Documents PDF (WeasyPrint)
`apps/common/pdf.py::html_vers_pdf` importe WeasyPrint **paresseusement** (libs
natives requises seulement au rendu, sur le VPS). Les documents légaux (facture,
reçu) rendent leur PDF au 1ᵉʳ téléchargement puis le **mettent en cache** (privé,
immuable) ; devis rendu à la volée. Un **signataire** optionnel
(`coeur.Signataire`, image en base64) peut être apposé.

### Numérotation légale
`valider_facture` attribue un numéro **séquentiel, continu, sans trou** à la
validation, sous verrou (`select_for_update`) dans une transaction. Séquence
partagée facture/avoir (préfixe `F`/`A`). Idem `emettre_recu` (préfixe `R`).
Les devis sont numérotés plus souplement (préfixe `D`, sans criticité légale).
> Nuance de test : SQLite rend `select_for_update` inopérant ; les tests
> valident les règles fonctionnelles, la sûreté concurrentielle repose sur
> PostgreSQL.

### Cycle de modération
`brouillon → proposé → publié / refusé` (mixin `apps.common.models.Moderation`),
réutilisé pour spectacles et événements. Le membre propose ; le bureau
valide/refuse (avec motif). Transitions gardées dans le service.

### Configuration paramétrable (jamais en dur)
Singletons éditables en admin : `coeur.ParametresAssociation` (identité légale
pour les documents), `gouvernance.ParametresGouvernance` (quorum, majorités,
pouvoirs). `coeur.Signataire` (référentiel de signataires habilités/délégataires).

---

## Qualité & tests

- **pytest + pytest-django** ; base SQLite en mémoire (`config/settings_test.py`),
  médias dans un dossier temporaire. `pytest -q`.
- **ruff** (`ruff.toml`, ligne 100, migrations exclues) : `ruff check .` / `ruff format .`.
- Le rendu PDF est **mocké** dans les tests (`html_vers_pdf` remplacé) : la suite
  tourne sans WeasyPrint.
- Zones traitées **test-first** : numérotation légale, quorum/résolutions,
  versionnement, anti-IDOR.

---

## Reste à faire

- **Déploiement VPS** : Nginx + Gunicorn (systemd) + PostgreSQL + Certbot +
  webhook GitHub. Installer les libs natives de WeasyPrint (`libpango`, `libcairo`,
  `libgdk-pixbuf`, `libffi`). Fichiers prêts dans `deploiement/`.
- Pistes v2/v3 (hors périmètre sans demande, cf. cahier §15) : relances
  automatiques, interfaces sur mesure (explorateur de fichiers, éditeur de
  facture, dashboard budget), newsletter, billetterie, gestion des bénévoles.
