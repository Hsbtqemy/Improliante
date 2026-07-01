"""Modèles du domaine « Gouvernance » (cf. cahier §8).

Carnet de sujets, réunions / AG, résolutions, pouvoirs, présences, et un objet
de configuration `ParametresGouvernance` (aucune règle statutaire codée en dur).

⚠️ Zone à risque : le **calcul du quorum** et de l'**adoption des résolutions**
(seuils de majorité, base des exprimés, contrôle du nombre de pouvoirs) n'est PAS
implémenté ici. Ces règles statutaires doivent être calculées dans un service
dédié, écrit en test-first, en lisant `ParametresGouvernance`. Les modèles ne
stockent que les données brutes + quelques compteurs factuels.

Règle de cohérence (§8.4) : le droit de vote est figé à la date de l'AG — on le
capture dans `Presence.peut_voter` au moment de la tenue, sans recalcul rétroactif.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.common.models import Horodatage


class ParametresGouvernance(models.Model):
    """Configuration statutaire éditable (unique instance)."""

    vote_reserve_aux_membres_a_jour = models.BooleanField(
        "vote réservé aux membres à jour de cotisation",
        default=True,
        help_text="Valeur par défaut prudente — à ajuster selon les statuts.",
    )
    max_pouvoirs_par_personne = models.PositiveIntegerField(
        "nombre max de pouvoirs par personne", default=2
    )
    # Ratios exprimés entre 0 et 1 (ex. 0.333 = 1/3, 0.5 = 1/2, 0.667 = 2/3).
    quorum_ag_ordinaire = models.DecimalField(
        "quorum AG ordinaire", max_digits=4, decimal_places=3, default=Decimal("0.333")
    )
    quorum_ag_extraordinaire = models.DecimalField(
        "quorum AG extraordinaire", max_digits=4, decimal_places=3, default=Decimal("0.500")
    )
    majorite_simple = models.DecimalField(
        "majorité simple", max_digits=4, decimal_places=3, default=Decimal("0.500")
    )
    majorite_qualifiee = models.DecimalField(
        "majorité qualifiée", max_digits=4, decimal_places=3, default=Decimal("0.667")
    )

    class Meta:
        verbose_name = "paramètres de gouvernance"
        verbose_name_plural = "paramètres de gouvernance"

    def __str__(self) -> str:
        return "Paramètres de gouvernance"

    def save(self, *args, **kwargs):
        """Force une instance unique (singleton, pk=1)."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> ParametresGouvernance:
        """Retourne l'unique instance, en la créant au besoin."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Reunion(Horodatage):
    """Réunion de bureau ou assemblée générale."""

    class TypeReunion(models.TextChoices):
        AG_ORDINAIRE = "ag_ordinaire", "AG ordinaire"
        AG_EXTRAORDINAIRE = "ag_extraordinaire", "AG extraordinaire"
        BUREAU = "bureau", "Réunion de bureau"

    class Statut(models.TextChoices):
        PREPARATION = "preparation", "Préparation"
        CONVOQUEE = "convoquee", "Convoquée"
        TENUE = "tenue", "Tenue"
        ARCHIVEE = "archivee", "Archivée"

    titre = models.CharField(max_length=200)
    type_reunion = models.CharField("type", max_length=18, choices=TypeReunion.choices)
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.PREPARATION)
    date = models.DateTimeField(null=True, blank=True)
    lieu_texte = models.CharField("lieu", max_length=255, blank=True)

    convocation_texte = models.TextField("texte de convocation", blank=True)
    date_convocation = models.DateField("date d'envoi de la convocation", null=True, blank=True)

    compte_rendu = models.ForeignKey(
        "documents.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reunions_pv",
        verbose_name="compte-rendu (PV)",
    )
    documents = models.ManyToManyField(
        "documents.Document",
        blank=True,
        related_name="reunions",
        verbose_name="documents joints",
    )
    evenement = models.ForeignKey(
        "agenda.Evenement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reunions",
        verbose_name="événement agenda",
    )

    class Meta:
        verbose_name = "réunion / AG"
        verbose_name_plural = "réunions / AG"
        ordering = ["-date", "-id"]

    def __str__(self) -> str:
        return self.titre

    @property
    def nb_presents(self) -> int:
        return self.presences.filter(statut=Presence.Statut.PRESENT).count()

    @property
    def nb_representes(self) -> int:
        return self.presences.filter(statut=Presence.Statut.REPRESENTE).count()

    @property
    def nb_pouvoirs(self) -> int:
        return self.pouvoirs.count()


class Sujet(Horodatage):
    """Sujet du carnet (continu), pouvant être porté à l'ordre du jour d'une réunion."""

    class Statut(models.TextChoices):
        PROPOSE = "propose", "Proposé"
        OUVERT = "ouvert", "Ouvert"
        ORDRE_DU_JOUR = "ordre_du_jour", "À l'ordre du jour"
        TRAITE = "traite", "Traité"
        REPORTE = "reporte", "Reporté"
        REFUSE = "refuse", "Refusé"

    class Priorite(models.TextChoices):
        BASSE = "basse", "Basse"
        NORMALE = "normale", "Normale"
        HAUTE = "haute", "Haute"

    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    propose_par = models.ForeignKey(
        "coeur.Membre",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sujets_proposes",
        verbose_name="proposé par",
    )
    statut = models.CharField(max_length=14, choices=Statut.choices, default=Statut.PROPOSE)
    priorite = models.CharField("priorité", max_length=8, choices=Priorite.choices, default=Priorite.NORMALE)
    categorie = models.CharField("catégorie", max_length=120, blank=True)
    motif_refus = models.TextField("motif de refus", blank=True)

    documents = models.ManyToManyField(
        "documents.Document", blank=True, related_name="sujets", verbose_name="documents liés"
    )
    reunion = models.ForeignKey(
        Reunion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sujets",
        verbose_name="réunion (ordre du jour)",
    )
    ordre_du_jour = models.PositiveIntegerField("position à l'ordre du jour", default=0)
    fusionne_dans = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sujets_fusionnes",
        verbose_name="fusionné dans",
    )
    date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "sujet"
        verbose_name_plural = "sujets"
        ordering = ["-priorite", "-id"]

    def __str__(self) -> str:
        return self.titre


class Resolution(Horodatage):
    """Résolution soumise au vote lors d'une réunion (résultat calculé ailleurs)."""

    class TypeMajorite(models.TextChoices):
        SIMPLE = "simple", "Majorité simple"
        QUALIFIEE = "qualifiee", "Majorité qualifiée"
        UNANIMITE = "unanimite", "Unanimité"

    reunion = models.ForeignKey(Reunion, on_delete=models.CASCADE, related_name="resolutions")
    sujet = models.ForeignKey(
        Sujet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolutions",
    )
    intitule = models.CharField("intitulé", max_length=300)
    texte = models.TextField(blank=True)
    type_majorite = models.CharField(
        "type de majorité", max_length=10, choices=TypeMajorite.choices, default=TypeMajorite.SIMPLE
    )
    nombre_pour = models.PositiveIntegerField("pour", default=0)
    nombre_contre = models.PositiveIntegerField("contre", default=0)
    nombre_abstention = models.PositiveIntegerField("abstention", default=0)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "résolution"
        verbose_name_plural = "résolutions"
        ordering = ["ordre", "id"]

    def __str__(self) -> str:
        return self.intitule


class Pouvoir(models.Model):
    """Procuration d'un membre absent (mandant) à un membre présent (mandataire)."""

    reunion = models.ForeignKey(Reunion, on_delete=models.CASCADE, related_name="pouvoirs")
    mandant = models.ForeignKey(
        "coeur.Membre", on_delete=models.PROTECT, related_name="pouvoirs_donnes", verbose_name="mandant (absent)"
    )
    mandataire = models.ForeignKey(
        "coeur.Membre", on_delete=models.PROTECT, related_name="pouvoirs_recus", verbose_name="mandataire (présent)"
    )

    class Meta:
        verbose_name = "pouvoir"
        verbose_name_plural = "pouvoirs"
        constraints = [
            models.UniqueConstraint(
                fields=["reunion", "mandant"], name="pouvoir_unique_par_mandant"
            ),
            models.CheckConstraint(
                condition=~models.Q(mandant=models.F("mandataire")),
                name="pouvoir_mandant_distinct_mandataire",
                violation_error_message="Le mandant et le mandataire doivent être différents.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.mandant} → {self.mandataire}"


class Presence(models.Model):
    """Présence d'un membre à une réunion (droit de vote figé à la tenue)."""

    class Statut(models.TextChoices):
        PRESENT = "present", "Présent"
        EXCUSE = "excuse", "Excusé"
        REPRESENTE = "represente", "Représenté"
        ABSENT = "absent", "Absent"

    reunion = models.ForeignKey(Reunion, on_delete=models.CASCADE, related_name="presences")
    membre = models.ForeignKey("coeur.Membre", on_delete=models.PROTECT, related_name="presences")
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.ABSENT)
    peut_voter = models.BooleanField(
        "droit de vote",
        default=False,
        help_text="Figé à la date de l'AG (ne pas recalculer rétroactivement).",
    )

    class Meta:
        verbose_name = "présence"
        verbose_name_plural = "présences"
        constraints = [
            models.UniqueConstraint(
                fields=["reunion", "membre"], name="presence_unique_par_membre"
            )
        ]

    def __str__(self) -> str:
        return f"{self.membre} — {self.get_statut_display()}"
