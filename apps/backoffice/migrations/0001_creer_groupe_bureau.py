"""Crée le groupe « Bureau » (rôle d'administration de l'association).

Le nom est répété en dur ici volontairement : une migration doit rester
autonome et ne pas dépendre d'une constante applicative susceptible d'évoluer
(cf. apps.coeur.roles.NOM_GROUPE_BUREAU pour l'usage côté code).
"""

from __future__ import annotations

from django.db import migrations

NOM_GROUPE_BUREAU = "Bureau"


def creer_groupe(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=NOM_GROUPE_BUREAU)


def supprimer_groupe(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=NOM_GROUPE_BUREAU).delete()


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(creer_groupe, supprimer_groupe),
    ]
