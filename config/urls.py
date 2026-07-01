"""Routage racine du projet.

À l'amorçage, seul l'admin Django est exposé (cf. §2 du cahier des charges :
« démarrer toute la logique sur l'admin »). Les routes du front public et de
l'espace membre seront ajoutées via des include() par app, au fur et à mesure.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

# Personnalisation de l'en-tête de l'admin (back-office).
admin.site.site_header = "Administration — Association"
admin.site.site_title = "Association"
admin.site.index_title = "Back-office"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.vitrine.urls")),  # front public
    path("", include("apps.espace_membre.urls")),  # espace membre (connecté)
    path("", include("apps.backoffice.urls")),  # back-office bureau
]

# En développement uniquement : service des fichiers médias par Django.
# En production, Nginx sert les fichiers statiques et les médias publics ;
# les médias privés passent par une vue authentifiée / X-Accel-Redirect.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
