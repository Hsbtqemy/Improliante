"""Tests des calculs de gouvernance (zone à risque, cf. cahier §8)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.budget.models import Adhesion, Saison
from apps.coeur.models import Membre, Utilisateur
from apps.documents.models import Document
from apps.gouvernance.models import (
    BlocCompteRendu,
    ParametresGouvernance,
    Pouvoir,
    Presence,
    Resolution,
    Reunion,
    Sujet,
)
from apps.gouvernance.services import (
    ReponseConvocationImpossible,
    calcul_quorum,
    donner_pouvoir,
    enregistrer_presence_membre,
    figer_les_regles,
    generer_compte_rendu,
    mandataires_en_exces,
    preremplir_droit_de_vote,
    resultat_resolution,
)


@pytest.fixture
def params(db):
    return ParametresGouvernance.load()


@pytest.fixture
def make_membre(db):
    compteur = {"n": 0}

    def _make():
        compteur["n"] += 1
        user = Utilisateur.objects.create(username=f"membre{compteur['n']}")
        return Membre.objects.create(user=user)

    return _make


def _reunion(type_reunion=Reunion.TypeReunion.AG_ORDINAIRE):
    return Reunion.objects.create(titre="Réunion", type_reunion=type_reunion)


def _presence(reunion, membre, statut, peut_voter=True):
    return Presence.objects.create(
        reunion=reunion, membre=membre, statut=statut, peut_voter=peut_voter
    )


def _resolution(type_majorite, pour, contre, abstention=0):
    return Resolution.objects.create(
        reunion=_reunion(),
        intitule="R",
        type_majorite=type_majorite,
        nombre_pour=pour,
        nombre_contre=contre,
        nombre_abstention=abstention,
    )


# --- Quorum ---------------------------------------------------------------


def test_quorum_atteint(params, make_membre):
    params.quorum_ag_ordinaire = Decimal("0.500")
    params.save()
    reunion = _reunion()
    membres = [make_membre() for _ in range(4)]
    _presence(reunion, membres[0], Presence.Statut.PRESENT)
    _presence(reunion, membres[1], Presence.Statut.REPRESENTE)
    _presence(reunion, membres[2], Presence.Statut.ABSENT)
    _presence(reunion, membres[3], Presence.Statut.EXCUSE)

    resultat = calcul_quorum(reunion)
    assert resultat.electorat == 4
    assert resultat.presents_representes == 2
    assert resultat.atteint is True  # 2/4 = 0.5 >= 0.5


def test_quorum_non_atteint(params, make_membre):
    params.quorum_ag_ordinaire = Decimal("0.500")
    params.save()
    reunion = _reunion()
    membres = [make_membre() for _ in range(4)]
    _presence(reunion, membres[0], Presence.Statut.PRESENT)
    for membre in membres[1:]:
        _presence(reunion, membre, Presence.Statut.ABSENT)

    resultat = calcul_quorum(reunion)
    assert resultat.presents_representes == 1
    assert resultat.atteint is False  # 1/4 < 0.5


def test_quorum_bureau_non_applicable(params):
    resultat = calcul_quorum(_reunion(Reunion.TypeReunion.BUREAU))
    assert resultat.applicable is False
    assert resultat.atteint is True


def test_quorum_electorat_vide(params):
    resultat = calcul_quorum(_reunion())
    assert resultat.electorat == 0
    assert resultat.atteint is False


# --- Adoption des résolutions --------------------------------------------


def test_majorite_simple_adoptee(params):
    res = _resolution(Resolution.TypeMajorite.SIMPLE, pour=3, contre=2, abstention=1)
    resultat = resultat_resolution(res)
    assert resultat.base == 5  # exprimés (défaut)
    assert resultat.adoptee is True  # 3/5 > 0.5


def test_majorite_simple_egalite_rejetee(params):
    res = _resolution(Resolution.TypeMajorite.SIMPLE, pour=2, contre=2)
    assert resultat_resolution(res).adoptee is False  # 2/4 = 0.5, pas > 0.5


def test_majorite_qualifiee_deux_tiers(params):
    adoptee = _resolution(Resolution.TypeMajorite.QUALIFIEE, pour=2, contre=1)
    assert resultat_resolution(adoptee).adoptee is True  # 2/3 -> 0.667 >= 0.667
    rejetee = _resolution(Resolution.TypeMajorite.QUALIFIEE, pour=3, contre=2)
    assert resultat_resolution(rejetee).adoptee is False  # 3/5 = 0.6 < 0.667


def test_unanimite(params):
    ok = _resolution(Resolution.TypeMajorite.UNANIMITE, pour=5, contre=0, abstention=1)
    assert resultat_resolution(ok).adoptee is True
    ko = _resolution(Resolution.TypeMajorite.UNANIMITE, pour=5, contre=1)
    assert resultat_resolution(ko).adoptee is False


def test_base_presents_change_le_resultat(params):
    params.base_majorite = ParametresGouvernance.BaseMajorite.PRESENTS
    params.save()
    res = _resolution(Resolution.TypeMajorite.SIMPLE, pour=3, contre=2, abstention=2)
    resultat = resultat_resolution(res)
    assert resultat.base == 7  # abstentions comprises
    assert resultat.adoptee is False  # 3/7 < 0.5 (en exprimés, 3/5 serait adopté)


# --- Pouvoirs -------------------------------------------------------------


def test_mandataires_en_exces(params, make_membre):
    params.max_pouvoirs_par_personne = 2
    params.save()
    reunion = _reunion()
    mandataire = make_membre()
    for _ in range(3):
        Pouvoir.objects.create(reunion=reunion, mandant=make_membre(), mandataire=mandataire)

    assert mandataires_en_exces(reunion) == {mandataire.pk: 3}


def test_pouvoirs_conformes(params, make_membre):
    params.max_pouvoirs_par_personne = 2
    params.save()
    reunion = _reunion()
    mandataire = make_membre()
    for _ in range(2):
        Pouvoir.objects.create(reunion=reunion, mandant=make_membre(), mandataire=mandataire)

    assert mandataires_en_exces(reunion) == {}


# --- Pré-remplissage du droit de vote -------------------------------------


def test_prerempli_vote_ouvert_a_tous_si_non_reserve(params, make_membre):
    params.vote_reserve_aux_membres_a_jour = False
    params.save()
    reunion = _reunion()
    presences = [
        _presence(reunion, make_membre(), Presence.Statut.PRESENT, peut_voter=False)
        for _ in range(2)
    ]

    assert preremplir_droit_de_vote(reunion) == 2
    for presence in presences:
        presence.refresh_from_db()
        assert presence.peut_voter is True


def test_prerempli_reserve_aux_membres_a_jour(params, make_membre):
    params.vote_reserve_aux_membres_a_jour = True
    params.save()
    saison = Saison.objects.create(nom="2025-2026")
    reunion = _reunion()
    membre_a_jour = make_membre()
    membre_pas_a_jour = make_membre()
    Adhesion.objects.create(membre=membre_a_jour, saison=saison, statut=Adhesion.Statut.PAYEE)
    Adhesion.objects.create(
        membre=membre_pas_a_jour, saison=saison, statut=Adhesion.Statut.EN_ATTENTE
    )
    p_ok = _presence(reunion, membre_a_jour, Presence.Statut.PRESENT, peut_voter=False)
    p_ko = _presence(reunion, membre_pas_a_jour, Presence.Statut.PRESENT, peut_voter=True)

    preremplir_droit_de_vote(reunion, saison)

    p_ok.refresh_from_db()
    p_ko.refresh_from_db()
    assert p_ok.peut_voter is True
    assert p_ko.peut_voter is False


def test_prerempli_reserve_sans_saison_leve_erreur(params):
    params.vote_reserve_aux_membres_a_jour = True
    params.save()
    with pytest.raises(ValueError):
        preremplir_droit_de_vote(_reunion())


def test_prerempli_inclut_un_adherent_sans_compte(params, db):
    """Un adhérent SANS compte de connexion, mais à jour, vote quand même en AG :
    le droit de vote est indexé par membre (pas par compte)."""
    params.vote_reserve_aux_membres_a_jour = True
    params.save()
    saison = Saison.objects.create(nom="2025-2026")
    reunion = _reunion()
    adherent = Membre.objects.create(prenom="Sans", nom="Compte")  # aucun user
    assert adherent.a_un_compte is False
    Adhesion.objects.create(membre=adherent, saison=saison, statut=Adhesion.Statut.PAYEE)
    presence = _presence(reunion, adherent, Presence.Statut.PRESENT, peut_voter=False)

    preremplir_droit_de_vote(reunion, saison)

    presence.refresh_from_db()
    assert presence.peut_voter is True


# --- Réponse d'un membre à sa convocation (présence / pouvoir) -------------


def _reunion_convoquee():
    return Reunion.objects.create(
        titre="AG",
        type_reunion=Reunion.TypeReunion.AG_ORDINAIRE,
        statut=Reunion.Statut.CONVOQUEE,
    )


def test_membre_declare_sa_presence(make_membre):
    reunion = _reunion_convoquee()
    presence = enregistrer_presence_membre(reunion, make_membre(), Presence.Statut.PRESENT)
    assert presence.statut == Presence.Statut.PRESENT
    assert presence.peut_voter is False  # fixé par le bureau, pas à l'auto-déclaration


def test_declarer_present_retire_le_pouvoir_donne(make_membre):
    reunion = _reunion_convoquee()
    a, b = make_membre(), make_membre()
    donner_pouvoir(reunion, a, b)
    enregistrer_presence_membre(reunion, a, Presence.Statut.PRESENT)
    assert not Pouvoir.objects.filter(reunion=reunion, mandant=a).exists()


def test_donner_pouvoir_cree_le_pouvoir_et_marque_represente(make_membre):
    reunion = _reunion_convoquee()
    a, b = make_membre(), make_membre()
    pouvoir = donner_pouvoir(reunion, a, b)
    assert pouvoir.mandataire == b
    assert Presence.objects.get(reunion=reunion, membre=a).statut == Presence.Statut.REPRESENTE


def test_donner_pouvoir_a_soi_meme_refuse(make_membre):
    reunion = _reunion_convoquee()
    a = make_membre()
    with pytest.raises(ReponseConvocationImpossible):
        donner_pouvoir(reunion, a, a)


def test_donner_pouvoir_refuse_au_dela_du_plafond(params, make_membre):
    params.max_pouvoirs_par_personne = 1
    params.save()
    reunion = _reunion_convoquee()
    mandataire = make_membre()
    donner_pouvoir(reunion, make_membre(), mandataire)  # 1er pouvoir : accepté
    with pytest.raises(ReponseConvocationImpossible):
        donner_pouvoir(reunion, make_membre(), mandataire)  # 2e : dépasse le plafond


# --- Gel des règles à la clôture (GOU-01) ------------------------------------
#
# Quorum et majorités étaient relus dans les paramètres COURANTS, à chaque
# affichage. Relever le quorum en février pouvait donc faire tomber une AG de
# janvier — ou l'inverse : une résolution adoptée redevenait rejetée sans que
# personne n'ait touché aux votes.


def _reunion_close(type_reunion=Reunion.TypeReunion.AG_ORDINAIRE):
    reunion = _reunion(type_reunion)
    reunion.statut = Reunion.Statut.ARCHIVEE
    reunion.save(update_fields=["statut"])
    figer_les_regles(reunion)
    return reunion


def test_une_reunion_close_garde_son_quorum(params, make_membre):
    params.quorum_ag_ordinaire = Decimal("0.500")
    params.save()
    reunion = _reunion()
    for membre in [make_membre() for _ in range(4)]:
        _presence(reunion, membre, Presence.Statut.PRESENT)
    assert calcul_quorum(reunion).atteint is True

    reunion.statut = Reunion.Statut.ARCHIVEE
    reunion.save(update_fields=["statut"])
    figer_les_regles(reunion)
    params.quorum_ag_ordinaire = Decimal("0.900")  # statuts modifiés après coup
    params.save()

    quorum = calcul_quorum(reunion)
    assert quorum.seuil == Decimal("0.500")
    assert quorum.atteint is True


def test_une_reunion_close_garde_sa_majorite(params, make_membre):
    params.majorite_simple = Decimal("0.500")
    params.save()
    reunion = _reunion_close()
    resolution = Resolution.objects.create(
        reunion=reunion,
        intitule="Approbation",
        type_majorite=Resolution.TypeMajorite.SIMPLE,
        nombre_pour=6,
        nombre_contre=4,
    )
    assert resultat_resolution(resolution).adoptee is True

    params.majorite_simple = Decimal("0.900")
    params.save()

    assert resultat_resolution(resolution).adoptee is True


def test_avant_cloture_les_regles_courantes_s_appliquent(params, make_membre):
    """Tant que la réunion n'est pas close, elle suit les statuts en vigueur —
    sinon corriger un seuil mal saisi serait impossible."""
    params.majorite_simple = Decimal("0.500")
    params.save()
    reunion = _reunion()
    resolution = Resolution.objects.create(
        reunion=reunion,
        intitule="Approbation",
        type_majorite=Resolution.TypeMajorite.SIMPLE,
        nombre_pour=6,
        nombre_contre=4,
    )
    assert resultat_resolution(resolution).adoptee is True

    params.majorite_simple = Decimal("0.900")
    params.save()

    assert resultat_resolution(resolution).adoptee is False


def test_archiver_depuis_l_admin_fige_aussi_les_regles(db, rf, params):
    """Le statut est modifiable dans l'admin : le gel ne peut pas vivre
    seulement dans l'écran du bureau, sinon ce chemin-là laisse une assemblée
    à la merci du prochain réglage."""
    from django.contrib import admin as django_admin

    params.quorum_ag_ordinaire = Decimal("0.500")
    params.save()
    reunion = _reunion()
    reunion.statut = Reunion.Statut.ARCHIVEE
    requete = rf.post("/admin/")
    requete.user = Utilisateur.objects.create_superuser(username="admin", password="x")

    django_admin.site.get_model_admin(Reunion).save_model(requete, reunion, None, True)

    reunion.refresh_from_db()
    assert reunion.regles_figees["quorum"] == "0.500"


def test_le_gel_ne_se_rejoue_pas(params):
    """Refiger écraserait les règles du jour par celles d'aujourd'hui."""
    params.quorum_ag_ordinaire = Decimal("0.500")
    params.save()
    reunion = _reunion_close()

    params.quorum_ag_ordinaire = Decimal("0.900")
    params.save()
    assert figer_les_regles(reunion) is False

    assert calcul_quorum(reunion).seuil == Decimal("0.500")


def test_le_registre_d_une_reunion_close_ne_se_rouvre_pas(params, make_membre):
    """Rouvrir le registre après la clôture changerait l'électorat d'une
    assemblée déjà tenue, donc son quorum — et le gel des règles n'y pourrait
    rien, puisqu'il ne porte que sur les seuils."""
    params.vote_reserve_aux_membres_a_jour = False
    params.save()
    reunion = _reunion_close()
    make_membre()  # un membre arrivé après la séance

    with pytest.raises(ValueError):
        preremplir_droit_de_vote(reunion)


# --- Registre électoral (GOU-01) ---------------------------------------------
#
# Le quorum se calculait sur les présences ENREGISTRÉES : vingt électeurs dont
# cinq inscrits donnaient un quorum atteint à 100 %. Le dénominateur doit être
# l'électorat, donc le registre doit contenir tout le monde — présents comme
# absents.


def test_le_preremplissage_inscrit_tous_les_electeurs(params, make_membre):
    params.vote_reserve_aux_membres_a_jour = True
    params.save()
    saison = Saison.objects.create(nom="2025-2026")
    reunion = _reunion()
    a_jour = [make_membre() for _ in range(3)]
    for membre in a_jour:
        Adhesion.objects.create(membre=membre, saison=saison, statut=Adhesion.Statut.PAYEE)
    retardataire = make_membre()
    _presence(reunion, a_jour[0], Presence.Statut.PRESENT)

    preremplir_droit_de_vote(reunion, saison=saison)

    assert reunion.presences.filter(peut_voter=True).count() == 3
    # Inscrit d'office, mais absent tant que personne ne dit le contraire.
    assert reunion.presences.get(membre=a_jour[1]).statut == Presence.Statut.ABSENT
    # Le membre qui n'est pas à jour n'entre pas dans l'électorat.
    assert not reunion.presences.filter(membre=retardataire, peut_voter=True).exists()


def test_le_registre_ne_s_ouvre_pas_pour_une_reunion_de_bureau(params, make_membre):
    """Un bureau n'a pas d'électorat : le quorum n'y est pas applicable, et
    inscrire d'office toute l'association à une réunion de bureau produirait une
    liste de présences qui ne veut rien dire."""
    params.vote_reserve_aux_membres_a_jour = False
    params.save()
    reunion = _reunion(Reunion.TypeReunion.BUREAU)
    _presence(reunion, make_membre(), Presence.Statut.PRESENT)
    make_membre()  # membre de l'association, étranger au bureau

    preremplir_droit_de_vote(reunion)

    assert reunion.presences.count() == 1


def test_le_quorum_se_calcule_sur_l_electorat_complet(params, make_membre):
    """Le cas de l'audit, chiffres compris."""
    params.vote_reserve_aux_membres_a_jour = False
    params.quorum_ag_ordinaire = Decimal("0.500")
    params.save()
    reunion = _reunion()
    membres = [make_membre() for _ in range(20)]

    preremplir_droit_de_vote(reunion)
    for membre in membres[:5]:
        Presence.objects.filter(reunion=reunion, membre=membre).update(
            statut=Presence.Statut.PRESENT
        )

    quorum = calcul_quorum(reunion)

    assert quorum.electorat == 20
    assert quorum.presents_representes == 5
    assert quorum.atteint is False


# --- Pouvoirs : un seul service pour les deux chemins (GOU-01) ---------------
#
# Le membre passait par `donner_pouvoir`, qui contrôle le plafond ; le bureau
# écrivait directement en base, sans aucun contrôle. Le plafond est statutaire :
# il ne peut pas dépendre de qui saisit.


def test_le_bureau_ne_depasse_pas_le_plafond_de_pouvoirs(params, make_membre):
    params.max_pouvoirs_par_personne = 1
    params.save()
    reunion = _reunion_convoquee()
    mandataire = make_membre()
    donner_pouvoir(reunion, make_membre(), mandataire, par_le_bureau=True)

    with pytest.raises(ReponseConvocationImpossible):
        donner_pouvoir(reunion, make_membre(), mandataire, par_le_bureau=True)

    assert reunion.pouvoirs.count() == 1


def test_le_bureau_enregistre_un_pouvoir_sur_une_reunion_deja_tenue(make_membre):
    """Ce qui justifiait un second chemin : un pouvoir papier se saisit pendant
    ou après la séance, quand la réunion n'accepte plus de réponse en ligne. Le
    plafond, lui, s'applique dans les deux cas."""
    reunion = Reunion.objects.create(
        titre="AG tenue",
        type_reunion=Reunion.TypeReunion.AG_ORDINAIRE,
        statut=Reunion.Statut.TENUE,
    )
    a, b = make_membre(), make_membre()

    pouvoir = donner_pouvoir(reunion, a, b, par_le_bureau=True)

    assert pouvoir.mandataire == b
    with pytest.raises(ReponseConvocationImpossible):
        donner_pouvoir(reunion, make_membre(), b)  # le membre, lui, ne peut plus


def test_pas_de_reponse_si_reunion_non_convoquee(make_membre):
    reunion = Reunion.objects.create(
        titre="AG tenue",
        type_reunion=Reunion.TypeReunion.AG_ORDINAIRE,
        statut=Reunion.Statut.TENUE,
    )
    with pytest.raises(ReponseConvocationImpossible):
        enregistrer_presence_membre(reunion, make_membre(), Presence.Statut.PRESENT)


# --- Génération du compte-rendu (PV) ---------------------------------------


def test_generer_compte_rendu_depose_un_document_membres(db, monkeypatch):
    # PDF mocké : on stocke le HTML rendu pour pouvoir vérifier son contenu.
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: html.encode()
    )
    bureau = Utilisateur.objects.create(username="bureau")
    reunion = _reunion()
    membre = Membre.objects.create(prenom="Alice", nom="Martin")
    _presence(reunion, membre, Presence.Statut.PRESENT)
    Sujet.objects.create(
        titre="Budget prévisionnel",
        reunion=reunion,
        statut=Sujet.Statut.ORDRE_DU_JOUR,
        notes="Adopté sans opposition",
    )

    doc = generer_compte_rendu(reunion, par=bureau)

    reunion.refresh_from_db()
    assert reunion.compte_rendu_id == doc.pk
    assert doc.confidentialite == Document.Confidentialite.MEMBRES
    contenu = doc.fichier.open("rb").read().decode()
    assert "Martin" in contenu  # présent listé
    assert "Adopté sans opposition" in contenu  # notes du point d'ordre du jour


def test_regenerer_pv_remplace_sans_creer_de_doublon(db, monkeypatch):
    monkeypatch.setattr("apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: b"%PDF-1.4")
    bureau = Utilisateur.objects.create(username="bureau")
    reunion = _reunion()
    doc1 = generer_compte_rendu(reunion, par=bureau)
    doc2 = generer_compte_rendu(reunion, par=bureau)
    assert doc1.pk == doc2.pk  # même Document, fichier remplacé
    assert Document.objects.count() == 1


def test_pv_intercale_les_blocs_de_recit_dans_le_deroule(db, monkeypatch):
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: html.encode()
    )
    bureau = Utilisateur.objects.create(username="bureau")
    reunion = _reunion()
    sujet = Sujet.objects.create(titre="Budget", reunion=reunion, statut=Sujet.Statut.ORDRE_DU_JOUR)
    BlocCompteRendu.objects.create(reunion=reunion, apres_sujet=None, texte="Ouverture de seance")
    BlocCompteRendu.objects.create(reunion=reunion, apres_sujet=sujet, texte="Transition suivante")

    contenu = generer_compte_rendu(reunion, par=bureau).fichier.open("rb").read().decode()
    # Ordre attendu dans le déroulé : préambule < point < bloc rattaché au point.
    assert (
        contenu.index("Ouverture de seance")
        < contenu.index("Budget")
        < contenu.index("Transition suivante")
    )
