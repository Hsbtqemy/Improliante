"""Tests de l'espace membre : accès protégé + anti-IDOR."""

from __future__ import annotations

from decimal import Decimal

from apps.budget.models import Adhesion, Saison
from apps.coeur.models import Membre, Utilisateur
from apps.common.models import Moderation
from apps.spectacles.models import Spectacle

Statut = Moderation.StatutModeration


def _membre(username):
    user = Utilisateur.objects.create_user(username=username, password="motdepasse")
    return Membre.objects.create(user=user)


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
