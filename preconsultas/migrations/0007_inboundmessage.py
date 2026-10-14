import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("preconsultas", "0006_simulated_consent_evidence"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="InboundMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("origin", models.CharField(default="local_simulation", max_length=30)),
                ("external_event_id", models.CharField(max_length=120)),
                ("contract_version", models.CharField(max_length=20)),
                ("kind", models.CharField(choices=[
                    ("text", "Texto"), ("audio", "Referência de áudio"),
                    ("image", "Referência de imagem"), ("pdf", "Referência de PDF"),
                ], max_length=5)),
                ("text", models.TextField(blank=True)),
                ("media", models.JSONField(blank=True, default=dict)),
                ("declared_at", models.DateTimeField()),
                ("received_at", models.DateTimeField(editable=False)),
                ("is_simulated", models.BooleanField(default=True, editable=False)),
                ("consent", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                            related_name="inbound_messages", to="preconsultas.consentevidence")),
                ("consultation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                                 related_name="inbound_messages", to="preconsultas.consultation")),
                ("operator", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                             related_name="simulated_inbound_messages", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["received_at", "id"],
                "constraints": [
                    models.UniqueConstraint(fields=("origin", "consultation", "external_event_id"),
                                            name="unique_inbound_namespace_event"),
                    models.CheckConstraint(condition=models.Q(origin="local_simulation", is_simulated=True),
                                           name="inbound_simulation_only"),
                    models.CheckConstraint(condition=models.Q(contract_version="sim.v1"), name="inbound_contract_v1"),
                    models.CheckConstraint(condition=models.Q(kind__in=["text", "audio", "image", "pdf"]),
                                           name="inbound_kind_valid"),
                    models.CheckConstraint(condition=~models.Q(external_event_id=""), name="inbound_id_not_empty"),
                    models.CheckConstraint(
                        condition=(models.Q(kind="text", media={}) & ~models.Q(text=""))
                        | (models.Q(kind__in=["audio", "image", "pdf"], text="") & ~models.Q(media={})),
                        name="inbound_content_matches_kind",
                    ),
                ],
            },
        ),
    ]
