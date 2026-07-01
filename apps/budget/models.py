"""Modèles du domaine « Budget » (cf. cahier §5).

- `Saison` : exercice / année associative.
- `Categorie` : poste analytique (pour le bilan annuel par catégorie).
- `Adhesion` : relie un `Membre` à une `Saison` (statut, montant attendu et versé).
- `Transaction` : recette ou dépense, prévue ou réalisée (budget prévisionnel vs
  réel), avec catégorie et lien optionnel vers une facture ou une adhésion.
"""

from __future__ import annotations

from django.db import models

from apps.common.models import Horodatage


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

    membre = models.ForeignKey(
        "coeur.Membre", on_delete=models.PROTECT, related_name="adhesions"
    )
    saison = models.ForeignKey(
        Saison, on_delete=models.PROTECT, related_name="adhesions"
    )
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.EN_ATTENTE
    )
    montant_attendu = models.DecimalField(
        "montant attendu", max_digits=8, decimal_places=2, default=0
    )
    montant_verse = models.DecimalField(
        "montant versé", max_digits=8, decimal_places=2, default=0
    )
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
