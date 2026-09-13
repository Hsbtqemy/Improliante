"""Tests du module de rôles (`apps.coeur.roles`) et des signataires."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.coeur.models import (
    CHAMPS_PUBLICS_ARTISTE,
    BrouillonPageArtiste,
    Membre,
    Signataire,
    Utilisateur,
)
from apps.coeur.roles import NOM_GROUPE_BUREAU, est_bureau
from apps.coeur.services import (
    OuvertureCompteImpossible,
    aligner_brouillon_apres_saisie,
    brouillon_de,
    brouillon_en_attente,
    creer_membre,
    membres_en_vedette,
    ouvrir_compte,
    publier_page_artiste,
    synchroniser_compte,
)
from apps.medias.models import Media


def test_utilisateur_lambda_n_est_pas_bureau(db):
    user = Utilisateur.objects.create_user(username="lambda", password="x")
    assert est_bureau(user) is False


def test_membre_du_groupe_bureau_est_bureau(db):
    user = Utilisateur.objects.create_user(username="secretaire", password="x")
    groupe, _ = Group.objects.get_or_create(name=NOM_GROUPE_BUREAU)
    user.groups.add(groupe)
    assert est_bureau(user) is True


def test_staff_est_bureau(db):
    user = Utilisateur.objects.create_user(username="admin", password="x", is_staff=True)
    assert est_bureau(user) is True


def test_compte_inactif_n_est_pas_bureau(db):
    user = Utilisateur.objects.create_user(
        username="ancien", password="x", is_staff=True, is_active=False
    )
    assert est_bureau(user) is False


def test_signataire_image_base64_renvoie_un_data_uri(db):
    sig = Signataire.objects.create(
        nom="Alice",
        qualite="Présidente",
        signature_image=SimpleUploadedFile("sig.png", b"\x89PNG-faux", content_type="image/png"),
    )
    uri = sig.image_base64()
    assert uri.startswith("data:image/png;base64,")


def test_signataire_sans_image_renvoie_chaine_vide(db):
    sig = Signataire.objects.create(nom="Bob", qualite="Trésorier")
    assert sig.image_base64() == ""


# --- Sélection des membres en vedette (page association) -------------------


def _membre_vedette(nom, *, visible=True, une=False):
    user = Utilisateur.objects.create(username=nom, last_name=nom)
    return Membre.objects.create(user=user, nom=nom, visible_sur_site=visible, mis_en_avant=une)


def test_vedette_inclut_les_a_la_une_et_complete_au_hasard(db):
    une1 = _membre_vedette("une1", une=True)
    une2 = _membre_vedette("une2", une=True)
    for i in range(5):
        _membre_vedette(f"autre{i}")

    vedette = membres_en_vedette(nombre=4)
    assert len(vedette) == 4
    assert une1 in vedette and une2 in vedette  # les « à la une » d'abord
    assert all(m.visible_sur_site for m in vedette)  # complété par des visibles


def test_vedette_exclut_les_membres_masques(db):
    cache_une = _membre_vedette("cacheune", visible=False, une=True)
    visible = _membre_vedette("visible")
    vedette = membres_en_vedette(nombre=6)
    assert cache_une not in vedette  # masqué, même « à la une »
    assert visible in vedette


def test_vedette_bornee_au_nombre(db):
    for i in range(10):
        _membre_vedette(f"m{i}", une=True)
    assert len(membres_en_vedette(nombre=6)) == 6


# --- Membre = personne : identité sur la fiche, compte optionnel -----------


def test_creer_membre_sans_compte(db):
    """Une fiche adhérent existe sans compte de connexion."""
    membre = creer_membre(prenom="Zoé", nom="Nadal", email="zoe@example.org")
    assert membre.user_id is None
    assert membre.a_un_compte is False
    assert membre.nom_complet == "Zoé Nadal"
    assert str(membre) == "Zoé Nadal"
    assert Utilisateur.objects.count() == 0  # aucun compte créé


def test_str_membre_robuste_sans_identite(db):
    """`__str__` ne casse jamais : identité vide et sans compte → libellé de repli."""
    membre = creer_membre(prenom="", nom="", email="")
    assert str(membre) == "Nouveau membre"


def test_nom_liste_met_le_nom_de_famille_en_premier(db):
    """Pour les listes triées par nom : « Nom Prénom » (nom de famille d'abord)."""
    membre = creer_membre(prenom="Zoé", nom="Nadal")
    assert membre.nom_liste == "Nadal Zoé"
    assert creer_membre(prenom="", nom="").nom_liste == "Nouveau membre"  # repli


def test_ouvrir_compte_cree_le_compte_et_recopie_l_identite(db):
    membre = creer_membre(prenom="Zoé", nom="Nadal", email="zoe@example.org")
    uidb64, token = ouvrir_compte(membre)
    membre.refresh_from_db()
    assert membre.a_un_compte is True
    assert membre.user.username == "zoe@example.org"  # e-mail = identifiant
    assert membre.user.first_name == "Zoé" and membre.user.last_name == "Nadal"
    assert membre.user.has_usable_password() is False  # activation requise
    assert uidb64 and token


def test_ouvrir_compte_refuse_sans_email(db):
    membre = creer_membre(prenom="Sans", nom="Mail", email="")
    with pytest.raises(OuvertureCompteImpossible):
        ouvrir_compte(membre)
    assert Utilisateur.objects.count() == 0


def test_ouvrir_compte_refuse_email_deja_pris(db):
    Utilisateur.objects.create_user(username="pris@example.org", password="x")
    membre = creer_membre(prenom="Doublon", nom="Mail", email="pris@example.org")
    with pytest.raises(OuvertureCompteImpossible):
        ouvrir_compte(membre)


def test_ouvrir_compte_refuse_si_deja_un_compte(db):
    membre = creer_membre(prenom="Deja", nom="La", email="deja@example.org")
    ouvrir_compte(membre)
    with pytest.raises(OuvertureCompteImpossible):
        ouvrir_compte(membre)


def test_synchroniser_compte_recopie_sans_toucher_l_identifiant(db):
    membre = creer_membre(prenom="Ava", nom="Prat", email="ava@example.org")
    ouvrir_compte(membre)
    membre.prenom, membre.nom, membre.email = "Ava", "Prade", "ava2@example.org"
    membre.save()
    synchroniser_compte(membre)
    membre.user.refresh_from_db()
    assert membre.user.last_name == "Prade"
    assert membre.user.email == "ava2@example.org"
    assert membre.user.username == "ava@example.org"  # identifiant inchangé


# --- Adresse publique d'un membre : le slug de /@prenom-nom ----------------


def test_slug_derive_du_nom_sans_accent_ni_majuscule(db):
    membre = creer_membre(prenom="Jeanne", nom="Dupré", email="jeanne@example.org")
    assert membre.slug == "jeanne-dupre"
    assert membre.get_absolute_url() == "/@jeanne-dupre/"


def test_slug_d_un_homonyme_est_suffixe_sans_toucher_au_premier(db):
    """Le premier arrivé garde son adresse : elle est peut-être déjà partagée."""
    premiere = creer_membre(prenom="Jeanne", nom="Dupont", email="j1@example.org")
    seconde = creer_membre(prenom="Jeanne", nom="Dupont", email="j2@example.org")
    troisieme = creer_membre(prenom="Jeanne", nom="Dupont", email="j3@example.org")
    assert premiere.slug == "jeanne-dupont"
    assert seconde.slug == "jeanne-dupont-2"
    assert troisieme.slug == "jeanne-dupont-3"


def test_slug_d_une_fiche_sans_nom_part_de_membre(db):
    """Prénom et nom sont facultatifs : le slug ne peut pas être vide."""
    anonyme = creer_membre(prenom="", nom="", email="anonyme@example.org")
    autre = creer_membre(prenom="", nom="", email="autre@example.org")
    assert anonyme.slug == "membre"
    assert autre.slug == "membre-2"


def test_slug_ne_suit_pas_un_changement_de_nom(db):
    """Figé exprès : régénérer casserait les liens déjà en circulation."""
    membre = creer_membre(prenom="Marie", nom="Martin", email="marie@example.org")
    membre.prenom, membre.nom = "Marie", "Bernard"
    membre.save()
    membre.refresh_from_db()
    assert membre.slug == "marie-martin"


def test_slug_choisi_a_la_main_est_respecte(db):
    membre = Membre.objects.create(prenom="Sur", nom="Mesure", slug="la-patronne")
    membre.refresh_from_db()
    assert membre.slug == "la-patronne"


# --- Brouillon d'une page artiste (VIT-4) -----------------------------------


def _artiste(nom="Camille", **champs):
    champs.setdefault("bio", "Biographie publiée.")
    champs.setdefault("role_public", "Comédienne")
    return Membre.objects.create(nom=nom, visible_sur_site=True, **champs)


def test_publier_emporte_la_video_sans_qu_on_ait_eu_a_la_reciter(db):
    """Le jeu de champs recopiés se DÉDUIT de `ContenuPublicArtiste`.

    Ce test ne vérifie pas la vidéo pour elle-même : il vérifie qu'AJOUTER un
    champ éditorial suffit à ce que « Publier » l'emmène. Si la liste des champs
    recopiés redevenait un jour une énumération tenue à la main, il tomberait —
    et c'est tout ce qu'on lui demande.
    """
    membre = _artiste()
    brouillon = brouillon_de(membre)
    brouillon.video_youtube = "dQw4w9WgXcQ"
    brouillon.video_titre = "Extrait"
    brouillon.video_texte = "Trois minutes."
    brouillon.save()

    assert publier_page_artiste(membre) is True

    membre.refresh_from_db()
    assert membre.video_youtube == "dQw4w9WgXcQ"
    assert membre.video_titre == "Extrait"
    assert membre.video_texte == "Trois minutes."
    # Déduit, et pas recopié par chance : le champ est dans le jeu partagé.
    assert "video_youtube" in CHAMPS_PUBLICS_ARTISTE


def test_un_premier_brouillon_part_de_la_page_publiee(db):
    """Un brouillon vide effacerait la page en le publiant. Il part donc de ce
    que le public voit déjà, et l'artiste retouche."""
    membre = _artiste()

    brouillon = brouillon_de(membre)

    assert brouillon.bio == "Biographie publiée."
    assert brouillon.role_public == "Comédienne"
    assert brouillon_en_attente(membre) is False


def test_enregistrer_un_brouillon_ne_change_rien_a_la_page_publique(db):
    """La promesse du chantier, en une phrase."""
    membre = _artiste()
    brouillon = brouillon_de(membre)

    brouillon.bio = "Nouvelle biographie, pas encore relue."
    brouillon.save()

    membre.refresh_from_db()
    assert membre.bio == "Biographie publiée."
    assert brouillon_en_attente(membre) is True


def test_publier_recopie_tout_le_brouillon_d_un_coup(db):
    membre = _artiste()
    photo = Media.objects.create(fichier="medias/portrait.jpg", alt="Portrait")
    brouillon = brouillon_de(membre)
    brouillon.bio = "Biographie relue."
    brouillon.role_public = "Comédienne, mise en scène"
    brouillon.site_web = "https://exemple.org"
    brouillon.photo = photo
    brouillon.save()

    assert publier_page_artiste(membre) is True

    membre.refresh_from_db()
    assert membre.bio == "Biographie relue."
    assert membre.role_public == "Comédienne, mise en scène"
    assert membre.site_web == "https://exemple.org"
    assert membre.photo_id == photo.pk
    assert brouillon_en_attente(membre) is False


def test_publier_deux_fois_n_est_pas_une_erreur(db):
    """Un double-clic, un retour arrière du navigateur : le second geste ne
    doit pas lever, il doit dire qu'il n'y avait rien à publier."""
    membre = _artiste()
    brouillon = brouillon_de(membre)
    brouillon.bio = "Relue."
    brouillon.save()

    assert publier_page_artiste(membre) is True
    assert publier_page_artiste(membre) is False


def test_publier_sans_brouillon_ne_touche_a_rien(db):
    membre = _artiste()
    assert publier_page_artiste(membre) is False
    membre.refresh_from_db()
    assert membre.bio == "Biographie publiée."


def test_un_champ_vide_au_brouillon_se_publie_vide(db):
    """Effacer sa biographie est une modification comme une autre : la
    publication recopie, elle ne fusionne pas. Un service qui ignorerait les
    valeurs vides rendrait un effacement impossible à publier."""
    membre = _artiste()
    brouillon = brouillon_de(membre)
    brouillon.bio = ""
    brouillon.save()

    assert publier_page_artiste(membre) is True

    membre.refresh_from_db()
    assert membre.bio == ""


def test_le_brouillon_d_un_artiste_ne_touche_pas_celui_d_un_autre(db):
    camille = _artiste("Camille")
    dominique = _artiste("Dominique")
    brouillon = brouillon_de(camille)
    brouillon.bio = "La biographie de Camille."
    brouillon.save()

    publier_page_artiste(camille)

    dominique.refresh_from_db()
    assert dominique.bio == "Biographie publiée."
    assert brouillon_en_attente(dominique) is False


def test_demander_deux_fois_le_brouillon_rend_le_meme(db):
    membre = _artiste()
    premier = brouillon_de(membre)
    premier.bio = "En cours."
    premier.save()

    second = brouillon_de(membre)

    assert second.pk == premier.pk
    assert second.bio == "En cours."


def test_la_publication_trace_son_auteur(db):
    membre = _artiste()
    user = Utilisateur.objects.create_user(username="camille", password="x")
    brouillon = brouillon_de(membre)
    brouillon.bio = "Relue."
    brouillon.modifie_par = user
    brouillon.save()

    publier_page_artiste(membre, par=user)

    brouillon.refresh_from_db()
    assert brouillon.publie_le is not None
    assert brouillon.publie_par == user


def test_la_publication_recopie_tous_les_champs_du_jeu_partage(db):
    """Le garde-fou de la promesse : la liste des champs recopiés se déduit du
    jeu partagé. La remplacer un jour par une liste écrite à la main ferait
    tomber ce test — sans quoi le champ oublié serait un champ que « Publier »
    ne recopie pas, en silence."""
    from apps.coeur.models import CHAMPS_PUBLICS_ARTISTE, ContenuPublicArtiste

    declares = {champ.attname for champ in ContenuPublicArtiste._meta.fields}

    assert declares == set(CHAMPS_PUBLICS_ARTISTE)
    assert declares, "le jeu partagé ne déclare plus aucun champ éditorial"


def test_une_saisie_du_bureau_emmene_un_brouillon_qui_n_attendait_rien(db):
    """Écrire la fiche, c'est publier. Si le brouillon ne portait aucun travail
    en cours, il suit — sinon il garderait l'ancien texte et le rendrait à la
    fiche à la prochaine publication de l'artiste."""
    membre = _artiste(role_public="Comédienne")
    brouillon_de(membre)  # l'artiste a ouvert son écran, sans rien changer
    contenu_avant = dict(membre.contenu_public)

    membre.role_public = "Comédienne, mise en scène"
    membre.save()
    assert aligner_brouillon_apres_saisie(membre, contenu_avant) is True

    assert brouillon_de(membre).role_public == "Comédienne, mise en scène"
    assert brouillon_en_attente(membre) is False


def test_une_saisie_du_bureau_ne_touche_pas_un_travail_en_cours(db):
    """Le revers : un brouillon qui dit autre chose porte du travail, et il
    n'est pas écrasé. L'avertissement du bureau devient alors vrai — cette
    publication-là recouvrira bien sa saisie."""
    membre = _artiste(role_public="Comédienne")
    brouillon = brouillon_de(membre)
    brouillon.role_public = "En cours de réécriture"
    brouillon.save()
    contenu_avant = dict(membre.contenu_public)

    membre.role_public = "Comédienne, mise en scène"
    membre.save()
    assert aligner_brouillon_apres_saisie(membre, contenu_avant) is False

    assert brouillon_de(membre).role_public == "En cours de réécriture"
    assert brouillon_en_attente(membre) is True


def test_l_alignement_ne_fabrique_pas_un_brouillon(db):
    """Une personne sans compte n'en a jamais eu : le bureau écrit sa fiche,
    point."""
    membre = _artiste()
    assert aligner_brouillon_apres_saisie(membre, dict(membre.contenu_public)) is False
    assert BrouillonPageArtiste.objects.filter(membre=membre).count() == 0


def test_lire_le_brouillon_sans_le_creer(db):
    """`creer=False` rend le contenu publié, sans écrire : afficher un écran ou
    un aperçu ne laisse pas de ligne en base."""
    membre = _artiste(bio="Biographie publiée.")

    lu = brouillon_de(membre, creer=False)

    assert lu.pk is None
    assert lu.bio == "Biographie publiée."
    assert BrouillonPageArtiste.objects.filter(membre=membre).count() == 0


def test_l_admin_emmene_le_brouillon_comme_le_back_office(db, rf):
    """L'admin écrivait `Membre` sans passer par l'alignement : c'était la
    porte de service, et elle rouvrait le décalage que le back-office referme.

    Le test exerce le crochet `save_model` directement — c'est lui qu'on a
    posé, et le formulaire d'admin complet n'apporterait rien de plus ici.
    """
    from django.contrib import admin as django_admin
    from django.contrib.messages.storage.fallback import FallbackStorage

    from apps.coeur.admin import MembreAdmin

    membre = _artiste(role_public="Comédienne")
    brouillon_de(membre)  # ouvert, sans travail en cours

    requete = rf.post("/admin/coeur/membre/1/change/")
    requete.user = Utilisateur.objects.create_superuser(username="root", password="x")
    requete.session = {}
    requete._messages = FallbackStorage(requete)

    membre.role_public = "Comédienne, mise en scène"
    MembreAdmin(Membre, django_admin.site).save_model(requete, membre, None, change=True)

    assert brouillon_de(membre).role_public == "Comédienne, mise en scène"
    assert brouillon_en_attente(membre) is False


def test_l_admin_ne_touche_pas_a_un_travail_en_cours_et_le_signale(db, rf):
    """Le revers : un brouillon qui porte du travail n'est pas écrasé, et
    l'admin est averti que sa saisie sera recouverte."""
    from django.contrib import admin as django_admin
    from django.contrib.messages.storage.fallback import FallbackStorage

    from apps.coeur.admin import MembreAdmin

    membre = _artiste(role_public="Comédienne")
    page = brouillon_de(membre)
    page.role_public = "En cours de réécriture"
    page.save()

    requete = rf.post("/admin/coeur/membre/1/change/")
    requete.user = Utilisateur.objects.create_superuser(username="root", password="x")
    requete.session = {}
    requete._messages = FallbackStorage(requete)

    membre.role_public = "Comédienne, mise en scène"
    MembreAdmin(Membre, django_admin.site).save_model(requete, membre, None, change=True)

    assert brouillon_de(membre).role_public == "En cours de réécriture"
    messages = [str(m) for m in requete._messages]
    assert any("modifications non publiées" in m for m in messages)
