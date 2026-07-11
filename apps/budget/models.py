"""Modèles du domaine « Budget » (cf. cahier §5).

- `Saison` : exercice / année associative.
- `Categorie` : poste analytique (pour le bilan annuel par catégorie).
- `Adhesion` : relie un `Membre` à une `Saison` (statut, montant attendu et versé).
- `Transaction` : recette ou dépense, prévue ou réalisée (budget prévisionnel vs
  réel), avec catégorie et lien optionnel vers une facture ou une adhésion.
- `SoldeTresorerie` : solde en banque de référence (singleton), repère de
  gestion à rapprocher des comptes réels — pas une source de vérité comptable.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import Horodatage
from apps.common.stockage import StockagePrive


class Saison(models.Model):
    """Exercice associatif (ex. « 2025-2026 »)."""

    nom = models.CharField(max_length=50, unique=True)
    date_debut = models.DateField("début", null=True, blank=True)
    date_fin = models.DateField("fin", null=True, blank=True)

    class Meta:
        verbose_name = "saison"
        verbose_name_plural = "saisons"
        ordering = ["-date_debut", "-nom"]

    def __str__(self) -> str:
        return self.nom


class Categorie(models.Model):
    """Poste analytique d'une transaction (pour le bilan par catégorie)."""

    nom = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "catégorie"
        verbose_name_plural = "catégories"
        ordering = ["nom"]

    def __str__(self) -> str:
        return self.nom


class Adhesion(models.Model):
    """Adhésion d'un membre pour une saison donnée."""

    class Statut(models.TextChoices):
        PAYEE = "payee", "Payé"
        EXONEREE = "exoneree", "Exonéré"
        EN_ATTENTE = "en_attente", "En attente"

    membre = models.ForeignKey("coeur.Membre", on_delete=models.PROTECT, related_name="adhesions")
    saison = models.ForeignKey(Saison, on_delete=models.PROTECT, related_name="adhesions")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.EN_ATTENTE)
    montant_attendu = models.DecimalField(
        "montant attendu", max_digits=8, decimal_places=2, default=0
    )
    montant_verse = models.DecimalField("montant versé", max_digits=8, decimal_places=2, default=0)
    date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "adhésion"
        verbose_name_plural = "adhésions"
        ordering = ["-saison__date_debut", "membre"]
        constraints = [
            models.UniqueConstraint(
                fields=["membre", "saison"],
                name="adhesion_unique_membre_saison",
            )
        ]

    def __str__(self) -> str:
        return f"{self.membre} — {self.saison}"

    @property
    def a_jour(self) -> bool:
        """Vrai si l'adhésion est réglée ou exonérée (droit de vote éventuel)."""
        return self.statut in {self.Statut.PAYEE, self.Statut.EXONEREE}


class Transaction(Horodatage):
    """Mouvement financier : recette ou dépense, prévu ou réalisé."""

    class TypeFlux(models.TextChoices):
        RECETTE = "recette", "Recette"
        DEPENSE = "depense", "Dépense"

    class Statut(models.TextChoices):
        PREVU = "prevu", "Prévu"
        REALISE = "realise", "Réalisé"

    type_flux = models.CharField("type", max_length=8, choices=TypeFlux.choices)
    statut = models.CharField(max_length=8, choices=Statut.choices, default=Statut.PREVU)
    libelle = models.CharField("libellé", max_length=200)
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()

    categorie = models.ForeignKey(
        Categorie,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    saison = models.ForeignKey(
        Saison,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    facture = models.ForeignKey(
        "facturation.Facture",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    adhesion = models.ForeignKey(
        Adhesion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )

    class Meta:
        verbose_name = "transaction"
        verbose_name_plural = "transactions"
        ordering = ["-date", "-id"]

    def __str__(self) -> str:
        return f"{self.libelle} ({self.get_type_flux_display()} {self.montant})"


class CompteurRecu(models.Model):
    """Compteur séquentiel de numéros de reçu fiscal, par année.

    Même principe que `CompteurFacture` : une ligne par année, `dernier`
    incrémenté sous verrou à l'émission pour une série continue sans trou
    (contrainte légale — cf. budget/services.py).
    """

    annee = models.PositiveIntegerField("année", unique=True)
    dernier = models.PositiveIntegerField("dernier numéro attribué", default=0)

    class Meta:
        verbose_name = "compteur de reçus fiscaux"
        verbose_name_plural = "compteurs de reçus fiscaux"
        ordering = ["-annee"]

    def __str__(self) -> str:
        return f"{self.annee} → {self.dernier}"


class RecuFiscal(Horodatage):
    """Reçu fiscal (Cerfa n° 11580) émis pour un don ou une cotisation.

    Document LÉGAL : numéro séquentiel sans trou attribué à l'émission, et
    **snapshot** des données (donateur, montant, date) — le reçu ne doit pas
    changer si l'enregistrement source est modifié ensuite. Le PDF est rendu
    paresseusement (WeasyPrint) au premier téléchargement puis mis en cache
    dans le stockage privé.
    """

    class TypeVersement(models.TextChoices):
        DON = "don", "Don"
        COTISATION = "cotisation", "Cotisation"

    class Forme(models.TextChoices):
        NUMERAIRE = "numeraire", "Numéraire"
        CHEQUE = "cheque", "Chèque"
        VIREMENT = "virement", "Virement"
        AUTRE = "autre", "Autre"

    numero = models.CharField("numéro", max_length=20, unique=True)
    date_emission = models.DateField("date d'émission")

    type_versement = models.CharField(
        "type de versement", max_length=12, choices=TypeVersement.choices
    )
    forme = models.CharField(
        "forme du don", max_length=12, choices=Forme.choices, default=Forme.NUMERAIRE
    )
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    date_versement = models.DateField("date du versement")

    # Snapshot du donateur (figé à l'émission).
    donateur_nom = models.CharField("nom du donateur", max_length=200)
    donateur_adresse = models.CharField("adresse", max_length=255, blank=True)
    donateur_code_postal = models.CharField("code postal", max_length=16, blank=True)
    donateur_ville = models.CharField("ville", max_length=120, blank=True)

    # Rattachements optionnels (traçabilité comptable ; null si saisie manuelle).
    membre = models.ForeignKey(
        "coeur.Membre",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recus_fiscaux",
        verbose_name="membre concerné",
    )
    adhesion = models.ForeignKey(
        Adhesion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recus_fiscaux",
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recus_fiscaux",
        verbose_name="transaction (don)",
    )

    # PDF Cerfa mis en cache au 1er téléchargement (stockage privé, hors web).
    fichier = models.FileField(
        "PDF du reçu", upload_to="recus/%Y/", storage=StockagePrive, blank=True
    )
    emis_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recus_emis",
        verbose_name="émis par",
    )
    # Signature optionnelle ; à défaut, le Cerfa retombe sur le signataire texte
    # des paramètres de l'association.
    signataire = models.ForeignKey(
        "coeur.Signataire",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="signataire",
    )

    class Meta:
        verbose_name = "reçu fiscal"
        verbose_name_plural = "reçus fiscaux"
        ordering = ["-date_emission", "-id"]

    def __str__(self) -> str:
        return f"Reçu {self.numero} — {self.donateur_nom}"


class SoldeTresorerie(models.Model):
    """Solde de trésorerie de référence — **singleton** (pk=1).

    Ce que le trésorier constate en banque à un instant donné (dernier pointage).
    C'est un **repère de gestion et de prévision**, volontairement libre et non
    lié aux saisons : la vérité reste le relevé bancaire, que l'on rapproche
    après coup. Sert de point de départ à la trésorerie prévisionnelle
    (cf. `services.tresorerie`)."""

    montant = models.DecimalField("solde en banque", max_digits=12, decimal_places=2, default=0)
    date_pointage = models.DateField("date du pointage", null=True, blank=True)
    note = models.CharField("note", max_length=200, blank=True)

    class Meta:
        verbose_name = "solde de trésorerie"
        verbose_name_plural = "solde de trésorerie"

    def __str__(self) -> str:
        return f"{self.montant} € au {self.date_pointage or '—'}"

    def save(self, *args, **kwargs):
        """Force une instance unique (singleton, pk=1)."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def charger(cls) -> SoldeTresorerie:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
