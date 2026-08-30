"""Adresse publique d'un membre : `/@prenom-nom` au lieu de `/membres/<id>/`.

Trois temps obligés : on ne peut pas ajouter d'un coup une colonne UNIQUE non
vide sur une table peuplée. Ajout à blanc, remplissage, puis pose de l'unicité.
"""

from django.db import migrations, models
from django.utils.text import slugify

LONGUEUR_MAX_SLUG = 150


def remplir_slugs(apps, schema_editor):
    """Slug des fiches déjà en base, dans l'ordre de création.

    Même règle que `apps.coeur.services.slug_membre_unique` — recopiée et non
    importée : une migration doit rester figée dans le temps, insensible aux
    évolutions ultérieures du service."""
    Membre = apps.get_model("coeur", "Membre")
    pris = set()
    for membre in Membre.objects.order_by("pk"):
        base = (slugify(f"{membre.prenom} {membre.nom}".strip()) or "membre")[:LONGUEUR_MAX_SLUG]
        candidat = base
        rang = 1
        while candidat in pris:
            rang += 1
            candidat = f"{base}-{rang}"
        pris.add(candidat)
        membre.slug = candidat
        membre.save(update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [
        ("coeur", "0012_alter_lienreseau_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="membre",
            name="slug",
            field=models.SlugField(
                blank=True,
                # `SlugField` est indexé par défaut. Poser cet index ici puis
                # l'unicité plus bas ferait entrer en collision les deux index
                # `..._like` que PostgreSQL nomme à l'identique. On ajoute donc
                # la colonne nue : c'est `AlterField` qui crée l'index, une fois.
                db_index=False,
                default="",
                help_text=(
                    "Fin de l'adresse publique : /@prenom-nom. Rempli tout seul à la "
                    "création et volontairement figé ensuite — le modifier casse les "
                    "liens déjà partagés."
                ),
                max_length=160,
                verbose_name="adresse de la page",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(remplir_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="membre",
            name="slug",
            field=models.SlugField(
                blank=True,
                help_text=(
                    "Fin de l'adresse publique : /@prenom-nom. Rempli tout seul à la "
                    "création et volontairement figé ensuite — le modifier casse les "
                    "liens déjà partagés."
                ),
                max_length=160,
                unique=True,
                verbose_name="adresse de la page",
            ),
        ),
    ]
