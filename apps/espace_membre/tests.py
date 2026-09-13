"""Tests de l'espace membre : accès protégé + anti-IDOR."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.utils.html import escape
from django.utils.timezone import make_aware

from apps.agenda.models import Evenement, ImageEvenement
from apps.budget.models import Adhesion, RecuFiscal, Saison
from apps.budget.services import emettre_recu
from apps.coeur.models import LienReseau, Membre, Utilisateur, champs_images_artiste
from apps.coeur.services import brouillon_de, brouillon_en_attente
from apps.common.models import Moderation
from apps.documents import services as doc_services
from apps.documents.models import Document, Dossier
from apps.espace_membre.forms import PageArtisteForm
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


def _image_png(nom="image.png", taille=(2, 2)):
    """Fabrique une vraie image PNG (validée par ImageField/Pillow).

    Minuscule par défaut — la plupart des tests ne regardent que le geste. Une
    taille explicite sert là où le TRAITEMENT est en jeu : sous 600 px de large,
    aucune vignette n'est produite, et une assertion « pas de vignette » serait
    alors vraie sans rien prouver."""
    from io import BytesIO

    from PIL import Image

    tampon = BytesIO()
    Image.new("RGB", taille, "red").save(tampon, "PNG")
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
    document = _document(Document.Confidentialite.CONNECTES)
    reponse = client.get(f"/espace/documents/{document.pk}/telecharger/")
    assert reponse.status_code == 302
    assert "/connexion/" in reponse.url


def test_document_tout_compte_connecte_est_servi_a_un_membre(client, db):
    membre = _membre("alice")
    document = _document(Document.Confidentialite.CONNECTES, contenu=b"contenu ouvert")
    client.force_login(membre.user)
    reponse = client.get(f"/espace/documents/{document.pk}/telecharger/")
    assert reponse.status_code == 200
    assert _corps_stream(reponse) == b"contenu ouvert"
    assert "attachment" in reponse["Content-Disposition"]


def test_document_tout_compte_connecte_est_servi_sans_fiche_membre(client, db):
    """Ce que le niveau veut VRAIMENT dire, et pourquoi il ne s'appelle plus
    « Public » : il est plus large que « Membres » (un compte technique y a
    droit) tout en restant fermé aux visiteurs. Le libellé disait l'inverse."""
    user = Utilisateur.objects.create_user(username="technique", password="x")
    document = _document(Document.Confidentialite.CONNECTES)
    client.force_login(user)
    assert client.get(f"/espace/documents/{document.pk}/telecharger/").status_code == 200


def test_le_niveau_le_plus_ouvert_ne_s_annonce_pas_comme_public(db):
    """Le mot « Public » en base de documents privés a fait classer des pièces
    au mauvais niveau. Le libellé doit dire ce que le contrôle fait."""
    libelles = dict(Document.Confidentialite.choices)
    assert libelles[Document.Confidentialite.CONNECTES] == "Tout compte connecté"
    assert "Public" not in libelles.values()


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
    _document(Document.Confidentialite.CONNECTES, titre="StatutsPublics")
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


def test_le_sommaire_des_fichiers_est_navigable(client, db):
    """Chaque branche du panneau latéral est un lien vers sa section, y compris
    depuis un dossier — et y compris Association, dont un membre ne voit pas
    l'arborescence."""
    membre = _membre("alice")
    dossier = _dossier_membre(membre, Visibilite.PRIVE, nom="Photos")
    client.force_login(membre.user)
    for url in ("/espace/fichiers/", f"/espace/fichiers/{dossier.pk}/"):
        corps = client.get(url).content.decode()
        for ancre in ("t-perso", "t-partage", "t-bureau", "t-association", "t-recus"):
            assert f'href="/espace/fichiers/#{ancre}"' in corps, (url, ancre)


def test_les_sections_portent_les_ancres_du_sommaire(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    corps = client.get("/espace/fichiers/").content.decode()
    for ancre in ("t-perso", "t-partage", "t-bureau", "t-association", "t-recus"):
        assert f'id="{ancre}"' in corps, ancre


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


# Compte connecté SANS fiche membre (compte technique, fiche supprimée…). Le
# filtre `proprietaire=membre` devenait `proprietaire=None` : exactement les
# dossiers officiels et communs, et les documents non classés comme les PV.


def _compte_sans_fiche():
    return Utilisateur.objects.create_user(username="sansfiche", password="x")


def test_compte_sans_fiche_ne_supprime_pas_un_dossier_officiel_ou_commun(client, db):
    officiel = doc_services.creer_dossier_association(nom="Statuts")
    commun = doc_services.creer_dossier_commun(nom="Répétitions")
    client.force_login(_compte_sans_fiche())
    for dossier in (officiel, commun):
        assert client.post(f"/espace/fichiers/{dossier.pk}/supprimer/").status_code == 404
        assert Dossier.objects.filter(pk=dossier.pk).exists()


def test_compte_sans_fiche_ne_supprime_pas_un_document_officiel(client, db):
    officiel = _fichier(doc_services.creer_dossier_association(nom="Statuts"), titre="Statuts")
    non_classe = _document(Document.Confidentialite.MEMBRES, titre="PV")
    client.force_login(_compte_sans_fiche())
    for document in (officiel, non_classe):
        chemin = document.fichier.name
        assert client.post(f"/espace/fichiers/doc/{document.pk}/supprimer/").status_code == 404
        assert Document.objects.filter(pk=document.pk).exists()
        assert document.fichier.storage.exists(chemin)  # le fichier physique aussi


def test_nouvelle_version_d_une_version_deja_remplacee_refusee(client, db):
    """Repartir d'une ancienne version créait une seconde branche courante."""
    v1 = _document(Document.Confidentialite.MEMBRES, titre="Statuts")
    doc_services.remplacer_document(v1, fichier=SimpleUploadedFile("v2.pdf", b"v2"))
    client.force_login(_staff())

    reponse = client.post(
        f"/espace/association/doc/{v1.pk}/nouvelle-version/",
        {"fichier": SimpleUploadedFile("v3.pdf", b"v3")},
    )

    assert reponse.status_code == 302
    assert Document.objects.count() == 2
    assert Document.objects.filter(courant=True).count() == 1


# Un compte rendu rend compte à TOUS les membres, réunion de bureau comprise —
# décision de l'association (sept. 2026). La page d'une réunion de bureau reste
# réservée au bureau ; son PV, non. Ce test fixe ce choix, qu'un audit avait
# pris pour une fuite.


def test_un_membre_sans_moteur_pdf_recoit_un_message_pas_une_500(client, db, monkeypatch):
    """Le reçu fiscal d'un membre passe par le même rendu : sans les
    bibliothèques natives, il tombait en erreur 500 côté membre aussi."""
    from apps.common.pdf import RenduPDFIndisponible

    def absent(html, *, base_url=None):
        raise RenduPDFIndisponible(
            "Les bibliothèques natives de WeasyPrint sont introuvables sur cette machine."
        )

    monkeypatch.setattr("apps.common.pdf.html_vers_pdf", absent)
    membre = _membre("alice")
    saison = Saison.objects.create(nom="2025-2026")
    adhesion = Adhesion.objects.create(
        membre=membre, saison=saison, statut=Adhesion.Statut.PAYEE, montant_verse=Decimal("30")
    )
    recu = emettre_recu(
        type_versement=RecuFiscal.TypeVersement.COTISATION,
        montant=Decimal("30"),
        date_versement=date(2026, 3, 1),
        donateur_nom=str(membre),
        membre=membre,
        adhesion=adhesion,
    )
    client.force_login(membre.user)

    reponse = client.get(f"/espace/recus/{recu.pk}/telecharger/", follow=True)

    corps = reponse.content.decode()
    assert reponse.status_code == 200
    # Sans apostrophe dans l'assertion : le gabarit l'échappe en `&#x27;`.
    assert "pas pu être produit" in corps
    # Le membre n'a pas à lire le nom des bibliothèques manquantes.
    assert "WeasyPrint" not in corps
    assert "GTK" not in corps


def test_le_pv_d_une_reunion_de_bureau_est_lisible_par_tout_membre(client, db, monkeypatch):
    from apps.gouvernance.services import generer_compte_rendu

    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: b"%PDF-1.4 pv"
    )
    reunion = Reunion.objects.create(
        titre="Bureau de mars",
        type_reunion=Reunion.TypeReunion.BUREAU,
        statut=Reunion.Statut.TENUE,
    )
    pv = generer_compte_rendu(reunion, par=_staff())

    client.force_login(_membre("alice").user)
    assert client.get(f"/espace/documents/{pv.pk}/telecharger/").status_code == 200


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


def test_le_formulaire_refuse_une_video_d_un_autre_hebergeur(client, db):
    """Un refus explicite, pas un champ vidé en silence.

    Vider l'adresse sans rien dire ferait croire à l'artiste que sa vidéo est
    enregistrée ; il ne le découvrirait qu'en relisant sa page publiée — et il
    n'aurait aucune raison de soupçonner le formulaire.
    """
    membre = _membre("vimeoiste")
    client.force_login(membre.user)

    reponse = client.post(PROFIL, _donnees_profil(video_youtube="https://vimeo.com/76979871"))

    assert reponse.status_code == 200  # réaffiché avec l'erreur, pas redirigé
    # `escape` parce que le gabarit échappe les apostrophes : chercher le message
    # tel qu'on l'a écrit ne trouverait rien — et le contrôle aurait l'air de
    # tenir si on l'avait écrit avec `not in`.
    assert escape("n'est pas celle d'une vidéo YouTube") in reponse.content.decode()
    assert brouillon_de(membre, creer=False).video_youtube == ""


def test_le_formulaire_garde_l_identifiant_et_non_l_adresse_collee(client, db):
    """Ce qui est stocké ne peut désigner qu'une vidéo YouTube.

    Le gabarit reconstruit l'adresse à partir d'un fournisseur qu'il choisit :
    même un gabarit distrait ne peut pas faire partir une requête ailleurs.
    """
    membre = _membre("videaste")
    client.force_login(membre.user)

    client.post(
        PROFIL,
        _donnees_profil(video_youtube="https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s"),
    )

    assert brouillon_de(membre, creer=False).video_youtube == "dQw4w9WgXcQ"


def test_profil_exige_la_connexion(client, db):
    reponse = client.get(PROFIL)
    assert reponse.status_code == 302
    assert "/connexion/" in reponse.url


def test_enregistrer_son_profil_ne_met_rien_en_ligne(client, db):
    """La promesse du chantier : le public lit le `Membre`, l'écran écrit le
    brouillon. Tant qu'on n'a pas publié, la page ne bouge pas."""
    membre = _membre("alice")
    client.force_login(membre.user)

    reponse = client.post(
        PROFIL,
        _donnees_profil(role_public="Comédienne", bio="Une bio", site_web="https://alice.example"),
    )

    assert reponse.status_code == 302
    membre.refresh_from_db()
    assert membre.role_public == ""
    assert membre.site_web == ""
    assert brouillon_de(membre).role_public == "Comédienne"
    assert brouillon_en_attente(membre) is True


def test_publier_met_la_page_en_ligne(client, db):
    """Et « Publier » enregistre d'abord : on ne clique pas dessus en voulant
    mettre en ligne la version d'avant."""
    membre = _membre("alice")
    client.force_login(membre.user)

    client.post(
        PROFIL,
        _donnees_profil(
            role_public="Comédienne",
            bio="Une bio relue",
            site_web="https://alice.example",
            action="publier",
        ),
    )

    membre.refresh_from_db()
    assert membre.role_public == "Comédienne"
    assert membre.bio == "Une bio relue"
    assert membre.site_web == "https://alice.example"
    assert brouillon_en_attente(membre) is False


def test_publier_sans_rien_de_neuf_le_dit_au_lieu_de_lever(client, db):
    """Double-clic, retour arrière du navigateur : un non-événement, pas une
    erreur. C'est la leçon du bouton « Retirer » de la gouvernance."""
    membre = _membre("alice")
    client.force_login(membre.user)
    client.post(PROFIL, _donnees_profil(role_public="Comédienne", action="publier"))

    reponse = client.post(
        PROFIL, _donnees_profil(role_public="Comédienne", action="publier"), follow=True
    )

    assert reponse.status_code == 200
    assert "Rien de neuf à publier" in reponse.content.decode()


def test_membre_ajoute_un_reseau(client, db):
    """Les liens ne passent PAS par le brouillon : ce sont une liste, pas une
    présentation, et l'écran le dit là où ils se saisissent."""
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


def test_le_telephone_n_attend_pas_la_publication(client, db):
    """Il n'est pas public : il n'a pas de version publique à protéger."""
    membre = _membre("alice")
    client.force_login(membre.user)

    client.post(PROFIL, _donnees_profil(telephone="0600000000"))

    membre.refresh_from_db()
    assert membre.telephone == "0600000000"


def test_membre_ajoute_une_photo_de_profil(client, db):
    """Elle part au brouillon, comme le reste de la présentation : publier la
    recopie sur la fiche publique."""
    membre = _membre("alice")
    client.force_login(membre.user)
    client.post(
        PROFIL,
        _donnees_profil(photo_fichier=_image_png("portrait.png"), photo_alt="Portrait d'Alice"),
    )

    membre.refresh_from_db()
    assert membre.photo is None
    brouillon = brouillon_de(membre)
    assert brouillon.photo is not None
    assert brouillon.photo.alt == "Portrait d'Alice"

    client.post(PROFIL, _donnees_profil(action="publier"))
    membre.refresh_from_db()
    assert membre.photo_id == brouillon.photo_id


def test_profil_ne_touche_que_sa_propre_fiche(client, db):
    """ANTI-IDOR : l'édition passe par request.user.membre (aucun id d'URL) —
    ni la fiche d'un autre membre, ni son brouillon, ne sont affectés."""
    alice = _membre("alice")
    bob = _membre("bob")
    bob.role_public = "Régisseur"
    bob.save()

    client.force_login(alice.user)
    client.post(PROFIL, _donnees_profil(role_public="Metteuse en scène", action="publier"))

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


def test_la_convocation_offre_le_pv_corrige_et_non_celui_d_avant(client, db, monkeypatch):
    """Même point que côté bureau, et c'est ici qu'il compte : le PV part en
    confidentialité « Membres », donc à toute l'association. Un membre suivait
    le lien d'une version que la GED avait remplacée."""
    from django.core.files.base import ContentFile

    from apps.documents.services import remplacer_document
    from apps.gouvernance.services import generer_compte_rendu

    monkeypatch.setattr("apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: b"%PDF v1")
    membre = _membre("convoque")
    reunion = Reunion.objects.create(
        titre="AG", type_reunion=Reunion.TypeReunion.AG_ORDINAIRE, statut=Reunion.Statut.TENUE
    )
    v1 = generer_compte_rendu(reunion, par=membre.user)
    v2 = remplacer_document(
        v1, fichier=ContentFile(b"%PDF corrige", name="pv.pdf"), par=membre.user
    )
    client.force_login(membre.user)

    corps = client.get(f"/espace/convocations/{reunion.pk}/").content.decode()

    assert f"/espace/documents/{v2.pk}/telecharger/" in corps
    assert f"/espace/documents/{v1.pk}/telecharger/" not in corps


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
    """Les reçus sont une section de « Fichiers » ; un membre n'y voit que les siens."""
    membre = _membre("alice")
    autre = _membre("bob")
    _recu_pour(membre, montant=Decimal("111.00"))
    _recu_pour(autre, montant=Decimal("999.00"))

    client.force_login(membre.user)
    corps = client.get("/espace/fichiers/").content.decode()
    assert "111" in corps
    assert "999" not in corps  # anti-IDOR : pas le reçu d'un autre membre


def test_ancienne_page_recus_redirige_vers_les_fichiers(client, db):
    """La route dédiée survit en redirection : signets et liens déjà envoyés."""
    membre = _membre("alice")
    client.force_login(membre.user)
    reponse = client.get("/espace/recus/")
    assert reponse.status_code == 302
    assert reponse["Location"] == "/espace/fichiers/#t-recus"


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


# --- Accessibilité : aide reliée au champ (aria-describedby) ----------------


def test_formulaire_lie_l_aide_via_aria_describedby(db):
    """Le texte d'aide d'un champ est relié au widget (WCAG 1.3.1), avec un id
    qui correspond au <span class="champ__aide"> du gabarit.

    L'id suit désormais la convention de DJANGO (`_helptext`) et non plus celle
    d'un mixin maison (`_aide`) : deux conventions concurrentes laissaient une
    référence morte dans tout formulaire qui oubliait le mixin."""
    from apps.espace_membre.forms import PageArtisteForm

    html = str(PageArtisteForm()["role_public"])
    assert 'aria-describedby="id_role_public_helptext"' in html


# --- Déplacement d'un dossier (GED-1) ---------------------------------------


def test_membre_deplace_son_dossier(client, db):
    alice = _membre("alice")
    source = _dossier_membre(alice, Visibilite.PRIVE, nom="Photos")
    cible = _dossier_membre(alice, Visibilite.PRIVE, nom="Archives")
    client.force_login(alice.user)

    reponse = client.post(f"/espace/fichiers/{source.pk}/deplacer/", {"parent": cible.pk})

    assert reponse.status_code == 302
    source.refresh_from_db()
    assert source.get_parent().pk == cible.pk


def test_membre_ne_peut_pas_deplacer_le_dossier_d_un_autre(client, db):
    """Règle 1 : le déplacement ne doit pas devenir la porte dérobée que le
    renommage n'est pas."""
    alice = _membre("alice")
    dossier = _dossier_membre(alice, Visibilite.PRIVE, nom="Alice")
    cible = _dossier_membre(alice, Visibilite.PRIVE, nom="Cible")
    bob = _membre("bob")
    client.force_login(bob.user)

    assert client.get(f"/espace/fichiers/{dossier.pk}/deplacer/").status_code == 404
    reponse = client.post(f"/espace/fichiers/{dossier.pk}/deplacer/", {"parent": cible.pk})
    assert reponse.status_code == 404

    dossier.refresh_from_db()
    assert dossier.get_parent() is None


def test_le_dossier_d_un_autre_membre_n_est_pas_une_cible_proposee(client, db):
    """Anti-IDOR jusque dans la liste déroulante : un dossier qu'on ne peut
    pas voir ne doit pas non plus être proposé comme destination."""
    alice = _membre("alice")
    bob = _membre("bob")
    a_alice = _dossier_membre(alice, Visibilite.PRIVE, nom="Photos")
    a_bob = _dossier_membre(bob, Visibilite.PRIVE, nom="Chez Bob")
    client.force_login(alice.user)

    reponse = client.get(f"/espace/fichiers/{a_alice.pk}/deplacer/")
    cibles = list(reponse.context["form"].fields["parent"].queryset)

    assert a_bob not in cibles


def test_un_dossier_ne_se_propose_pas_lui_meme_ni_ses_sous_dossiers(client, db):
    alice = _membre("alice")
    parent = _dossier_membre(alice, Visibilite.PRIVE, nom="Photos")
    enfant = _dossier_membre(alice, Visibilite.PRIVE, parent=parent, nom="2025")
    client.force_login(alice.user)

    reponse = client.get(f"/espace/fichiers/{parent.pk}/deplacer/")
    cibles = list(reponse.context["form"].fields["parent"].queryset)

    assert parent not in cibles
    assert enfant not in cibles


def test_deplacer_vers_un_dossier_partage_expose_le_sous_arbre(client, db):
    """La conséquence que l'écran annonce doit être celle qui se produit."""
    alice = _membre("alice")
    prive = _dossier_membre(alice, Visibilite.PRIVE, nom="Brouillons")
    enfant = _dossier_membre(alice, Visibilite.PRIVE, parent=prive, nom="2025")
    partage = _dossier_membre(alice, Visibilite.PARTAGE, nom="Troupe")
    client.force_login(alice.user)

    client.post(f"/espace/fichiers/{prive.pk}/deplacer/", {"parent": partage.pk})

    prive.refresh_from_db()
    enfant.refresh_from_db()
    assert prive.visibilite == Visibilite.PARTAGE
    assert enfant.visibilite == Visibilite.PARTAGE


def test_l_ecran_de_deplacement_annonce_ce_qui_part_avec_le_dossier(client, db):
    alice = _membre("alice")
    parent = _dossier_membre(alice, Visibilite.PRIVE, nom="Photos")
    _dossier_membre(alice, Visibilite.PRIVE, parent=parent, nom="2025")
    client.force_login(alice.user)

    corps = client.get(f"/espace/fichiers/{parent.pk}/deplacer/").content.decode()

    assert "sous-dossier" in corps
    assert "confidentialité" in corps.lower() or "visible par toute la troupe" in corps


def test_un_membre_ne_deplace_pas_un_dossier_officiel(client, db):
    """L'espace ASSOCIATION est au bureau : un membre n'y touche pas."""
    alice = _membre("alice")
    officiel = doc_services.creer_dossier_association(nom="Statuts")
    client.force_login(alice.user)

    assert client.get(f"/espace/fichiers/{officiel.pk}/deplacer/").status_code == 404


def test_le_bureau_deplace_un_dossier_officiel(client, db):
    officiel = doc_services.creer_dossier_association(nom="Statuts")
    cible = doc_services.creer_dossier_association(nom="Archives")
    client.force_login(_staff())

    reponse = client.post(f"/espace/fichiers/{officiel.pk}/deplacer/", {"parent": cible.pk})

    assert reponse.status_code == 302
    officiel.refresh_from_db()
    assert officiel.get_parent().pk == cible.pk


def test_un_post_force_vers_le_dossier_d_un_autre_est_refuse(client, db):
    """Le champ ne PROPOSE pas la cible d'un autre membre — encore faut-il que
    la forcer à la main échoue. Deux barrières le refusent : le queryset du
    formulaire, puis les invariants du service."""
    alice = _membre("alice")
    bob = _membre("bob")
    a_alice = _dossier_membre(alice, Visibilite.PRIVE, nom="Photos")
    chez_bob = _dossier_membre(bob, Visibilite.PRIVE, nom="Chez Bob")
    client.force_login(alice.user)

    reponse = client.post(f"/espace/fichiers/{a_alice.pk}/deplacer/", {"parent": chez_bob.pk})

    assert reponse.status_code == 200  # réaffiché avec l'erreur, pas exécuté
    a_alice.refresh_from_db()
    assert a_alice.get_parent() is None


def test_les_destinations_annoncent_leur_confidentialite(client, db):
    """L'audience se décide en choisissant la destination : « partagé » et
    « transmis au bureau » n'exposent pas au même monde, et le choix se fait
    dans la liste, pas dans l'encart."""
    alice = _membre("alice")
    source = _dossier_membre(alice, Visibilite.PRIVE, nom="Brouillons")
    _dossier_membre(alice, Visibilite.PARTAGE, nom="Troupe")
    _dossier_membre(alice, Visibilite.BUREAU, nom="Transmis")
    client.force_login(alice.user)

    corps = client.get(f"/espace/fichiers/{source.pk}/deplacer/").content.decode()

    assert "Partagé (toute la troupe)" in corps
    assert "Transmis au bureau" in corps


def test_deplacer_vers_la_branche_bureau_expose_au_bureau(client, db):
    """La troisième audience, que l'écran passait sous silence."""
    alice = _membre("alice")
    prive = _dossier_membre(alice, Visibilite.PRIVE, nom="Brouillons")
    enfant = _dossier_membre(alice, Visibilite.PRIVE, parent=prive, nom="Notes")
    bureau = _dossier_membre(alice, Visibilite.BUREAU, nom="Transmis")
    client.force_login(alice.user)

    client.post(f"/espace/fichiers/{prive.pk}/deplacer/", {"parent": bureau.pk})

    prive.refresh_from_db()
    enfant.refresh_from_db()
    assert prive.visibilite == Visibilite.BUREAU
    assert enfant.visibilite == Visibilite.BUREAU


def test_l_ecran_d_un_dossier_mene_a_son_deplacement(client, db):
    """Une fonction qu'aucun écran ne propose n'existe pas pour l'utilisateur."""
    alice = _membre("alice")
    dossier = _dossier_membre(alice, Visibilite.PRIVE, nom="Photos")
    client.force_login(alice.user)

    corps = client.get(f"/espace/fichiers/{dossier.pk}/").content.decode()

    assert f"/espace/fichiers/{dossier.pk}/deplacer/" in corps


def test_le_lecteur_sans_droit_d_ecriture_ne_voit_pas_le_deplacement(client, db):
    """Le lien suit `peut_ecrire` : un membre qui consulte un dossier commun en
    lecture ne doit pas se voir proposer de le déranger."""
    alice = _membre("alice")
    officiel = doc_services.creer_dossier_association(nom="Statuts")
    client.force_login(alice.user)

    # Un membre non-bureau n'atteint même pas l'écran d'un dossier officiel.
    assert client.get(f"/espace/fichiers/{officiel.pk}/deplacer/").status_code == 404


def test_le_tableau_de_bord_membre_ne_reprend_pas_les_entrees_du_rail(client, db):
    """Le tableau de bord membre portait quatre « Accès rapides » qui rouvraient
    des entrées du rail affichées juste à côté, dont deux vers la même page —
    le doublon démonté côté gestion, en plus petit. L'invariant est partagé
    (`conftest.liens_nus_rouvrant_le_rail`) pour qu'il ne diverge pas d'un
    écran à l'autre."""
    from conftest import liens_nus_rouvrant_le_rail

    membre = _membre("camille")
    client.force_login(membre.user)

    nus = liens_nus_rouvrant_le_rail(client.get("/espace/").content.decode())

    assert not nus, "liens nus rouvrant le rail :\n  " + "\n  ".join(nus)


# --- Fin d'adhésion : lecture seule (SEC-05) --------------------------------
#
# `Membre.actif = False` retirait du corps électoral et des listes de sélection,
# mais laissait l'espace membre entièrement ouvert en écriture. La décision :
# l'ancien membre CONSULTE (un reçu fiscal sert plusieurs années) et n'écrit plus.


def _membre_inactif(username="ancien"):
    membre = _membre(username)
    membre.actif = False
    membre.save(update_fields=["actif"])
    return membre


def test_membre_inactif_telecharge_encore_son_recu(client, db, monkeypatch):
    """Le cœur de la décision : ce qui lui appartient lui reste accessible."""
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: b"%PDF-1.4 x"
    )
    membre = _membre_inactif()
    recu = _recu_pour(membre)
    client.force_login(membre.user)

    reponse = client.get(f"/espace/recus/{recu.pk}/telecharger/")

    assert reponse.status_code == 200
    assert b"".join(reponse.streaming_content).startswith(b"%PDF")


def test_membre_inactif_consulte_encore_ses_ecrans(client, db):
    """La lecture ne se ferme nulle part : ni tableau de bord, ni projets, ni
    fichiers, ni convocations."""
    membre = _membre_inactif()
    client.force_login(membre.user)

    for url in ("/espace/", "/espace/projets/", "/espace/fichiers/", "/espace/convocations/"):
        assert client.get(url).status_code == 200, url


def test_membre_inactif_ne_cree_plus_de_projet(client, db):
    membre = _membre_inactif()
    client.force_login(membre.user)

    reponse = client.post(
        "/espace/projets/nouveau/", _donnees_projet(action="enregistrer"), follow=True
    )

    assert Spectacle.objects.count() == 0
    assert "adhésion" in reponse.content.decode()


def test_membre_inactif_ne_modifie_plus_son_projet(client, db):
    """Ses fiches restent en ligne et lisibles ; il ne les retouche plus."""
    membre = _membre_inactif()
    projet = Spectacle.objects.create(
        titre="Ancien", type_portage=Spectacle.TypePortage.PERSONNEL, cree_par=membre.user
    )
    projet.porteurs.add(membre)
    client.force_login(membre.user)

    client.post(
        f"/espace/projets/{projet.pk}/modifier/",
        _donnees_projet(titre="Retouché", action="enregistrer"),
    )

    projet.refresh_from_db()
    assert projet.titre == "Ancien"


def test_membre_inactif_ne_depose_plus_de_fichier(client, db):
    membre = _membre_inactif()
    dossier = _dossier_membre(membre, Visibilite.PRIVE, nom="Perso")
    client.force_login(membre.user)

    client.post(
        f"/espace/fichiers/{dossier.pk}/",
        {
            "form_type": "document",
            "titre": "Tardif",
            "description": "",
            "fichier": SimpleUploadedFile("x.pdf", b"data", content_type="application/pdf"),
        },
    )

    assert not Document.objects.filter(titre="Tardif").exists()


def test_membre_inactif_ne_repond_plus_a_une_convocation(client, db):
    """Il reçoit encore la convocation et lit l'ordre du jour — mais il n'est
    plus électeur, donc il ne se déclare plus présent ni représenté."""
    membre = _membre_inactif()
    ag = Reunion.objects.create(
        type_reunion=Reunion.TypeReunion.AG_ORDINAIRE,
        titre="AG 2026",
        date=make_aware(datetime(2026, 6, 1, 18, 0)),
        statut=Reunion.Statut.CONVOQUEE,
    )
    client.force_login(membre.user)

    corps = client.get(f"/espace/convocations/{ag.pk}/").content.decode()
    client.post(f"/espace/convocations/{ag.pk}/", {"statut": Presence.Statut.PRESENT})

    assert "AG 2026" in corps, "la convocation reste lisible"
    assert not Presence.objects.filter(reunion=ag, membre=membre).exists()


def test_membre_inactif_ne_se_voit_pas_proposer_d_ecrire(client, db):
    """Un bouton qui mène à un refus est un défaut d'interface : il disparaît."""
    membre = _membre_inactif()
    client.force_login(membre.user)

    corps = client.get("/espace/projets/").content.decode()

    assert "/espace/projets/nouveau/" not in corps


def test_un_membre_du_bureau_ecrit_meme_si_sa_fiche_est_inactive(client, db):
    """Le bureau administre l'association, pas sa propre adhésion : fermer son
    écriture bloquerait la gestion. Le contournement est volontaire, donc testé."""
    membre = _membre_inactif("tresorier")
    membre.user.is_staff = True
    membre.user.save(update_fields=["is_staff"])
    client.force_login(membre.user)

    client.post("/espace/projets/nouveau/", _donnees_projet(action="enregistrer"))

    assert Spectacle.objects.count() == 1


def test_membre_inactif_ne_recoit_pas_un_formulaire_qui_sera_refuse(client, db):
    """Défaut trouvé en relecture du lot 6 : les liens étaient bien masqués,
    mais les écrans restaient atteignables par leur adresse et affichaient un
    formulaire complet. L'ancien membre l'aurait rempli pour se voir refuser
    l'enregistrement à la fin — sa saisie perdue pour une réponse qu'on pouvait
    lui donner au début. Un écran qui n'est QUE un geste d'écriture se ferme."""
    membre = _membre_inactif()
    projet = Spectacle.objects.create(
        titre="Ancien", type_portage=Spectacle.TypePortage.PERSONNEL, cree_par=membre.user
    )
    projet.porteurs.add(membre)
    racine = _dossier_membre(membre, Visibilite.PRIVE, nom="Racine")
    sous = _dossier_membre(membre, Visibilite.PRIVE, nom="Sous", parent=racine)
    client.force_login(membre.user)

    ecrans = (
        "/espace/profil/",
        "/espace/projets/nouveau/",
        f"/espace/projets/{projet.pk}/modifier/",
        "/espace/evenements/nouveau/",
        f"/espace/fichiers/{sous.pk}/deplacer/",
        f"/espace/fichiers/{sous.pk}/editer/",
    )
    for url in ecrans:
        reponse = client.get(url)
        assert reponse.status_code == 302, f"{url} rend encore un formulaire"
        assert reponse["Location"] == "/espace/", url


def test_le_membre_a_jour_atteint_toujours_ces_ecrans(client, db):
    """Le garde-fou ci-dessus ne doit pas fermer la porte à qui a le droit — ni
    les écrans, ni leurs entrées de navigation."""
    membre = _membre("active")
    client.force_login(membre.user)

    for url in ("/espace/profil/", "/espace/projets/nouveau/", "/espace/evenements/nouveau/"):
        assert client.get(url).status_code == 200, url

    corps = client.get("/espace/").content.decode()
    assert "/espace/profil/" in corps, "le rail a perdu « Mon profil » pour tout le monde"
    assert "/espace/projets/nouveau/" in corps


def test_une_page_membre_ne_redemande_pas_les_groupes_a_chaque_controle(client, db):
    """Régression introduite puis corrigée dans le lot 6 : `est_bureau` retourne
    en base à chaque appel, et le contrôle d'écriture l'appelait une fois de
    plus par vue ET par gabarit — trois requêtes de groupes identiques sur
    chaque page servie à un membre connecté, là où une suffit.

    L'assertion porte sur cette requête précise, pas sur un total : un total se
    périme au premier `select_related` ajouté ailleurs et ne dirait plus rien."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    membre = _membre("alice")
    client.force_login(membre.user)
    client.get("/espace/")  # première passe : cache de gabarits

    with CaptureQueriesContext(connection) as requetes:
        client.get("/espace/")

    groupes = [r["sql"] for r in requetes.captured_queries if "auth_group" in r["sql"]]
    assert len(groupes) <= 1, f"{len(groupes)} requêtes de groupes pour une seule page"


def test_aucun_ecran_lisible_n_offre_de_formulaire_a_un_membre_inactif(client, db):
    """Le pendant du test précédent, pour les écrans qui RESTENT ouverts : ils
    se consultent, et n'y proposent plus aucun geste. Deux oublis trouvés en
    relecture — le formulaire « Nouveau dossier » de la page Fichiers, et le
    lien « Mon profil » du rail, qui ne mène plus qu'à un refus."""
    membre = _membre_inactif()
    dossier = _dossier_membre(membre, Visibilite.PRIVE, nom="Perso")
    client.force_login(membre.user)

    for url in ("/espace/", "/espace/fichiers/", f"/espace/fichiers/{dossier.pk}/"):
        corps = client.get(url).content.decode()
        assert "Nouveau dossier" not in corps, url
        assert 'name="form_type"' not in corps, url
        assert "/espace/profil/" not in corps, url


# --- Mot de passe oublié (FRONT-07) -----------------------------------------
#
# Aucune route ne le permettait : il fallait intervenir à la main sur le serveur.
# Le parcours s'écrit et s'éprouve avec le backend console de Django ; brancher un
# vrai SMTP au déploiement est une ligne de réglage.


def _lien_de_reinitialisation(corps):
    """Extrait le chemin du lien contenu dans le courriel envoyé."""
    import re

    trouve = re.search(r"/mot-de-passe/nouveau/[^\s]+", corps)
    return trouve.group(0) if trouve else None


# --- « Mot de passe oublié » : le seul formulaire qui écrit à un tiers (PUB-01)


def _demande_de_lien(client, adresse="alice@example.org", origine="203.0.113.7"):
    return client.post("/mot-de-passe/oublie/", {"email": adresse}, REMOTE_ADDR=origine)


def _membre_joignable(nom="alice", adresse="alice@example.org"):
    membre = _membre(nom)
    membre.user.email = adresse
    membre.user.save(update_fields=["email"])
    return membre


def test_une_boite_ne_se_noie_pas_par_repetition(client, db, mailoutbox, settings):
    """L'abus visé : on saisit l'adresse de QUELQU'UN D'AUTRE, et c'est sa
    boîte qui reçoit. Le lot qui a ajouté ce parcours ne l'a borné en rien."""
    _membre_joignable()
    settings.DEBIT_MOT_DE_PASSE = (99, 3600)  # on isole la borne par adresse
    settings.DEBIT_MOT_DE_PASSE_PAR_ADRESSE = (2, 3600)

    for _ in range(6):
        _demande_de_lien(client)

    assert len(mailoutbox) == 2


def test_changer_d_origine_ne_rouvre_pas_la_part_d_une_adresse(client, db, mailoutbox, settings):
    """Une limite par origine seule ne protégerait personne : changer d'origine
    ne coûte rien, alors que la boîte noyée reste la même."""
    _membre_joignable()
    settings.DEBIT_MOT_DE_PASSE = (99, 3600)
    settings.DEBIT_MOT_DE_PASSE_PAR_ADRESSE = (2, 3600)

    for n in range(6):
        _demande_de_lien(client, origine=f"203.0.113.{n}")

    assert len(mailoutbox) == 2


def test_une_origine_bloquee_n_epuise_pas_la_part_d_une_adresse(client, db, mailoutbox, settings):
    """L'ORDRE des deux bornes, et c'est tout le sujet de ce contrôle.

    Si l'on comptait l'adresse alors que l'origine est déjà refusée, un
    attaquant depuis une origine bloquée consommerait la part de sa victime et
    l'empêcherait, elle, de recevoir son propre lien. La borne d'origine doit
    donc sortir SANS toucher au compteur de l'adresse.
    """
    _membre_joignable()
    settings.DEBIT_MOT_DE_PASSE = (1, 3600)
    settings.DEBIT_MOT_DE_PASSE_PAR_ADRESSE = (2, 3600)

    _demande_de_lien(client, origine="203.0.113.1")  # part : origine 1, adresse 1
    _demande_de_lien(client, origine="203.0.113.1")  # refusé sur l'origine
    _demande_de_lien(client, origine="203.0.113.9")  # la victime, ailleurs

    assert len(mailoutbox) == 2, (
        "la tentative refusée sur l'origine a consommé la part de l'adresse"
    )


def test_le_refus_ne_se_voit_pas_sur_la_page(client, db, mailoutbox, settings):
    """Refuser ne doit RIEN changer à ce que la page affiche.

    Elle annonce déjà qu'un courriel est parti sans le confirmer — c'est ce qui
    empêche d'énumérer les comptes. Un message de refus visible ici le
    rouvrirait : il dirait « cette adresse existe assez pour valoir une limite ».
    """
    _membre_joignable()
    settings.DEBIT_MOT_DE_PASSE_PAR_ADRESSE = (1, 3600)

    accepte = _demande_de_lien(client)
    refuse = _demande_de_lien(client)
    inconnue = _demande_de_lien(client, adresse="personne@example.org")

    assert len(mailoutbox) == 1
    assert accepte.status_code == refuse.status_code == inconnue.status_code == 302
    assert accepte.url == refuse.url == inconnue.url


def test_la_page_de_connexion_mene_au_mot_de_passe_oublie(client, db):
    """Sans ce lien, le parcours n'existe que pour qui connaît l'adresse."""
    corps = client.get("/connexion/").content.decode()
    assert "/mot-de-passe/oublie/" in corps


def test_un_membre_recoit_un_lien_et_change_son_mot_de_passe(client, db, mailoutbox):
    membre = _membre("alice")
    membre.user.email = "alice@example.org"
    membre.user.save(update_fields=["email"])

    client.post("/mot-de-passe/oublie/", {"email": "alice@example.org"})

    assert len(mailoutbox) == 1
    lien = _lien_de_reinitialisation(mailoutbox[0].body)
    assert lien is not None, "aucun lien dans le courriel"

    # Django redirige vers une URL à jeton masqué avant d'afficher le formulaire.
    reponse = client.get(lien, follow=True)
    assert reponse.status_code == 200
    client.post(
        reponse.request["PATH_INFO"],
        {"new_password1": "unMotDePasse!42", "new_password2": "unMotDePasse!42"},
        follow=True,
    )

    client.logout()
    assert client.login(username="alice", password="unMotDePasse!42")


def test_un_membre_invite_mais_jamais_activo_recoit_le_lien(client, db, mailoutbox):
    """LE piège du parcours. `ouvrir_compte` pose un mot de passe INUTILISABLE
    (le membre le choisit via son lien d'activation), et le formulaire de Django
    écarte justement ces comptes. La personne la plus susceptible d'avoir oublié
    son mot de passe est celle qui n'en a jamais défini : sans correctif, elle
    reçoit le silence, sur une page qui lui affirme qu'un courriel est parti."""
    from apps.coeur.services import creer_membre, ouvrir_compte

    membre = creer_membre(prenom="Bob", nom="Martin", email="bob@example.org")
    ouvrir_compte(membre)
    membre.user.refresh_from_db()
    assert not membre.user.has_usable_password()

    client.post("/mot-de-passe/oublie/", {"email": "bob@example.org"})

    assert len(mailoutbox) == 1, "le compte invité n'a rien reçu"
    assert _lien_de_reinitialisation(mailoutbox[0].body) is not None


def test_une_adresse_inconnue_ne_se_trahit_pas(client, db, mailoutbox):
    """Anti-énumération, comme les 404 de l'espace membre : la réponse est la
    même que pour une adresse connue, et rien ne part."""
    membre = _membre("alice")
    membre.user.email = "alice@example.org"
    membre.user.save(update_fields=["email"])

    connue = client.post("/mot-de-passe/oublie/", {"email": "alice@example.org"})
    mailoutbox.clear()
    inconnue = client.post("/mot-de-passe/oublie/", {"email": "personne@example.org"})

    assert inconnue.status_code == connue.status_code
    assert inconnue.url == connue.url
    assert len(mailoutbox) == 0


def test_un_lien_perime_ne_propose_pas_de_formulaire(client, db):
    """Le cas que l'audit demandait explicitement. Un jeton invalide ne doit pas
    rendre une page vide ni une erreur : il s'explique, et renvoie au départ."""
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    membre = _membre("alice")
    uidb64 = urlsafe_base64_encode(force_bytes(membre.user.pk))

    corps = client.get(f"/mot-de-passe/nouveau/{uidb64}/jeton-invalide/", follow=True)
    texte = corps.content.decode()

    assert 'name="new_password1"' not in texte, "un formulaire est offert sur un lien mort"
    assert "expiré" in texte or "invalide" in texte
    assert "/mot-de-passe/oublie/" in texte, "aucun moyen de recommencer"


def test_un_lien_ne_sert_qu_une_fois(client, db, mailoutbox):
    """Usage unique : le mot de passe changé, le lien reçu par courriel est mort.
    Sans quoi un courriel ancien rouvrirait le compte indéfiniment."""
    membre = _membre("alice")
    membre.user.email = "alice@example.org"
    membre.user.save(update_fields=["email"])
    client.post("/mot-de-passe/oublie/", {"email": "alice@example.org"})
    lien = _lien_de_reinitialisation(mailoutbox[0].body)

    premiere = client.get(lien, follow=True)
    client.post(
        premiere.request["PATH_INFO"],
        {"new_password1": "unMotDePasse!42", "new_password2": "unMotDePasse!42"},
        follow=True,
    )

    texte = client.get(lien, follow=True).content.decode()
    assert 'name="new_password1"' not in texte, "le lien sert une seconde fois"


def test_les_deux_ecrans_terminaux_du_parcours_se_rendent(client, db, mailoutbox):
    """Trouvé en relecture : aucun test ne rendait « Vérifiez votre messagerie »,
    l'écran que TOUT LE MONDE voit après avoir demandé un lien — les tests
    s'arrêtaient à la redirection. Une erreur de gabarit y serait partie en
    production sans bruit. Idem pour l'écran de fin."""
    membre = _membre("alice")
    membre.user.email = "alice@example.org"
    membre.user.save(update_fields=["email"])

    envoye = client.post("/mot-de-passe/oublie/", {"email": "alice@example.org"}, follow=True)
    assert envoye.status_code == 200
    assert "messagerie" in envoye.content.decode()

    lien = _lien_de_reinitialisation(mailoutbox[0].body)
    saisie = client.get(lien, follow=True)
    fin = client.post(
        saisie.request["PATH_INFO"],
        {"new_password1": "unMotDePasse!42", "new_password2": "unMotDePasse!42"},
        follow=True,
    )
    assert fin.status_code == 200
    corps = fin.content.decode()
    assert "/connexion/" in corps, "l'écran de fin ne ramène pas à la connexion"


# --- Aperçu de ma page publique (VIT-4) -------------------------------------

APERCU = "/espace/profil/apercu/"


def test_l_apercu_montre_le_brouillon_et_la_page_publique_ne_bouge_pas(client, db):
    membre = _membre("alice")
    membre.visible_sur_site = True
    membre.bio = "Biographie en ligne."
    membre.save()
    client.force_login(membre.user)
    client.post(PROFIL, _donnees_profil(bio="Biographie retravaillée."))

    apercu = client.get(APERCU).content.decode()
    publique = client.get(membre.get_absolute_url()).content.decode()

    assert "Biographie retravaillée." in apercu
    assert "Biographie en ligne." not in apercu
    assert "Biographie en ligne." in publique
    assert "Biographie retravaillée." not in publique


def test_l_apercu_n_ecrit_rien(client, db):
    """Un aperçu qui publierait serait le contraire de ce qu'on construit."""
    membre = _membre("alice")
    membre.bio = "Biographie en ligne."
    membre.save()
    client.force_login(membre.user)
    client.post(PROFIL, _donnees_profil(bio="Brouillon."))

    client.get(APERCU)

    membre.refresh_from_db()
    assert membre.bio == "Biographie en ligne."
    assert brouillon_en_attente(membre) is True


def test_l_apercu_se_dit_apercu(client, db):
    """Sans bandeau, on croit regarder sa page en ligne et on ne publie jamais."""
    membre = _membre("alice")
    client.force_login(membre.user)
    corps = client.get(APERCU).content.decode()
    assert "Aperçu" in corps


def test_l_apercu_n_est_ni_indexable_ni_mis_en_cache_partage(client, db):
    """Un aperçu n'est pas une seconde adresse pour la même page. Le `noindex`
    ne protège pas l'accès — la session s'en charge — mais il évite que
    l'aperçu devienne un doublon référencé."""
    membre = _membre("alice")
    client.force_login(membre.user)

    reponse = client.get(APERCU)

    assert reponse["X-Robots-Tag"] == "noindex, nofollow"
    assert "no-store" in reponse["Cache-Control"]
    assert "private" in reponse["Cache-Control"]


def test_l_apercu_demande_une_session(client, db):
    """Anti-IDOR par construction : aucun identifiant dans l'URL, donc rien à
    forger — reste à refuser l'anonyme."""
    reponse = client.get(APERCU)
    assert reponse.status_code == 302
    assert "/connexion" in reponse["Location"] or "login" in reponse["Location"]


def test_l_apercu_sert_la_page_publique_et_pas_une_maquette(client, db):
    """Il passe par le gabarit ET le contexte publics : ce que l'aperçu montre
    de la page — ses dates, ses spectacles — vient du même code."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.agenda.models import Evenement, Intervention

    membre = _membre("alice")
    membre.visible_sur_site = True
    membre.save()
    evenement = Evenement.objects.create(
        titre="SoireeAnnoncee",
        date_debut=timezone.now() + timedelta(days=5),
        statut_moderation=Evenement.StatutModeration.PUBLIE,
    )
    Intervention.objects.create(evenement=evenement, membre=membre, role="Comédienne")
    client.force_login(membre.user)

    corps = client.get(APERCU).content.decode()

    assert "Prochaines participations" in corps
    assert "SoireeAnnoncee" in corps


def test_un_profil_jamais_enregistre_n_annonce_pas_d_enregistrement(client, db):
    """Le brouillon naît à la première ouverture de l'écran : afficher son
    horodatage de création annoncerait un geste que personne n'a fait."""
    membre = _membre("alice")
    client.force_login(membre.user)

    corps = client.get(PROFIL).content.decode()

    assert "Dernier enregistrement" not in corps
    assert "Version publique" in corps

    client.post(PROFIL, _donnees_profil(bio="Un début."))
    assert "Dernier enregistrement" in client.get(PROFIL).content.decode()


def test_regarder_son_profil_n_ecrit_rien_en_base(client, db):
    """Un GET qui crée se paie le jour où l'on compte « qui a commencé à
    éditer » et où l'on compte en fait « qui a ouvert la page »."""
    from apps.coeur.models import BrouillonPageArtiste

    membre = _membre("alice")
    client.force_login(membre.user)

    client.get(PROFIL)
    client.get(APERCU)
    assert BrouillonPageArtiste.objects.filter(membre=membre).count() == 0

    client.post(PROFIL, _donnees_profil(bio="Un début."))
    assert BrouillonPageArtiste.objects.filter(membre=membre).count() == 1


def test_la_page_publique_ne_porte_pas_le_bandeau_d_apercu(client, db):
    """Le drapeau `apercu` n'est posé que par l'espace membre : un jour où il
    fuirait dans le contexte public, la page annoncerait à tout le monde
    qu'elle n'est visible que de lui."""
    membre = _membre("alice")
    membre.visible_sur_site = True
    membre.save()

    corps = client.get(membre.get_absolute_url()).content.decode()

    assert "bandeau-apercu" not in corps
    assert "Retour aux membres" in corps


# --- Photo d'un brouillon : privée jusqu'à publication (VIT-4) --------------


def _photo_de_brouillon(client, membre, nom="portrait.png", taille=(1200, 800)):
    """Téléverse un portrait dans le brouillon et rend le `Media` créé.

    Assez large pour qu'une vignette SOIT due : sans quoi « le brouillon n'a pas
    de vignette » serait vrai par la taille de l'image, pas par la règle."""
    client.post(
        PROFIL,
        _donnees_profil(photo_fichier=_image_png(nom, taille), photo_alt="Portrait"),
    )
    return brouillon_de(membre).photo


def _couverture_de_brouillon(client, membre, nom="couverture.png", taille=(1200, 800)):
    """Téléverse une couverture de vidéo dans le brouillon et rend le `Media`."""
    client.post(
        PROFIL,
        _donnees_profil(couverture_fichier=_image_png(nom, taille), couverture_alt="Couverture"),
    )
    return brouillon_de(membre).video_couverture


def test_l_ecran_offre_chaque_image_du_jeu_partage(db):
    """La correspondance modèle ↔ écran est le seul point récité de ce lot.

    Ajouter une image au modèle sans l'offrir ici donnerait un champ que rien
    n'atteint — et personne ne saurait qu'il manque, puisque le modèle, lui,
    serait complet. Ce contrôle est ce qui le dit.
    """
    assert set(PageArtisteForm.IMAGES) == set(champs_images_artiste())
    for prefixe in PageArtisteForm.IMAGES.values():
        for suffixe in ("_fichier", "_alt"):
            assert f"{prefixe}{suffixe}" in PageArtisteForm().fields
        assert f"retirer_{prefixe}" in PageArtisteForm().fields


def test_une_couverture_de_brouillon_se_sert_par_la_route_protegee(client, db):
    """Même garde que le portrait, sans qu'on ait eu à l'écrire deux fois.

    La route cherche le rattachement sur TOUTES les images du jeu : nommer
    `photo` l'aurait laissée sans porteur, donc refusée à son propriétaire — et
    « réparer » ça en retirant le garde l'aurait ouverte à tout le monde.
    """
    alice = _membre("alice")
    client.force_login(alice.user)
    media = _couverture_de_brouillon(client, alice)

    assert media is not None and media.est_prive is True
    assert client.get(f"/espace/profil/image/{media.pk}/").status_code == 200

    bob = _membre("bob")
    client.force_login(bob.user)
    assert client.get(f"/espace/profil/image/{media.pk}/").status_code == 404


def test_une_couverture_sans_texte_alternatif_est_refusee(client, db):
    """Règle 2 du dépôt : pas de média sans `alt`. Le contrôle porte sur le jeu
    des images, la couverture en a donc hérité sans qu'on y pense."""
    membre = _membre("alice")
    client.force_login(membre.user)

    reponse = client.post(
        PROFIL, _donnees_profil(couverture_fichier=_image_png("c.png", (600, 400)))
    )

    assert reponse.status_code == 200
    assert escape("La description de l'image est obligatoire.") in reponse.content.decode()
    assert brouillon_de(membre, creer=False).video_couverture_id is None


def test_une_photo_de_brouillon_n_est_pas_ecrite_dans_la_racine_web(client, db):
    """Cacher une page ne rend pas son portrait confidentiel : le fichier vit
    sous MEDIA_PRIVE_ROOT, que Nginx n'expose pas."""
    membre = _membre("alice")
    client.force_login(membre.user)

    media = _photo_de_brouillon(client, membre)

    assert media.est_prive is True
    assert not media.fichier
    assert media.fichier_prive.name.startswith("brouillons/")
    # Le traitement a bien tourné sur le fichier privé (dimensions connues)…
    assert media.largeur == 1200
    # …mais SANS vignette : elle irait dans le stockage PUBLIC, et une miniature
    # d'une image qu'on protège est une fuite de cette image.
    assert not media.vignette


def test_une_photo_de_brouillon_ne_se_lit_pas_sans_session(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    media = _photo_de_brouillon(client, membre)

    client.logout()
    reponse = client.get(f"/espace/profil/image/{media.pk}/")

    assert reponse.status_code == 302
    assert "/connexion" in reponse["Location"] or "login" in reponse["Location"]


def test_une_photo_de_brouillon_ne_se_lit_pas_par_un_autre_membre(client, db):
    """ANTI-IDOR : l'identifiant est dans l'URL, donc forgeable. Le refus porte
    sur le rattachement métier — quel brouillon référence ce média — et non sur
    `cree_par`, qui décrit un geste et non une propriété."""
    alice = _membre("alice")
    bob = _membre("bob")
    client.force_login(alice.user)
    media = _photo_de_brouillon(client, alice)

    client.force_login(bob.user)
    reponse = client.get(f"/espace/profil/image/{media.pk}/")

    assert reponse.status_code == 404  # 404 et non 403 : ne pas confirmer l'existence


def test_son_proprietaire_lit_sa_photo_de_brouillon(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    media = _photo_de_brouillon(client, membre)

    reponse = client.get(f"/espace/profil/image/{media.pk}/")

    assert reponse.status_code == 200
    assert "inline" in reponse["Content-Disposition"]


def test_le_bureau_lit_la_photo_d_un_brouillon(client, db):
    """Il accompagne les pages : la matrice du guide lui donne la lecture."""
    from django.contrib.auth.models import Group

    alice = _membre("alice")
    client.force_login(alice.user)
    media = _photo_de_brouillon(client, alice)

    bureau = _membre("bureau")
    bureau.user.is_staff = True
    bureau.user.save()
    groupe, _ = Group.objects.get_or_create(name="Bureau")
    bureau.user.groups.add(groupe)
    client.force_login(bureau.user)

    assert client.get(f"/espace/profil/image/{media.pk}/").status_code == 200


def test_la_route_privee_refuse_un_media_deja_public(client, db):
    """Le cas qui compte n'est pas un média étranger — le rattachement le
    refuse déjà — mais le média du demandeur APRÈS publication : le brouillon
    le référence encore, et son fichier privé n'existe plus. Sans ce garde, la
    route ouvrirait un fichier vide et rendrait une erreur 500.

    Un lien resté ouvert dans un onglet suffit à y arriver."""
    membre = _membre("alice")
    client.force_login(membre.user)
    media = _photo_de_brouillon(client, membre)
    servie = client.get(f"/espace/profil/image/{media.pk}/")
    assert servie.status_code == 200
    # On relâche le FICHIER, pas la réponse : `close()` sur une réponse émet
    # `request_finished`, donc ferme la connexion à la base sous PostgreSQL et
    # fait échouer le POST qui suit. Le fichier, lui, doit bien être rendu :
    # Windows le verrouille tant qu'il est ouvert, et la publication ne peut
    # alors pas le déplacer.
    from conftest import relacher_le_fichier

    relacher_le_fichier(servie)

    client.post(PROFIL, _donnees_profil(action="publier"))

    media.refresh_from_db()
    assert media.est_prive is False
    assert brouillon_de(membre).photo_id == media.pk  # toujours référencé
    assert client.get(f"/espace/profil/image/{media.pk}/").status_code == 404


def test_publier_fait_passer_la_photo_dans_la_racine_web(client, db):
    """Publier une page, c'est aussi publier son portrait : le fichier QUITTE
    le stockage privé. Sans ce déplacement, la page publiée montrerait un cadre
    vide — les gabarits publics testent `fichier`."""
    membre = _membre("alice")
    membre.visible_sur_site = True
    membre.save()
    client.force_login(membre.user)
    media = _photo_de_brouillon(client, membre)
    nom_prive = media.fichier_prive.name

    client.post(PROFIL, _donnees_profil(action="publier"))

    media.refresh_from_db()
    assert media.est_prive is False
    assert media.fichier.name.startswith("medias/")
    assert not media.fichier_prive.storage.exists(nom_prive)

    membre.refresh_from_db()
    assert membre.photo_id == media.pk
    corps = client.get(membre.get_absolute_url()).content.decode()
    assert media.fichier.url in corps
    # Et plus par la route protégée : sur la page publique, elle renverrait un
    # visiteur anonyme vers la connexion au lieu d'une image.
    assert f"/espace/profil/image/{media.pk}/" not in corps


def test_l_apercu_sert_la_couverture_du_brouillon_par_la_route_protegee(client, db):
    """Le chemin où la couverture est PRIVÉE, et le seul où la façade la rend.

    Les autres contrôles de couverture regardent soit la route seule, soit une
    page publiée — donc une image publique. Ici l'artiste relit sa page avant de
    la publier : c'est le moment où un `src` vers la racine web servirait une
    image que personne ne devrait encore voir, et où un `src` vide donnerait un
    cadre noir sans que rien ne tombe.
    """
    membre = _membre("alice")
    membre.visible_sur_site = True
    membre.save()
    client.force_login(membre.user)
    # Un SEUL envoi : le formulaire porte tous les champs du brouillon, donc un
    # second POST sans la vidéo la viderait — c'est le comportement voulu d'un
    # ModelForm, et c'est un piège pour qui enchaîne deux envois partiels.
    client.post(
        PROFIL,
        _donnees_profil(
            video_youtube="https://youtu.be/dQw4w9WgXcQ",
            couverture_fichier=_image_png("couv.png", (1200, 800)),
            couverture_alt="Couverture",
        ),
    )
    media = brouillon_de(membre).video_couverture
    assert media is not None and media.est_prive is True

    corps = client.get(APERCU).content.decode()

    assert "video-clic__facade--couverte" in corps, "la façade rend sa variante nue"
    assert f'src="/espace/profil/image/{media.pk}/"' in corps
    assert "Couverture" in corps  # le texte alternatif est bien posé


def test_l_apercu_sert_la_photo_du_brouillon_par_la_route_protegee(client, db):
    membre = _membre("alice")
    membre.visible_sur_site = True
    membre.save()
    client.force_login(membre.user)
    media = _photo_de_brouillon(client, membre)

    corps = client.get(APERCU).content.decode()

    assert f"/espace/profil/image/{media.pk}/" in corps


# --- Abandonner un brouillon (VIT-4) ----------------------------------------

ABANDON = "/espace/profil/abandonner/"


def test_abandonner_ramene_le_brouillon_a_la_page_en_ligne(client, db):
    """Le geste qui manquait en face d'« Enregistrer le brouillon » : sans
    historique, une retouche malheureuse ne se défaisait pas, et il fallait
    recopier à la main depuis sa propre page publique."""
    membre = _membre("alice")
    membre.bio = "Biographie en ligne."
    membre.save()
    client.force_login(membre.user)
    client.post(PROFIL, _donnees_profil(bio="Retouche regrettée."))
    assert brouillon_en_attente(membre) is True

    reponse = client.post(ABANDON, follow=True)

    assert brouillon_de(membre).bio == "Biographie en ligne."
    assert brouillon_en_attente(membre) is False
    assert "Modifications abandonnées" in reponse.content.decode()


def test_abandonner_ne_touche_pas_a_la_page_publique(client, db):
    membre = _membre("alice")
    membre.bio = "Biographie en ligne."
    membre.save()
    client.force_login(membre.user)
    client.post(PROFIL, _donnees_profil(bio="Retouche."))

    client.post(ABANDON)

    membre.refresh_from_db()
    assert membre.bio == "Biographie en ligne."


def test_abandonner_deux_fois_n_est_pas_une_erreur(client, db):
    membre = _membre("alice")
    client.force_login(membre.user)
    client.post(PROFIL, _donnees_profil(bio="Retouche."))
    client.post(ABANDON)

    reponse = client.post(ABANDON, follow=True)

    assert reponse.status_code == 200
    assert "rien à abandonner" in reponse.content.decode()


def test_le_bouton_d_abandon_n_est_offert_que_s_il_y_a_de_quoi(client, db):
    """Un bouton qui ne fait rien se clique quand même, et laisse croire qu'il
    a fait quelque chose."""
    membre = _membre("alice")
    client.force_login(membre.user)

    assert "Abandonner mes modifications" not in client.get(PROFIL).content.decode()

    client.post(PROFIL, _donnees_profil(bio="Retouche."))
    assert "Abandonner mes modifications" in client.get(PROFIL).content.decode()


def test_abandonner_ne_se_fait_pas_en_GET(client, db):
    """Un geste destructeur ne s'exécute pas sur une simple visite d'URL."""
    membre = _membre("alice")
    client.force_login(membre.user)
    client.post(PROFIL, _donnees_profil(bio="Retouche."))

    assert client.get(ABANDON).status_code == 405
    assert brouillon_en_attente(membre) is True


def test_abandonner_ne_touche_pas_au_brouillon_d_un_autre(client, db):
    """ANTI-IDOR par construction : aucun identifiant d'URL. Reste à le tenir."""
    alice = _membre("alice")
    bob = _membre("bob")
    bob.bio = "En ligne chez Bob."
    bob.save()
    client.force_login(bob.user)
    client.post(PROFIL, _donnees_profil(bio="Brouillon de Bob."))

    client.force_login(alice.user)
    client.post(PROFIL, _donnees_profil(bio="Brouillon d'Alice."))
    client.post(ABANDON)

    assert brouillon_de(bob).bio == "Brouillon de Bob."
    assert brouillon_en_attente(bob) is True
