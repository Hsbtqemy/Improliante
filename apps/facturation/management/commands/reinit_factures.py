"""Réinitialise la numérotation des factures — RÉSERVÉ AUX DONNÉES DE TEST.

Supprime toutes les factures et remet les compteurs à zéro. Refuse de s'exécuter
si `DEBUG=False` : en production, la numérotation est continue et ne se remet
JAMAIS à zéro (contrainte légale, cf. cahier §4).
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.facturation.models import CompteurFacture, Facture


class Command(BaseCommand):
    help = (
        "Supprime toutes les factures et remet la numérotation à zéro "
        "(données de TEST uniquement, jamais en production)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Confirme la suppression (opération destructive).",
        )

    def handle(self, *args, **options) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "Refusé : DEBUG=False. La numérotation des factures ne se "
                "réinitialise jamais en production (continuité légale)."
            )
        if not options["yes"]:
            raise CommandError("Opération destructive : ajoutez --yes pour confirmer.")

        nb_factures = Facture.objects.count()
        nb_compteurs = CompteurFacture.objects.count()
        Facture.objects.all().delete()
        CompteurFacture.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"{nb_factures} facture(s) et {nb_compteurs} compteur(s) supprimés. "
                "La numérotation repartira à 0001."
            )
        )
