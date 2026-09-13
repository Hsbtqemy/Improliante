"""Traite les images déjà en base : réduction et vignette.

À lancer UNE FOIS après la mise en service du traitement (lot 17) — les médias
téléversés avant n'ont ni dimensions ni vignette, et le traitement ne se
déclenche qu'à l'enregistrement.

    python manage.py preparer_medias
    python manage.py preparer_medias --tout   # retraite même ceux déjà traités
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.medias.models import Media
from apps.medias.services import preparer_media


class Command(BaseCommand):
    help = "Réduit les images déjà téléversées et produit leurs vignettes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tout",
            action="store_true",
            help="Retraite aussi les médias qui portent déjà des dimensions.",
        )

    def handle(self, *args, **options):
        medias = Media.objects.filter(type_media=Media.TypeMedia.IMAGE).exclude(fichier="")
        if not options["tout"]:
            medias = medias.filter(largeur__isnull=True)
        traites = ignores = 0
        for media in medias.iterator():
            if options["tout"]:
                media.largeur = None  # force la reprise
            if preparer_media(media):
                media.save(
                    update_fields=[
                        "largeur",
                        "hauteur",
                        "vignette",
                        "vignette_largeur",
                        "vignette_hauteur",
                    ]
                )
                traites += 1
            else:
                # Fichier absent, format laissé intact (GIF animé), ou déjà fait.
                ignores += 1
        self.stdout.write(f"{traites} média(s) traité(s), {ignores} ignoré(s).")
