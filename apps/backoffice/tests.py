"""Tests du back-office : contrôle d'accès bureau + validation de modération."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import make_aware

from apps.agenda.models import Evenement
from apps.budget.models import Adhesion, Categorie, RecuFiscal, Saison, Transaction
from apps.budget.services import emettre_recu
from apps.coeur.models import Membre, Signataire, Utilisateur
from apps.coeur.roles import NOM_GROUPE_BUREAU
from apps.common.models import Moderation
from apps.documents.models import Document, Dossier
from apps.facturation.models import Client, Devis, Facture, LigneDevis, LigneFacture
from apps.gouvernance.models import Pouvoir, Presence, Resolution, Reunion, Sujet
from apps.spectacles.models import Spectacle

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


def test_parametres_reserve_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get("/bureau/parametres/").status_code == 403


def test_editer_parametres_association(client, db):
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
    reponse = client.post("/bureau/membres/nouveau/", _donnees_nouveau_membre())
    assert reponse.status_code == 200  # page réaffichée avec le lien d'activation

    user = Utilisateur.objects.get(email="camille.martin@example.org")
    assert user.username == "camille.martin@example.org"  # e-mail = identifiant
    assert user.has_usable_password() is False  # activation requise avant connexion
    assert hasattr(user, "membre")
    assert reponse.context["lien_activation"]  # lien affiché au bureau
    assert est_bureau(user) is False  # un nouveau membre n'a PAS l'accès bureau


def test_creation_membre_refuse_un_email_deja_pris(client, db):
    Utilisateur.objects.create_user(
        username="camille.martin@example.org",
        email="camille.martin@example.org",
        password="x",
    )
    client.force_login(_staff())
    reponse = client.post("/bureau/membres/nouveau/", _donnees_nouveau_membre())
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

    # L'adhésion n'est plus proposée comme éligible.
    page = client.get(RECUS)
    assert adhesion not in list(page.context["adhesions"])


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
        facture=facture, designation="Ligne A", quantite=Decimal("1"),
        prix_unitaire_ht=Decimal("10"), ordre=0,
    )
    ligne_b = LigneFacture.objects.create(
        facture=facture, designation="Ligne B", quantite=Decimal("1"),
        prix_unitaire_ht=Decimal("20"), ordre=1,
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


# --- GED --------------------------------------------------------------------


def test_ged_reservee_au_bureau(client, db):
    client.force_login(_membre("lambda"))
    assert client.get("/bureau/documents/").status_code == 403


def test_creer_dossier_racine(client, db):
    client.force_login(_staff())
    client.post("/bureau/documents/", {"form_type": "dossier", "nom": "Statuts", "description": ""})
    dossier = Dossier.objects.get(nom="Statuts")
    assert dossier.depth == 1  # dossier racine


def test_creer_sous_dossier(client, db):
    racine = Dossier.add_root(nom="Vie associative")
    client.force_login(_staff())
    client.post(
        f"/bureau/documents/dossier/{racine.pk}/",
        {"form_type": "dossier", "nom": "PV d'AG", "description": ""},
    )
    enfant = Dossier.objects.get(nom="PV d'AG")
    assert enfant.depth == 2
    assert enfant.get_parent().nom == "Vie associative"


def test_televerser_document_dans_un_dossier(client, db):
    bureau = _staff()
    dossier = Dossier.add_root(nom="Documents")
    client.force_login(bureau)
    client.post(
        f"/bureau/documents/dossier/{dossier.pk}/",
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
        f"/bureau/documents/{ancien.pk}/nouvelle-version/",
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
    factures = list(client.get("/bureau/factures/?statut=brouillon").context["factures"])
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
    page1 = client.get("/bureau/factures/").context["page"]
    assert page1.paginator.num_pages == 2
    assert len(page1.object_list) == 20
    page2 = client.get("/bureau/factures/?page=2").context["page"]
    assert len(page2.object_list) == 5


def test_pagination_page_non_numerique_toleree(client, db):
    Client.objects.create(nom="X")
    client.force_login(_staff())
    # ?page=abc ne doit pas planter (get_page renvoie la 1re page).
    assert client.get("/bureau/factures/?page=abc").status_code == 200


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
