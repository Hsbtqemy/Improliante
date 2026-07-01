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
