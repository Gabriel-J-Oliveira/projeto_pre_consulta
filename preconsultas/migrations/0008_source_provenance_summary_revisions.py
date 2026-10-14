import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("preconsultas", "0007_inboundmessage"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(
            model_name="sourceitem", name="inbound_message",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                       related_name="clinical_source", to="preconsultas.inboundmessage"),
        ),
        migrations.AddField(
            model_name="sourceitem", name="materialized_at", field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="sourceitem", name="materialized_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name="materialized_sources", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="sourceitem", name="author", field=models.CharField(choices=[
                ("patient", "Paciente"), ("ai", "Assistente virtual"), ("simulation", "Entrada simulada"),
            ], max_length=20),
        ),
        migrations.AlterField(
            model_name="sourceitem", name="kind", field=models.CharField(choices=[
                ("message", "Mensagem"), ("audio", "Áudio"), ("pdf", "PDF"), ("image", "Referência de imagem"),
            ], max_length=20),
        ),
        migrations.CreateModel(
            name="SummaryRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("logical_key", models.SlugField()), ("number", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(editable=False)),
                ("section", models.CharField(max_length=80)), ("label", models.CharField(max_length=120)),
                ("attribution", models.CharField(choices=[
                    ("patient", "Relatado pelo paciente"), ("ai", "Síntese da IA"), ("doctor", "Ajustado pelo médico"),
                ], max_length=20)),
                ("original_value", models.TextField()), ("presented_value", models.TextField()),
                ("is_hidden", models.BooleanField(default=False)),
                ("correction_reference", models.PositiveBigIntegerField(blank=True, null=True)),
                ("consultation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                                 related_name="summary_revisions", to="preconsultas.consultation")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                               related_name="summary_revisions", to=settings.AUTH_USER_MODEL)),
                ("summary_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                                 related_name="revisions", to="preconsultas.summaryitem")),
            ],
            options={"ordering": ["number", "id"]},
        ),
        migrations.CreateModel(
            name="SummaryRevisionSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("revision", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                              related_name="source_references", to="preconsultas.summaryrevision")),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                            related_name="revision_references", to="preconsultas.sourceitem")),
            ],
        ),
        migrations.AddField(
            model_name="summaryrevision", name="sources",
            field=models.ManyToManyField(related_name="revisions", through="preconsultas.SummaryRevisionSource", to="preconsultas.sourceitem"),
        ),
        migrations.AddConstraint(model_name="summaryrevisionsource",
                                 constraint=models.UniqueConstraint(fields=("revision", "source"), name="unique_revision_source")),
        migrations.AddConstraint(model_name="summaryrevision",
                                 constraint=models.UniqueConstraint(fields=("consultation", "logical_key", "number"), name="unique_summary_revision")),
        migrations.AddConstraint(model_name="summaryrevision",
                                 constraint=models.CheckConstraint(condition=models.Q(number__gte=1), name="summary_revision_positive")),
    ]
