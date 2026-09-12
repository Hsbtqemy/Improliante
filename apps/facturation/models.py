"""Modèles du domaine « Facturation » (cf. cahier §4).

Client, Devis (transformable en facture) et Facture, chacun avec ses lignes
(désignation / quantité / prix unitaire / TVA) → totaux HT / TVA / TTC calculés.

⚠️ Numérotation des factures (contrainte LÉGALE) : séquentielle, continue, sans
trou, attribuée **à la validation** (pas au brouillon). Le champ `numero` est
unique et reste NULL tant que la facture est en brouillon. L'ALLOCATION ATOMIQUE
du numéro (transaction + verrou) n'est pas implémentée ici : c'est une zone à
risque à traiter en test-first, dans un service dédié (`facturation/services.py`).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.common.models import Horodatage
from apps.common.stockage import StockagePrive

CENT = Decimal("0.01")


class Client(Horodatage):
    """Destinataire d'un devis ou d'une facture (structure ou particulier)."""

    nom = models.CharField(max_length=200)
    adresse = models.TextField(blank=True)
    code_postal = models.CharField("code postal", max_length=16, blank=True)
    ville = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    telephone = models.CharField("téléphone", max_length=32, blank=True)
    siret = models.CharField("SIRET", max_length=20, blank=True)
    numero_tva = models.CharField("n° TVA intracommunautaire", max_length=20, blank=True)

    class Meta:
        verbose_name = "client"
        verbose_name_plural = "clients"
        ordering = ["nom"]

    def __str__(self) -> str:
        return self.nom


class AvecTotaux(models.Model):
    """Mixin abstrait : totaux HT / TVA / TTC calculés à partir de `self.lignes`."""

    class Meta:
        abstract = True

    @property
    def total_ht(self) -> Decimal:
        return sum((ligne.total_ht for ligne in self.lignes.all()), Decimal("0.00"))

    @property
    def total_tva(self) -> Decimal:
        return sum((ligne.montant_tva for ligne in self.lignes.all()), Decimal("0.00"))

    @property
    def total_ttc(self) -> Decimal:
        return self.total_ht + self.total_tva


class LigneCommerciale(models.Model):
    """Base abstraite d'une ligne de devis ou de facture."""

    designation = models.CharField("désignation", max_length=300)
    quantite = models.DecimalField("quantité", max_digits=10, decimal_places=2, default=1)
    prix_unitaire_ht = models.DecimalField(
        "prix unitaire HT", max_digits=10, decimal_places=2, default=0
    )
    taux_tva = models.DecimalField("taux de TVA (%)", max_digits=5, decimal_places=2, default=0)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        constraints = [
            # Un taux hors de [0, 100] ne se rattrape pas à la lecture : il fausse
            # la TVA de la pièce. La base le refuse, quel que soit le chemin —
            # formulaire, admin ou shell. Quantité et prix, eux, restent libres de
            # signe : une remise est une ligne négative légitime, et c'est le
            # SIGNE DE LA PIÈCE que le service contrôle à l'émission.
            models.CheckConstraint(
                condition=models.Q(taux_tva__gte=0) & models.Q(taux_tva__lte=100),
                name="%(app_label)s_%(class)s_taux_tva_entre_0_et_100",
                # Le `%%` n'est pas une coquille : Django interpole ce message
                # (`%(name)s`), et un `%` seul y lève « incomplete format » —
                # une erreur 500 à la place du message attendu.
                violation_error_message="Le taux de TVA doit être compris entre 0 et 100 %%.",
            ),
        ]

    @property
    def total_ht(self) -> Decimal:
        # Arrondi au centime ligne par ligne, AVANT la somme, et au pair le plus
        # proche (défaut de `quantize` : 0,125 → 0,12, et non 0,13). Convention
        # retenue le 12 sept. 2026 — aucun texte n'impose l'arrondi commercial.
        # `front/static/js/facturation.js` la reproduit à l'identique, pour que
        # l'écran de saisie annonce le montant qui sera réellement émis.
        return (self.quantite * self.prix_unitaire_ht).quantize(CENT)

    @property
    def montant_tva(self) -> Decimal:
        return (self.total_ht * self.taux_tva / Decimal("100")).quantize(CENT)

    @property
    def total_ttc(self) -> Decimal:
        return self.total_ht + self.montant_tva

    def __str__(self) -> str:
        return self.designation


class Devis(AvecTotaux, Horodatage):
    """Devis adressé à un client, transformable en facture."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        ENVOYE = "envoye", "Envoyé"
        ACCEPTE = "accepte", "Accepté"
        REFUSE = "refuse", "Refusé"
        FACTURE = "facture", "Facturé"

    numero = models.CharField("numéro", max_length=20, blank=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="devis")
    objet = models.CharField(max_length=200, blank=True)
    date = models.DateField()
    date_validite = models.DateField("valable jusqu'au", null=True, blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON)
    conditions = models.TextField("conditions / mentions", blank=True)
    signataire = models.ForeignKey(
        "coeur.Signataire",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="signataire",
    )

    class Meta:
        verbose_name = "devis"
        verbose_name_plural = "devis"
        ordering = ["-date", "-id"]

    def __str__(self) -> str:
        return self.numero or f"Devis (brouillon #{self.pk})"


class LigneDevis(LigneCommerciale):
    devis = models.ForeignKey(Devis, on_delete=models.CASCADE, related_name="lignes")

    class Meta(LigneCommerciale.Meta):
        verbose_name = "ligne de devis"
        verbose_name_plural = "lignes"
        ordering = ["ordre", "id"]


class Facture(AvecTotaux, Horodatage):
    """Facture émise pour un client (numéro attribué à la validation)."""

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        VALIDEE = "validee", "Validée"
        PAYEE = "payee", "Payée"
        ANNULEE = "annulee", "Annulée"

    class TypePiece(models.TextChoices):
        FACTURE = "facture", "Facture"
        AVOIR = "avoir", "Avoir"

    # NULL tant que brouillon ; attribué (unique, sans trou) à la validation.
    numero = models.CharField("numéro", max_length=20, unique=True, null=True, blank=True)
    type_piece = models.CharField(
        "type de pièce", max_length=8, choices=TypePiece.choices, default=TypePiece.FACTURE
    )
    # Un avoir annule (tout ou partie de) la facture qu'il référence.
    avoir_de = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="avoirs",
        verbose_name="avoir sur la facture",
    )
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="factures")
    devis_origine = models.ForeignKey(
        Devis,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="factures",
        verbose_name="devis d'origine",
    )
    objet = models.CharField(max_length=200, blank=True)
    # Émise à la validation (comme le numéro) : nulle tant que la facture est brouillon.
    date = models.DateField("date d'émission", null=True, blank=True)
    date_echeance = models.DateField("échéance", null=True, blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON)
    date_validation = models.DateTimeField("validée le", null=True, blank=True)
    mentions_legales = models.TextField("mentions légales", blank=True)

    # Signature optionnelle (apposée sur le PDF si renseignée).
    signataire = models.ForeignKey(
        "coeur.Signataire",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="signataire",
    )

    # PDF rendu dès la validation, puis conservé (stockage privé, hors racine
    # web — document légal immuable). Repli : rendu au 1er téléchargement si le
    # moteur PDF manquait à l'émission (cf. services.valider_facture).
    fichier = models.FileField(
        "PDF de la facture", upload_to="factures/%Y/", storage=StockagePrive, blank=True
    )

    # Ce que la pièce disait d'elle-même à l'émission : émetteur, client, lignes
    # et totaux. Le PDF en est l'archive ; ceci permet de le reconstruire à
    # l'identique s'il disparaît, plutôt que de le recalculer avec les données du
    # jour (cf. apps/common/instantane.py).
    instantane = models.JSONField("instantané d'émission", default=dict, blank=True, editable=False)

    class Meta:
        verbose_name = "facture"
        verbose_name_plural = "factures"
        ordering = ["-date", "-id"]

    def __str__(self) -> str:
        libelle = "Avoir" if self.type_piece == self.TypePiece.AVOIR else "Facture"
        return self.numero or f"{libelle} (brouillon #{self.pk})"


class LigneFacture(LigneCommerciale):
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name="lignes")

    class Meta(LigneCommerciale.Meta):
        verbose_name = "ligne de facture"
        verbose_name_plural = "lignes"
        ordering = ["ordre", "id"]


class CompteurFacture(models.Model):
    """Compteur séquentiel de numéros de facture, par année.

    Une ligne par année ; `dernier` est incrémenté sous verrou
    (`select_for_update`) à la validation d'une facture, pour garantir une
    numérotation continue et sans trou (cf. facturation/services.py).
    """

    annee = models.PositiveIntegerField("année", unique=True)
    dernier = models.PositiveIntegerField("dernier numéro attribué", default=0)

    class Meta:
        verbose_name = "compteur de factures"
        verbose_name_plural = "compteurs de factures"
        ordering = ["-annee"]

    def __str__(self) -> str:
        return f"{self.annee} → {self.dernier}"
