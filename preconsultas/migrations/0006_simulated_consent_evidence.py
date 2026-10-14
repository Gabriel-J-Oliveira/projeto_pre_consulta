import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("preconsultas", "0005_operational_state_engine"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="operationalevent", name="kind",
            field=models.CharField(choices=[
                ("consent_recorded", "Manifestação simulada registrada"),
                ("state_changed", "Estado operacional alterado"),
                ("created", "Registro criado"), ("invite_planned", "Convite previsto"),
                ("invite_simulated", "Convite demonstrativo"),
                ("awaiting_consent", "Aguardando consentimento"),
                ("interview_in_progress", "Entrevista em andamento"),
                ("ready", "Pré-consulta pronta"), ("incomplete", "Pré-consulta incompleta"),
                ("consent_declined", "Consentimento recusado"),
            ], max_length=30),
        ),
        migrations.CreateModel(
            name="ConsentEvidence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("term_version", models.CharField(max_length=80)),
                ("manifestation", models.CharField(choices=[
                    ("accepted", "Aceite simulado"), ("declined", "Recusa simulada"),
                ], max_length=8)),
                ("origin", models.CharField(default="local_simulation", editable=False, max_length=30)),
                ("occurred_at", models.DateTimeField(editable=False)),
                ("is_simulated", models.BooleanField(default=True, editable=False)),
                ("consultation", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="consent_evidence",
                    to="preconsultas.consultation")),
                ("event", models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT, related_name="consent_evidence",
                    to="preconsultas.operationalevent")),
                ("operator", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="simulated_consent_evidence",
                    to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["id"],
                "constraints": [
                    models.UniqueConstraint(fields=("consultation", "term_version"), name="unique_consent_consultation_version"),
                    models.CheckConstraint(condition=models.Q(is_simulated=True, origin="local_simulation"), name="consent_simulation_only"),
                    models.CheckConstraint(condition=models.Q(manifestation__in=["accepted", "declined"]), name="consent_manifestation_valid"),
                    models.CheckConstraint(condition=~models.Q(term_version=""), name="consent_version_not_empty"),
                ],
            },
        ),
    ]
