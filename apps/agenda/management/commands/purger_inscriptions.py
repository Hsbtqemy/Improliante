"""Purge les inscriptions des événements passés (RGPD).

Une feuille d'inscription collecte des noms et des adresses e-mail. Rien ne
justifie de les garder une fois la représentation jouée : le cahier §15 range
la billetterie en v3, mais la minimisation des données ne se remet pas à plus
tard. Cette commande est le geste que la conservation exige.

Volontairement MANUELLE : la planifier suppose un cron sur le serveur, donc le
déploiement (DEP-1). En attendant, elle se lance à la main sans rien attendre :

    python manage.py purger_inscriptions --jours 90
    python manage.py purger_inscriptions --jours 90 --pour-de-vrai
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.agenda.models import Inscription

JOURS_PAR_DEFAUT = 90


class Command(BaseCommand):
    help = "Supprime les inscriptions des événements terminés depuis N jours."

    def add_arguments(self, parser):
        parser.add_argument(
            "--jours",
            type=int,
            default=JOURS_PAR_DEFAUT,
            help=f"Ancienneté au-delà de laquelle purger (défaut : {JOURS_PAR_DEFAUT}).",
        )
        parser.add_argument(
            "--pour-de-vrai",
            action="store_true",
            help="Sans ce drapeau, la commande ne fait que compter.",
        )

    def handle(self, *args, **options):
        jours = options["jours"]
        limite = timezone.now() - timezone.timedelta(days=jours)
        # La date de l'ÉVÉNEMENT fait foi, pas celle de la réservation : une
        # place prise un an à l'avance ne doit pas s'effacer avant la soirée.
        concernees = Inscription.objects.filter(evenement__date_debut__lt=limite)
        nombre = concernees.count()

        if not options["pour_de_vrai"]:
            self.stdout.write(
                f"{nombre} inscription(s) à purger (événements antérieurs au "
                f"{limite:%d/%m/%Y}). Relancer avec --pour-de-vrai pour supprimer."
            )
            return

        concernees.delete()
        self.stdout.write(self.style.SUCCESS(f"{nombre} inscription(s) supprimée(s)."))
