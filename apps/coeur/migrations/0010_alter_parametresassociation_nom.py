from django.db import migrations, models


def nommer_l_association(apps, schema_editor):
    """`AlterField` ne pose le défaut que sur les lignes FUTURES : une base déjà
    installée garderait son nom vide, et la page d'accueil son titre amputé.
    On ne touche que les enregistrements réellement vides."""
    Parametres = apps.get_model("coeur", "ParametresAssociation")
    Parametres.objects.filter(nom="").update(nom="L'Improliante")


class Migration(migrations.Migration):
    dependencies = [
        ("coeur", "0009_parametresassociation_accroche_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="parametresassociation",
            name="nom",
            field=models.CharField(default="L'Improliante", max_length=200),
        ),
        migrations.RunPython(nommer_l_association, migrations.RunPython.noop),
    ]
