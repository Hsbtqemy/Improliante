"""Tests de la numérotation des factures (zone à risque, cf. cahier §4).

Note : par défaut ces tests tournent sur SQLite, où `select_for_update` est un
no-op — ils valident alors les RÈGLES (séquentielle, continue, sans trou, à la
validation), pas leur tenue en concurrence. Le test de validations simultanées,
en fin de fichier, éprouve le verrou lui-même et ne s'exécute que sur le moteur
de production : `TEST_POSTGRES=1 pytest`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib import admin
from django.core.management import call_command

from apps.coeur.models import Signataire, Utilisateur
from apps.common.pdf import RenduPDFIndisponible
from apps.facturation.admin import LigneFactureInline
from apps.facturation.models import (
    Client,
    CompteurFacture,
    Devis,
    Facture,
    LigneDevis,
    LigneFacture,
)
from apps.facturation.services import (
    AvoirExcessif,
    AvoirSansOrigine,
    DevisDejaFacture,
    FactureDejaValidee,
    FactureNonAvoirable,
    FactureSansLigne,
    MontantIncoherent,
    assurer_pdf_facture,
    creer_avoir,
    dupliquer_facture,
    numeroter_devis,
    pdf_de_facture,
    transformer_en_facture,
    valider_facture,
)


@pytest.fixture
def client_facture(db):
    return Client.objects.create(nom="Association X")


def _brouillon(client_facture, **champs):
    """Brouillon validable : une facture sans ligne est refusée à la validation."""
    facture = Facture.objects.create(client=client_facture, **champs)
    LigneFacture.objects.create(
        facture=facture, designation="Prestation", prix_unitaire_ht=Decimal("100")
    )
    return facture


def test_brouillon_sans_numero(client_facture):
    facture = Facture.objects.create(client=client_facture)
    assert facture.numero is None
    assert facture.statut == Facture.Statut.BROUILLON
    assert facture.date is None


# --- Convention d'arrondi ----------------------------------------------------
#
# Chaque ligne est arrondie au centime AVANT d'être sommée, au pair le plus
# proche. Ces deux tests fixent la convention : `facturation.js` la reproduit,
# et l'écran de saisie doit annoncer le montant qui sera émis.


def test_l_arrondi_d_une_ligne_se_fait_au_pair(client_facture):
    facture = Facture.objects.create(client=client_facture)
    LigneFacture.objects.create(
        facture=facture,
        designation="Demi-heure",
        quantite=Decimal("0.5"),
        prix_unitaire_ht=Decimal("0.25"),
    )
    assert facture.total_ht == Decimal("0.12")  # 0,125 au pair, et non 0,13


def test_les_lignes_sont_arrondies_avant_d_etre_sommees(client_facture):
    """L'exemple de l'audit : sommer d'abord donnerait 0,0495 €, donc 0,05 €."""
    facture = Facture.objects.create(client=client_facture)
    for rang in range(3):
        LigneFacture.objects.create(
            facture=facture,
            designation="Copie",
            quantite=Decimal("0.33"),
            prix_unitaire_ht=Decimal("0.05"),
            ordre=rang,
        )
    assert facture.total_ht == Decimal("0.06")


def test_validation_attribue_numero_statut_et_date(client_facture):
    facture = _brouillon(client_facture)
    valider_facture(facture, date_emission=date(2026, 3, 1))
    facture.refresh_from_db()
    assert facture.numero == "F2026-0001"
    assert facture.statut == Facture.Statut.VALIDEE
    assert facture.date == date(2026, 3, 1)
    assert facture.date_validation is not None


def test_sequence_continue_sans_trou(client_facture):
    numeros = []
    for _ in range(3):
        f = _brouillon(client_facture)
        valider_facture(f, date_emission=date(2026, 3, 1))
        f.refresh_from_db()
        numeros.append(f.numero)
    assert numeros == ["F2026-0001", "F2026-0002", "F2026-0003"]


def test_revalidation_interdite(client_facture):
    facture = _brouillon(client_facture)
    valider_facture(facture, date_emission=date(2026, 3, 1))
    with pytest.raises(FactureDejaValidee):
        valider_facture(facture)


def test_serie_annuelle_independante(client_facture):
    f2026 = _brouillon(client_facture)
    valider_facture(f2026, date_emission=date(2026, 12, 31))
    f2027 = _brouillon(client_facture)
    valider_facture(f2027, date_emission=date(2027, 1, 1))
    f2026.refresh_from_db()
    f2027.refresh_from_db()
    assert f2026.numero == "F2026-0001"
    assert f2027.numero == "F2027-0001"


def test_reinit_factures_remet_la_numerotation_a_zero(client_facture, settings):
    # La commande refuse de tourner hors DEBUG (protection prod) ; pytest force
    # DEBUG=False, on le réactive donc explicitement pour ce test.
    settings.DEBUG = True

    f = _brouillon(client_facture)
    valider_facture(f, date_emission=date(2026, 3, 1))
    assert Facture.objects.count() == 1

    call_command("reinit_factures", "--yes")
    assert Facture.objects.count() == 0

    # La numérotation repart bien à 0001.
    f2 = _brouillon(client_facture)
    valider_facture(f2, date_emission=date(2026, 3, 1))
    f2.refresh_from_db()
    assert f2.numero == "F2026-0001"


# --- Validation : l'état relu sous verrou, pas celui de l'appelant -----------
#
# Le compteur était verrouillé, la facture non. Deux requêtes ayant lu le même
# brouillon (double clic, deux onglets) passaient donc toutes deux le contrôle
# « encore brouillon ? », et la seconde réécrivait le numéro de la première :
# F2026-0001 consommé, porté par aucune pièce — un trou dans la série.


def test_deux_validations_du_meme_brouillon_n_emettent_qu_une_fois(client_facture):
    brouillon = _brouillon(client_facture)
    onglet_a = Facture.objects.get(pk=brouillon.pk)
    onglet_b = Facture.objects.get(pk=brouillon.pk)  # lu avant la 1re validation

    valider_facture(onglet_a, date_emission=date(2026, 3, 1))
    with pytest.raises(FactureDejaValidee):
        valider_facture(onglet_b, date_emission=date(2026, 3, 1))

    brouillon.refresh_from_db()
    assert brouillon.numero == "F2026-0001"
    assert CompteurFacture.objects.get(annee=2026).dernier == 1  # aucun numéro perdu


def test_une_facture_sans_ligne_n_est_pas_validee(client_facture):
    """La règle vivait dans la vue : l'action d'admin la contournait."""
    facture = Facture.objects.create(client=client_facture)
    with pytest.raises(FactureSansLigne):
        valider_facture(facture, date_emission=date(2026, 3, 1))
    facture.refresh_from_db()
    assert facture.numero is None
    assert not CompteurFacture.objects.filter(dernier__gt=0).exists()


# --- Devis : numérotation souple + transformation en facture ---------------


def test_numeroter_devis_attribue_un_numero(client_facture):
    devis = Devis.objects.create(client=client_facture, date=date(2026, 3, 1))
    numeroter_devis(devis)
    assert devis.numero == "D2026-0001"


def test_numeroter_devis_ne_reecrit_pas_un_numero_existant(client_facture):
    devis = Devis.objects.create(client=client_facture, date=date(2026, 3, 1), numero="D2026-0042")
    numeroter_devis(devis)
    assert devis.numero == "D2026-0042"


def test_numeroter_devis_ne_reutilise_pas_apres_suppression(client_facture):
    """Un numéro supprimé ne doit jamais être réattribué (pas de doublon)."""
    d1 = Devis.objects.create(client=client_facture, date=date(2026, 3, 1))
    numeroter_devis(d1)
    d2 = Devis.objects.create(client=client_facture, date=date(2026, 3, 1))
    numeroter_devis(d2)
    assert [d1.numero, d2.numero] == ["D2026-0001", "D2026-0002"]

    d1.delete()
    d3 = Devis.objects.create(client=client_facture, date=date(2026, 3, 1))
    numeroter_devis(d3)
    assert d3.numero == "D2026-0003"  # 0002 n'est pas réutilisé
    assert Devis.objects.filter(numero="D2026-0002").count() == 1  # aucun doublon


def test_transformer_en_facture_copie_client_et_lignes(client_facture):
    devis = Devis.objects.create(client=client_facture, date=date(2026, 3, 1), objet="Spectacle")
    LigneDevis.objects.create(
        devis=devis,
        designation="Représentation",
        quantite=2,
        prix_unitaire_ht=Decimal("100"),
        taux_tva=Decimal("20"),
    )
    facture = transformer_en_facture(devis)
    devis.refresh_from_db()
    assert devis.statut == Devis.Statut.FACTURE
    assert facture.client == client_facture
    assert facture.devis_origine == devis
    assert facture.objet == "Spectacle"
    assert facture.lignes.count() == 1
    assert facture.total_ttc == Decimal("240.00")  # 2 × 100 + 20 %


def test_transformer_un_devis_deja_facture_leve(client_facture):
    devis = Devis.objects.create(
        client=client_facture, date=date(2026, 3, 1), statut=Devis.Statut.FACTURE
    )
    with pytest.raises(DevisDejaFacture):
        transformer_en_facture(devis)


def test_deux_transformations_du_meme_devis_ne_creent_qu_une_facture(client_facture):
    """Même défaut que la validation : le statut testé était celui de
    l'instance reçue, lue avant la première transformation."""
    devis = Devis.objects.create(client=client_facture, date=date(2026, 3, 1))
    onglet_a = Devis.objects.get(pk=devis.pk)
    onglet_b = Devis.objects.get(pk=devis.pk)

    transformer_en_facture(onglet_a)
    with pytest.raises(DevisDejaFacture):
        transformer_en_facture(onglet_b)

    assert Facture.objects.filter(devis_origine=devis).count() == 1


# --- Avoir : annulation d'une facture validée ------------------------------


def _facture_validee(client_facture, **ligne):
    facture = Facture.objects.create(client=client_facture)
    LigneFacture.objects.create(
        facture=facture,
        designation=ligne.get("designation", "Prestation"),
        quantite=ligne.get("quantite", 2),
        prix_unitaire_ht=ligne.get("prix_unitaire_ht", Decimal("100")),
        taux_tva=ligne.get("taux_tva", Decimal("20")),
    )
    valider_facture(facture, date_emission=date(2026, 3, 1))
    return facture


def test_creer_avoir_reprend_les_lignes_inversees(client_facture):
    facture = _facture_validee(client_facture)
    avoir = creer_avoir(facture)
    assert avoir.type_piece == Facture.TypePiece.AVOIR
    assert avoir.avoir_de == facture
    assert avoir.statut == Facture.Statut.BROUILLON
    assert avoir.lignes.count() == 1
    assert avoir.total_ttc == Decimal("-240.00")  # 2×100 +20 %, inversé


def test_avoir_valide_prend_un_numero_de_serie_a_continue(client_facture):
    facture = _facture_validee(client_facture)  # F2026-0001
    avoir = creer_avoir(facture)
    valider_facture(avoir, date_emission=date(2026, 3, 1))
    avoir.refresh_from_db()
    assert facture.numero == "F2026-0001"
    assert avoir.numero == "A2026-0002"  # séquence partagée, continue


# --- Signe des pièces et bornes des lignes (FIN-04) --------------------------
#
# Interdire tout nombre négatif serait faux : une remise est une ligne négative
# légitime dans une facture. Ce qui doit tenir, c'est le SIGNE DE LA PIÈCE — une
# facture ne rembourse pas, un avoir ne facture pas — car le contrôle « jamais
# plus que le reste à annuler » suppose des avoirs négatifs.


def test_un_taux_de_tva_hors_bornes_est_refuse_par_la_base(client_facture):
    from django.db import IntegrityError

    facture = Facture.objects.create(client=client_facture)
    with pytest.raises(IntegrityError):
        LigneFacture.objects.create(
            facture=facture, designation="TVA impossible", taux_tva=Decimal("120")
        )


def test_un_taux_de_tva_negatif_est_refuse_par_la_base(client_facture):
    from django.db import IntegrityError

    facture = Facture.objects.create(client=client_facture)
    with pytest.raises(IntegrityError):
        LigneFacture.objects.create(
            facture=facture, designation="TVA négative", taux_tva=Decimal("-1")
        )


def test_la_borne_de_tva_vaut_aussi_pour_les_lignes_de_devis(client_facture):
    """La contrainte vit dans la classe abstraite : elle ne tient que parce que
    les `Meta` concrets en héritent. Un `class Meta:` neuf la ferait disparaître
    sans bruit, des deux côtés."""
    from django.db import IntegrityError

    devis = Devis.objects.create(client=client_facture, date=date(2026, 3, 1))
    with pytest.raises(IntegrityError):
        LigneDevis.objects.create(devis=devis, designation="X", taux_tva=Decimal("120"))


def test_une_remise_reste_possible_dans_une_facture(client_facture):
    """Une ligne négative est tolérée tant que la pièce reste une facture."""
    facture = Facture.objects.create(client=client_facture)
    LigneFacture.objects.create(
        facture=facture, designation="Prestation", prix_unitaire_ht=Decimal("100")
    )
    LigneFacture.objects.create(
        facture=facture,
        designation="Remise fidélité",
        quantite=Decimal("-1"),
        prix_unitaire_ht=Decimal("20"),
        ordre=1,
    )

    valider_facture(facture, date_emission=date(2026, 3, 1))

    facture.refresh_from_db()
    assert facture.numero == "F2026-0001"
    assert facture.total_ttc == Decimal("80.00")


def test_une_facture_au_total_negatif_ne_s_emet_pas(client_facture):
    """Ce serait un avoir déguisé : ni le bon type, ni le bon préfixe de numéro."""
    facture = Facture.objects.create(client=client_facture)
    LigneFacture.objects.create(
        facture=facture,
        designation="Remboursement",
        quantite=Decimal("-1"),
        prix_unitaire_ht=Decimal("100"),
    )

    with pytest.raises(MontantIncoherent):
        valider_facture(facture, date_emission=date(2026, 3, 1))

    facture.refresh_from_db()
    assert facture.numero is None


def test_un_avoir_remis_a_l_endroit_ne_s_emet_pas(client_facture):
    """Sans cette règle, il passerait le contrôle du reste à annuler, qui
    suppose des montants négatifs — et facturerait au lieu d'annuler."""
    facture = _facture_validee(client_facture)
    avoir = creer_avoir(facture)
    avoir.lignes.update(quantite=Decimal("2"))

    with pytest.raises(MontantIncoherent):
        valider_facture(avoir, date_emission=date(2026, 3, 1))


def test_un_avoir_detache_de_sa_facture_ne_s_emet_pas(client_facture):
    """`dupliquer_facture` détache volontairement la copie d'un avoir. Sans
    facture d'origine, elle échappait au contrôle du reste à annuler : elle peut
    donc se préparer, mais pas s'émettre telle quelle."""
    origine = _facture_validee(client_facture)
    copie = dupliquer_facture(creer_avoir(origine))

    with pytest.raises(AvoirSansOrigine):
        valider_facture(copie, date_emission=date(2026, 3, 1))

    assert copie.numero is None


def test_creer_avoir_sur_brouillon_refuse(client_facture):
    facture = Facture.objects.create(client=client_facture)  # brouillon
    with pytest.raises(FactureNonAvoirable):
        creer_avoir(facture)


def test_creer_avoir_sur_avoir_refuse(client_facture):
    facture = _facture_validee(client_facture)
    avoir = creer_avoir(facture)
    valider_facture(avoir, date_emission=date(2026, 3, 1))
    with pytest.raises(FactureNonAvoirable):
        creer_avoir(avoir)


def test_un_second_avoir_attend_que_le_premier_soit_valide(client_facture):
    """Double clic sur « Créer un avoir » : un seul brouillon."""
    facture = _facture_validee(client_facture)
    creer_avoir(facture)
    with pytest.raises(FactureNonAvoirable):
        creer_avoir(facture)
    assert facture.avoirs.count() == 1


def test_une_facture_entierement_annulee_ne_prend_plus_d_avoir(client_facture):
    facture = _facture_validee(client_facture)
    valider_facture(creer_avoir(facture), date_emission=date(2026, 3, 1))
    with pytest.raises(FactureNonAvoirable):
        creer_avoir(facture)


def test_les_avoirs_n_annulent_jamais_plus_que_la_facture(client_facture):
    """Un avoir partiel reste possible (l'avoir se retouche avant validation),
    mais la somme des avoirs validés ne dépasse jamais la facture."""
    facture = _facture_validee(client_facture)  # 2 × 100 HT + 20 % = 240 TTC
    partiel = creer_avoir(facture)
    partiel.lignes.update(quantite=-1)  # n'annule que la moitié : 120
    valider_facture(partiel, date_emission=date(2026, 3, 1))

    complet = creer_avoir(facture)  # reprend les 240 : 120 de trop
    with pytest.raises(AvoirExcessif):
        valider_facture(complet, date_emission=date(2026, 3, 1))

    complet.lignes.update(quantite=-1)
    valider_facture(complet, date_emission=date(2026, 3, 1))
    complet.refresh_from_db()
    assert complet.numero == "A2026-0003"  # le refus n'a consommé aucun numéro


# --- Signature ------------------------------------------------------------


def test_pdf_facture_rend_le_bloc_signataire(client_facture, monkeypatch):
    # Le moteur PDF renvoie le HTML : on vérifie que le bloc signature est rendu.
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: html.encode()
    )
    sig = Signataire.objects.create(
        nom="Alice Martin", qualite="Présidente", mention_delegation="délégation du bureau"
    )
    facture = Facture.objects.create(client=client_facture, signataire=sig)
    html = pdf_de_facture(facture).decode()
    assert "Alice Martin" in html
    assert "Présidente" in html
    assert "délégation du bureau" in html


def test_pdf_facture_sans_signataire_pas_de_bloc(client_facture, monkeypatch):
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: html.encode()
    )
    facture = Facture.objects.create(client=client_facture)
    html = pdf_de_facture(facture).decode()
    assert 'class="signature"' not in html


# --- PDF figé à l'émission ---------------------------------------------------


def test_le_pdf_est_fige_des_la_validation(
    client_facture, monkeypatch, django_capture_on_commit_callbacks
):
    """Rendu au premier téléchargement, le PDF reprenait les données du jour :
    renommer le client entre validation et téléchargement changeait la pièce."""
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: html.encode()
    )
    facture = _brouillon(client_facture)
    with django_capture_on_commit_callbacks(execute=True):
        valider_facture(facture, date_emission=date(2026, 3, 1))

    client_facture.nom = "Nouveau nom"
    client_facture.save()
    facture.refresh_from_db()
    assurer_pdf_facture(facture)  # ne rend rien : le fichier existe déjà

    contenu = facture.fichier.open("rb").read().decode()
    assert "Association X" in contenu
    assert "Nouveau nom" not in contenu


def test_sans_moteur_pdf_la_validation_tient(
    client_facture, monkeypatch, django_capture_on_commit_callbacks
):
    """Sans WeasyPrint (poste Windows), le numéro reste attribué ; le PDF sera
    rendu au premier téléchargement, comme avant."""

    def moteur_absent(html, *, base_url=None):
        raise RenduPDFIndisponible("pas de moteur")

    monkeypatch.setattr("apps.common.pdf.html_vers_pdf", moteur_absent)
    facture = _brouillon(client_facture)
    with django_capture_on_commit_callbacks(execute=True):
        valider_facture(facture, date_emission=date(2026, 3, 1))

    facture.refresh_from_db()
    assert facture.numero == "F2026-0001"
    assert not facture.fichier


def test_deux_premiers_telechargements_ne_rendent_le_pdf_qu_une_fois(client_facture, monkeypatch):
    """Deux requêtes parties d'une facture encore sans PDF : la seconde ne
    remplace pas le fichier archivé par la première."""
    rendus = []
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf",
        lambda html, *, base_url=None: rendus.append(html) or b"%PDF-1.4",
    )
    facture = _brouillon(client_facture)
    valider_facture(facture, date_emission=date(2026, 3, 1))  # sans commit : pas de PDF
    requete_a = Facture.objects.get(pk=facture.pk)
    requete_b = Facture.objects.get(pk=facture.pk)

    assurer_pdf_facture(requete_a)
    assurer_pdf_facture(requete_b)

    assert len(rendus) == 1
    assert requete_b.fichier.name == requete_a.fichier.name


# --- Instantané d'émission ---------------------------------------------------
#
# Le PDF archivé EST la pièce. Mais s'il disparaît — fichier perdu, stockage
# restauré à moitié — le régénérer depuis les données du jour donnerait une autre
# facture : autre nom d'association, autre adresse de client, autre signataire.
# L'émission fige donc aussi ce que la pièce disait d'elle-même.


def test_la_validation_fige_l_emetteur_et_le_client(client_facture):
    from apps.coeur.models import ParametresAssociation

    params = ParametresAssociation.load()
    params.nom = "Association Improliante"
    params.save()
    facture = _brouillon(client_facture)

    valider_facture(facture, date_emission=date(2026, 3, 1))

    facture.refresh_from_db()
    assert facture.instantane["emetteur"]["nom"] == "Association Improliante"
    assert facture.instantane["client"]["nom"] == "Association X"
    assert facture.instantane["totaux"]["total_ttc"] == "100.00"
    assert [ligne["designation"] for ligne in facture.instantane["lignes"]] == ["Prestation"]


def test_un_pdf_perdu_se_regenere_a_l_identique(
    client_facture, monkeypatch, django_capture_on_commit_callbacks
):
    """Le fichier n'est plus là ; la pièce, elle, ne bouge pas."""
    from apps.coeur.models import ParametresAssociation

    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: html.encode()
    )
    params = ParametresAssociation.load()
    params.nom = "Association Improliante"
    params.save()
    facture = _brouillon(client_facture)
    with django_capture_on_commit_callbacks(execute=True):
        valider_facture(facture, date_emission=date(2026, 3, 1))

    facture.refresh_from_db()
    facture.fichier.delete(save=True)  # sinistre : le PDF archivé a disparu
    params.nom = "Troupe renommée"
    params.save()
    client_facture.nom = "Autre client"
    client_facture.save()

    assurer_pdf_facture(facture)

    contenu = facture.fichier.open("rb").read().decode()
    assert "Association Improliante" in contenu
    assert "Association X" in contenu
    assert "Troupe renommée" not in contenu
    assert "Autre client" not in contenu


def test_le_rendu_fige_et_le_rendu_vivant_coincident_a_l_emission(client_facture, monkeypatch):
    """Garde-fou du dispositif : à l'instant de l'émission, l'instantané et les
    données vivantes disent forcément la même chose. Si un champ manque à
    l'instantané, la pièce reconstruite le perdra — et ce test le voit tout de
    suite, au lieu du jour où un PDF doit être régénéré."""
    from django.template.loader import render_to_string

    from apps.coeur.models import ParametresAssociation, Signataire

    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: html.encode()
    )
    params = ParametresAssociation.load()
    for champ, valeur in {
        "nom": "Association Improliante",
        "objet": "théâtre d'improvisation",
        "adresse": "3 rue des Arts",
        "code_postal": "75011",
        "ville": "Paris",
        "numero_rna": "W123456789",
        "numero_siret": "12345678900011",
        "iban": "FR7612345678901234567890123",
        "bic": "ABCDEFGH",
        "mention_tva": "TVA non applicable, art. 293 B du CGI",
    }.items():
        setattr(params, champ, valeur)
    params.save()
    signataire = Signataire.objects.create(
        nom="Alice Martin", qualite="Présidente", mention_delegation="délégation du bureau"
    )
    client_facture.adresse = "1 place du Théâtre"
    client_facture.code_postal = "69001"
    client_facture.ville = "Lyon"
    client_facture.siret = "98765432100017"
    client_facture.save()
    facture = _brouillon(
        client_facture,
        objet="Représentation",
        date_echeance=date(2026, 4, 30),
        mentions_legales="Pénalités de retard : trois fois le taux légal.",
        signataire=signataire,
    )
    valider_facture(facture, date_emission=date(2026, 3, 1))
    facture.refresh_from_db()

    fige = pdf_de_facture(facture).decode()
    vivant = render_to_string(
        "facture/facture.html",
        {"facture": facture, "asso": ParametresAssociation.load(), "apercu": False},
    )

    assert fige == vivant


def test_le_rendu_fige_d_un_avoir_coincide_aussi(client_facture, monkeypatch):
    """L'avoir a une ligne de plus à figer : la facture qu'il annule. Sans ce
    test, un `avoir_de` oublié dans l'instantané passait inaperçu — la pièce
    d'essai du test précédent n'en a pas."""
    from django.template.loader import render_to_string

    from apps.coeur.models import ParametresAssociation

    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: html.encode()
    )
    facture = _facture_validee(client_facture)
    avoir = creer_avoir(facture)
    valider_facture(avoir, date_emission=date(2026, 3, 1))
    avoir.refresh_from_db()

    fige = pdf_de_facture(avoir).decode()
    vivant = render_to_string(
        "facture/facture.html",
        {"facture": avoir, "asso": ParametresAssociation.load(), "apercu": False},
    )

    assert fige == vivant
    assert f"Avoir sur facture {facture.numero}" in fige


def test_l_apercu_d_un_brouillon_montre_les_donnees_du_jour(client_facture, monkeypatch):
    """Avant l'émission il n'y a rien à figer : l'aperçu doit refléter ce qui est
    saisi, sinon il ne sert à rien."""
    monkeypatch.setattr(
        "apps.common.pdf.html_vers_pdf", lambda html, *, base_url=None: html.encode()
    )
    client_facture.nom = "Nom corrigé avant émission"
    client_facture.save()
    facture = _brouillon(client_facture)

    html = pdf_de_facture(facture, apercu=True).decode()

    assert "Nom corrigé avant émission" in html


# --- Admin : mêmes règles que les écrans du bureau ---------------------------
#
# Le formulaire du bureau refusait déjà d'éditer une pièce émise ; l'admin, lui,
# laissait tout changer — client, lignes, statut — et supprimer.


def _superadmin():
    return Utilisateur.objects.create_superuser(username="admin", password="x")


def _requete_admin(rf):
    requete = rf.get("/admin/")
    requete.user = _superadmin()
    return requete


def test_admin_une_facture_emise_ne_se_supprime_pas(client, client_facture):
    facture = _brouillon(client_facture)
    valider_facture(facture, date_emission=date(2026, 3, 1))
    client.force_login(_superadmin())

    reponse = client.post(f"/admin/facturation/facture/{facture.pk}/delete/", {"post": "yes"})
    assert reponse.status_code == 403
    # L'action groupée « Supprimer » passe par le même contrôle, objet par objet.
    client.post(
        "/admin/facturation/facture/",
        {"action": "delete_selected", "_selected_action": [facture.pk], "post": "yes"},
    )
    assert Facture.objects.filter(pk=facture.pk).exists()


def test_admin_une_facture_emise_ne_garde_que_le_suivi_de_paiement(rf, client_facture):
    """Seul le statut bouge encore : aucun écran ne marque une facture payée,
    l'admin est aujourd'hui le seul chemin pour le faire."""
    facture = _brouillon(client_facture)
    valider_facture(facture, date_emission=date(2026, 3, 1))
    requete = _requete_admin(rf)
    modele_admin = admin.site.get_model_admin(Facture)

    figes = set(modele_admin.get_readonly_fields(requete, facture))
    assert {"client", "objet", "mentions_legales", "signataire", "avoir_de"} <= figes
    assert "statut" not in figes
    form = modele_admin.get_form(requete, facture)
    assert Facture.Statut.BROUILLON not in dict(form.base_fields["statut"].choices)
    # Les lignes suivent la pièce : ni ajout, ni retouche, ni retrait.
    inline = LigneFactureInline(Facture, admin.site)
    assert not inline.has_add_permission(requete, facture)
    assert not inline.has_change_permission(requete, facture)
    assert not inline.has_delete_permission(requete, facture)


def test_admin_le_statut_d_un_brouillon_ne_change_qu_en_validant(rf, client_facture):
    """Sinon « Validée » se choisirait dans une liste, sans numéro."""
    modele_admin = admin.site.get_model_admin(Facture)
    figes = modele_admin.get_readonly_fields(_requete_admin(rf), _brouillon(client_facture))
    assert "statut" in figes


def test_admin_l_action_de_validation_refuse_un_brouillon_sans_ligne(client, client_facture):
    facture = Facture.objects.create(client=client_facture)
    client.force_login(_superadmin())
    client.post(
        "/admin/facturation/facture/",
        {"action": "valider_factures", "_selected_action": [facture.pk]},
    )
    facture.refresh_from_db()
    assert facture.numero is None


def test_admin_marque_payee_une_facture_emise_sans_rien_changer_d_autre(client, client_facture):
    """Le seul geste qui reste sur une pièce émise, de bout en bout. Un client,
    un objet ou des lignes postés à la main en même temps sont ignorés."""
    facture = _brouillon(client_facture)
    valider_facture(facture, date_emission=date(2026, 3, 1))
    ligne = facture.lignes.get()
    client.force_login(_superadmin())

    reponse = client.post(
        f"/admin/facturation/facture/{facture.pk}/change/",
        {
            "statut": Facture.Statut.PAYEE,
            "client": Client.objects.create(nom="Autre client").pk,
            "objet": "Réécrit",
            "lignes-TOTAL_FORMS": "1",
            "lignes-INITIAL_FORMS": "1",
            "lignes-MIN_NUM_FORMS": "0",
            "lignes-MAX_NUM_FORMS": "1000",
            "lignes-0-id": ligne.pk,
            "lignes-0-facture": facture.pk,
            "lignes-0-designation": "Réécrite",
            "lignes-0-quantite": "99",
            "lignes-0-prix_unitaire_ht": "1",
            "lignes-0-taux_tva": "0",
            "lignes-0-ordre": "0",
        },
    )

    assert reponse.status_code == 302
    facture.refresh_from_db()
    ligne.refresh_from_db()
    assert facture.statut == Facture.Statut.PAYEE
    assert facture.client == client_facture
    assert facture.objet == ""
    assert (ligne.designation, ligne.quantite) == ("Prestation", Decimal("1.00"))


# --- Concurrence réelle (PostgreSQL uniquement) ------------------------------
#
# Tout ce qui précède tourne aussi bien sur SQLite, où `select_for_update` ne
# fait rien : ces tests-là valident la règle, jamais sa tenue sous charge. Le
# test ci-dessous est le seul à éprouver le VERROU, et il n'a de sens que sur
# le moteur de production. Le lancer :
#
#   TEST_POSTGRES=1 pytest apps/facturation/tests.py -q

NB_VALIDATIONS_SIMULTANEES = 8


@pytest.mark.django_db(transaction=True)
def test_la_numerotation_tient_sous_validations_simultanees():
    """Huit validations lancées au même instant produisent huit numéros
    distincts et contigus — aucun doublon, aucun trou.

    C'est LA garantie légale du cahier §4, et elle ne peut pas être vérifiée
    en séquentiel : sans verrou, deux transactions lisent le même compteur et
    attribuent le même numéro. `transaction=True` est indispensable — sans lui
    les données du test resteraient invisibles aux autres connexions."""
    import threading

    from django.db import connection, connections

    if connection.vendor != "postgresql":
        pytest.skip(
            "select_for_update est un no-op sur SQLite : le test passerait "
            "sans rien prouver. Relancer avec TEST_POSTGRES=1."
        )

    client = Client.objects.create(nom="Association X")
    factures = [_brouillon(client) for _ in range(NB_VALIDATIONS_SIMULTANEES)]

    # La barrière fait partir tout le monde ensemble : sans elle, les threads
    # s'égrènent et l'on retombe sur du séquentiel déguisé.
    barriere = threading.Barrier(NB_VALIDATIONS_SIMULTANEES)
    erreurs = []

    def valider(facture):
        try:
            barriere.wait(timeout=10)
            valider_facture(facture, date_emission=date(2026, 3, 1))
        except Exception as exc:  # noqa: BLE001 — on veut TOUTE erreur de thread
            erreurs.append(exc)
        finally:
            # Chaque thread a sa propre connexion : sans fermeture, elles
            # fuient et la base de test refuse de se laisser détruire.
            connections.close_all()

    threads = [threading.Thread(target=valider, args=(f,)) for f in factures]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not erreurs, f"validations en erreur : {erreurs}"

    numeros = sorted(Facture.objects.exclude(numero=None).values_list("numero", flat=True))
    attendus = [f"F2026-{i:04d}" for i in range(1, NB_VALIDATIONS_SIMULTANEES + 1)]
    assert numeros == attendus, "numérotation trouée ou dupliquée sous concurrence"


@pytest.mark.django_db(transaction=True)
def test_un_double_clic_simultane_n_emet_qu_une_fois():
    """Le même brouillon validé par deux requêtes au même instant : une seule
    émission, et le compteur n'avance que d'un cran. Le test séquentiel à
    instances périmées couvre la règle ; celui-ci éprouve le verrou de la
    facture elle-même, qui n'existe que sur PostgreSQL."""
    import threading

    from django.db import connection, connections

    if connection.vendor != "postgresql":
        pytest.skip("select_for_update est un no-op sur SQLite. Relancer avec TEST_POSTGRES=1.")

    brouillon = _brouillon(Client.objects.create(nom="Association X"))
    barriere = threading.Barrier(2)
    refus = []
    erreurs = []

    def valider():
        try:
            instance = Facture.objects.get(pk=brouillon.pk)
            barriere.wait(timeout=10)
            valider_facture(instance, date_emission=date(2026, 3, 1))
        except FactureDejaValidee as exc:
            refus.append(exc)
        except Exception as exc:  # noqa: BLE001 — on veut TOUTE erreur de thread
            erreurs.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=valider) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not erreurs, f"validations en erreur : {erreurs}"
    assert len(refus) == 1
    brouillon.refresh_from_db()
    assert brouillon.numero == "F2026-0001"
    assert CompteurFacture.objects.get(annee=2026).dernier == 1


# --- Duplication (FAC-1) -----------------------------------------------------


def test_dupliquer_une_facture_rend_un_brouillon_sans_identite_legale(client_facture):
    """Le point de vigilance : une copie ne rejoue pas le numéro. Reprendre
    celui de l'original créerait un doublon dans une série qui doit rester
    unique et continue (règle 4)."""
    origine = Facture.objects.create(client=client_facture, objet="Représentation")
    LigneFacture.objects.create(
        facture=origine, designation="Cachet", quantite=2, prix_unitaire_ht=Decimal("300")
    )
    valider_facture(origine, date_emission=date(2026, 3, 1))
    origine.refresh_from_db()

    copie = dupliquer_facture(origine)

    assert copie.pk != origine.pk
    assert copie.numero is None
    assert copie.statut == Facture.Statut.BROUILLON
    assert copie.date is None
    assert copie.date_validation is None
    # L'original n'est pas touché : c'est une pièce légale déjà émise.
    assert origine.numero == "F2026-0001"


def test_la_copie_reprend_les_lignes_et_leur_ordre(client_facture):
    origine = Facture.objects.create(client=client_facture, objet="Tournée")
    for rang, designation in enumerate(["Cachet", "Transport", "Repas"]):
        LigneFacture.objects.create(
            facture=origine,
            designation=designation,
            quantite=1,
            prix_unitaire_ht=Decimal("100"),
            ordre=rang,
        )

    copie = dupliquer_facture(origine)

    assert [ligne.designation for ligne in copie.lignes.all()] == [
        "Cachet",
        "Transport",
        "Repas",
    ]
    assert copie.client == origine.client
    assert copie.objet == origine.objet


def test_la_copie_recoit_son_propre_numero_a_sa_validation(client_facture):
    """La série reste continue et sans trou malgré la duplication."""
    origine = _brouillon(client_facture)
    valider_facture(origine, date_emission=date(2026, 3, 1))

    copie = dupliquer_facture(origine)
    valider_facture(copie, date_emission=date(2026, 3, 1))

    origine.refresh_from_db()
    copie.refresh_from_db()
    assert [origine.numero, copie.numero] == ["F2026-0001", "F2026-0002"]


def test_dupliquer_un_avoir_ne_le_relie_pas_a_la_facture_annulee(client_facture):
    """Un avoir ne s'annule pas deux fois : la copie est détachée."""
    origine = _brouillon(client_facture)
    valider_facture(origine, date_emission=date(2026, 3, 1))
    avoir = creer_avoir(origine)

    copie = dupliquer_facture(avoir)

    assert copie.type_piece == Facture.TypePiece.AVOIR
    assert copie.avoir_de is None


def test_dupliquer_un_brouillon_est_possible(client_facture):
    """Rien n'oblige à valider avant de dupliquer : préparer deux pièces
    voisines est un usage légitime."""
    brouillon = Facture.objects.create(client=client_facture, objet="Modèle")

    copie = dupliquer_facture(brouillon)

    assert copie.statut == Facture.Statut.BROUILLON
    assert copie.objet == "Modèle"
