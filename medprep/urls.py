from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView


urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url="/static/preconsultas/favicon.svg", permanent=False)),
    path("admin/", admin.site.urls),
    path("medico/", include("preconsultas.urls")),
    path("recepcao/", include("preconsultas.reception_urls")),
    path("", RedirectView.as_view(pattern_name="preconsultas:demo", permanent=False)),
]
