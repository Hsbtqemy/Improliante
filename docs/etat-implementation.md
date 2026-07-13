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
Tableau de bord (à traiter, prochaines dates, projets), **proposer/éditer son
projet** (spectacle), **proposer/éditer un événement**, répondre à ses
**convocations/CR d'AG** (présence / pouvoir), ses **reçus fiscaux**, et gérer
tous ses **fichiers** dans un explorateur unifié (« Fichiers »). Tout est filtré
par le membre connecté (voir *Anti-IDOR*).

**Explorateur « Fichiers » à quatre branches.** Un seul écran (`espace_membre.
mes_fichiers`) présente quatre branches, portées par `Dossier.espace` +
`Dossier.visibilite` :
- **Perso** : `espace=PERSO`, `proprietaire=membre`, `visibilite=PRIVE` — à lui seul ;
- **Partagé** : `espace=COMMUN` (`proprietaire` NULL) — espace **collaboratif** :
  tout membre y lit ET écrit (détail `dossier_commun`, URL `espace/commun/`) ;
- **Bureau** : `espace=PERSO`, `proprietaire=membre`, `visibilite=BUREAU` — transmis
  au bureau (consultable en agrégat via `backoffice:fichiers_membres`) ;
- **Association** : `espace=ASSOCIATION` (`proprietaire` NULL) — documents officiels
  de l'asso. **Éditable par le bureau** (dossiers, dépôt avec `confidentialite`,
  **versionnement**, suppression) ; **lecture seule filtrée par confidentialité**
  pour les membres (détail `dossier_association`, URL `espace/association/`).

La **branche est choisie à la création** (bouton par branche ; création Association
réservée au bureau) ; un **sous-dossier hérite de la branche de sa racine**
(services `creer_dossier_membre` / `creer_dossier_commun` / `creer_dossier_association`).
La même `dossier_detail.html` sert les quatre branches, pilotée par `peut_ecrire`
(= `est_proprio` / `est_bureau`) + les noms d'URL et `avec_confidentialite`.

**Accès (helpers `apps/espace_membre/views.py`).** L'accès à un document suit
l'espace de son dossier : `PERSO` → `_peut_voir_dossier_membre` (Perso =
propriétaire seul, **bureau exclu** ; Bureau = propriétaire + bureau) ; `COMMUN` →
`_peut_voir_espace_commun` (tout membre) ; `ASSOCIATION`/non classé → par
`confidentialite` (`_documents_accessibles` : bureau tout, `PUBLIC`→connecté,
`MEMBRES`→membre, `PRIVE`→déposant). **Étanchéité** : chaque famille d'URL filtre
son espace (`get_object_or_404(..., espace=…)` → un pk d'un autre espace = 404) ;
l'écriture Association est gardée par `est_bureau` (POST non-bureau → 404).

### Back-office (`apps/backoffice`) — bureau
3ᵉ app métier (sans modèle propre), **interface sur-mesure** (templates sur
`base.html`, pas l'admin Django) : **tableau de bord** (compteurs + accès
rapides), **finances** (hub : porte d'entrée unique — chiffres clés facturation /
cotisations / **trésorerie** + tuiles « à traiter » vers les sections),
**modération** (valider/refuser projets et événements, fixer la
visibilité), **programmation** (gestion directe des **événements** et **projets** :
liste, création avec **publication immédiate** possible, édition de n'importe
quelle fiche même publiée, intervenants/distribution via formsets, porteurs en
cases à cocher, suppression — complète la modération ; la **mise en scène** n'a pas
de champ dédié : c'est une **ligne de distribution** au rôle libre « Mise en scène »),
**facturation** (un **écran unique à onglets** — Devis · Factures · Avoirs ·
Clients ; devis → transformation en facture ; facture brouillon → validation
numérotée → PDF ; **aperçu** ; **avoir**), **cotisations & reçus** (onglets
**adhésions** — par saison + statut + montants, personne choisie ou **créée à
la volée**, avec ou sans compte — et **reçus fiscaux** Cerfa),
**membres** (fiches ; création avec accès en ligne optionnel ; **ouverture
d'accès** a posteriori), **fichiers transmis** (agrégat en lecture des dossiers
que les membres marquent « transmis au bureau » ; la gestion documentaire
officielle est passée dans la branche **Association** de l'explorateur « Fichiers »),
**budget** (mouvements + bilan par catégorie + export Excel ; **trésorerie** =
solde en banque de référence saisi par le trésorier + prévisionnel = solde +
reste à réaliser du budget de la saison — repère de gestion à rapprocher des
comptes, pas une compta),
**gouvernance** (réunions/AG : quorum, ordre du jour, présences avec
préremplissage des droits de vote, pouvoirs, résolutions avec résultat ;
**compte-rendu en déroulé** — note/décision par point + **blocs de récit
libre** (`BlocCompteRendu`) intercalables (préambule, échanges, transitions) +
conclusion — et **génération du PV en PDF** reprenant présences/pouvoirs/quorum/
résolutions, déposé dans la GED via `gouvernance.services.generer_compte_rendu` ;
**édition de la réunion** — statut, convocation — hors admin),
**réglages** (paramètres de l'association, équipe = groupe « Bureau »). Listes
filtrables et paginées.

> L'admin Django (`/admin/`) reste disponible en parallèle pour la config rare
> et les CRUD techniques non couverts par un écran sur-mesure.

---

## Conventions transverses (à suivre absolument)

### Couche services
La logique métier vit dans un `services.py`, **pas dans les vues** (qui
orchestrent et rendent le retour utilisateur). Points d'entrée notables :
- `apps/common/moderation.py` : `soumettre_a_moderation`, `valider`, `refuser` ;
  `publier` (publication directe par le bureau, depuis n'importe quel état).
- `apps/common/fiches.py` : `ImagesFicheFormMixin` + `appliquer_images` — briques
  affiche/galerie mutualisées entre l'espace membre et le back-office (programmation).
- `apps/facturation/services.py` : `valider_facture` (numéro légal),
  `creer_avoir`, `transformer_en_facture`, `numeroter_devis`, rendus PDF.
- `apps/budget/services.py` : `emettre_recu`, `bilan_par_categorie`, PDF Cerfa ;
  `tresorerie` (solde en banque de référence + prévisionnel) ; `resume_cotisations`
  (chiffres du hub Finances). Facturation : `apps/facturation/services.py::resume_facturation`.
- `apps/coeur/services.py` : `creer_membre` (fiche seule, sans compte),
  `ouvrir_compte` (crée l'`Utilisateur` + lien d'activation), `synchroniser_compte`
  (recopie l'identité vers le compte sans toucher l'identifiant), `creer_compte_membre`
  (raccourci fiche + accès).
- `apps/documents/services.py` : `remplacer_document` (versionnement) ;
  `creer_dossier_membre`, `televerser_fichier_membre`, `modifier_dossier_membre`,
  `supprimer_dossier_membre`, `supprimer_document_membre` (espace « Mes fichiers »).
  Validation d'upload partagée : `apps/documents/validators.py`
  (`valider_fichier_document` : taille max + extensions exécutables refusées).

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

### Membre = personne, compte optionnel
`coeur.Membre` porte l'**identité** (`prenom`, `nom`, `email`) et le compte de
connexion (`user`, `OneToOne` nullable, `SET_NULL`) est **facultatif** : un
**adhérent peut exister sans accès en ligne**. `Membre.__str__` = `nom_complet`
puis e-mail puis identifiant du compte (jamais d'erreur si `user` est nul) ;
`a_un_compte` = présence d'un compte. Le tri et la recherche se font sur
`nom`/`prenom` (plus sur `user__…`). Le droit de vote en AG est indexé par
`membre_id`, donc un adhérent sans compte **vote quand même**. Limite assumée :
`synchroniser_compte` ne re-synchronise pas l'identifiant de connexion
(`username`) quand l'e-mail change (la connexion reste stable).

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
