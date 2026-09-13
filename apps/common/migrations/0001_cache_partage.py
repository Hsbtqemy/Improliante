"""La table du cache partagé — socle de la limitation de débit (PUB-01).

Le cache par défaut de Django vit dans la MÉMOIRE DU PROCESSUS. Gunicorn en
lance plusieurs : chaque worker aurait alors son propre compteur, et une limite
de cinq envois par heure en autoriserait cinq PAR WORKER — sans que rien ne le
dise, et sans qu'aucun test puisse le voir, la suite ne tournant que dans un
seul processus.

Une table de base donne un compteur partagé sans ajouter de service à
administrer. C'est ce que Redis ferait mieux, et ce qu'il faudra si le trafic
change ; à l'échelle d'une association, une écriture par envoi de formulaire
n'est pas un sujet.
"""

from django.core.management import call_command
from django.db import migrations

TABLE = "cache_partage"


def creer(apps, schema_editor):
    call_command(
        "createcachetable",
        TABLE,
        database=schema_editor.connection.alias,
        verbosity=0,
    )


def supprimer(apps, schema_editor):
    schema_editor.execute(f"DROP TABLE IF EXISTS {TABLE}")


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [migrations.RunPython(creer, supprimer)]
