"""Tests de l'espace membre : accès protégé + anti-IDOR."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.utils.timezone import make_aware

from apps.agenda.models import Evenement, ImageEvenement
from apps.budget.models import Adhesion, RecuFiscal, Saison
from apps.budget.services import emettre_recu
from apps.coeur.models import LienReseau, Membre, Utilisateur
from apps.common.models import Moderation
from apps.documents import services as doc_services
from apps.documents.models import Document, Dossier
from apps.gouvernance.models import Pouvoir, Presence, Reunion, Sujet
from apps.medias.models import Media
from apps.spectacles.models import ImageSpectacle, Spectacle

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


def _evenement_publie(titre, quand, *, visibilite=Evenement.Visibilite.MEMBRES):
    return Evenement.objects.create(
        titre=titre,
        date_debut=quand,
        statut_moderation=Moderation.StatutModeration.PUBLIE,
        visibilite=visibilite,
    )


def test_accueil_montre_les_prochaines_dates(client, db):
    membre = _membre("alice")
    _evenement_publie("Générale à venir", timezone.now() + timedelta(days=10))
    _evenement_publie("Vieux spectacle", timezone.now() - timedelta(days=10))
    client.force_login(membre.user)
    corps = client.get("/espace/").content.decode()
    assert "Générale à venir" in corps
    assert "Vieux spectacle" not in corps  # date passée, exclue


def test_accueil_signale_une_convocation_sans_reponse(client, db):
    membre = _membre("alice")
    Reunion.objects.create(
        titre="AG 2026",
        type_reunion=Reunion.TypeReunion.AG_ORDINAIRE,
        statut=Reunion.Statut.CONVOQUEE,
        date=timezone.now() + timedelta(days=20),
    )
    client.force_login(membre.user)
    corps = client.get("/espace/").content.decode()
    assert "AG 2026" in corps
    assert "Répondre à la convocation" in corps


def test_accueil_convocation_disparait_apres_reponse(client, db):
    membre = _membre("alice")
    reunion = Reunion.objects.create(
        titre="AG 2026",
        type_reunion=Reunion.TypeReunion.AG_ORDINAIRE,
        statut=Reunion.Statut.CONVOQUEE,
        date=timezone.now() + timedelta(days=20),
    )
    Presence.objects.create(reunion=reunion, membre=membre, statut=Presence.Statut.PRESENT)
    client.force_login(membre.user)
    corps = client.get("/espace/").content.decode()
    assert "Tout est à jour" in corps  # plus rien à traiter


def test_accueil_propose_de_soumettre_un_projet_brouillon(client, db):
    membre = _membre("alice")
    _projet_de(membre, titre="Création en cours")  # brouillon par défaut
    client.force_login(membre.user)
    corps = client.get("/espace/").content.decode()
    assert "Finaliser et soumettre" in corps


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
        f"/espace/projets/{projet.pk}/modifier/",
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

    assert client.get(f"/espace/projets/{projet.pk}/modifier/").status_code == 404
    reponse = client.post(
        f"/espace/projets/{projet.pk}/modifier/",
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
        f"/espace/projets/{projet.pk}/modifier/",
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


# --- Projets : images (affiche + galerie) ----------------------------------


def _image_png(nom="image.png"):
    """Fabrique une vraie image PNG minuscule (validée par ImageField/Pillow)."""
    from io import BytesIO

    from PIL import Image

    tampon = BytesIO()
    Image.new("RGB", (2, 2), "red").save(tampon, "PNG")
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type="image/png")


def _projet_de(membre, titre="Mon projet"):
    projet = Spectacle.objects.create(titre=titre, type_portage=Spectacle.TypePortage.PERSONNEL)
    projet.porteurs.add(membre)
    return projet


def test_membre_ajoute_une_affiche_a_son_projet(client, db):
    membre = _membre("alice")
    projet = _projet_de(membre)
    client.force_login(membre.user)
    client.post(
        f"/espace/projets/{projet.pk}/modifier/",
        _donnees_projet(
            titre=projet.titre,
            action="enregistrer",
            affiche_fichier=_image_png("affiche.png"),
            affiche_alt="Affiche du spectacle",
        ),
    )
    projet.refresh_from_db()
    assert projet.affiche is not None
    assert projet.affiche.alt == "Affiche du spectacle"
    assert projet.affiche.cree_par == membre.user


def test_affiche_sans_alt_est_refusee(client, db):
    """`alt` obligatoire (accessibilité) : une affiche sans texte alternatif
    est rejetée et n'est pas enregistrée."""
    membre = _membre("alice")
    projet = _projet_de(membre)
    client.force_login(membre.user)
    reponse = client.post(
        f"/espace/projets/{projet.pk}/modifier/",
        _donnees_projet(
            titre=projet.titre, action="enregistrer", affiche_fichier=_image_png("affiche.png")
        ),
    )
    assert reponse.status_code == 200  # formulaire réaffiché avec l'erreur
    projet.refresh_from_db()
    assert projet.affiche is None
    assert Media.objects.count() == 0


def test_membre_ajoute_une_image_a_la_galerie(client, db):
    membre = _membre("alice")
    projet = _projet_de(membre)
    client.force_login(membre.user)
    client.post(
        f"/espace/projets/{projet.pk}/modifier/",
        _donnees_projet(
            titre=projet.titre,
            action="enregistrer",
            galerie_fichier=_image_png("g1.png"),
            galerie_alt="Photo de répétition",
        ),
    )
    assert projet.images.count() == 1
    assert projet.images.get().media.alt == "Photo de répétition"


def test_membre_retire_une_image_de_sa_galerie(client, db):
    membre = _membre("alice")
    projet = _projet_de(membre)
    media = Media.objects.create(alt="x", fichier=_image_png("x.png"))
    image = ImageSpectacle.objects.create(spectacle=projet, media=media, ordre=1)
    client.force_login(membre.user)
    client.post(
        f"/espace/projets/{projet.pk}/modifier/",
        _donnees_projet(titre=projet.titre, action="enregistrer", supprimer_image=str(image.pk)),
    )
    assert projet.images.count() == 0


def test_membre_ne_peut_pas_retirer_l_image_d_un_autre_projet(client, db):
    """ANTI-IDOR : le retrait est borné au projet édité ; l'id d'une image
    appartenant à un autre projet est ignoré."""
    membre = _membre("alice")
    mien = _projet_de(membre, titre="Le mien")

    autre_membre = _membre("bob")
    autre_projet = _projet_de(autre_membre, titre="Le sien")
    media = Media.objects.create(alt="x", fichier=_image_png("x.png"))
    image_autre = ImageSpectacle.objects.create(spectacle=autre_projet, media=media, ordre=1)

    client.force_login(membre.user)
    client.post(
        f"/espace/projets/{mien.pk}/modifier/",
        _donnees_projet(
            titre=mien.titre, action="enregistrer", supprimer_image=str(image_autre.pk)
        ),
    )
    assert ImageSpectacle.objects.filter(pk=image_autre.pk).exists()  # non supprimée


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

    assert client.get(f"/espace/evenements/{evenement.pk}/modifier/").status_code == 404
    reponse = client.post(
        f"/espace/evenements/{evenement.pk}/modifier/",
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
        f"/espace/evenements/{evenement.pk}/modifier/",
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


# --- Événements : images (affiche + galerie) -------------------------------


def _evenement_de(membre, titre="Mon événement"):
    return Evenement.objects.create(
        titre=titre,
        date_debut=make_aware(datetime(2026, 9, 1, 20, 30)),
        cree_par=membre.user,
    )


def test_membre_ajoute_une_affiche_a_son_evenement(client, db):
    membre = _membre("alice")
    evenement = _evenement_de(membre)
    client.force_login(membre.user)
    client.post(
        f"/espace/evenements/{evenement.pk}/modifier/",
        _donnees_evenement(
            titre=evenement.titre,
            action="enregistrer",
            affiche_fichier=_image_png("affiche.png"),
            affiche_alt="Affiche de l'événement",
        ),
    )
    evenement.refresh_from_db()
    assert evenement.affiche is not None
    assert evenement.affiche.alt == "Affiche de l'événement"
    assert evenement.affiche.cree_par == membre.user


def test_affiche_evenement_sans_alt_est_refusee(client, db):
    membre = _membre("alice")
    evenement = _evenement_de(membre)
    client.force_login(membre.user)
    reponse = client.post(
        f"/espace/evenements/{evenement.pk}/modifier/",
        _donnees_evenement(
            titre=evenement.titre, action="enregistrer", affiche_fichier=_image_png("a.png")
        ),
    )
    assert reponse.status_code == 200  # formulaire réaffiché avec l'erreur
    evenement.refresh_from_db()
    assert evenement.affiche is None


def test_membre_ajoute_une_image_a_la_galerie_evenement(client, db):
    membre = _membre("alice")
    evenement = _evenement_de(membre)
    client.force_login(membre.user)
    client.post(
        f"/espace/evenements/{evenement.pk}/modifier/",
        _donnees_evenement(
            titre=evenement.titre,
            action="enregistrer",
            galerie_fichier=_image_png("g1.png"),
            galerie_alt="Photo sur scène",
        ),
    )
    assert evenement.images.count() == 1
    assert evenement.images.get().media.alt == "Photo sur scène"


def test_membre_ne_peut_pas_retirer_l_image_d_un_autre_evenement(client, db):
    """ANTI-IDOR : le retrait est borné à l'événement édité."""
    membre = _membre("alice")
    mien = _evenement_de(membre, titre="Le mien")

    autre_membre = _membre("bob")
    autre = _evenement_de(autre_membre, titre="Le sien")
    media = Media.objects.create(alt="x", fichier=_image_png("x.png"))
    image_autre = ImageEvenement.objects.create(evenement=autre, media=media, ordre=1)

    client.force_login(membre.user)
    client.post(
        f"/espace/evenements/{mien.pk}/modifier/",
        _donnees_evenement(
            titre=mien.titre, action="enregistrer", supprimer_image=str(image_autre.pk)
        ),
    )
    assert ImageEvenement.objects.filter(pk=image_autre.pk).exists()  # non supprimée


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


def test_documents_association_lisibles_selon_confidentialite(client, db):
    """Branche Association (documents non classés) sur l'explorateur : un membre
    voit les documents publics/membres, jamais un privé d'autrui ni un fichier
    personnel d'un autre membre."""
    membre = _membre("alice")
    _document(Document.Confidentialite.PUBLIC, titre="StatutsPublics")
    _document(Document.Confidentialite.MEMBRES, titre="ConvocationAG")
    _document(
        Document.Confidentialite.PRIVE, titre="ContratConfidentiel", cree_par=_membre("rh").user
    )
    bob = _membre("bob")
    perso_bob = _dossier_membre(bob, Visibilite.PRIVE, nom="PersoBob")
    _fichier(perso_bob, cree_par=bob.user, titre="FichierPersoBob")

    client.force_login(membre.user)
    corps = client.get("/espace/fichiers/").content.decode()
    assert "StatutsPublics" in corps
    assert "ConvocationAG" in corps
    assert "ContratConfidentiel" not in corps  # privé d'autrui : masqué
    assert "FichierPersoBob" not in corps  # fichier perso d'autrui : jamais côté association


# --- Mes fichiers : espace fichiers personnel du membre --------------------

Visibilite = Dossier.Visibilite


def _staff(username="bureau"):
    return Utilisateur.objects.create_user(username=username, password="x", is_staff=True)


def _dossier_membre(membre, visibilite, *, parent=None, nom="Dossier"):
    return doc_services.creer_dossier_membre(membre, nom=nom, visibilite=visibilite, parent=parent)


def _fichier(dossier, *, cree_par=None, titre="Fichier", contenu=b"data"):
    return Document.objects.create(
        titre=titre,
        dossier=dossier,
        cree_par=cree_par,
        fichier=SimpleUploadedFile(f"{titre}.pdf", contenu, content_type="application/pdf"),
    )


def test_mes_fichiers_exige_la_connexion(client, db):
    reponse = client.get("/espace/fichiers/")
    assert reponse.status_code == 302
    assert "/connexion/" in reponse.url


def test_membre_cree_un_dossier_racine(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    reponse = client.post(
        "/espace/fichiers/",
        {"form_type": "dossier", "nom": "Photos", "description": "", "visibilite": "prive"},
    )
    assert reponse.status_code == 302
    dossier = Dossier.objects.get(nom="Photos")
    assert dossier.proprietaire == membre
    assert dossier.get_depth() == 1
    assert dossier.visibilite == "prive"


def test_membre_cree_sous_dossier_et_televerse(client, db):
    membre = _membre("alice")
    racine = _dossier_membre(membre, Visibilite.PRIVE, nom="Racine")
    client.force_login(membre.user)
    client.post(
        f"/espace/fichiers/{racine.pk}/",
        {"form_type": "dossier", "nom": "Sous", "description": "", "visibilite": "prive"},
    )
    sous = Dossier.objects.get(nom="Sous")
    assert sous.get_depth() == 2
    assert sous.proprietaire == membre
    reponse = client.post(
        f"/espace/fichiers/{racine.pk}/",
        {
            "form_type": "document",
            "titre": "Mon PDF",
            "description": "",
            "fichier": SimpleUploadedFile("x.pdf", b"data", content_type="application/pdf"),
        },
    )
    assert reponse.status_code == 302
    doc = Document.objects.get(titre="Mon PDF")
    assert doc.dossier == racine
    assert doc.cree_par == membre.user


def test_dossier_prive_invisible_pour_un_autre_membre(client, db):
    """ANTI-IDOR : le dossier privé d'autrui renvoie 404 (GET et POST), inchangé."""
    alice = _membre("alice")
    prive = _dossier_membre(alice, Visibilite.PRIVE, nom="Prive")
    bob = _membre("bob")
    client.force_login(bob.user)
    assert client.get(f"/espace/fichiers/{prive.pk}/").status_code == 404
    reponse = client.post(
        f"/espace/fichiers/{prive.pk}/",
        {
            "form_type": "document",
            "titre": "Intrus",
            "fichier": SimpleUploadedFile("i.pdf", b"x", content_type="application/pdf"),
        },
    )
    assert reponse.status_code == 404
    assert not Document.objects.filter(titre="Intrus").exists()


def test_dossier_prive_invisible_du_bureau(client, db):
    """Décision produit : privé = strictement personnel, le bureau n'y accède pas."""
    alice = _membre("alice")
    prive = _dossier_membre(alice, Visibilite.PRIVE, nom="Prive")
    doc = _fichier(prive, cree_par=alice.user, titre="Perso")
    client.force_login(_staff())
    assert client.get(f"/espace/fichiers/{prive.pk}/").status_code == 404
    assert client.get(f"/espace/documents/{doc.pk}/telecharger/").status_code == 404


def test_dossier_bureau_visible_du_bureau_pas_des_membres(client, db):
    alice = _membre("alice")
    dossier = _dossier_membre(alice, Visibilite.BUREAU, nom="PourBureau")
    doc = _fichier(dossier, cree_par=alice.user, titre="Note")
    bob = _membre("bob")
    client.force_login(bob.user)
    assert client.get(f"/espace/fichiers/{dossier.pk}/").status_code == 404
    assert client.get(f"/espace/documents/{doc.pk}/telecharger/").status_code == 404
    client.force_login(_staff())
    assert client.get(f"/espace/documents/{doc.pk}/telecharger/").status_code == 200


def test_creer_dossier_par_branche_via_le_landing(client, db):
    """Le landing crée un dossier dans la branche indiquée (perso / bureau / partage)."""
    membre = _membre("alice")
    client.force_login(membre.user)
    client.post("/espace/fichiers/", {"form_type": "dossier", "branche": "perso", "nom": "P"})
    client.post("/espace/fichiers/", {"form_type": "dossier", "branche": "bureau", "nom": "B"})
    client.post("/espace/fichiers/", {"form_type": "dossier", "branche": "partage", "nom": "S"})
    p = Dossier.objects.get(nom="P")
    assert p.espace == "perso" and p.visibilite == "prive" and p.proprietaire == membre
    b = Dossier.objects.get(nom="B")
    assert b.espace == "perso" and b.visibilite == "bureau" and b.proprietaire == membre
    s = Dossier.objects.get(nom="S")
    assert s.espace == "commun" and s.proprietaire is None


def test_sous_dossier_herite_de_la_branche_du_parent(client, db):
    membre = _membre("alice")
    bureau = _dossier_membre(membre, Visibilite.BUREAU, nom="Bur")
    client.force_login(membre.user)
    client.post(f"/espace/fichiers/{bureau.pk}/", {"form_type": "dossier", "nom": "Sub"})
    sub = Dossier.objects.get(nom="Sub")
    assert sub.visibilite == "bureau"  # hérité du parent, pas choisi
    assert sub.proprietaire == membre


def test_dossier_membre_absent_de_la_branche_association(client, db):
    """Étanchéité : un dossier PERSONNEL n'appartient pas à l'espace Association —
    son URL Association renvoie 404, et il reste invisible du bureau."""
    alice = _membre("alice")
    dossier = _dossier_membre(alice, Visibilite.PRIVE, nom="DossierMembreAlice")
    client.force_login(_staff())
    assert client.get(f"/espace/association/{dossier.pk}/").status_code == 404  # mauvais espace
    corps = client.get("/espace/fichiers/").content.decode()
    assert "DossierMembreAlice" not in corps  # privé d'un membre : jamais côté bureau


def test_upload_extension_interdite_refusee(client, db):
    alice = _membre("alice")
    dossier = _dossier_membre(alice, Visibilite.PRIVE, nom="D")
    client.force_login(alice.user)
    reponse = client.post(
        f"/espace/fichiers/{dossier.pk}/",
        {
            "form_type": "document",
            "titre": "Virus",
            "fichier": SimpleUploadedFile("x.exe", b"MZ", content_type="application/octet-stream"),
        },
    )
    assert reponse.status_code == 200  # formulaire re-rendu avec l'erreur
    assert not Document.objects.filter(titre="Virus").exists()


def test_upload_trop_volumineux_refuse(client, db, monkeypatch):
    from apps.documents import validators

    monkeypatch.setattr(validators, "TAILLE_MAX_DOCUMENT", 10)
    alice = _membre("alice")
    dossier = _dossier_membre(alice, Visibilite.PRIVE, nom="D")
    client.force_login(alice.user)
    reponse = client.post(
        f"/espace/fichiers/{dossier.pk}/",
        {
            "form_type": "document",
            "titre": "Gros",
            "fichier": SimpleUploadedFile(
                "gros.pdf", b"12345678901234567890", content_type="application/pdf"
            ),
        },
    )
    assert reponse.status_code == 200
    assert not Document.objects.filter(titre="Gros").exists()


def test_membre_renomme_son_dossier(client, db):
    alice = _membre("alice")
    dossier = _dossier_membre(alice, Visibilite.PRIVE, nom="Avant")
    client.force_login(alice.user)
    reponse = client.post(
        f"/espace/fichiers/{dossier.pk}/editer/",
        {"nom": "Apres", "description": "maj"},
    )
    assert reponse.status_code == 302
    dossier.refresh_from_db()
    assert dossier.nom == "Apres"
    assert dossier.description == "maj"


def test_membre_ne_peut_pas_editer_le_dossier_d_un_autre(client, db):
    alice = _membre("alice")
    dossier = _dossier_membre(alice, Visibilite.PRIVE, nom="Alice")
    bob = _membre("bob")
    client.force_login(bob.user)
    assert client.get(f"/espace/fichiers/{dossier.pk}/editer/").status_code == 404
    reponse = client.post(
        f"/espace/fichiers/{dossier.pk}/editer/",
        {"nom": "Pirate", "description": ""},
    )
    assert reponse.status_code == 404
    dossier.refresh_from_db()
    assert dossier.nom == "Alice"


def test_supprimer_dossier_vide(client, db):
    alice = _membre("alice")
    dossier = _dossier_membre(alice, Visibilite.PRIVE, nom="Vide")
    client.force_login(alice.user)
    reponse = client.post(f"/espace/fichiers/{dossier.pk}/supprimer/")
    assert reponse.status_code == 302
    assert not Dossier.objects.filter(pk=dossier.pk).exists()


def test_supprimer_dossier_non_vide_bloque(client, db):
    alice = _membre("alice")
    dossier = _dossier_membre(alice, Visibilite.PRIVE, nom="Plein")
    _fichier(dossier, cree_par=alice.user, titre="F")
    client.force_login(alice.user)
    reponse = client.post(f"/espace/fichiers/{dossier.pk}/supprimer/")
    assert reponse.status_code == 302  # redirection + message d'erreur
    assert Dossier.objects.filter(pk=dossier.pk).exists()


def test_supprimer_son_document(client, db):
    alice = _membre("alice")
    dossier = _dossier_membre(alice, Visibilite.PRIVE, nom="D")
    doc = _fichier(dossier, cree_par=alice.user, titre="AJeter")
    client.force_login(alice.user)
    reponse = client.post(f"/espace/fichiers/doc/{doc.pk}/supprimer/")
    assert reponse.status_code == 302
    assert not Document.objects.filter(pk=doc.pk).exists()


def test_membre_ne_supprime_pas_le_document_d_un_autre(client, db):
    alice = _membre("alice")
    dossier = _dossier_membre(alice, Visibilite.PRIVE, nom="D")
    doc = _fichier(dossier, cree_par=alice.user, titre="Precieux")
    bob = _membre("bob")
    client.force_login(bob.user)
    assert client.post(f"/espace/fichiers/doc/{doc.pk}/supprimer/").status_code == 404
    assert Document.objects.filter(pk=doc.pk).exists()


def test_landing_affiche_les_trois_branches(client, db):
    alice = _membre("alice")
    bob = _membre("bob")
    _dossier_membre(alice, Visibilite.PRIVE, nom="AlicePrive")
    _dossier_membre(alice, Visibilite.BUREAU, nom="AliceBureau")
    _dossier_commun("DossierTroupe")
    _dossier_membre(bob, Visibilite.PRIVE, nom="BobPrive")
    client.force_login(alice.user)
    corps = client.get("/espace/fichiers/").content.decode()
    assert "AlicePrive" in corps  # branche Perso
    assert "AliceBureau" in corps  # branche Bureau
    assert "DossierTroupe" in corps  # branche Partagé (espace commun)
    assert "BobPrive" not in corps  # le perso d'autrui n'apparaît jamais


def test_ecran_fichiers_transmis_bureau(client, db):
    alice = _membre("alice")
    _dossier_membre(alice, Visibilite.BUREAU, nom="TransmisAlice")
    _dossier_membre(alice, Visibilite.PRIVE, nom="PriveAlice")
    client.force_login(_staff())
    corps = client.get("/bureau/fichiers-transmis/").content.decode()
    assert "TransmisAlice" in corps
    assert "PriveAlice" not in corps


def test_fichiers_transmis_reserve_au_bureau(client, db):
    alice = _membre("alice")
    client.force_login(alice.user)
    assert client.get("/bureau/fichiers-transmis/").status_code == 403


# --- Espace commun : dossiers collaboratifs de la troupe -------------------


def _dossier_commun(nom="Commun", *, parent=None):
    return doc_services.creer_dossier_commun(nom=nom, parent=parent)


def test_membre_cree_un_dossier_partage_via_le_landing(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    reponse = client.post(
        "/espace/fichiers/",
        {"form_type": "dossier", "branche": "partage", "nom": "Affiches", "description": ""},
    )
    assert reponse.status_code == 302
    d = Dossier.objects.get(nom="Affiches")
    assert d.espace == "commun"
    assert d.proprietaire is None


def test_espace_commun_collaboratif_entre_membres(client, db):
    _membre("alice")
    commun = _dossier_commun("Musiques")
    bob = _membre("bob")  # un AUTRE membre peut contribuer
    client.force_login(bob.user)
    assert client.get(f"/espace/commun/{commun.pk}/").status_code == 200
    client.post(
        f"/espace/commun/{commun.pk}/",
        {"form_type": "dossier", "nom": "Acte 1", "description": ""},
    )
    assert Dossier.objects.filter(nom="Acte 1", espace="commun").exists()
    reponse = client.post(
        f"/espace/commun/{commun.pk}/",
        {
            "form_type": "document",
            "titre": "BandeSon",
            "fichier": SimpleUploadedFile("s.mp3", b"audio", content_type="audio/mpeg"),
        },
    )
    assert reponse.status_code == 302
    doc = Document.objects.get(titre="BandeSon")
    assert doc.dossier == commun
    assert doc.cree_par == bob.user


def test_document_commun_telechargeable_par_tout_membre(client, db):
    commun = _dossier_commun("Partages")
    doc = _fichier(commun, titre="Note", contenu=b"hello")
    bob = _membre("bob")
    client.force_login(bob.user)
    reponse = client.get(f"/espace/documents/{doc.pk}/telecharger/")
    assert reponse.status_code == 200
    assert _corps_stream(reponse) == b"hello"


def test_espace_commun_refuse_sans_fiche_membre(client, db):
    commun = _dossier_commun("Truc")
    user = Utilisateur.objects.create_user(username="tech", password="x")
    client.force_login(user)
    # Pas de fiche membre : redirigé hors de l'espace commun.
    assert client.get(f"/espace/commun/{commun.pk}/").status_code == 302


def test_dossier_commun_hors_branche_association(client, db):
    """Étanchéité : un dossier COMMUN n'est pas dans l'espace Association — son URL
    Association renvoie 404 (même pour le bureau)."""
    commun = _dossier_commun("DossierCommunX")
    client.force_login(_staff())
    assert client.get(f"/espace/association/{commun.pk}/").status_code == 404


def test_membre_supprime_un_fichier_commun(client, db):
    alice = _membre("alice")
    commun = _dossier_commun("Commun")
    doc = _fichier(commun, cree_par=alice.user, titre="AJeter")
    bob = _membre("bob")  # collaboratif : un autre membre peut supprimer
    client.force_login(bob.user)
    reponse = client.post(f"/espace/commun/doc/{doc.pk}/supprimer/")
    assert reponse.status_code == 302
    assert not Document.objects.filter(pk=doc.pk).exists()


def test_supprimer_dossier_commun_non_vide_bloque(client, db):
    membre = _membre("alice")
    commun = _dossier_commun("Plein")
    _fichier(commun, titre="F")
    client.force_login(membre.user)
    reponse = client.post(f"/espace/commun/{commun.pk}/supprimer/")
    assert reponse.status_code == 302
    assert Dossier.objects.filter(pk=commun.pk).exists()


def test_url_commun_ne_touche_pas_un_dossier_perso(client, db):
    """Un dossier perso n'est pas atteignable via les URLs de l'espace commun."""
    alice = _membre("alice")
    perso = _dossier_membre(alice, Visibilite.PRIVE, nom="Perso")
    client.force_login(alice.user)
    assert client.get(f"/espace/commun/{perso.pk}/").status_code == 404
    assert client.post(f"/espace/commun/{perso.pk}/supprimer/").status_code == 404


# --- Activation de compte (lien signé transmis par le bureau) --------------

_MDP_FORT = "Improliante!2026"


def _compte_a_activer(email="lea@example.org"):
    from apps.coeur.services import creer_compte_membre, jeton_activation

    membre = creer_compte_membre(first_name="Léa", last_name="Roy", email=email)
    uidb64, token = jeton_activation(membre.user)
    return membre, f"/activation/{uidb64}/{token}/"


def test_activation_lien_valide_definit_le_mot_de_passe(client, db):
    membre, url = _compte_a_activer()
    assert client.get(url).status_code == 200  # page d'activation affichée
    reponse = client.post(url, {"new_password1": _MDP_FORT, "new_password2": _MDP_FORT})
    assert reponse.status_code == 302
    assert "/connexion/" in reponse.url
    membre.user.refresh_from_db()
    assert membre.user.has_usable_password() is True
    # Connexion possible avec le nouveau mot de passe (identifiant = e-mail).
    assert client.login(username="lea@example.org", password=_MDP_FORT) is True


def test_activation_lien_invalide_est_rejete(client, db):
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    membre, _ = _compte_a_activer()
    uidb64 = urlsafe_base64_encode(force_bytes(membre.user.pk))
    reponse = client.get(f"/activation/{uidb64}/mauvais-token/")
    assert reponse.status_code == 200
    assert reponse.context["lien_valide"] is False


def test_activation_token_a_usage_unique(client, db):
    """Le token inclut le hash du mot de passe : il devient caduc une fois le
    mot de passe défini (pas de réutilisation du lien)."""
    _, url = _compte_a_activer()
    client.post(url, {"new_password1": _MDP_FORT, "new_password2": _MDP_FORT})
    assert client.get(url).context["lien_valide"] is False


# --- Mon profil : bio, site web, réseaux, photo (anti-IDOR) -----------------

PROFIL = "/espace/profil/"


def _donnees_profil(**extra):
    donnees = {
        "role_public": "",
        "bio": "",
        "telephone": "",
        "site_web": "",
        # Formset des réseaux (préfixe = related_name « liens_reseaux »), vide.
        "liens_reseaux-TOTAL_FORMS": "1",
        "liens_reseaux-INITIAL_FORMS": "0",
        "liens_reseaux-MIN_NUM_FORMS": "0",
        "liens_reseaux-MAX_NUM_FORMS": "1000",
        "liens_reseaux-0-reseau": "",
        "liens_reseaux-0-url": "",
        "liens_reseaux-0-libelle": "",
        "liens_reseaux-0-ordre": "0",
    }
    donnees.update(extra)
    return donnees


def test_profil_exige_la_connexion(client, db):
    reponse = client.get(PROFIL)
    assert reponse.status_code == 302
    assert "/connexion/" in reponse.url


def test_membre_met_a_jour_son_profil(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    reponse = client.post(
        PROFIL,
        _donnees_profil(role_public="Comédienne", bio="Une bio", site_web="https://alice.example"),
    )
    assert reponse.status_code == 302
    membre.refresh_from_db()
    assert membre.role_public == "Comédienne"
    assert membre.site_web == "https://alice.example"


def test_membre_ajoute_un_reseau(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    client.post(
        PROFIL,
        _donnees_profil(
            **{
                "liens_reseaux-0-reseau": LienReseau.Reseau.INSTAGRAM,
                "liens_reseaux-0-url": "https://instagram.com/alice",
            }
        ),
    )
    lien = membre.liens_reseaux.get()
    assert lien.reseau == LienReseau.Reseau.INSTAGRAM
    assert lien.url == "https://instagram.com/alice"


def test_membre_ajoute_une_photo_de_profil(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    client.post(
        PROFIL,
        _donnees_profil(photo_fichier=_image_png("portrait.png"), photo_alt="Portrait d'Alice"),
    )
    membre.refresh_from_db()
    assert membre.photo is not None
    assert membre.photo.alt == "Portrait d'Alice"


def test_profil_ne_touche_que_sa_propre_fiche(client, db):
    """ANTI-IDOR : l'édition passe par request.user.membre (aucun id d'URL) —
    la fiche d'un autre membre n'est jamais affectée."""
    alice = _membre("alice")
    bob = _membre("bob")
    bob.role_public = "Régisseur"
    bob.save()

    client.force_login(alice.user)
    client.post(PROFIL, _donnees_profil(role_public="Metteuse en scène"))

    alice.refresh_from_db()
    bob.refresh_from_db()
    assert alice.role_public == "Metteuse en scène"
    assert bob.role_public == "Régisseur"  # inchangé


def test_profil_reseau_d_autrui_non_modifiable_par_id_forge(client, db):
    """ANTI-IDOR (formset) : un POST forgé avec l'id d'un LienReseau appartenant
    à un autre membre ne doit ni le modifier, ni le voler, ni le supprimer."""
    alice = _membre("alice")
    bob = _membre("bob")
    lien_bob = LienReseau.objects.create(
        membre=bob, reseau=LienReseau.Reseau.INSTAGRAM, url="https://instagram.com/bob"
    )

    client.force_login(alice.user)
    client.post(
        PROFIL,
        _donnees_profil(
            **{
                "liens_reseaux-INITIAL_FORMS": "1",
                "liens_reseaux-0-id": str(lien_bob.pk),
                "liens_reseaux-0-reseau": LienReseau.Reseau.YOUTUBE,
                "liens_reseaux-0-url": "https://youtube.com/pirate",
                "liens_reseaux-0-ordre": "0",
            }
        ),
    )

    lien_bob.refresh_from_db()
    assert lien_bob.membre_id == bob.pk  # non réassigné à alice
    assert lien_bob.reseau == LienReseau.Reseau.INSTAGRAM  # non modifié
    assert lien_bob.url == "https://instagram.com/bob"
    assert not alice.liens_reseaux.exists()  # rien créé chez alice non plus


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


# --- Réponse à une convocation (présence / pouvoir en libre-service) -------


def _ag_convoquee(titre="AG 2026"):
    return Reunion.objects.create(
        titre=titre,
        type_reunion=Reunion.TypeReunion.AG_ORDINAIRE,
        statut=Reunion.Statut.CONVOQUEE,
    )


def test_membre_declare_sa_presence_sur_la_convocation(client, db):
    membre = _membre("alice")
    reunion = _ag_convoquee()
    client.force_login(membre.user)
    reponse = client.post(
        f"/espace/convocations/{reunion.pk}/", {"statut": Presence.Statut.PRESENT}
    )
    assert reponse.status_code == 302
    assert Presence.objects.get(reunion=reunion, membre=membre).statut == Presence.Statut.PRESENT


def test_membre_donne_pouvoir_depuis_la_convocation(client, db):
    membre = _membre("alice")
    mandataire = _membre("bob")
    reunion = _ag_convoquee()
    client.force_login(membre.user)
    reponse = client.post(
        f"/espace/convocations/{reunion.pk}/",
        {"statut": Presence.Statut.REPRESENTE, "mandataire": mandataire.pk},
    )
    assert reponse.status_code == 302
    assert Pouvoir.objects.filter(reunion=reunion, mandant=membre, mandataire=mandataire).exists()
    presence = Presence.objects.get(reunion=reunion, membre=membre)
    assert presence.statut == Presence.Statut.REPRESENTE


def test_reponse_impossible_sur_une_ag_tenue(client, db):
    membre = _membre("alice")
    reunion = Reunion.objects.create(
        titre="AG tenue",
        type_reunion=Reunion.TypeReunion.AG_ORDINAIRE,
        statut=Reunion.Statut.TENUE,
    )
    client.force_login(membre.user)
    reponse = client.post(
        f"/espace/convocations/{reunion.pk}/", {"statut": Presence.Statut.PRESENT}
    )
    assert reponse.status_code == 200  # lecture seule : pas de formulaire
    assert not Presence.objects.filter(reunion=reunion, membre=membre).exists()


def test_reponse_convocation_anti_idor_sur_reunion_bureau(client, db):
    membre = _membre("alice")
    reunion = Reunion.objects.create(
        titre="Bureau",
        type_reunion=Reunion.TypeReunion.BUREAU,
        statut=Reunion.Statut.CONVOQUEE,
    )
    client.force_login(membre.user)
    # Réunion de bureau : hors périmètre d'un membre simple -> 404.
    reponse = client.post(
        f"/espace/convocations/{reunion.pk}/", {"statut": Presence.Statut.PRESENT}
    )
    assert reponse.status_code == 404
    assert not Presence.objects.filter(reunion=reunion).exists()


# --- Branche Association : lecture membre vs écriture bureau ----------------


def test_membre_lit_les_documents_association_sans_arborescence(client, db):
    """Un membre voit les documents officiels accessibles en liste plate (via
    l'explorateur), sans le nom des dossiers, et n'accède pas à l'arborescence
    (réservée au bureau : 404)."""
    membre = _membre("alice")
    dossier = Dossier.add_root(nom="DossierSecret")  # espace ASSOCIATION par défaut
    Document.objects.create(
        titre="StatutsMembres",
        dossier=dossier,
        confidentialite=Document.Confidentialite.MEMBRES,
        fichier=SimpleUploadedFile("s.pdf", b"x"),
    )
    client.force_login(membre.user)
    corps = client.get("/espace/fichiers/").content.decode()
    assert "StatutsMembres" in corps  # document accessible listé
    assert "DossierSecret" not in corps  # nom de dossier officiel jamais exposé
    # La navigation dans un dossier officiel est réservée au bureau.
    assert client.get(f"/espace/association/{dossier.pk}/").status_code == 404


def test_membre_ne_voit_pas_un_document_association_prive(client, db):
    """Un document « Privé » d'autrui n'est pas listé pour un membre."""
    membre = _membre("alice")
    dossier = Dossier.add_root(nom="Confidentiel")
    Document.objects.create(
        titre="DocPriveAsso",
        dossier=dossier,
        confidentialite=Document.Confidentialite.PRIVE,
        fichier=SimpleUploadedFile("p.pdf", b"x"),
        cree_par=_membre("rh").user,
    )
    client.force_login(membre.user)
    corps = client.get("/espace/fichiers/").content.decode()
    assert "DocPriveAsso" not in corps


def test_bureau_supprime_un_dossier_association_vide(client, db):
    dossier = Dossier.add_root(nom="ASupprimer")
    client.force_login(_staff())
    reponse = client.post(f"/espace/association/{dossier.pk}/supprimer/")
    assert reponse.status_code == 302
    assert not Dossier.objects.filter(pk=dossier.pk).exists()


def test_suppression_association_reservee_au_bureau(client, db):
    dossier = Dossier.add_root(nom="Protege")
    client.force_login(_membre("lambda").user)
    reponse = client.post(f"/espace/association/{dossier.pk}/supprimer/")
    assert reponse.status_code == 404
    assert Dossier.objects.filter(pk=dossier.pk).exists()


# --- Fiche verrouillée : raccourci back-office pour le bureau ---------------


def _evenement_verrouille(auteur):
    """Événement « proposé » (en attente du contrôle initial du bureau, donc
    verrouillé côté auteur) créé par `auteur`. NB : une fois *publié*, il
    redevient éditable — c'est le cas testé plus bas."""
    return Evenement.objects.create(
        titre="Nuit blanche",
        date_debut=timezone.now() + timedelta(days=5),
        statut_moderation=Statut.PROPOSE,
        visibilite=Evenement.Visibilite.PUBLIC,
        cree_par=auteur.user,
    )


def test_evenement_verrouille_le_bureau_a_un_lien_backoffice(client, db):
    """Quand l'auteur est aussi membre du bureau, la page verrouillée propose
    d'éditer dans le back-office plutôt que « contactez le bureau »."""
    membre = _membre("presidente")
    membre.user.is_staff = True  # membre du bureau (est_bureau)
    membre.user.save()
    evt = _evenement_verrouille(membre)
    client.force_login(membre.user)

    corps = client.get(f"/espace/evenements/{evt.pk}/modifier/").content.decode()
    assert "Modifier dans le back-office" in corps
    assert f"/bureau/evenements/{evt.pk}/" in corps
    assert "Contactez le bureau" not in corps


def test_evenement_verrouille_membre_ordinaire_renvoie_au_bureau(client, db):
    """Un auteur sans rôle bureau garde le message « contactez le bureau »."""
    membre = _membre("simple")
    evt = _evenement_verrouille(membre)
    client.force_login(membre.user)

    corps = client.get(f"/espace/evenements/{evt.pk}/modifier/").content.decode()
    assert "Contactez le bureau" in corps
    assert "Modifier dans le back-office" not in corps


# --- Édition d'une fiche PUBLIÉE : en ligne aussitôt + signalement bureau ---


def _evenement_publie_de(auteur, titre="Avant"):
    return Evenement.objects.create(
        titre=titre,
        date_debut=make_aware(datetime(2026, 9, 1, 20, 30)),
        statut_moderation=Statut.PUBLIE,
        visibilite=Evenement.Visibilite.PUBLIC,
        cree_par=auteur.user,
    )


def test_membre_edite_son_evenement_publie_en_ligne_et_signale(client, db):
    """La retouche d'un événement publié reste en ligne (pas de re-modération)
    et lève le drapeau « à revoir » pour le bureau."""
    membre = _membre("alice")
    evt = _evenement_publie_de(membre)
    client.force_login(membre.user)

    reponse = client.post(
        f"/espace/evenements/{evt.pk}/modifier/",
        _donnees_evenement(titre="Après", action="enregistrer"),
    )
    assert reponse.status_code == 302
    evt.refresh_from_db()
    assert evt.titre == "Après"
    assert evt.statut_moderation == Statut.PUBLIE  # reste publié
    assert evt.modifie_apres_publication is True  # signalé au bureau


def test_membre_edite_son_projet_publie_en_ligne_et_signale(client, db):
    membre = _membre("alice")
    projet = Spectacle.objects.create(
        titre="Avant",
        type_portage=Spectacle.TypePortage.PERSONNEL,
        statut_moderation=Statut.PUBLIE,
    )
    projet.porteurs.add(membre)
    client.force_login(membre.user)

    client.post(
        f"/espace/projets/{projet.pk}/modifier/",
        _donnees_projet(titre="Après", action="enregistrer"),
    )
    projet.refresh_from_db()
    assert projet.titre == "Après"
    assert projet.statut_moderation == Statut.PUBLIE
    assert projet.modifie_apres_publication is True


def test_page_edition_publie_annonce_mise_en_ligne_immediate(client, db):
    membre = _membre("alice")
    evt = _evenement_publie_de(membre, titre="Publié")
    client.force_login(membre.user)

    corps = client.get(f"/espace/evenements/{evt.pk}/modifier/").content.decode()
    assert "immédiatement" in corps
    assert "Enregistrer les modifications" in corps
    assert "Soumettre à validation" not in corps  # déjà publié : pas de re-soumission


def test_bureau_voit_les_fiches_a_revoir_et_les_acquitte(client, db):
    membre = _membre("alice")
    evt = _evenement_publie_de(membre, titre="Retouche")
    evt.modifie_apres_publication = True
    evt.save(update_fields=["modifie_apres_publication"])
    client.force_login(_staff())

    corps = client.get("/bureau/moderation/").content.decode()
    assert "À revoir" in corps
    assert "Retouche" in corps

    reponse = client.post(f"/bureau/moderation/evenement/{evt.pk}/revu/")
    assert reponse.status_code == 302
    evt.refresh_from_db()
    assert evt.modifie_apres_publication is False


# --- Fiche (lecture) de ses propres événements / projets -------------------


def test_voir_evenement_affiche_fiche_bouton_modifier_et_lien_public(client, db):
    membre = _membre("alice")
    evt = _evenement_publie_de(membre, titre="Ma fiche")
    client.force_login(membre.user)

    reponse = client.get(f"/espace/evenements/{evt.pk}/")
    assert reponse.status_code == 200
    corps = reponse.content.decode()
    assert "Ma fiche" in corps
    assert f"/espace/evenements/{evt.pk}/modifier/" in corps  # bouton « Modifier »
    assert f"/agenda/{evt.pk}/" in corps  # « Voir sur le site » (publié + public)


def test_voir_evenement_anti_idor(client, db):
    proprietaire = _membre("proprio")
    evt = _evenement_publie_de(proprietaire)
    client.force_login(_membre("intrus").user)
    assert client.get(f"/espace/evenements/{evt.pk}/").status_code == 404


def test_voir_evenement_propose_pas_de_bouton_modifier(client, db):
    membre = _membre("alice")
    evt = _evenement_verrouille(membre)  # proposé → verrouillé côté auteur
    client.force_login(membre.user)

    corps = client.get(f"/espace/evenements/{evt.pk}/").content.decode()
    assert "modification en pause" in corps
    assert f"/espace/evenements/{evt.pk}/modifier/" not in corps


def test_voir_projet_anti_idor(client, db):
    proprietaire = _membre("proprio")
    projet = Spectacle.objects.create(titre="Secret", type_portage=Spectacle.TypePortage.PERSONNEL)
    projet.porteurs.add(proprietaire)
    client.force_login(_membre("intrus").user)
    assert client.get(f"/espace/projets/{projet.pk}/").status_code == 404


def test_mes_evenements_lie_vers_la_fiche_pas_le_formulaire(client, db):
    membre = _membre("alice")
    evt = _evenement_publie_de(membre)
    client.force_login(membre.user)
    corps = client.get("/espace/evenements/").content.decode()
    assert f'href="/espace/evenements/{evt.pk}/"' in corps  # vers la fiche (lecture)
