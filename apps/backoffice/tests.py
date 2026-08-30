"""Tests du back-office : contrôle d'accès bureau + validation de modération."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import make_aware

from apps.agenda import services as agenda_services
from apps.agenda.models import Evenement, Intervention
from apps.budget.models import (
    Adhesion,
    Categorie,
    RecuFiscal,
    Saison,
    SoldeTresorerie,
    Transaction,
)
from apps.budget.services import emettre_recu
from apps.coeur.models import Membre, Signataire, Utilisateur
from apps.coeur.roles import NOM_GROUPE_BUREAU
from apps.common.models import Moderation
from apps.documents.models import Document, Dossier
from apps.facturation.models import Client, Devis, Facture, LigneDevis, LigneFacture
from apps.facturation.services import valider_facture
from apps.gouvernance.models import (
    BlocCompteRendu,
    Pouvoir,
    Presence,
    Resolution,
    Reunion,
    Sujet,
)
from apps.spectacles.models import LigneDistribution, Spectacle

Statut = Moderation.StatutModeration
FILE = "/bureau/moderation/"
RECUS = "/bureau/recus/"


def _membre(username):
    user = Utilisateur.objects.create_user(username=username, password="x")
    Membre.objects.create(user=user)
    return user


def _staff(username="bureau"):
    return Utilisateur.objects.create_user(username=username, password="x", is_staff=True)


def _projet_propose(titre="Projet proposé"):
    return Spectacle.objects.create(titre=titre, statut_moderation=Statut.PROPOSE)


def _evenement_propose(titre="Événement proposé"):
    return Evenement.objects.create(
        titre=titre,
        date_debut=make_aware(datetime(2026, 11, 1, 20, 0)),
        statut_moderation=Statut.PROPOSE,
    )


# --- Paramètres & équipe ----------------------------------------------------


_URLS_REGLAGES = (
    "/bureau/parametres/",
    "/bureau/parametres/site/",
    "/bureau/parametres/contact/",
    "/bureau/parametres/signataires/",
)


def test_parametres_reserve_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    for url in _URLS_REGLAGES:
        assert client.get(url).status_code == 403, url


def test_editer_identite_legale(client, db):
    from apps.coeur.models import ParametresAssociation

    client.force_login(_staff())
    reponse = client.post(
        "/bureau/parametres/",
        {
            "nom": "L'Improliante",
            "objet": "spectacle vivant",
            "adresse": "1 rue du Théâtre",
            "code_postal": "75001",
            "ville": "Paris",
            "numero_rna": "W123",
            "numero_siret": "",
            "article_cgi": "200",
            "signataire_nom": "Alice",
            "signataire_qualite": "Présidente",
        },
    )
    assert reponse.status_code == 302
    assert ParametresAssociation.load().nom == "L'Improliante"


def test_editer_les_textes_du_site(client, db):
    from apps.coeur.models import ParametresAssociation

    client.force_login(_staff())
    reponse = client.post(
        "/bureau/parametres/site/",
        {"accroche": "en pleine lumière.", "presentation": "Une troupe."},
    )
    assert reponse.status_code == 302
    params = ParametresAssociation.load()
    assert (params.accroche, params.presentation) == ("en pleine lumière.", "Une troupe.")


def test_un_ecran_de_reglages_n_ecrit_que_ses_propres_champs(client, db):
    """Trois écrans, un seul modèle : enregistrer les textes du site ne doit pas
    recopier par-dessus l'identité légale saisie ailleurs."""
    from apps.coeur.models import ParametresAssociation

    params = ParametresAssociation.load()
    params.numero_rna, params.signataire_nom = "W999", "Alice"
    params.save()

    client.force_login(_staff())
    client.post(
        "/bureau/parametres/site/",
        {"accroche": "autre accroche", "presentation": "autre présentation"},
    )

    params.refresh_from_db()
    assert params.accroche == "autre accroche"
    assert (params.numero_rna, params.signataire_nom) == ("W999", "Alice")


# --- Signataires ------------------------------------------------------------


def test_signataires_reserve_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get("/bureau/parametres/signataires/").status_code == 403


def test_le_bureau_cree_un_signataire_sans_passer_par_l_admin(client, db):
    client.force_login(_staff())
    reponse = client.post(
        "/bureau/parametres/signataires/",
        {
            "nom": "Alice Martin",
            "qualite": "Présidente",
            "mention_delegation": "",
            "membre": "",
            "actif": "on",
        },
    )
    assert reponse.status_code == 302
    assert Signataire.objects.get(nom="Alice Martin").qualite == "Présidente"


def test_le_defaut_ne_retient_que_les_signataires_en_service(client, db):
    """Un signataire retiré du service serait proposé partout sans figurer
    dans les choix des pièces : il ne peut pas devenir le défaut."""
    from apps.backoffice.forms import SignataireParDefautForm

    actif = Signataire.objects.create(nom="Active", qualite="Présidente")
    Signataire.objects.create(nom="Retirée", qualite="Ancienne", actif=False)
    choix = set(SignataireParDefautForm().fields["signataire_par_defaut"].queryset)
    assert choix == {actif}


def test_le_defaut_est_preselectionne_sur_une_piece_neuve(client, db):
    from apps.backoffice.forms import FactureForm
    from apps.coeur.models import ParametresAssociation

    sig = Signataire.objects.create(nom="Alice Martin", qualite="Présidente")
    params = ParametresAssociation.load()
    params.signataire_par_defaut = sig
    params.save()
    assert FactureForm().fields["signataire"].initial == sig


def test_le_defaut_ne_touche_pas_une_piece_existante(client, db):
    """Présélectionner à l'édition réécrirait un choix déjà fait — ou en poserait
    un là où l'absence de signataire était volontaire."""
    from apps.backoffice.forms import FactureForm
    from apps.coeur.models import ParametresAssociation

    sig = Signataire.objects.create(nom="Alice Martin", qualite="Présidente")
    params = ParametresAssociation.load()
    params.signataire_par_defaut = sig
    params.save()
    facture = Facture.objects.create(client=Client.objects.create(nom="Théâtre municipal"))
    assert FactureForm(instance=facture).fields["signataire"].initial is None


def test_un_signataire_utilise_ne_se_supprime_pas(client, db):
    """Les clés sont en SET_NULL : supprimer effacerait le lien sans bruit sur
    des pièces déjà établies. On retire du service à la place."""
    sig = Signataire.objects.create(nom="Alice Martin", qualite="Présidente")
    Facture.objects.create(client=Client.objects.create(nom="Théâtre municipal"), signataire=sig)
    client.force_login(_staff())
    client.post(f"/bureau/parametres/signataires/{sig.pk}/supprimer/")
    assert Signataire.objects.filter(pk=sig.pk).exists()


def test_un_signataire_inutilise_se_supprime(client, db):
    sig = Signataire.objects.create(nom="Jamais Servi", qualite="Trésorier")
    client.force_login(_staff())
    reponse = client.post(f"/bureau/parametres/signataires/{sig.pk}/supprimer/")
    assert reponse.status_code == 302
    assert not Signataire.objects.filter(pk=sig.pk).exists()


def test_les_quatre_ecrans_de_reglages_portent_leurs_onglets(client, db):
    client.force_login(_staff())
    for url in _URLS_REGLAGES:
        corps = client.get(url).content.decode()
        for cible in _URLS_REGLAGES:
            assert f'href="{cible}"' in corps, (url, cible)


def test_equipe_ajouter_et_retirer_du_bureau(client, db):
    from apps.coeur.roles import est_bureau

    cible = _membre("nouveau")  # pas bureau au départ
    assert est_bureau(cible) is False

    client.force_login(_staff())
    client.post("/bureau/equipe/", {"utilisateur": cible.pk, "action": "ajouter"})
    cible.refresh_from_db()
    assert est_bureau(cible) is True

    client.post("/bureau/equipe/", {"utilisateur": cible.pk, "action": "retirer"})
    cible.refresh_from_db()
    assert est_bureau(cible) is False


# --- Création de compte membre (par le bureau) -----------------------------


def _donnees_nouveau_membre(**extra):
    donnees = {
        "prenom": "Camille",
        "nom": "Martin",
        "email": "camille.martin@example.org",
        "role_public": "",
        "telephone": "",
    }
    donnees.update(extra)
    return donnees


def test_creation_membre_reservee_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get("/bureau/membres/nouveau/").status_code == 403


def test_bureau_cree_un_compte_membre(client, db):
    from apps.coeur.roles import est_bureau

    client.force_login(_staff())
    reponse = client.post("/bureau/membres/nouveau/", _donnees_nouveau_membre(ouvrir_acces="on"))
    assert reponse.status_code == 200  # page réaffichée avec le lien d'activation

    user = Utilisateur.objects.get(email="camille.martin@example.org")
    assert user.username == "camille.martin@example.org"  # e-mail = identifiant
    assert user.has_usable_password() is False  # activation requise avant connexion
    assert hasattr(user, "membre")
    assert reponse.context["lien_activation"]  # lien affiché au bureau
    assert est_bureau(user) is False  # un nouveau membre n'a PAS l'accès bureau


def test_bureau_cree_une_personne_sans_compte(client, db):
    """Par défaut (case décochée), on crée une fiche adhérent SANS compte."""
    client.force_login(_staff())
    reponse = client.post("/bureau/membres/nouveau/", _donnees_nouveau_membre())
    assert reponse.status_code == 200
    membre = Membre.objects.get(email="camille.martin@example.org")
    assert membre.a_un_compte is False  # aucun compte de connexion
    assert membre.nom_complet == "Camille Martin"
    assert Utilisateur.objects.filter(email="camille.martin@example.org").count() == 0
    assert reponse.context["lien_activation"] is None


def test_creation_membre_refuse_un_email_deja_pris(client, db):
    Utilisateur.objects.create_user(
        username="camille.martin@example.org",
        email="camille.martin@example.org",
        password="x",
    )
    client.force_login(_staff())
    reponse = client.post("/bureau/membres/nouveau/", _donnees_nouveau_membre(ouvrir_acces="on"))
    assert reponse.status_code == 200
    assert reponse.context["lien_activation"] is None  # rien de créé
    assert Utilisateur.objects.filter(email="camille.martin@example.org").count() == 1


def test_bureau_bascule_la_visibilite_d_un_membre(client, db):
    membre = _membre("visible_ou_non").membre
    assert membre.visible_sur_site is False  # masqué par défaut
    url = f"/bureau/membres/{membre.pk}/visibilite/"

    client.force_login(_staff())
    client.post(url)
    membre.refresh_from_db()
    assert membre.visible_sur_site is True  # publié

    client.post(url)
    membre.refresh_from_db()
    assert membre.visible_sur_site is False  # remasqué


def test_bascule_visibilite_reservee_au_bureau_et_en_post(client, db):
    membre = _membre("cible").membre
    url = f"/bureau/membres/{membre.pk}/visibilite/"
    # GET interdit (require_POST) même pour un membre du bureau.
    assert client.get(url).status_code == 302  # login_required d'abord
    client.force_login(_membre("lambda"))
    assert client.post(url).status_code == 403  # pas bureau
    client.force_login(_staff())
    assert client.get(url).status_code == 405  # méthode non autorisée


def test_bureau_bascule_la_mise_en_avant(client, db):
    membre = _membre("vedette_ou_non").membre
    assert membre.mis_en_avant is False
    url = f"/bureau/membres/{membre.pk}/a-la-une/"

    client.force_login(_staff())
    client.post(url)
    membre.refresh_from_db()
    assert membre.mis_en_avant is True

    client.post(url)
    membre.refresh_from_db()
    assert membre.mis_en_avant is False


# --- Tableau de bord bureau -------------------------------------------------


def test_dashboard_bureau_reserve_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get("/bureau/").status_code == 403


def test_dashboard_bureau_compte_les_taches_en_attente(client, db):
    _projet_propose()
    _evenement_propose()
    Facture.objects.create(client=Client.objects.create(nom="X"))  # brouillon
    client.force_login(_staff())
    reponse = client.get("/bureau/")
    assert reponse.status_code == 200
    assert reponse.context["projets_a_moderer"] == 1
    assert reponse.context["evenements_a_moderer"] == 1
    assert reponse.context["a_moderer"] == 2
    assert reponse.context["factures_brouillon"] == 1


# --- Contrôle d'accès -------------------------------------------------------


def test_file_moderation_exige_la_connexion(client, db):
    reponse = client.get(FILE)
    assert reponse.status_code == 302
    assert "/connexion/" in reponse.url


def test_file_moderation_interdite_hors_bureau(client, db):
    user = _membre("lambda")
    client.force_login(user)
    assert client.get(FILE).status_code == 403


def test_bureau_staff_accede_a_la_file(client, db):
    client.force_login(_staff())
    assert client.get(FILE).status_code == 200


def test_membre_du_groupe_bureau_accede_a_la_file(client, db):
    """Le rôle passe par le groupe « Bureau », pas seulement par is_staff."""
    user = _membre("secretaire")
    groupe, _ = Group.objects.get_or_create(name=NOM_GROUPE_BUREAU)
    user.groups.add(groupe)
    client.force_login(user)
    assert client.get(FILE).status_code == 200


# --- Validation / refus des projets ----------------------------------------


def test_valider_un_projet_le_publie(client, db):
    bureau = _staff()
    projet = _projet_propose()
    client.force_login(bureau)
    client.post(f"/bureau/moderation/projet/{projet.pk}/", {"action": "valider"})
    projet.refresh_from_db()
    assert projet.statut_moderation == Statut.PUBLIE
    assert projet.valide_par == bureau


def test_refuser_un_projet_avec_motif(client, db):
    projet = _projet_propose()
    client.force_login(_staff())
    client.post(
        f"/bureau/moderation/projet/{projet.pk}/",
        {"action": "refuser", "motif": "Titre à revoir."},
    )
    projet.refresh_from_db()
    assert projet.statut_moderation == Statut.REFUSE
    assert projet.motif_refus == "Titre à revoir."


def test_refuser_un_projet_sans_motif_echoue(client, db):
    projet = _projet_propose()
    client.force_login(_staff())
    client.post(f"/bureau/moderation/projet/{projet.pk}/", {"action": "refuser", "motif": ""})
    projet.refresh_from_db()
    assert projet.statut_moderation == Statut.PROPOSE  # inchangé


def test_moderer_projet_refuse_le_get(client, db):
    projet = _projet_propose()
    client.force_login(_staff())
    assert client.get(f"/bureau/moderation/projet/{projet.pk}/").status_code == 405


# --- Validation des événements (avec visibilité) ---------------------------


def test_valider_un_evenement_fixe_la_visibilite(client, db):
    evenement = _evenement_propose()
    client.force_login(_staff())
    client.post(
        f"/bureau/moderation/evenement/{evenement.pk}/",
        {"action": "valider", "visibilite": Evenement.Visibilite.MEMBRES},
    )
    evenement.refresh_from_db()
    assert evenement.statut_moderation == Statut.PUBLIE
    assert evenement.visibilite == Evenement.Visibilite.MEMBRES


def test_valider_un_evenement_visibilite_invalide_est_rejete(client, db):
    evenement = _evenement_propose()
    client.force_login(_staff())
    client.post(
        f"/bureau/moderation/evenement/{evenement.pk}/",
        {"action": "valider", "visibilite": "n_importe_quoi"},
    )
    evenement.refresh_from_db()
    assert evenement.statut_moderation == Statut.PROPOSE  # non publié


def test_hors_bureau_ne_peut_pas_moderer(client, db):
    """Un membre lambda ne peut pas valider en tapant l'URL directement."""
    projet = _projet_propose()
    client.force_login(_membre("intrus"))
    reponse = client.post(f"/bureau/moderation/projet/{projet.pk}/", {"action": "valider"})
    assert reponse.status_code == 403
    projet.refresh_from_db()
    assert projet.statut_moderation == Statut.PROPOSE


# --- Reçus fiscaux ----------------------------------------------------------


def _donnees_recu(**extra):
    donnees = {
        "type_versement": RecuFiscal.TypeVersement.DON,
        "forme": RecuFiscal.Forme.NUMERAIRE,
        "montant": "75.00",
        "date_versement": "2026-03-01",
        "donateur_nom": "Paul Durand",
        "donateur_adresse": "1 rue des Arts",
        "donateur_code_postal": "75001",
        "donateur_ville": "Paris",
    }
    donnees.update(extra)
    return donnees


def test_liste_recus_reservee_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get(RECUS).status_code == 403


def test_bureau_accede_a_la_liste_des_recus(client, db):
    client.force_login(_staff())
    assert client.get(RECUS).status_code == 200


def test_emission_manuelle_d_un_recu(client, db):
    client.force_login(_staff())
    reponse = client.post("/bureau/recus/nouveau/", _donnees_recu())
    assert reponse.status_code == 302
    recu = RecuFiscal.objects.get()
    assert recu.numero == "R2026-0001"
    assert recu.montant == Decimal("75.00")
    assert recu.membre is None  # saisie manuelle : aucun rattachement


def test_emission_depuis_adhesion_rattache_le_membre(client, db):
    bureau = _staff()
    membre = _membre("donateur")
    saison = Saison.objects.create(nom="2025-2026")
    adhesion = Adhesion.objects.create(
        membre=membre.membre,
        saison=saison,
        statut=Adhesion.Statut.PAYEE,
        montant_verse=Decimal("40.00"),
    )
    client.force_login(bureau)
    reponse = client.post(
        "/bureau/recus/nouveau/",
        _donnees_recu(
            adhesion=adhesion.pk,
            type_versement=RecuFiscal.TypeVersement.COTISATION,
            montant="40.00",
            donateur_nom=str(membre.membre),
        ),
    )
    assert reponse.status_code == 302
    recu = RecuFiscal.objects.get()
    assert recu.membre == membre.membre
    assert recu.adhesion == adhesion


def test_pas_de_second_recu_pour_une_meme_adhesion(client, db):
    """Un versement = un seul reçu Cerfa : une adhésion déjà pourvue d'un reçu
    ne doit pas pouvoir en générer un second (garde-fou légal contre les
    doublons), et ne figure plus dans les adhésions éligibles proposées."""
    bureau = _staff()
    membre = _membre("donateur")
    saison = Saison.objects.create(nom="2025-2026")
    adhesion = Adhesion.objects.create(
        membre=membre.membre,
        saison=saison,
        statut=Adhesion.Statut.PAYEE,
        montant_verse=Decimal("40.00"),
    )
    donnees = _donnees_recu(
        adhesion=adhesion.pk,
        type_versement=RecuFiscal.TypeVersement.COTISATION,
        montant="40.00",
        donateur_nom=str(membre.membre),
    )
    client.force_login(bureau)

    # 1er reçu : émis normalement.
    assert client.post("/bureau/recus/nouveau/", donnees).status_code == 302
    assert RecuFiscal.objects.filter(adhesion=adhesion).count() == 1

    # 2e tentative sur la même adhésion : refusée, aucun reçu supplémentaire.
    assert client.post("/bureau/recus/nouveau/", donnees).status_code == 302
    assert RecuFiscal.objects.filter(adhesion=adhesion).count() == 1

    # Dans l'écran Adhésions, elle affiche « Reçu émis », plus « Émettre un reçu ».
    corps = client.get("/bureau/adhesions/").content.decode()
    assert "Reçu émis" in corps
    assert "Émettre un reçu" not in corps


def test_montant_negatif_est_refuse(client, db):
    client.force_login(_staff())
    reponse = client.post("/bureau/recus/nouveau/", _donnees_recu(montant="-10"))
    assert reponse.status_code == 200  # formulaire réaffiché
    assert RecuFiscal.objects.count() == 0


def test_bureau_telecharge_le_pdf(client, db, monkeypatch):
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: b"%PDF-1.4 x"
    )
    recu = emettre_recu(
        type_versement=RecuFiscal.TypeVersement.DON,
        montant=Decimal("10.00"),
        date_versement=date(2026, 1, 1),
        donateur_nom="X",
    )
    client.force_login(_staff())
    reponse = client.get(f"/bureau/recus/{recu.pk}/telecharger/")
    assert reponse.status_code == 200
    assert b"".join(reponse.streaming_content).startswith(b"%PDF")


# --- Facturation ------------------------------------------------------------


def _donnees_facture(client_facture, **extra):
    donnees = {
        "client": client_facture.pk,
        "objet": "Prestation artistique",
        "date_echeance": "",
        "mentions_legales": "",
        "lignes-TOTAL_FORMS": "1",
        "lignes-INITIAL_FORMS": "0",
        "lignes-MIN_NUM_FORMS": "0",
        "lignes-MAX_NUM_FORMS": "1000",
        "lignes-0-designation": "Atelier théâtre",
        "lignes-0-quantite": "2",
        "lignes-0-prix_unitaire_ht": "100.00",
        "lignes-0-taux_tva": "20.00",
        "lignes-0-ordre": "0",
    }
    donnees.update(extra)
    return donnees


def test_factures_reservees_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get("/bureau/factures/").status_code == 403


def test_creer_facture_avec_lignes(client, db):
    client_facture = Client.objects.create(nom="Théâtre municipal")
    client.force_login(_staff())
    reponse = client.post("/bureau/factures/nouvelle/", _donnees_facture(client_facture))
    assert reponse.status_code == 302
    facture = Facture.objects.get()
    assert facture.statut == Facture.Statut.BROUILLON
    assert facture.numero is None
    assert facture.lignes.count() == 1
    assert facture.total_ttc == Decimal("240.00")  # 2 × 100 HT + 20 % TVA


def test_creer_facture_avec_signataire(client, db):
    sig = Signataire.objects.create(nom="Alice", qualite="Présidente")
    client_facture = Client.objects.create(nom="Théâtre municipal")
    client.force_login(_staff())
    client.post("/bureau/factures/nouvelle/", _donnees_facture(client_facture, signataire=sig.pk))
    facture = Facture.objects.get()
    assert facture.signataire == sig


def _lignes_post(donnees, lignes):
    """Remplace les lignes du POST par `lignes` = [(désignation, qté, PU, TVA)]."""
    for cle in list(donnees):
        if cle.startswith("lignes-") and cle[len("lignes-")].isdigit():
            del donnees[cle]
    donnees["lignes-TOTAL_FORMS"] = str(len(lignes))
    for i, (des, q, pu, tva) in enumerate(lignes):
        donnees[f"lignes-{i}-designation"] = des
        donnees[f"lignes-{i}-quantite"] = q
        donnees[f"lignes-{i}-prix_unitaire_ht"] = pu
        donnees[f"lignes-{i}-taux_tva"] = tva
        donnees[f"lignes-{i}-ordre"] = str(i)
    return donnees


def test_creer_facture_avec_plusieurs_lignes(client, db):
    client_facture = Client.objects.create(nom="Théâtre municipal")
    client.force_login(_staff())
    donnees = _lignes_post(
        _donnees_facture(client_facture),
        [
            ("Atelier", "2", "100.00", "20.00"),  # 200 HT, 40 TVA
            ("Représentation", "1", "500.00", "20.00"),  # 500 HT, 100 TVA
            ("Défraiement", "3", "50.00", "0.00"),  # 150 HT, 0 TVA
        ],
    )
    reponse = client.post("/bureau/factures/nouvelle/", donnees)
    assert reponse.status_code == 302
    facture = Facture.objects.get()
    assert facture.lignes.count() == 3
    assert facture.total_ht == Decimal("850.00")
    assert facture.total_ttc == Decimal("990.00")  # 850 + 140 de TVA


def test_ordre_des_lignes_suit_la_saisie(client, db):
    """« Ordre » n'est plus saisi : les lignes gardent l'ordre de saisie (0, 1, 2…)."""
    client.force_login(_staff())
    donnees = _lignes_post(
        _donnees_facture(Client.objects.create(nom="X")),
        [
            ("Première", "1", "10", "0"),
            ("Deuxième", "1", "20", "0"),
            ("Troisième", "1", "30", "0"),
        ],
    )
    client.post("/bureau/factures/nouvelle/", donnees)
    lignes = list(Facture.objects.get().lignes.all())  # triées par ordre, id
    assert [ligne.designation for ligne in lignes] == ["Première", "Deuxième", "Troisième"]
    assert [ligne.ordre for ligne in lignes] == [0, 1, 2]


def _champs_nouveau_client(nom):
    """Champs préfixés du fieldset « Nouveau client » (seul `nom` est requis)."""
    base = {
        "nom": nom,
        "adresse": "",
        "code_postal": "",
        "ville": "",
        "email": "",
        "telephone": "",
        "siret": "",
        "numero_tva": "",
    }
    return {f"nouveau_client-{cle}": valeur for cle, valeur in base.items()}


def test_creer_facture_cree_le_client_a_la_volee(client, db):
    client.force_login(_staff())
    donnees = _donnees_facture(Client.objects.create(nom="Ignoré"))
    donnees["client"] = "__nouveau__"
    donnees.update(_champs_nouveau_client("Compagnie du Ru"))
    reponse = client.post("/bureau/factures/nouvelle/", donnees)
    assert reponse.status_code == 302
    nouveau = Client.objects.get(nom="Compagnie du Ru")
    assert Facture.objects.get().client == nouveau


def test_client_inline_annule_si_facture_invalide(client, db):
    """Si le reste du formulaire est invalide, le client créé à la volée est
    annulé (transaction) — pas de client orphelin."""
    client.force_login(_staff())
    donnees = _donnees_facture(Client.objects.create(nom="Ignoré"))
    donnees["client"] = "__nouveau__"
    donnees.update(_champs_nouveau_client("Éphémère"))
    donnees["lignes-0-prix_unitaire_ht"] = "abc"  # ligne invalide → formset KO
    reponse = client.post("/bureau/factures/nouvelle/", donnees)
    assert reponse.status_code == 200  # formulaire réaffiché
    assert not Client.objects.filter(nom="Éphémère").exists()  # rollback
    assert not Facture.objects.exists()


def test_creer_devis_cree_le_client_a_la_volee(client, db):
    client.force_login(_staff())
    donnees = _donnees_devis(Client.objects.create(nom="Ignoré"))
    donnees["client"] = "__nouveau__"
    donnees.update(_champs_nouveau_client("Scène Nomade"))
    reponse = client.post("/bureau/devis/nouveau/", donnees)
    assert reponse.status_code == 302
    nouveau = Client.objects.get(nom="Scène Nomade")
    assert Devis.objects.get().client == nouveau


def test_valider_facture_attribue_le_numero(client, db):
    client_facture = Client.objects.create(nom="Théâtre municipal")
    facture = Facture.objects.create(client=client_facture)
    LigneFacture.objects.create(
        facture=facture, designation="Prestation", quantite=1, prix_unitaire_ht=Decimal("50")
    )
    client.force_login(_staff())
    reponse = client.post(f"/bureau/factures/{facture.pk}/valider/")
    assert reponse.status_code == 302
    facture.refresh_from_db()
    assert facture.statut == Facture.Statut.VALIDEE
    assert facture.numero and facture.numero.startswith("F")


def test_valider_facture_sans_ligne_refuse(client, db):
    client_facture = Client.objects.create(nom="Théâtre")
    facture = Facture.objects.create(client=client_facture)
    client.force_login(_staff())
    client.post(f"/bureau/factures/{facture.pk}/valider/")
    facture.refresh_from_db()
    assert facture.statut == Facture.Statut.BROUILLON  # non validée
    assert facture.numero is None


def test_facture_validee_non_editable(client, db):
    """Une facture validée est présentée en lecture seule (pas de formulaire)."""
    from apps.facturation.services import valider_facture

    client_facture = Client.objects.create(nom="Théâtre")
    facture = Facture.objects.create(client=client_facture)
    LigneFacture.objects.create(
        facture=facture, designation="X", quantite=1, prix_unitaire_ht=Decimal("10")
    )
    valider_facture(facture)
    client.force_login(_staff())
    corps = client.get(f"/bureau/factures/{facture.pk}/").content.decode()
    assert "n'est plus modifiable" in corps


def test_telecharger_facture_brouillon_404(client, db):
    client_facture = Client.objects.create(nom="Théâtre")
    facture = Facture.objects.create(client=client_facture)
    client.force_login(_staff())
    assert client.get(f"/bureau/factures/{facture.pk}/telecharger/").status_code == 404


def test_telecharger_facture_validee(client, db, monkeypatch):
    from apps.facturation.services import valider_facture

    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: b"%PDF-1.4 f"
    )
    client_facture = Client.objects.create(nom="Théâtre")
    facture = Facture.objects.create(client=client_facture)
    LigneFacture.objects.create(
        facture=facture, designation="X", quantite=1, prix_unitaire_ht=Decimal("10")
    )
    valider_facture(facture)
    client.force_login(_staff())
    reponse = client.get(f"/bureau/factures/{facture.pk}/telecharger/")
    assert reponse.status_code == 200
    assert b"".join(reponse.streaming_content).startswith(b"%PDF")


def test_facture_pdf_contient_reglement_et_net_a_payer(client, db, monkeypatch):
    """Le PDF de facture rend les nouveaux blocs : règlement (IBAN), mention de
    TVA et « Net à payer »."""
    from apps.coeur.models import ParametresAssociation
    from apps.facturation.services import valider_facture

    params = ParametresAssociation.load()
    params.nom = "L'Improliante"
    params.iban = "FR7612345678901234567890123"
    params.bic = "ABCDEFGH"
    params.mention_tva = "TVA non applicable, art. 293 B du CGI"
    params.save()

    captures = []
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf",
        lambda html, *, base_url=None: captures.append(html) or b"%PDF-1.4",
    )
    cl = Client.objects.create(nom="Théâtre")
    facture = Facture.objects.create(client=cl)
    LigneFacture.objects.create(
        facture=facture,
        designation="Atelier",
        quantite=Decimal("2"),
        prix_unitaire_ht=Decimal("100"),
        taux_tva=Decimal("20"),
    )
    valider_facture(facture)
    client.force_login(_staff())
    client.get(f"/bureau/factures/{facture.pk}/telecharger/")

    html = captures[0]
    assert "Net à payer" in html
    assert "IBAN FR7612345678901234567890123" in html
    assert "TVA non applicable, art. 293 B du CGI" in html


def test_supprimer_une_ligne_de_facture(client, db):
    cl = Client.objects.create(nom="X")
    facture = Facture.objects.create(client=cl)
    ligne_a = LigneFacture.objects.create(
        facture=facture,
        designation="Ligne A",
        quantite=Decimal("1"),
        prix_unitaire_ht=Decimal("10"),
        ordre=0,
    )
    ligne_b = LigneFacture.objects.create(
        facture=facture,
        designation="Ligne B",
        quantite=Decimal("1"),
        prix_unitaire_ht=Decimal("20"),
        ordre=1,
    )
    client.force_login(_staff())
    donnees = {
        "client": cl.pk,
        "objet": "",
        "date_echeance": "",
        "mentions_legales": "",
        "lignes-TOTAL_FORMS": "2",
        "lignes-INITIAL_FORMS": "2",
        "lignes-MIN_NUM_FORMS": "0",
        "lignes-MAX_NUM_FORMS": "1000",
        "lignes-0-id": str(ligne_a.pk),
        "lignes-0-designation": "Ligne A",
        "lignes-0-quantite": "1",
        "lignes-0-prix_unitaire_ht": "10",
        "lignes-0-taux_tva": "0",
        "lignes-0-ordre": "0",
        "lignes-1-id": str(ligne_b.pk),
        "lignes-1-designation": "Ligne B",
        "lignes-1-quantite": "1",
        "lignes-1-prix_unitaire_ht": "20",
        "lignes-1-taux_tva": "0",
        "lignes-1-ordre": "1",
        "lignes-1-DELETE": "on",
    }
    reponse = client.post(f"/bureau/factures/{facture.pk}/", donnees)
    assert reponse.status_code == 302
    facture.refresh_from_db()
    assert facture.lignes.count() == 1
    assert facture.lignes.first() == ligne_a


def test_creer_client(client, db):
    client.force_login(_staff())
    reponse = client.post("/bureau/clients/", {"nom": "Nouvelle scène", "ville": "Lyon"})
    assert reponse.status_code == 302
    assert Client.objects.filter(nom="Nouvelle scène").exists()


# --- Devis ------------------------------------------------------------------


def _donnees_devis(client_facture, **extra):
    donnees = {
        "client": client_facture.pk,
        "objet": "Prestation",
        "date": "2026-03-01",
        "date_validite": "",
        "conditions": "",
        "lignes-TOTAL_FORMS": "1",
        "lignes-INITIAL_FORMS": "0",
        "lignes-MIN_NUM_FORMS": "0",
        "lignes-MAX_NUM_FORMS": "1000",
        "lignes-0-designation": "Représentation",
        "lignes-0-quantite": "1",
        "lignes-0-prix_unitaire_ht": "200.00",
        "lignes-0-taux_tva": "0",
        "lignes-0-ordre": "0",
    }
    donnees.update(extra)
    return donnees


def test_devis_reserve_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get("/bureau/devis/").status_code == 403


def test_creer_devis_attribue_un_numero(client, db):
    client_facture = Client.objects.create(nom="Théâtre municipal")
    client.force_login(_staff())
    reponse = client.post("/bureau/devis/nouveau/", _donnees_devis(client_facture))
    assert reponse.status_code == 302
    devis = Devis.objects.get()
    assert devis.numero == "D2026-0001"
    assert devis.lignes.count() == 1


def test_creer_devis_avec_plusieurs_lignes(client, db):
    client_facture = Client.objects.create(nom="Théâtre municipal")
    client.force_login(_staff())
    donnees = _lignes_post(
        _donnees_devis(client_facture),
        [
            ("Conception", "1", "300.00", "0.00"),
            ("Répétitions", "4", "80.00", "0.00"),  # 320 HT
            ("Représentation", "2", "250.00", "0.00"),  # 500 HT
        ],
    )
    reponse = client.post("/bureau/devis/nouveau/", donnees)
    assert reponse.status_code == 302
    devis = Devis.objects.get()
    assert devis.lignes.count() == 3
    assert devis.total_ht == Decimal("1120.00")  # 300 + 320 + 500


def test_changer_statut_devis(client, db):
    client_facture = Client.objects.create(nom="Théâtre")
    devis = Devis.objects.create(client=client_facture, date=date(2026, 3, 1))
    client.force_login(_staff())
    client.post(f"/bureau/devis/{devis.pk}/statut/", {"action": "accepter"})
    devis.refresh_from_db()
    assert devis.statut == Devis.Statut.ACCEPTE


def test_transformer_devis_cree_une_facture(client, db):
    client_facture = Client.objects.create(nom="Théâtre")
    devis = Devis.objects.create(client=client_facture, date=date(2026, 3, 1))
    LigneDevis.objects.create(
        devis=devis, designation="X", quantite=1, prix_unitaire_ht=Decimal("50")
    )
    client.force_login(_staff())
    reponse = client.post(f"/bureau/devis/{devis.pk}/transformer/")
    assert reponse.status_code == 302
    devis.refresh_from_db()
    assert devis.statut == Devis.Statut.FACTURE
    facture = Facture.objects.get()
    assert facture.devis_origine == devis
    assert f"/bureau/factures/{facture.pk}/" in reponse.url


def test_telecharger_devis_pdf(client, db, monkeypatch):
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: b"%PDF-1.4 d"
    )
    client_facture = Client.objects.create(nom="Théâtre")
    devis = Devis.objects.create(client=client_facture, date=date(2026, 3, 1))
    client.force_login(_staff())
    reponse = client.get(f"/bureau/devis/{devis.pk}/telecharger/")
    assert reponse.status_code == 200
    assert reponse.content.startswith(b"%PDF")


# --- Aperçus (dry-run avant verrouillage) ----------------------------------


def test_apercu_facture_brouillon_ne_consomme_pas_de_numero(client, db, monkeypatch):
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: b"%PDF-1.4 a"
    )
    client_facture = Client.objects.create(nom="Théâtre")
    facture = Facture.objects.create(client=client_facture)
    client.force_login(_staff())
    reponse = client.get(f"/bureau/factures/{facture.pk}/apercu/")
    assert reponse.status_code == 200
    assert reponse.content.startswith(b"%PDF")
    facture.refresh_from_db()
    assert facture.numero is None  # l'aperçu ne verrouille aucun numéro
    assert facture.statut == Facture.Statut.BROUILLON


def test_previsualiser_recu_ne_cree_pas_de_recu(client, db, monkeypatch):
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: b"%PDF-1.4 r"
    )
    client.force_login(_staff())
    reponse = client.post("/bureau/recus/nouveau/", _donnees_recu(action="previsualiser"))
    assert reponse.status_code == 200
    assert reponse.content.startswith(b"%PDF")
    assert RecuFiscal.objects.count() == 0  # prévisualisation : rien n'est émis


# --- Avoir ------------------------------------------------------------------


def _facture_validee_bo(nom="Théâtre"):
    from apps.facturation.services import valider_facture

    facture = Facture.objects.create(client=Client.objects.create(nom=nom))
    LigneFacture.objects.create(
        facture=facture, designation="X", quantite=1, prix_unitaire_ht=Decimal("50")
    )
    valider_facture(facture)
    return facture


def test_creer_avoir_depuis_une_facture_validee(client, db):
    facture = _facture_validee_bo()
    client.force_login(_staff())
    reponse = client.post(f"/bureau/factures/{facture.pk}/avoir/")
    assert reponse.status_code == 302
    avoir = Facture.objects.get(type_piece=Facture.TypePiece.AVOIR)
    assert avoir.avoir_de == facture
    assert f"/bureau/factures/{avoir.pk}/" in reponse.url


def test_creer_avoir_sur_brouillon_refuse_par_la_vue(client, db):
    facture = Facture.objects.create(client=Client.objects.create(nom="Théâtre"))
    client.force_login(_staff())
    client.post(f"/bureau/factures/{facture.pk}/avoir/")
    assert not Facture.objects.filter(type_piece=Facture.TypePiece.AVOIR).exists()


# --- Documents : branche Association de l'explorateur unifié (gérée par le bureau) --
# La GED a fusionné dans l'explorateur « Fichiers » (espace_membre). L'espace
# ASSOCIATION est éditable par le bureau ; un membre le consulte en lecture seule.


def test_creation_dossier_association_reservee_au_bureau(client, db):
    client.force_login(_membre("lambda"))  # membre simple, pas bureau
    reponse = client.post(
        "/espace/fichiers/",
        {"form_type": "dossier", "branche": "association", "nom": "Statuts", "description": ""},
    )
    assert reponse.status_code == 404  # écriture Association réservée au bureau
    assert not Dossier.objects.filter(nom="Statuts").exists()


def test_bureau_cree_un_dossier_association_racine(client, db):
    client.force_login(_staff())
    client.post(
        "/espace/fichiers/",
        {"form_type": "dossier", "branche": "association", "nom": "Statuts", "description": ""},
    )
    dossier = Dossier.objects.get(nom="Statuts")
    assert dossier.depth == 1
    assert dossier.espace == Dossier.Espace.ASSOCIATION


def test_bureau_cree_un_sous_dossier_association(client, db):
    racine = Dossier.add_root(nom="Vie associative")  # espace=ASSOCIATION par défaut
    client.force_login(_staff())
    client.post(
        f"/espace/association/{racine.pk}/",
        {"form_type": "dossier", "nom": "PV d'AG", "description": ""},
    )
    enfant = Dossier.objects.get(nom="PV d'AG")
    assert enfant.depth == 2
    assert enfant.espace == Dossier.Espace.ASSOCIATION


def test_bureau_televerse_un_document_association(client, db):
    bureau = _staff()
    dossier = Dossier.add_root(nom="Documents")
    client.force_login(bureau)
    client.post(
        f"/espace/association/{dossier.pk}/",
        {
            "form_type": "document",
            "titre": "Statuts 2026",
            "confidentialite": Document.Confidentialite.MEMBRES,
            "description": "",
            "date_validite": "",
            "fichier": SimpleUploadedFile(
                "statuts.pdf", b"contenu", content_type="application/pdf"
            ),
        },
    )
    doc = Document.objects.get()
    assert doc.dossier == dossier
    assert doc.titre == "Statuts 2026"
    assert doc.confidentialite == Document.Confidentialite.MEMBRES
    assert doc.cree_par == bureau
    assert doc.courant is True
    assert doc.version == 1


def test_nouvelle_version_remplace_l_ancienne(client, db):
    dossier = Dossier.add_root(nom="Documents")
    ancien = Document.objects.create(
        titre="Statuts",
        dossier=dossier,
        confidentialite=Document.Confidentialite.MEMBRES,
        fichier=SimpleUploadedFile("v1.pdf", b"v1"),
    )
    client.force_login(_staff())
    client.post(
        f"/espace/association/doc/{ancien.pk}/nouvelle-version/",
        {"fichier": SimpleUploadedFile("v2.pdf", b"v2")},
    )
    ancien.refresh_from_db()
    assert ancien.courant is False
    nouveau = Document.objects.get(version=2)
    assert nouveau.courant is True
    assert nouveau.remplace == ancien


# --- Budget -----------------------------------------------------------------


def test_budget_reserve_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get("/bureau/budget/").status_code == 403


def test_creer_transaction(client, db):
    saison = Saison.objects.create(nom="2025-2026")
    client.force_login(_staff())
    reponse = client.post(
        "/bureau/budget/transaction/nouvelle/",
        {
            "saison": saison.pk,
            "type_flux": Transaction.TypeFlux.RECETTE,
            "statut": Transaction.Statut.REALISE,
            "libelle": "Subvention",
            "montant": "500.00",
            "date": "2026-03-01",
            "categorie": "",
        },
    )
    assert reponse.status_code == 302
    mouvement = Transaction.objects.get()
    assert mouvement.libelle == "Subvention"
    assert mouvement.montant == Decimal("500.00")


def test_supprimer_transaction(client, db):
    saison = Saison.objects.create(nom="2025-2026")
    mouvement = Transaction.objects.create(
        saison=saison,
        type_flux=Transaction.TypeFlux.DEPENSE,
        libelle="x",
        montant=Decimal("10"),
        date=date(2026, 3, 1),
    )
    client.force_login(_staff())
    client.post(f"/bureau/budget/transaction/{mouvement.pk}/supprimer/")
    assert not Transaction.objects.filter(pk=mouvement.pk).exists()


def test_creer_saison(client, db):
    client.force_login(_staff())
    client.post("/bureau/budget/saisons/", {"nom": "2026-2027", "date_debut": "", "date_fin": ""})
    assert Saison.objects.filter(nom="2026-2027").exists()


def test_creer_categorie(client, db):
    client.force_login(_staff())
    client.post("/bureau/budget/categories/", {"nom": "Communication", "description": ""})
    assert Categorie.objects.filter(nom="Communication").exists()


def test_bilan_affiche_les_totaux(client, db):
    saison = Saison.objects.create(nom="2025-2026")
    Transaction.objects.create(
        saison=saison,
        type_flux=Transaction.TypeFlux.RECETTE,
        statut=Transaction.Statut.REALISE,
        libelle="Don",
        montant=Decimal("800"),
        date=date(2026, 3, 1),
    )
    client.force_login(_staff())
    corps = client.get(f"/bureau/budget/bilan/?saison={saison.pk}").content.decode()
    assert "800" in corps


def test_bilan_tolere_un_parametre_saison_non_numerique(client, db):
    """?saison=abc ne doit pas provoquer d'erreur 500 (conversion de pk)."""
    client.force_login(_staff())
    assert client.get("/bureau/budget/bilan/?saison=abc").status_code == 200


def test_creer_recu_tolere_un_parametre_adhesion_non_numerique(client, db):
    client.force_login(_staff())
    assert client.get("/bureau/recus/nouveau/?adhesion=abc").status_code == 200


def test_export_excel_du_bilan(client, db):
    saison = Saison.objects.create(nom="2025-2026")
    Transaction.objects.create(
        saison=saison,
        type_flux=Transaction.TypeFlux.RECETTE,
        statut=Transaction.Statut.REALISE,
        libelle="Don",
        montant=Decimal("800"),
        date=date(2026, 3, 1),
    )
    client.force_login(_staff())
    reponse = client.get(f"/bureau/budget/bilan/excel/?saison={saison.pk}")
    assert reponse.status_code == 200
    assert "spreadsheetml" in reponse["Content-Type"]
    assert reponse.content[:2] == b"PK"  # xlsx = archive ZIP


def test_export_excel_reserve_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get("/bureau/budget/bilan/excel/").status_code == 403


# --- Filtres avancés --------------------------------------------------------


def test_filtre_factures_par_statut(client, db):
    c = Client.objects.create(nom="X")
    brouillon = Facture.objects.create(client=c)
    validee = _facture_validee_bo("Théâtre")
    client.force_login(_staff())
    reponse = client.get("/bureau/facturation/?onglet=factures&statut=brouillon")
    factures = list(reponse.context["objets"])
    assert brouillon in factures
    assert validee not in factures


def test_filtre_transactions_par_type(client, db):
    saison = Saison.objects.create(nom="2025-2026")
    recette = Transaction.objects.create(
        saison=saison,
        type_flux=Transaction.TypeFlux.RECETTE,
        libelle="r",
        montant=Decimal("10"),
        date=date(2026, 3, 1),
    )
    depense = Transaction.objects.create(
        saison=saison,
        type_flux=Transaction.TypeFlux.DEPENSE,
        libelle="d",
        montant=Decimal("5"),
        date=date(2026, 3, 1),
    )
    client.force_login(_staff())
    txs = list(client.get("/bureau/budget/?type_flux=recette").context["transactions"])
    assert recette in txs
    assert depense not in txs


def test_filtre_transactions_categorie_non_numerique_toleree(client, db):
    client.force_login(_staff())
    assert client.get("/bureau/budget/?categorie=abc").status_code == 200


# --- Pagination -------------------------------------------------------------


def test_pagination_des_factures(client, db):
    c = Client.objects.create(nom="X")
    for _ in range(25):
        Facture.objects.create(client=c)  # > 20 (une page)
    client.force_login(_staff())
    page1 = client.get("/bureau/facturation/?onglet=factures").context["page"]
    assert page1.paginator.num_pages == 2
    assert len(page1.object_list) == 20
    page2 = client.get("/bureau/facturation/?onglet=factures&page=2").context["page"]
    assert len(page2.object_list) == 5


def test_pagination_page_non_numerique_toleree(client, db):
    Client.objects.create(nom="X")
    client.force_login(_staff())
    # ?page=abc ne doit pas planter (get_page renvoie la 1re page).
    assert client.get("/bureau/facturation/?onglet=factures&page=abc").status_code == 200


# --- Gouvernance ------------------------------------------------------------


def _reunion(type_reunion=Reunion.TypeReunion.AG_ORDINAIRE, statut=Reunion.Statut.CONVOQUEE):
    return Reunion.objects.create(
        titre="AG",
        type_reunion=type_reunion,
        statut=statut,
        date=make_aware(datetime(2026, 6, 1, 18, 0)),
    )


def test_gouvernance_reservee_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get("/bureau/gouvernance/").status_code == 403


def test_creer_reunion(client, db):
    client.force_login(_staff())
    reponse = client.post(
        "/bureau/gouvernance/",
        {
            "titre": "AG 2026",
            "type_reunion": Reunion.TypeReunion.AG_ORDINAIRE,
            "statut": Reunion.Statut.CONVOQUEE,
            "date": "2026-06-01T18:00",
            "lieu_texte": "",
            "convocation_texte": "",
        },
    )
    assert reponse.status_code == 302
    assert Reunion.objects.filter(titre="AG 2026").exists()


def test_ajouter_sujet_a_l_ordre_du_jour(client, db):
    reunion = _reunion()
    client.force_login(_staff())
    client.post(
        f"/bureau/gouvernance/reunion/{reunion.pk}/sujet/",
        {
            "titre": "Budget",
            "description": "",
            "priorite": Sujet.Priorite.NORMALE,
            "ordre_du_jour": 1,
        },
    )
    assert reunion.sujets.filter(titre="Budget", statut=Sujet.Statut.ORDRE_DU_JOUR).exists()


def test_detail_reunion_calcule_le_quorum(client, db):
    reunion = _reunion()
    membre = _membre("alice").membre
    Presence.objects.create(
        reunion=reunion, membre=membre, statut=Presence.Statut.PRESENT, peut_voter=True
    )
    client.force_login(_staff())
    reponse = client.get(f"/bureau/gouvernance/reunion/{reunion.pk}/")
    assert reponse.status_code == 200
    assert reponse.context["quorum"].electorat == 1
    assert reponse.context["quorum"].presents_representes == 1


def test_saisir_presence_puis_mise_a_jour(client, db):
    reunion = _reunion()
    membre = _membre("alice").membre
    client.force_login(_staff())
    client.post(
        f"/bureau/gouvernance/reunion/{reunion.pk}/presence/",
        {"membre": membre.pk, "statut": Presence.Statut.PRESENT, "peut_voter": "on"},
    )
    presence = Presence.objects.get(reunion=reunion, membre=membre)
    assert presence.statut == Presence.Statut.PRESENT
    assert presence.peut_voter is True

    # Ré-enregistrer le même membre met à jour (pas de doublon ni d'IntegrityError).
    client.post(
        f"/bureau/gouvernance/reunion/{reunion.pk}/presence/",
        {"membre": membre.pk, "statut": Presence.Statut.EXCUSE},
    )
    presence.refresh_from_db()
    assert presence.statut == Presence.Statut.EXCUSE
    assert presence.peut_voter is False
    assert Presence.objects.filter(reunion=reunion, membre=membre).count() == 1


def test_pouvoir_mandant_egal_mandataire_refuse(client, db):
    reunion = _reunion()
    membre = _membre("alice").membre
    client.force_login(_staff())
    client.post(
        f"/bureau/gouvernance/reunion/{reunion.pk}/pouvoir/",
        {"mandant": membre.pk, "mandataire": membre.pk},
    )
    assert Pouvoir.objects.count() == 0  # refusé : mandant == mandataire


def test_resolution_adoptee_affichee(client, db):
    reunion = _reunion()
    client.force_login(_staff())
    client.post(
        f"/bureau/gouvernance/reunion/{reunion.pk}/resolution/",
        {
            "intitule": "Approbation des comptes",
            "texte": "",
            "type_majorite": Resolution.TypeMajorite.SIMPLE,
            "sujet": "",
            "nombre_pour": 10,
            "nombre_contre": 2,
            "nombre_abstention": 1,
            "ordre": 0,
        },
    )
    assert Resolution.objects.filter(intitule="Approbation des comptes").exists()
    corps = client.get(f"/bureau/gouvernance/reunion/{reunion.pk}/").content.decode()
    assert "Adoptée" in corps  # 10 pour / 12 exprimés > majorité simple


def test_preremplir_droits_de_vote(client, db):
    reunion = _reunion()
    membre = _membre("alice").membre
    Presence.objects.create(
        reunion=reunion, membre=membre, statut=Presence.Statut.PRESENT, peut_voter=False
    )
    saison = Saison.objects.create(nom="2025-2026")
    Adhesion.objects.create(
        membre=membre, saison=saison, statut=Adhesion.Statut.PAYEE, montant_verse=Decimal("20")
    )
    client.force_login(_staff())
    client.post(
        f"/bureau/gouvernance/reunion/{reunion.pk}/preremplir-votes/", {"saison": saison.pk}
    )
    presence = Presence.objects.get(reunion=reunion, membre=membre)
    assert presence.peut_voter is True  # membre à jour → droit de vote


# --- Adhésions (écran back-office) -----------------------------------------


def _donnees_adhesion(**extra):
    donnees = {
        "statut": Adhesion.Statut.PAYEE,
        "montant_attendu": "30",
        "montant_verse": "30",
        "date": "",
    }
    donnees.update(extra)
    return donnees


def test_adhesions_reservees_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get("/bureau/adhesions/").status_code == 403


def test_creer_adhesion_pour_une_personne_existante(client, db):
    membre = _membre("alice").membre
    saison = Saison.objects.create(nom="2025-2026")
    client.force_login(_staff())
    reponse = client.post(
        "/bureau/adhesions/nouvelle/", _donnees_adhesion(membre=membre.pk, saison=saison.pk)
    )
    assert reponse.status_code == 302
    adhesion = Adhesion.objects.get(membre=membre, saison=saison)
    assert adhesion.statut == Adhesion.Statut.PAYEE
    assert adhesion.montant_verse == Decimal("30")


def test_creer_adhesion_avec_nouvelle_personne_sans_compte(client, db):
    """Création à la volée : la personne est créée sans compte, puis rattachée."""
    saison = Saison.objects.create(nom="2025-2026")
    client.force_login(_staff())
    reponse = client.post(
        "/bureau/adhesions/nouvelle/",
        _donnees_adhesion(saison=saison.pk, **{"nouveau-prenom": "Théo", "nouveau-nom": "Bon"}),
    )
    assert reponse.status_code == 302
    membre = Membre.objects.get(nom="Bon")
    assert membre.a_un_compte is False
    assert Adhesion.objects.filter(membre=membre, saison=saison).exists()


def test_creer_adhesion_exige_une_personne(client, db):
    saison = Saison.objects.create(nom="2025-2026")
    client.force_login(_staff())
    reponse = client.post("/bureau/adhesions/nouvelle/", _donnees_adhesion(saison=saison.pk))
    assert reponse.status_code == 200  # réaffiché avec une erreur
    assert Adhesion.objects.count() == 0


def test_adhesion_unique_par_membre_et_saison(client, db):
    membre = _membre("alice").membre
    saison = Saison.objects.create(nom="2025-2026")
    Adhesion.objects.create(membre=membre, saison=saison, statut=Adhesion.Statut.PAYEE)
    client.force_login(_staff())
    reponse = client.post(
        "/bureau/adhesions/nouvelle/", _donnees_adhesion(membre=membre.pk, saison=saison.pk)
    )
    assert reponse.status_code == 200  # doublon refusé
    assert Adhesion.objects.filter(membre=membre, saison=saison).count() == 1


def test_editer_adhesion_change_le_statut(client, db):
    membre = _membre("alice").membre
    saison = Saison.objects.create(nom="2025-2026")
    adhesion = Adhesion.objects.create(
        membre=membre, saison=saison, statut=Adhesion.Statut.EN_ATTENTE
    )
    client.force_login(_staff())
    reponse = client.post(
        f"/bureau/adhesions/{adhesion.pk}/",
        _donnees_adhesion(membre=membre.pk, saison=saison.pk, statut=Adhesion.Statut.PAYEE),
    )
    assert reponse.status_code == 302
    adhesion.refresh_from_db()
    assert adhesion.statut == Adhesion.Statut.PAYEE


def test_supprimer_adhesion(client, db):
    membre = _membre("alice").membre
    saison = Saison.objects.create(nom="2025-2026")
    adhesion = Adhesion.objects.create(membre=membre, saison=saison)
    client.force_login(_staff())
    reponse = client.post(f"/bureau/adhesions/{adhesion.pk}/supprimer/")
    assert reponse.status_code == 302
    assert not Adhesion.objects.filter(pk=adhesion.pk).exists()


def test_liste_membres_signale_les_personnes_sans_compte(client, db):
    Membre.objects.create(prenom="Sans", nom="Compte")  # adhérent sans compte
    client.force_login(_staff())
    corps = client.get("/bureau/membres/").content.decode()
    assert "Sans compte" in corps


def test_ouvrir_acces_membre_cree_le_compte(client, db):
    membre = Membre.objects.create(prenom="Neo", nom="Phyte", email="neo@example.org")
    client.force_login(_staff())
    reponse = client.post(f"/bureau/membres/{membre.pk}/ouvrir-acces/")
    assert reponse.status_code == 200
    membre.refresh_from_db()
    assert membre.a_un_compte is True
    assert reponse.context["lien_activation"]


def test_ouvrir_acces_reserve_au_bureau_et_en_post(client, db):
    membre = Membre.objects.create(prenom="Neo", nom="Phyte", email="neo@example.org")
    url = f"/bureau/membres/{membre.pk}/ouvrir-acces/"
    client.force_login(_staff())
    assert client.get(url).status_code == 405  # require_POST
    client.force_login(_membre("lambda"))
    assert client.post(url).status_code == 403  # pas bureau


def test_liste_adhesions_s_affiche(client, db):
    membre = Membre.objects.create(prenom="Zoé", nom="Nadal")
    saison = Saison.objects.create(nom="2025-2026")
    Adhesion.objects.create(membre=membre, saison=saison, statut=Adhesion.Statut.PAYEE)
    client.force_login(_staff())
    reponse = client.get("/bureau/adhesions/")
    assert reponse.status_code == 200
    corps = reponse.content.decode()
    assert "2025-2026" in corps
    assert "Nadal Zoé" in corps  # nom de famille en premier


def test_creer_adhesion_formulaire_s_affiche(client, db):
    client.force_login(_staff())
    reponse = client.get("/bureau/adhesions/nouvelle/")
    assert reponse.status_code == 200
    assert "nouvelle personne" in reponse.content.decode().lower()  # bloc à la volée


def test_editer_membre_propose_d_ouvrir_un_acces(client, db):
    membre = Membre.objects.create(prenom="Ed", nom="Iteur", email="ed@example.org")
    client.force_login(_staff())
    reponse = client.get(f"/bureau/membres/{membre.pk}/")
    assert reponse.status_code == 200
    assert "Ouvrir un accès" in reponse.content.decode()  # section personne sans compte


# --- Tri des listes par en-tête de colonne ---------------------------------


def test_liste_membres_triable_par_email(client, db):
    Membre.objects.create(prenom="A", nom="Zed", email="z@example.org")
    Membre.objects.create(prenom="B", nom="Abbe", email="a@example.org")
    client.force_login(_staff())
    reponse = client.get("/bureau/membres/?tri=email")
    assert [m.email for m in reponse.context["membres"]] == ["a@example.org", "z@example.org"]
    assert reponse.context["tri_courant"] == "email"


def test_liste_membres_tri_descendant(client, db):
    Membre.objects.create(nom="Abbe")
    Membre.objects.create(nom="Zed")
    client.force_login(_staff())
    reponse = client.get("/bureau/membres/?tri=-nom")
    assert [m.nom for m in reponse.context["membres"]] == ["Zed", "Abbe"]


def test_liste_membres_tri_inconnu_retombe_sur_le_defaut(client, db):
    """Clé de tri hors whitelist → tri par défaut (nom), pas d'injection ORM."""
    Membre.objects.create(nom="Zed")
    Membre.objects.create(nom="Abbe")
    client.force_login(_staff())
    reponse = client.get("/bureau/membres/", {"tri": "; DROP TABLE"})
    assert [m.nom for m in reponse.context["membres"]] == ["Abbe", "Zed"]
    assert reponse.context["tri_courant"] == ""


def test_liste_adhesions_triable_par_montant_verse(client, db):
    saison = Saison.objects.create(nom="2025-2026")
    haut = Membre.objects.create(nom="Haut")
    bas = Membre.objects.create(nom="Bas")
    Adhesion.objects.create(membre=haut, saison=saison, montant_verse=Decimal("50"))
    Adhesion.objects.create(membre=bas, saison=saison, montant_verse=Decimal("10"))
    client.force_login(_staff())
    reponse = client.get("/bureau/adhesions/?tri=verse")
    assert [a.montant_verse for a in reponse.context["adhesions"]] == [
        Decimal("10"),
        Decimal("50"),
    ]


def test_liste_adhesions_tri_et_filtre_se_combinent(client, db):
    saison = Saison.objects.create(nom="2025-2026")
    m1 = Membre.objects.create(nom="Un")
    m2 = Membre.objects.create(nom="Deux")
    Adhesion.objects.create(membre=m1, saison=saison, statut=Adhesion.Statut.PAYEE)
    Adhesion.objects.create(membre=m2, saison=saison, statut=Adhesion.Statut.EN_ATTENTE)
    client.force_login(_staff())
    reponse = client.get("/bureau/adhesions/?statut=payee&tri=personne")
    adhesions = list(reponse.context["adhesions"])
    assert len(adhesions) == 1 and adhesions[0].membre == m1  # filtre conservé


# --- Pont adhésion -> reçu fiscal (dans l'écran Adhésions) -----------------


def test_adhesion_eligible_propose_d_emettre_un_recu(client, db):
    membre = _membre("alice").membre
    saison = Saison.objects.create(nom="2025-2026")
    Adhesion.objects.create(
        membre=membre, saison=saison, statut=Adhesion.Statut.PAYEE, montant_verse=Decimal("30")
    )
    client.force_login(_staff())
    corps = client.get("/bureau/adhesions/").content.decode()
    assert "Émettre un reçu" in corps


def test_adhesion_en_attente_ne_propose_pas_de_recu(client, db):
    membre = _membre("alice").membre
    saison = Saison.objects.create(nom="2025-2026")
    Adhesion.objects.create(
        membre=membre, saison=saison, statut=Adhesion.Statut.EN_ATTENTE, montant_verse=Decimal("0")
    )
    client.force_login(_staff())
    corps = client.get("/bureau/adhesions/").content.decode()
    assert "Émettre un reçu" not in corps


# --- Programmation : gestion directe des événements & projets (bureau) ------


def _donnees_evenement(**extra):
    donnees = {
        "titre": "Générale",
        "description": "",
        "date_debut": "2026-09-01T20:30",
        "date_fin": "",
        "lieu": "",
        "lieu_texte": "Théâtre X",
        "visibilite": Evenement.Visibilite.PUBLIC,
        "spectacle": "",
        "affiche_alt": "",
        "galerie_alt": "",
        "lignes-TOTAL_FORMS": "0",
        "lignes-INITIAL_FORMS": "0",
        "lignes-MIN_NUM_FORMS": "0",
        "lignes-MAX_NUM_FORMS": "1000",
    }
    donnees.update(extra)
    return donnees


def _donnees_projet(**extra):
    donnees = {
        "titre": "Nouveau spectacle",
        "synopsis": "",
        "note_intention": "",
        "type_portage": Spectacle.TypePortage.ASSOCIATION,
        "statut_projet": Spectacle.StatutProjet.EN_CREATION,
        "genre": "",
        "public_vise": "",
        "duree_minutes": "",
        "affiche_alt": "",
        "galerie_alt": "",
        "lignes-TOTAL_FORMS": "0",
        "lignes-INITIAL_FORMS": "0",
        "lignes-MIN_NUM_FORMS": "0",
        "lignes-MAX_NUM_FORMS": "1000",
    }
    donnees.update(extra)
    return donnees


def test_programmation_reservee_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get("/bureau/evenements/").status_code == 403
    assert client.get("/bureau/projets/").status_code == 403
    assert client.get("/bureau/evenements/nouveau/").status_code == 403


def test_bureau_cree_un_evenement_publie(client, db):
    bureau = _staff()
    client.force_login(bureau)
    reponse = client.post("/bureau/evenements/nouveau/", _donnees_evenement(action="publier"))
    assert reponse.status_code == 302
    evenement = Evenement.objects.get(titre="Générale")
    assert evenement.statut_moderation == Evenement.StatutModeration.PUBLIE
    assert evenement.valide_par == bureau
    assert evenement.date_publication is not None
    assert evenement.visibilite == Evenement.Visibilite.PUBLIC
    assert evenement.cree_par == bureau


def test_bureau_cree_un_evenement_en_brouillon(client, db):
    client.force_login(_staff())
    client.post("/bureau/evenements/nouveau/", _donnees_evenement(action="brouillon"))
    assert Evenement.objects.get().statut_moderation == Evenement.StatutModeration.BROUILLON


def test_bureau_edite_un_evenement_publie_sans_le_depublier(client, db):
    evenement = Evenement.objects.create(
        titre="Ancien titre",
        date_debut=make_aware(datetime(2026, 9, 1, 20, 30)),
        statut_moderation=Evenement.StatutModeration.PUBLIE,
        visibilite=Evenement.Visibilite.PUBLIC,
    )
    client.force_login(_staff())
    client.post(
        f"/bureau/evenements/{evenement.pk}/",
        _donnees_evenement(titre="Titre corrigé", action="publier"),
    )
    evenement.refresh_from_db()
    assert evenement.titre == "Titre corrigé"
    assert evenement.statut_moderation == Evenement.StatutModeration.PUBLIE


def test_bureau_ajoute_un_intervenant(client, db):
    membre = _membre("alice").membre
    client.force_login(_staff())
    client.post(
        "/bureau/evenements/nouveau/",
        _donnees_evenement(
            action="publier",
            **{
                "lignes-TOTAL_FORMS": "1",
                "lignes-0-membre": str(membre.pk),
                "lignes-0-role": "Comédienne",
            },
        ),
    )
    evenement = Evenement.objects.get()
    assert Intervention.objects.filter(evenement=evenement, membre=membre).exists()


def test_bureau_supprime_un_evenement(client, db):
    evenement = _evenement_propose("À supprimer")
    client.force_login(_staff())
    reponse = client.post(f"/bureau/evenements/{evenement.pk}/supprimer/")
    assert reponse.status_code == 302
    assert not Evenement.objects.filter(pk=evenement.pk).exists()


def test_liste_evenements_filtre_par_statut(client, db):
    Evenement.objects.create(
        titre="Zebre",
        date_debut=make_aware(datetime(2026, 9, 1, 20, 30)),
        statut_moderation=Evenement.StatutModeration.PUBLIE,
        visibilite=Evenement.Visibilite.PUBLIC,
    )
    Evenement.objects.create(
        titre="Alpha",
        date_debut=make_aware(datetime(2026, 10, 1, 20, 30)),
        statut_moderation=Evenement.StatutModeration.BROUILLON,
        visibilite=Evenement.Visibilite.MEMBRES,
    )
    client.force_login(_staff())
    corps = client.get("/bureau/evenements/?statut_moderation=publie").content.decode()
    assert "Zebre" in corps
    assert "Alpha" not in corps


def test_bureau_cree_un_projet_association(client, db):
    """Le bureau n'est pas restreint : `type_portage=association` (interdit au membre)."""
    client.force_login(_staff())
    client.post("/bureau/projets/nouveau/", _donnees_projet(action="publier"))
    projet = Spectacle.objects.get()
    assert projet.type_portage == Spectacle.TypePortage.ASSOCIATION
    assert projet.statut_moderation == Spectacle.StatutModeration.PUBLIE


def test_bureau_ajoute_une_ligne_de_distribution(client, db):
    membre = _membre("alice").membre
    client.force_login(_staff())
    client.post(
        "/bureau/projets/nouveau/",
        _donnees_projet(
            action="brouillon",
            **{
                "lignes-TOTAL_FORMS": "1",
                "lignes-0-membre": str(membre.pk),
                "lignes-0-nom_externe": "",
                "lignes-0-role": "Mise en scène",
            },
        ),
    )
    projet = Spectacle.objects.get()
    assert LigneDistribution.objects.filter(spectacle=projet, membre=membre).exists()


def test_distribution_refuse_membre_et_nom_externe(client, db):
    membre = _membre("alice").membre
    client.force_login(_staff())
    reponse = client.post(
        "/bureau/projets/nouveau/",
        _donnees_projet(
            action="brouillon",
            **{
                "lignes-TOTAL_FORMS": "1",
                "lignes-0-membre": str(membre.pk),
                "lignes-0-nom_externe": "Jean Externe",
                "lignes-0-role": "Rôle",
            },
        ),
    )
    assert reponse.status_code == 200  # formset invalide → rien créé
    assert Spectacle.objects.count() == 0


def test_formulaire_evenement_bureau_s_affiche(client, db):
    client.force_login(_staff())
    reponse = client.get("/bureau/evenements/nouveau/")
    assert reponse.status_code == 200
    assert "Intervenants" in reponse.content.decode()  # formset rendu


def test_liste_projets_bureau_s_affiche(client, db):
    _projet_propose("Mon spectacle")
    client.force_login(_staff())
    corps = client.get("/bureau/projets/").content.decode()
    assert "Mon spectacle" in corps


def test_bureau_ajoute_plusieurs_intervenants(client, db):
    alice = _membre("alice").membre
    bob = _membre("bob").membre
    client.force_login(_staff())
    client.post(
        "/bureau/evenements/nouveau/",
        _donnees_evenement(
            action="publier",
            **{
                "lignes-TOTAL_FORMS": "2",
                "lignes-0-membre": str(alice.pk),
                "lignes-0-role": "Comédienne",
                "lignes-1-membre": str(bob.pk),
                "lignes-1-role": "Technique",
            },
        ),
    )
    evenement = Evenement.objects.get()
    assert Intervention.objects.filter(evenement=evenement).count() == 2


def test_finances_reservee_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get("/bureau/finances/").status_code == 403


def test_finances_agrege_les_chiffres(client, db):
    saison = Saison.objects.create(nom="2025-2026")
    Facture.objects.create(client=Client.objects.create(nom="A"))  # brouillon → à valider
    Adhesion.objects.create(
        membre=_membre("adh").membre,
        saison=saison,
        statut=Adhesion.Statut.EN_ATTENTE,
        montant_attendu=Decimal("40.00"),
    )
    Devis.objects.create(
        client=Client.objects.create(nom="B"), date="2026-01-01", statut=Devis.Statut.ENVOYE
    )
    client.force_login(_staff())
    reponse = client.get("/bureau/finances/")
    assert reponse.status_code == 200
    assert reponse.context["saison"] == saison
    assert reponse.context["facturation"]["factures_a_valider"] == 1
    assert reponse.context["facturation"]["devis_a_suivre"] == 1
    assert reponse.context["cotisations"]["adhesions_en_attente"] == 1


def test_budget_met_a_jour_le_solde_de_tresorerie(client, db):
    client.force_login(_staff())
    reponse = client.post(
        "/bureau/budget/",
        {"montant": "3200.00", "date_pointage": "2026-06-30", "note": "relevé de juin"},
    )
    assert reponse.status_code == 302
    solde = SoldeTresorerie.charger()
    assert solde.montant == Decimal("3200.00")
    assert str(solde.date_pointage) == "2026-06-30"


def test_budget_affiche_le_panneau_tresorerie(client, db):
    Saison.objects.create(nom="2025-2026")
    client.force_login(_staff())
    corps = client.get("/bureau/budget/").content.decode()
    assert "Solde en banque" in corps


def test_facturation_onglets_accessibles(client, db):
    client.force_login(_staff())
    for onglet in ("devis", "factures", "avoirs"):
        reponse = client.get(f"/bureau/facturation/?onglet={onglet}")
        assert reponse.status_code == 200
        assert reponse.context["onglet"] == onglet


def test_facturation_separe_factures_et_avoirs(client, db):
    c = Client.objects.create(nom="Théâtre")
    facture = Facture.objects.create(client=c)  # type FACTURE par défaut
    avoir = Facture.objects.create(client=c, type_piece=Facture.TypePiece.AVOIR)
    client.force_login(_staff())
    factures = client.get("/bureau/facturation/?onglet=factures").context["objets"].object_list
    avoirs = client.get("/bureau/facturation/?onglet=avoirs").context["objets"].object_list
    assert facture in factures and avoir not in factures
    assert avoir in avoirs and facture not in avoirs


def test_anciennes_urls_facturation_redirigent(client, db):
    client.force_login(_staff())
    r_factures = client.get("/bureau/factures/")
    r_devis = client.get("/bureau/devis/")
    assert r_factures.status_code == 302 and "onglet=factures" in r_factures["Location"]
    assert r_devis.status_code == 302 and "onglet=devis" in r_devis["Location"]


def test_gouvernance_enregistre_les_notes(client, db):
    reunion = Reunion.objects.create(titre="AG", type_reunion=Reunion.TypeReunion.AG_ORDINAIRE)
    sujet = Sujet.objects.create(
        titre="Point 1", reunion=reunion, statut=Sujet.Statut.ORDRE_DU_JOUR
    )
    client.force_login(_staff())
    client.post(
        f"/bureau/gouvernance/reunion/{reunion.pk}/notes/",
        {"synthese": "RAS", f"notes_{sujet.pk}": "Adopté"},
    )
    reunion.refresh_from_db()
    sujet.refresh_from_db()
    assert reunion.compte_rendu_texte == "RAS"
    assert sujet.notes == "Adopté"


def test_gouvernance_genere_le_pv_depuis_l_ecran(client, db, monkeypatch):
    monkeypatch.setattr("apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: b"%PDF")
    reunion = Reunion.objects.create(titre="AG", type_reunion=Reunion.TypeReunion.AG_ORDINAIRE)
    client.force_login(_staff())
    reponse = client.post(f"/bureau/gouvernance/reunion/{reunion.pk}/pv/")
    assert reponse.status_code == 302
    reunion.refresh_from_db()
    assert reunion.compte_rendu_id is not None


def test_gouvernance_edite_une_reunion(client, db):
    reunion = Reunion.objects.create(
        titre="AG",
        type_reunion=Reunion.TypeReunion.AG_ORDINAIRE,
        statut=Reunion.Statut.PREPARATION,
    )
    client.force_login(_staff())
    reponse = client.post(
        f"/bureau/gouvernance/reunion/{reunion.pk}/modifier/",
        {
            "titre": "AG 2026",
            "type_reunion": Reunion.TypeReunion.AG_ORDINAIRE,
            "statut": Reunion.Statut.CONVOQUEE,
            "lieu_texte": "Salle B",
            "convocation_texte": "Venez nombreux.",
        },
    )
    assert reponse.status_code == 302
    reunion.refresh_from_db()
    assert reunion.titre == "AG 2026"
    assert reunion.statut == Reunion.Statut.CONVOQUEE  # transition de statut via l'édition


def test_gouvernance_edition_reservee_au_bureau(client, db):
    reunion = Reunion.objects.create(titre="AG", type_reunion=Reunion.TypeReunion.AG_ORDINAIRE)
    client.force_login(_membre("edit_lambda"))
    assert client.get(f"/bureau/gouvernance/reunion/{reunion.pk}/modifier/").status_code == 403


def test_gouvernance_ajoute_un_bloc_de_recit(client, db):
    reunion = Reunion.objects.create(titre="AG", type_reunion=Reunion.TypeReunion.AG_ORDINAIRE)
    sujet = Sujet.objects.create(
        titre="Point 1", reunion=reunion, statut=Sujet.Statut.ORDRE_DU_JOUR
    )
    client.force_login(_staff())
    # Bloc en préambule
    client.post(
        f"/bureau/gouvernance/reunion/{reunion.pk}/bloc/",
        {"apres_sujet": "", "titre": "Préambule", "texte": "Contexte d'ouverture"},
    )
    # Bloc rattaché à un point
    client.post(
        f"/bureau/gouvernance/reunion/{reunion.pk}/bloc/",
        {"apres_sujet": str(sujet.pk), "titre": "", "texte": "Transition"},
    )
    assert reunion.blocs.count() == 2
    intro = reunion.blocs.get(titre="Préambule")
    assert intro.apres_sujet_id is None
    assert reunion.blocs.get(texte="Transition").apres_sujet_id == sujet.pk


def test_gouvernance_edite_et_supprime_un_bloc(client, db):
    reunion = Reunion.objects.create(titre="AG", type_reunion=Reunion.TypeReunion.AG_ORDINAIRE)
    b1 = BlocCompteRendu.objects.create(reunion=reunion, texte="ancien")
    b2 = BlocCompteRendu.objects.create(reunion=reunion, texte="à supprimer")
    client.force_login(_staff())
    client.post(
        f"/bureau/gouvernance/reunion/{reunion.pk}/notes/",
        {
            "synthese": "",
            f"bloc_{b1.pk}_titre": "Titre",
            f"bloc_{b1.pk}_texte": "nouveau",
            f"bloc_{b2.pk}_texte": "peu importe",
            "supprimer_bloc": str(b2.pk),
        },
    )
    b1.refresh_from_db()
    assert b1.texte == "nouveau" and b1.titre == "Titre"
    assert not BlocCompteRendu.objects.filter(pk=b2.pk).exists()


def test_backoffice_formulaire_lie_l_aide_via_aria_describedby(db):
    """Accessibilité (WCAG 1.3.1) : l'aide des champs bureau est reliée au widget
    via aria-describedby, avec un id présent dans le gabarit."""
    from apps.backoffice.forms import IdentiteAssociationForm

    html = str(IdentiteAssociationForm()["mention_tva"])
    assert 'aria-describedby="id_mention_tva_aide"' in html


# --- Tableau de bord budgétaire (BUD-1) -------------------------------------


def _mouvement(saison, categorie, type_flux, statut, montant):
    return Transaction.objects.create(
        type_flux=type_flux,
        statut=statut,
        libelle="mouvement",
        montant=Decimal(montant),
        date=date(2026, 3, 1),
        categorie=categorie,
        saison=saison,
    )


def test_bilan_affiche_le_tableau_de_bord(client, db):
    saison = Saison.objects.create(nom="2025-2026")
    subventions = Categorie.objects.create(nom="Subventions")
    materiel = Categorie.objects.create(nom="Matériel")
    _mouvement(saison, subventions, Transaction.TypeFlux.RECETTE, Transaction.Statut.REALISE, "800")
    _mouvement(saison, materiel, Transaction.TypeFlux.DEPENSE, Transaction.Statut.PREVU, "300")
    _mouvement(saison, materiel, Transaction.TypeFlux.DEPENSE, Transaction.Statut.REALISE, "250")

    client.force_login(_staff())
    corps = client.get("/bureau/budget/bilan/").content.decode()

    assert "Recettes réalisées" in corps
    assert "Réalisé face au budget" in corps
    assert "Où partent les dépenses" in corps
    # Le tableau détaillé reste sur la page : c'est le jumeau accessible des
    # graphiques, et il porte les valeurs que les barres ne disent pas.
    assert "Détail par catégorie" in corps


def test_bilan_ecrit_les_largeurs_avec_un_point_decimal(client, db):
    """Le projet tourne en `LANGUAGE_CODE = "fr-fr"`. Un pourcentage rendu
    « 12,5 » produirait `style="width: 12,5%"` — une déclaration invalide, donc
    une barre à zéro. La part traverse le gabarit sous forme de chaîne."""
    saison = Saison.objects.create(nom="2025-2026")
    _mouvement(
        saison,
        Categorie.objects.create(nom="Petite"),
        Transaction.TypeFlux.DEPENSE,
        Transaction.Statut.REALISE,
        "125",
    )
    _mouvement(
        saison,
        Categorie.objects.create(nom="Grosse"),
        Transaction.TypeFlux.DEPENSE,
        Transaction.Statut.REALISE,
        "875",
    )

    client.force_login(_staff())
    corps = client.get("/bureau/budget/bilan/").content.decode()

    assert "flex-basis: 12.5%" in corps
    assert "flex-basis: 12,5%" not in corps
    assert "width: 100%" in corps  # la plus grosse barre occupe toute l'échelle


def test_bilan_sans_saison_n_affiche_pas_de_graphiques(client, db):
    client.force_login(_staff())
    reponse = client.get("/bureau/budget/bilan/")

    assert reponse.status_code == 200
    assert "tuiles" not in reponse.context
    assert "Créez d'abord une saison" in reponse.content.decode()


def test_le_hub_finances_mene_au_tableau_de_bord(client, db):
    """Le hub route vers les sections : sans ce lien, le tableau de bord ne
    s'atteint qu'en passant par Mouvements puis en changeant d'onglet."""
    client.force_login(_staff())
    corps = client.get("/bureau/finances/").content.decode()

    assert "/bureau/budget/bilan/" in corps


# --- Inscriptions du public (VIT-2) -----------------------------------------


def test_le_bureau_regle_la_jauge_d_un_evenement(client, db):
    """Sans ce champ au formulaire, la jauge ne serait réglable que depuis
    l'admin Django et la feuille d'inscription resterait inaccessible."""
    evenement = Evenement.objects.create(
        titre="Représentation",
        date_debut=make_aware(datetime(2026, 11, 1, 20, 0)),
        statut_moderation=Evenement.StatutModeration.PUBLIE,
    )
    client.force_login(_staff())

    client.post(
        f"/bureau/evenements/{evenement.pk}/",
        _donnees_evenement(titre="Représentation", places_max="50", action="publier"),
    )

    evenement.refresh_from_db()
    assert evenement.places_max == 50


def test_le_bureau_voit_qui_s_est_inscrit(client, db):
    evenement = Evenement.objects.create(
        titre="Représentation",
        date_debut=make_aware(datetime(2026, 11, 1, 20, 0)),
        places_max=20,
        statut_moderation=Evenement.StatutModeration.PUBLIE,
    )
    agenda_services.inscrire(evenement, nom="Camille Martin", email="camille@example.org", places=3)
    client.force_login(_staff())

    corps = client.get(f"/bureau/evenements/{evenement.pk}/inscriptions/").content.decode()

    assert "Camille Martin" in corps
    assert "camille@example.org" in corps


def test_la_feuille_des_inscrits_est_reservee_au_bureau(client, db):
    evenement = Evenement.objects.create(
        titre="Représentation",
        date_debut=make_aware(datetime(2026, 11, 1, 20, 0)),
        places_max=20,
    )
    reponse = client.get(f"/bureau/evenements/{evenement.pk}/inscriptions/")
    assert reponse.status_code in (302, 403, 404)


# --- Duplication de facture (FAC-1) -----------------------------------------


def test_le_bureau_duplique_une_facture_validee(client, db):
    c = Client.objects.create(nom="Théâtre")
    facture = Facture.objects.create(client=c, objet="Représentation")
    LigneFacture.objects.create(
        facture=facture, designation="Cachet", quantite=2, prix_unitaire_ht=Decimal("300")
    )
    valider_facture(facture, date_emission=date(2026, 3, 1))
    client.force_login(_staff())

    reponse = client.post(f"/bureau/factures/{facture.pk}/dupliquer/")

    copie = Facture.objects.exclude(pk=facture.pk).get()
    assert reponse.status_code == 302
    assert reponse.url == f"/bureau/factures/{copie.pk}/"
    assert copie.numero is None
    assert copie.lignes.count() == 1


def test_l_ecran_d_une_facture_propose_de_la_dupliquer(client, db):
    """Sans ce bouton, la duplication n'existerait que pour qui connaît l'URL."""
    c = Client.objects.create(nom="Théâtre")
    facture = Facture.objects.create(client=c)
    valider_facture(facture, date_emission=date(2026, 3, 1))
    client.force_login(_staff())

    corps = client.get(f"/bureau/factures/{facture.pk}/").content.decode()

    assert f"/bureau/factures/{facture.pk}/dupliquer/" in corps


def test_la_duplication_est_reservee_au_bureau(client, db):
    c = Client.objects.create(nom="Théâtre")
    facture = Facture.objects.create(client=c)
    reponse = client.post(f"/bureau/factures/{facture.pk}/dupliquer/")
    assert reponse.status_code in (302, 403, 404)
    assert Facture.objects.count() == 1


def test_l_ordre_des_lignes_suit_leur_position_dans_le_formulaire(client, db):
    """L'invariant sur lequel repose le déplacement côté client : les valeurs
    postées à l'index N deviennent la ligne N. Le JS se contente d'échanger les
    valeurs entre deux lignes — c'est le serveur qui fixe l'ordre."""
    c = Client.objects.create(nom="Théâtre")
    facture = Facture.objects.create(client=c)
    client.force_login(_staff())

    client.post(
        f"/bureau/factures/{facture.pk}/",
        {
            "client": str(c.pk),
            "objet": "Tournée",
            "date_echeance": "",
            "mentions_legales": "",
            "signataire": "",
            "lignes-TOTAL_FORMS": "2",
            "lignes-INITIAL_FORMS": "0",
            "lignes-MIN_NUM_FORMS": "0",
            "lignes-MAX_NUM_FORMS": "1000",
            "lignes-0-designation": "Transport",
            "lignes-0-quantite": "1",
            "lignes-0-prix_unitaire_ht": "80",
            "lignes-0-taux_tva": "20",
            "lignes-1-designation": "Cachet",
            "lignes-1-quantite": "1",
            "lignes-1-prix_unitaire_ht": "300",
            "lignes-1-taux_tva": "20",
        },
    )

    assert [ligne.designation for ligne in facture.lignes.all()] == ["Transport", "Cachet"]
    assert [ligne.ordre for ligne in facture.lignes.all()] == [0, 1]


def test_l_editeur_propose_de_deplacer_une_ligne(client, db):
    c = Client.objects.create(nom="Théâtre")
    facture = Facture.objects.create(client=c)
    LigneFacture.objects.create(
        facture=facture, designation="Cachet", quantite=1, prix_unitaire_ht=Decimal("300")
    )
    client.force_login(_staff())

    corps = client.get(f"/bureau/factures/{facture.pk}/").content.decode()

    assert "data-monter-ligne" in corps
    assert "data-descendre-ligne" in corps


def test_le_bureau_ajoute_un_interlocuteur_public(client, db):
    """L'écran « Page Contact » porte le formset des contacts : le bureau saisit
    ses interlocuteurs sans passer par l'admin Django."""
    from apps.coeur.models import ContactPublic, ParametresAssociation

    client.force_login(_staff())
    reponse = client.post(
        "/bureau/parametres/contact/",
        {
            "email_public": "bonjour@improliante.test",
            "telephone_public": "",
            "contacts_publics-TOTAL_FORMS": "1",
            "contacts_publics-INITIAL_FORMS": "0",
            "contacts_publics-MIN_NUM_FORMS": "0",
            "contacts_publics-MAX_NUM_FORMS": "1000",
            "contacts_publics-0-role": "Réservations",
            "contacts_publics-0-nom": "Camille Roux",
            "contacts_publics-0-email": "resa@improliante.test",
            "contacts_publics-0-telephone": "",
            "contacts_publics-0-ordre": "1",
        },
    )

    assert reponse.status_code == 302
    assert ParametresAssociation.load().email_public == "bonjour@improliante.test"
    contact = ContactPublic.objects.get()
    assert (contact.role, contact.nom) == ("Réservations", "Camille Roux")


# --- Densité de l'espace connecté -------------------------------------------
#
# Mesuré avant correction sur le tableau de bord bureau : 37 cibles de
# navigation à l'écran (8 en-tête + 19 rail + 10 cartes « Modules ») pour 4
# tuiles d'information, et 7 des 8 liens de la page dupliquaient le rail.


def test_l_entete_ne_deploie_pas_la_nav_publique_dans_l_espace_connecte(client, db):
    """Le rail porte déjà la navigation : déployer en plus les six liens publics
    mettait deux navigations concurrentes à l'écran."""
    client.force_login(_staff())

    corps = client.get("/bureau/").content.decode()
    entete = corps.split("<header", 1)[1].split("</header>", 1)[0]

    assert "Voir le site" in entete
    for lien_public in ("Galerie", "Spectacles", "Agenda", "L'association"):
        assert lien_public not in entete, lien_public


def test_le_tableau_de_bord_ne_reprend_plus_les_entrees_du_rail(client, db):
    """La grille « Modules » rouvrait dix destinations déjà dans le rail, sans
    rien en dire : de la navigation en double.

    Le même invariant vaut sur le tableau de bord MEMBRE — d'où la fonction
    partagée dans `conftest.py` plutôt qu'une règle réécrite de chaque côté.
    """
    from conftest import liens_nus_rouvrant_le_rail

    client.force_login(_staff())
    corps = client.get("/bureau/").content.decode()

    assert "Modules" not in corps.split('<main id="contenu"', 1)[1]
    nus = liens_nus_rouvrant_le_rail(corps)
    # « Ouvrir la file de modération » suit une liste nommée : elle apprend
    # quelque chose même sans chiffre. Dix liens nus, c'était le menu recopié.
    assert len(nus) <= 2, "liens nus rouvrant le rail :\n  " + "\n  ".join(nus)


def test_le_tableau_de_bord_nomme_ce_qui_attend_une_decision(client, db):
    """Une tuile qui affiche « 3 » ne dit pas QUOI : le tableau de bord liste
    les fiches en attente, pas seulement leur nombre."""
    _projet_propose(titre="Cabaret de printemps")
    client.force_login(_staff())

    contenu = client.get("/bureau/").content.decode().split('<main id="contenu"', 1)[1]

    assert "En attente d'une décision" in contenu
    assert "Cabaret de printemps" in contenu


def test_chaque_page_du_rail_se_repere_une_fois_et_une_seule(client, db):
    """Depuis que le rail ne déplie que le groupe courant, une page dont aucune
    entrée ne porte `aria-current` ouvre le premier groupe par défaut : on perd
    le repère de position. Ce test parcourt toutes les destinations du rail et
    exige que chacune s'y reconnaisse **exactement une fois**.

    Deux positions valides, et pas trois : dans un groupe (le groupe s'ouvre), ou
    hors groupe (« Vue d'ensemble », racine de l'espace — aucun groupe ne
    s'ouvre, et navigation.js doit distinguer ce cas de l'écran sans entrée du
    tout). Ce qui reste interdit : zéro marque, deux marques, ou un marquage
    partagé par deux groupes.

    Il couvre les conditions fragiles du gabarit, du type `{% if 'facture' in
    vn %}` : une URL renommée les casse en silence.
    """
    import re

    client.force_login(_staff())
    rail = client.get("/bureau/").content.decode().split('<nav id="nav-espace"', 1)[1]
    rail = rail.split("</nav>", 1)[0]
    destinations = sorted(set(re.findall(r'href="(/(?:bureau|espace)/[^"#?]*)"', rail)))
    assert len(destinations) >= 15, f"{len(destinations)} destinations : le rail a rétréci"

    fautives = []
    testees = 0
    hors_groupe = []
    for url in destinations:
        reponse = client.get(url)
        if reponse.status_code != 200:
            continue
        testees += 1
        corps = reponse.content.decode().split('<nav id="nav-espace"', 1)[1].split("</nav>", 1)[0]
        # Découper sur `<details>…</details>` et NON sur `"<details"` : depuis
        # qu'une entrée vit hors groupe, un simple split ferait porter au groupe
        # précédent tout ce qui le suit — et un rail hors groupe passerait pour
        # un groupe marqué. Les <details> ne s'imbriquent pas ici.
        groupes = re.findall(r"<details\b.*?</details>", corps, re.S)
        marques = sum('aria-current="page"' in g for g in groupes)
        total = corps.count('aria-current="page"')
        if total != 1:
            fautives.append(f"{url} → {total} entrée(s) marquée(s) dans le rail")
        elif marques > 1:
            fautives.append(f"{url} → {marques} groupes marqués à la fois")
        elif marques == 0:
            hors_groupe.append(url)

    assert testees >= 15, f"{testees} pages réellement testées sur {len(destinations)}"
    assert not fautives, "position non reconnue dans le rail :\n  " + "\n  ".join(fautives)
    # L'entrée hors groupe est une exception nommée, pas une porte ouverte : si
    # elle s'étendait à d'autres écrans, le rail perdrait ses groupes en silence.
    assert hors_groupe == ["/bureau/"], f"entrées hors groupe inattendues : {hors_groupe}"


# --- Messages de contact et signaux du tableau de bord -----------------------
#
# `MessageContact` était écrit par le formulaire public et lu UNIQUEMENT par
# l'admin Django : le site déposait des messages dans une boîte que l'interface
# métier n'ouvrait pas. Le champ `traite` existait et n'était jamais basculé.


def _message(nom="Camille", traite=False):
    from apps.vitrine.models import MessageContact

    return MessageContact.objects.create(
        nom=nom, email=f"{nom.lower()}@x.test", message="Bonjour", traite=traite
    )


def test_les_messages_recus_sont_lisibles_hors_admin(client, db):
    _message("Camille")
    client.force_login(_staff())

    corps = client.get("/bureau/messages/").content.decode()

    assert "Camille" in corps
    assert "camille@x.test" in corps


def test_la_liste_des_messages_montre_d_abord_ce_qui_reste_a_traiter(client, db):
    _message("Nonlu", traite=False)
    _message("Deja", traite=True)
    client.force_login(_staff())

    a_traiter = client.get("/bureau/messages/").content.decode()
    tous = client.get("/bureau/messages/?etat=tous").content.decode()

    assert "Nonlu" in a_traiter and "Deja" not in a_traiter
    assert "Nonlu" in tous and "Deja" in tous


def test_marquer_un_message_traite_le_sort_de_la_liste(client, db):
    from apps.vitrine.models import MessageContact

    message = _message("Camille")
    client.force_login(_staff())

    reponse = client.post(
        "/bureau/messages/", {"message": message.pk, "action": "traiter"}, follow=True
    )

    assert reponse.status_code == 200
    message.refresh_from_db()
    assert message.traite is True
    assert MessageContact.objects.filter(traite=False).count() == 0


def test_le_tableau_de_bord_nomme_les_factures_echues(client, db):
    """`date_echeance` était saisie et imprimée sans jamais être comparée à la
    date du jour : une facture validée impayée depuis six mois n'alertait rien.
    Et un compteur qui dit « 2 » ne dit pas lesquelles — on veut le nom."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.facturation.models import Client as ClientFacture
    from apps.facturation.models import Facture

    Facture.objects.create(
        client=ClientFacture.objects.create(nom="Théâtre du Nord"),
        statut=Facture.Statut.VALIDEE,
        date_echeance=timezone.localdate() - timedelta(days=30),
    )
    client.force_login(_staff())

    reponse = client.get("/bureau/")
    contenu = reponse.content.decode().split('<main id="contenu"', 1)[1]

    assert [r["genre"] for r in reponse.context["en_retard"]] == ["Facture"]
    assert "Théâtre du Nord" in contenu
    assert "impayée depuis 30 jours" in contenu


def test_une_reunion_convoquee_et_passee_est_signalee(client, db):
    """L'application ne demandait QUE les réunions `date >= maintenant` : une
    assemblée tenue mais jamais basculée en « tenue » — donc sans compte-rendu
    ni résolutions actées — tombait dans un angle mort."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.gouvernance.models import Reunion

    Reunion.objects.create(
        titre="Assemblée générale 2026",
        statut=Reunion.Statut.CONVOQUEE,
        date=timezone.now() - timedelta(days=21),
    )
    client.force_login(_staff())

    reponse = client.get("/bureau/")
    contenu = reponse.content.decode().split('<main id="contenu"', 1)[1]

    assert [r["genre"] for r in reponse.context["en_retard"]] == ["Réunion"]
    assert "Assemblée générale 2026" in contenu
    assert "sans compte-rendu" in contenu


def test_une_reunion_a_venir_n_est_pas_comptee_en_retard(client, db):
    """La borne de temps est le seul critère : sans elle, toute réunion
    convoquée passerait pour un retard."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.gouvernance.models import Reunion

    Reunion.objects.create(
        titre="Bureau de rentrée",
        statut=Reunion.Statut.CONVOQUEE,
        date=timezone.now() + timedelta(days=7),
    )
    client.force_login(_staff())

    assert client.get("/bureau/").context["en_retard"] == []


def test_une_cotisation_payee_sans_recu_est_signalee(client, db):
    """`RecuFiscal.adhesion` existe : le lien se déduit, et personne ne le
    déduisait. Le membre a payé, il y a droit, nul ne le sait."""
    from apps.budget.models import Adhesion, Saison
    from apps.coeur.models import Membre

    saison = Saison.objects.create(nom="2026", date_debut="2026-01-01", date_fin="2026-12-31")
    Adhesion.objects.create(
        membre=Membre.objects.create(nom="Roux", prenom="Camille"),
        saison=saison,
        statut=Adhesion.Statut.PAYEE,
    )
    client.force_login(_staff())

    signaux = client.get("/bureau/").context["signaux"]
    par_label = {s["label"]: s["nombre"] for s in signaux}

    assert par_label["cotisation(s) payée(s) sans reçu fiscal"] == 1


def test_le_tableau_de_bord_signale_les_cotisations_et_les_messages(client, db):
    from apps.budget.models import Adhesion, Saison
    from apps.coeur.models import Membre

    membre = Membre.objects.create(nom="Roux", prenom="Camille")
    saison = Saison.objects.create(nom="2026", date_debut="2026-01-01", date_fin="2026-12-31")
    Adhesion.objects.create(membre=membre, saison=saison, statut=Adhesion.Statut.EN_ATTENTE)
    _message("Camille")
    client.force_login(_staff())

    signaux = client.get("/bureau/").context["signaux"]
    par_label = {s["label"]: s["nombre"] for s in signaux}

    assert par_label["cotisation(s) en attente de paiement"] == 1
    assert par_label["message(s) reçu(s) à traiter"] == 1
