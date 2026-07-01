"""Tests de l'espace membre : accès protégé + anti-IDOR."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import make_aware

from apps.agenda.models import Evenement
from apps.budget.models import Adhesion, RecuFiscal, Saison
from apps.budget.services import emettre_recu
from apps.coeur.models import Membre, Utilisateur
from apps.common.models import Moderation
from apps.documents.models import Document
from apps.gouvernance.models import Pouvoir, Presence, Reunion, Sujet
from apps.spectacles.models import Spectacle

Statut = Moderation.StatutModeration


def _membre(username):
    user = Utilisateur.objects.create_user(username=username, password="motdepasse")
    return Membre.objects.create(user=user)


def _document(confidentialite, *, cree_par=None, titre="Doc", contenu=b"%PDF-1.4 secret"):
    return Document.objects.create(
        titre=titre,
        confidentialite=confidentialite,
        cree_par=cree_par,
        fichier=SimpleUploadedFile(f"{titre}.pdf", contenu, content_type="application/pdf"),
    )


def test_tableau_de_bord_exige_la_connexion(client, db):
    reponse = client.get("/espace/")
    assert reponse.status_code == 302
    assert "/connexion/" in reponse.url


def test_tableau_de_bord_montre_l_adhesion_du_membre(client, db):
    membre = _membre("alice")
    saison = Saison.objects.create(nom="2025-2026")
    Adhesion.objects.create(
        membre=membre, saison=saison, statut=Adhesion.Statut.PAYEE, montant_verse=Decimal("20.00")
    )
    client.force_login(membre.user)
    corps = client.get("/espace/").content.decode()
    assert "2025-2026" in corps


def test_le_membre_ne_voit_que_ses_propres_adhesions(client, db):
    saison = Saison.objects.create(nom="2025-2026")
    membre1 = _membre("membre1")
    Adhesion.objects.create(membre=membre1, saison=saison, montant_verse=Decimal("42.00"))
    membre2 = _membre("membre2")
    Adhesion.objects.create(membre=membre2, saison=saison, montant_verse=Decimal("999.00"))

    client.force_login(membre1.user)
    corps = client.get("/espace/").content.decode()
    assert "42" in corps
    assert "999" not in corps  # anti-IDOR : pas les données d'un autre membre


# --- Projets du membre : création, soumission, anti-IDOR par objet ---------


def _donnees_projet(**extra):
    donnees = {
        "titre": "Mon spectacle",
        "type_portage": Spectacle.TypePortage.PERSONNEL,
        "synopsis": "",
        "note_intention": "",
        "statut_projet": Spectacle.StatutProjet.EN_CREATION,
        "genre": "",
        "public_vise": "",
        "duree_minutes": "",
    }
    donnees.update(extra)
    return donnees


def test_creer_projet_exige_la_connexion(client, db):
    reponse = client.get("/espace/projets/nouveau/")
    assert reponse.status_code == 302
    assert "/connexion/" in reponse.url


def test_membre_cree_un_projet_en_brouillon(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    reponse = client.post("/espace/projets/nouveau/", _donnees_projet(action="enregistrer"))
    assert reponse.status_code == 302
    projet = Spectacle.objects.get()
    assert projet.statut_moderation == Statut.BROUILLON
    assert projet.cree_par == membre.user
    assert membre in projet.porteurs.all()  # le créateur devient porteur


def test_membre_soumet_un_projet_a_la_creation(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    client.post("/espace/projets/nouveau/", _donnees_projet(action="soumettre"))
    projet = Spectacle.objects.get()
    assert projet.statut_moderation == Statut.PROPOSE


def test_membre_ne_peut_pas_declarer_un_projet_association(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    reponse = client.post(
        "/espace/projets/nouveau/",
        _donnees_projet(type_portage=Spectacle.TypePortage.ASSOCIATION, action="enregistrer"),
    )
    assert reponse.status_code == 200  # formulaire réaffiché : choix invalide
    assert Spectacle.objects.count() == 0


def test_membre_edite_son_propre_projet(client, db):
    membre = _membre("alice")
    projet = Spectacle.objects.create(titre="Avant", type_portage=Spectacle.TypePortage.PERSONNEL)
    projet.porteurs.add(membre)
    client.force_login(membre.user)
    client.post(
        f"/espace/projets/{projet.pk}/",
        _donnees_projet(titre="Après", action="enregistrer"),
    )
    projet.refresh_from_db()
    assert projet.titre == "Après"


def test_membre_ne_peut_pas_editer_le_projet_d_un_autre(client, db):
    """ANTI-IDOR par objet : accès à la fiche d'un autre membre → 404, en
    lecture (GET) comme en écriture (POST)."""
    proprietaire = _membre("proprio")
    projet = Spectacle.objects.create(titre="Secret", type_portage=Spectacle.TypePortage.PERSONNEL)
    projet.porteurs.add(proprietaire)

    intrus = _membre("intrus")
    client.force_login(intrus.user)

    assert client.get(f"/espace/projets/{projet.pk}/").status_code == 404
    reponse = client.post(
        f"/espace/projets/{projet.pk}/",
        _donnees_projet(titre="Piraté", action="enregistrer"),
    )
    assert reponse.status_code == 404
    projet.refresh_from_db()
    assert projet.titre == "Secret"  # inchangé


def test_projet_propose_n_est_plus_editable_par_le_membre(client, db):
    membre = _membre("alice")
    projet = Spectacle.objects.create(
        titre="En attente",
        type_portage=Spectacle.TypePortage.PERSONNEL,
        statut_moderation=Statut.PROPOSE,
    )
    projet.porteurs.add(membre)
    client.force_login(membre.user)
    reponse = client.post(
        f"/espace/projets/{projet.pk}/",
        _donnees_projet(titre="Modif interdite", action="enregistrer"),
    )
    assert reponse.status_code == 302  # redirigé, non enregistré
    projet.refresh_from_db()
    assert projet.titre == "En attente"


def test_mes_projets_ne_liste_que_les_siens(client, db):
    membre = _membre("alice")
    a_moi = Spectacle.objects.create(titre="Le mien")
    a_moi.porteurs.add(membre)
    autre = _membre("bob")
    a_lui = Spectacle.objects.create(titre="Le sien")
    a_lui.porteurs.add(autre)

    client.force_login(membre.user)
    corps = client.get("/espace/projets/").content.decode()
    assert "Le mien" in corps
    assert "Le sien" not in corps


# --- Événements du membre : création, soumission, anti-IDOR ----------------


def _donnees_evenement(**extra):
    donnees = {
        "titre": "Ma représentation",
        "description": "",
        "date_debut": "2026-09-01T20:30",
        "date_fin": "",
        "lieu_texte": "Salle des fêtes",
        "spectacle": "",
    }
    donnees.update(extra)
    return donnees


def test_creer_evenement_exige_la_connexion(client, db):
    reponse = client.get("/espace/evenements/nouveau/")
    assert reponse.status_code == 302
    assert "/connexion/" in reponse.url


def test_membre_cree_un_evenement_en_brouillon(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    reponse = client.post("/espace/evenements/nouveau/", _donnees_evenement(action="enregistrer"))
    assert reponse.status_code == 302
    evenement = Evenement.objects.get()
    assert evenement.statut_moderation == Statut.BROUILLON
    assert evenement.cree_par == membre.user


def test_membre_soumet_un_evenement(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    client.post("/espace/evenements/nouveau/", _donnees_evenement(action="soumettre"))
    evenement = Evenement.objects.get()
    assert evenement.statut_moderation == Statut.PROPOSE


def test_date_fin_avant_debut_refusee(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    reponse = client.post(
        "/espace/evenements/nouveau/",
        _donnees_evenement(date_fin="2026-09-01T19:00", action="enregistrer"),
    )
    assert reponse.status_code == 200  # formulaire réaffiché avec l'erreur
    assert Evenement.objects.count() == 0


def test_membre_ne_peut_pas_editer_evenement_d_un_autre(client, db):
    """ANTI-IDOR : la propriété d'un événement passe par `cree_par`."""
    proprietaire = _membre("proprio")
    evenement = Evenement.objects.create(
        titre="Privé",
        date_debut=make_aware(datetime(2026, 9, 1, 20, 30)),
        cree_par=proprietaire.user,
    )
    intrus = _membre("intrus")
    client.force_login(intrus.user)

    assert client.get(f"/espace/evenements/{evenement.pk}/").status_code == 404
    reponse = client.post(
        f"/espace/evenements/{evenement.pk}/",
        _donnees_evenement(titre="Piraté", action="enregistrer"),
    )
    assert reponse.status_code == 404
    evenement.refresh_from_db()
    assert evenement.titre == "Privé"


def test_evenement_propose_n_est_plus_editable(client, db):
    membre = _membre("alice")
    evenement = Evenement.objects.create(
        titre="En attente",
        date_debut=make_aware(datetime(2026, 9, 1, 20, 30)),
        cree_par=membre.user,
        statut_moderation=Statut.PROPOSE,
    )
    client.force_login(membre.user)
    reponse = client.post(
        f"/espace/evenements/{evenement.pk}/",
        _donnees_evenement(titre="Modif interdite", action="enregistrer"),
    )
    assert reponse.status_code == 302
    evenement.refresh_from_db()
    assert evenement.titre == "En attente"


def test_membre_ne_peut_rattacher_que_ses_propres_spectacles(client, db):
    """Anti-IDOR au niveau du champ : un membre ne peut pas lier son événement
    au spectacle d'un autre."""
    membre = _membre("alice")
    autre = _membre("bob")
    spectacle_autrui = Spectacle.objects.create(titre="Show de Bob")
    spectacle_autrui.porteurs.add(autre)

    client.force_login(membre.user)
    reponse = client.post(
        "/espace/evenements/nouveau/",
        _donnees_evenement(spectacle=str(spectacle_autrui.pk), action="enregistrer"),
    )
    assert reponse.status_code == 200  # choix invalide : formulaire réaffiché
    assert Evenement.objects.count() == 0


def test_mes_evenements_ne_liste_que_les_siens(client, db):
    membre = _membre("alice")
    Evenement.objects.create(
        titre="Le mien", date_debut=make_aware(datetime(2026, 9, 1, 20, 30)), cree_par=membre.user
    )
    autre = _membre("bob")
    Evenement.objects.create(
        titre="Le sien", date_debut=make_aware(datetime(2026, 9, 2, 20, 30)), cree_par=autre.user
    )

    client.force_login(membre.user)
    corps = client.get("/espace/evenements/").content.decode()
    assert "Le mien" in corps
    assert "Le sien" not in corps


# --- Fichiers privés : stockage isolé + téléchargement contrôlé ------------


def _corps_stream(reponse):
    """Concatène le contenu d'une réponse en flux (FileResponse)."""
    return b"".join(reponse.streaming_content)


def test_le_fichier_prive_est_stocke_hors_racine_publique(db):
    """Propriété de sécurité : le fichier vit sous MEDIA_PRIVE_ROOT, jamais
    sous MEDIA_ROOT (servi publiquement par Nginx)."""
    document = _document(Document.Confidentialite.MEMBRES)
    chemin = document.fichier.path
    assert chemin.startswith(str(settings.MEDIA_PRIVE_ROOT))
    assert not chemin.startswith(str(settings.MEDIA_ROOT))


def test_telecharger_document_exige_la_connexion(client, db):
    document = _document(Document.Confidentialite.PUBLIC)
    reponse = client.get(f"/espace/documents/{document.pk}/telecharger/")
    assert reponse.status_code == 302
    assert "/connexion/" in reponse.url


def test_document_public_est_servi_a_un_membre_connecte(client, db):
    membre = _membre("alice")
    document = _document(Document.Confidentialite.PUBLIC, contenu=b"contenu public")
    client.force_login(membre.user)
    reponse = client.get(f"/espace/documents/{document.pk}/telecharger/")
    assert reponse.status_code == 200
    assert _corps_stream(reponse) == b"contenu public"
    assert "attachment" in reponse["Content-Disposition"]


def test_document_membres_refuse_sans_fiche_membre(client, db):
    """Un compte sans fiche membre n'accède pas aux documents « membres »."""
    user = Utilisateur.objects.create_user(username="technique", password="x")
    document = _document(Document.Confidentialite.MEMBRES)
    client.force_login(user)
    assert client.get(f"/espace/documents/{document.pk}/telecharger/").status_code == 404


def test_document_membres_servi_a_un_membre(client, db):
    membre = _membre("alice")
    document = _document(Document.Confidentialite.MEMBRES)
    client.force_login(membre.user)
    assert client.get(f"/espace/documents/{document.pk}/telecharger/").status_code == 200


def test_document_prive_refuse_a_un_autre_membre(client, db):
    """ANTI-IDOR / anti-énumération : un document privé d'autrui renvoie 404,
    pas 403 (on ne confirme pas son existence)."""
    auteur = _membre("auteur")
    document = _document(Document.Confidentialite.PRIVE, cree_par=auteur.user)
    intrus = _membre("intrus")
    client.force_login(intrus.user)
    assert client.get(f"/espace/documents/{document.pk}/telecharger/").status_code == 404


def test_document_prive_servi_a_son_auteur(client, db):
    auteur = _membre("auteur")
    document = _document(Document.Confidentialite.PRIVE, cree_par=auteur.user)
    client.force_login(auteur.user)
    assert client.get(f"/espace/documents/{document.pk}/telecharger/").status_code == 200


def test_document_prive_servi_au_bureau(client, db):
    staff = Utilisateur.objects.create_user(username="bureau", password="x", is_staff=True)
    auteur = _membre("auteur")
    document = _document(Document.Confidentialite.PRIVE, cree_par=auteur.user)
    client.force_login(staff)
    assert client.get(f"/espace/documents/{document.pk}/telecharger/").status_code == 200


def test_mes_documents_ne_liste_que_les_accessibles(client, db):
    membre = _membre("alice")
    _document(Document.Confidentialite.PUBLIC, titre="Statuts")
    _document(Document.Confidentialite.MEMBRES, titre="ConvocationAG")
    _document(
        Document.Confidentialite.PRIVE, titre="ContratConfidentiel", cree_par=_membre("rh").user
    )

    client.force_login(membre.user)
    corps = client.get("/espace/documents/").content.decode()
    assert "Statuts" in corps
    assert "ConvocationAG" in corps
    assert "ContratConfidentiel" not in corps  # privé d'autrui : masqué


# --- Convocations / CR d'AG : visibilité + contenu -------------------------


def _reunion(type_reunion, statut, *, titre="Réunion"):
    return Reunion.objects.create(
        titre=titre,
        type_reunion=type_reunion,
        statut=statut,
        date=make_aware(datetime(2026, 10, 15, 18, 30)),
    )


def _ag(statut=Reunion.Statut.CONVOQUEE, titre="AG 2026"):
    return _reunion(Reunion.TypeReunion.AG_ORDINAIRE, statut, titre=titre)


def test_convocations_exige_la_connexion(client, db):
    reponse = client.get("/espace/convocations/")
    assert reponse.status_code == 302
    assert "/connexion/" in reponse.url


def test_membre_voit_une_ag_convoquee(client, db):
    membre = _membre("alice")
    _ag(titre="AG ordinaire 2026")
    client.force_login(membre.user)
    corps = client.get("/espace/convocations/").content.decode()
    assert "AG ordinaire 2026" in corps


def test_membre_ne_voit_pas_une_ag_en_preparation(client, db):
    """Une AG encore en préparation n'est pas exposée (liste + détail 404)."""
    membre = _membre("alice")
    ag = _ag(statut=Reunion.Statut.PREPARATION, titre="Brouillon AG")
    client.force_login(membre.user)
    corps = client.get("/espace/convocations/").content.decode()
    assert "Brouillon AG" not in corps
    assert client.get(f"/espace/convocations/{ag.pk}/").status_code == 404


def test_membre_ne_voit_pas_une_reunion_de_bureau(client, db):
    """ANTI-IDOR : les réunions de bureau sont réservées au bureau (staff)."""
    membre = _membre("alice")
    bureau = _reunion(Reunion.TypeReunion.BUREAU, Reunion.Statut.CONVOQUEE, titre="Bureau interne")
    client.force_login(membre.user)
    corps = client.get("/espace/convocations/").content.decode()
    assert "Bureau interne" not in corps
    assert client.get(f"/espace/convocations/{bureau.pk}/").status_code == 404


def test_staff_voit_une_reunion_de_bureau(client, db):
    staff = Utilisateur.objects.create_user(username="bureau", password="x", is_staff=True)
    bureau = _reunion(Reunion.TypeReunion.BUREAU, Reunion.Statut.CONVOQUEE, titre="Bureau interne")
    client.force_login(staff)
    assert client.get(f"/espace/convocations/{bureau.pk}/").status_code == 200


def test_detail_convocation_montre_l_ordre_du_jour(client, db):
    membre = _membre("alice")
    ag = _ag()
    Sujet.objects.create(titre="Vote du budget 2026", reunion=ag, ordre_du_jour=1)
    client.force_login(membre.user)
    corps = client.get(f"/espace/convocations/{ag.pk}/").content.decode()
    assert "Vote du budget 2026" in corps


def test_pv_prive_non_liste_mais_pv_membres_visible(client, db):
    """Les documents liés à l'AG sont filtrés selon les droits : un PV privé
    d'autrui reste masqué, un document « membres » est proposé."""
    membre = _membre("alice")
    ag = _ag()
    pv_prive = _document(
        Document.Confidentialite.PRIVE, titre="PVConfidentiel", cree_par=_membre("rh").user
    )
    ag.compte_rendu = pv_prive
    ag.save()
    doc_membres = _document(Document.Confidentialite.MEMBRES, titre="AnnexeMembres")
    ag.documents.add(doc_membres)

    client.force_login(membre.user)
    corps = client.get(f"/espace/convocations/{ag.pk}/").content.decode()
    assert "PVConfidentiel" not in corps
    assert "AnnexeMembres" in corps


def test_membre_voit_son_statut_de_presence(client, db):
    membre = _membre("alice")
    ag = _ag()
    Presence.objects.create(
        reunion=ag, membre=membre, statut=Presence.Statut.REPRESENTE, peut_voter=True
    )
    mandataire = _membre("bob")
    Pouvoir.objects.create(reunion=ag, mandant=membre, mandataire=mandataire)

    client.force_login(membre.user)
    corps = client.get(f"/espace/convocations/{ag.pk}/").content.decode()
    assert "Représenté" in corps
    assert "donné pouvoir" in corps


# --- Reçus fiscaux du membre -----------------------------------------------


def _recu_pour(membre, **extra):
    donnees = {
        "type_versement": RecuFiscal.TypeVersement.DON,
        "montant": Decimal("10.00"),
        "date_versement": date(2026, 1, 1),
        "donateur_nom": str(membre),
        "membre": membre,
    }
    donnees.update(extra)
    return emettre_recu(**donnees)


def test_mes_recus_ne_liste_que_les_siens(client, db):
    membre = _membre("alice")
    autre = _membre("bob")
    _recu_pour(membre, montant=Decimal("111.00"))
    _recu_pour(autre, montant=Decimal("999.00"))

    client.force_login(membre.user)
    corps = client.get("/espace/recus/").content.decode()
    assert "111" in corps
    assert "999" not in corps  # anti-IDOR : pas le reçu d'un autre membre


def test_membre_telecharge_son_recu(client, db, monkeypatch):
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: b"%PDF-1.4 x"
    )
    membre = _membre("alice")
    recu = _recu_pour(membre)
    client.force_login(membre.user)
    reponse = client.get(f"/espace/recus/{recu.pk}/telecharger/")
    assert reponse.status_code == 200
    assert b"".join(reponse.streaming_content).startswith(b"%PDF")


def test_membre_ne_peut_pas_telecharger_le_recu_d_un_autre(client, db):
    """ANTI-IDOR : filtre membre= → 404 sur le reçu d'autrui (avant tout rendu)."""
    membre = _membre("alice")
    autre = _membre("bob")
    recu = _recu_pour(autre)
    client.force_login(membre.user)
    assert client.get(f"/espace/recus/{recu.pk}/telecharger/").status_code == 404


def test_telecharger_recu_exige_la_connexion(client, db):
    membre = _membre("alice")
    recu = _recu_pour(membre)
    reponse = client.get(f"/espace/recus/{recu.pk}/telecharger/")
    assert reponse.status_code == 302
    assert "/connexion/" in reponse.url
