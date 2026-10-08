from django.urls import path

from . import views


app_name = "preconsultas"

urlpatterns = [
    path("painel/", views.dashboard, name="dashboard"),
    path("pre-consultas/demo/", views.demo, name="demo"),
    path("pre-consultas/demo/apontamentos/", views.add_note, name="add_note"),
    path("pre-consultas/demo/correcoes/", views.correct_item, name="correct_item"),
    path("pre-consultas/demo/feedback/", views.add_feedback, name="add_feedback"),
    path(
        "pre-consultas/demo/anexos/<slug:source_key>/status/",
        views.attachment_status,
        name="attachment_status",
    ),
    path(
        "pre-consultas/demo/anexos/<slug:source_key>/conteudo/",
        views.attachment_content,
        name="attachment_content",
    ),
]
