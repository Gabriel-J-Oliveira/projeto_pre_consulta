from django.urls import path

from . import views


app_name = "recepcao"

urlpatterns = [
    path("pre-consultas/", views.reception_preconsultations, name="preconsultations"),
]

