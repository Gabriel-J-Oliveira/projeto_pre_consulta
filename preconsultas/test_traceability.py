from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from .ingestion import ingest_message
from .ingestion_simulator import simulation_envelopes
from .models import (
    Clinic, ConsentEvidence, Consultation, Correction, Doctor, InboundMessage,
    OperationalEvent, SourceItem, SummaryItem, SummaryRevision, SummaryRevisionSource,
)
from .test_ingestion import collecting_fixture
from .traceability import (
    TraceabilityPersistenceError, materialize_message, patient_history,
    record_summary_revision, source_provenance, summary_revisions,
)


def traceability_fixture():
    case, reception = collecting_fixture()
    doctor = get_user_model().objects.create_user("medico-rastreabilidade-ficticio")
    case.doctor.user = doctor
    case.doctor.save(update_fields=["user"])
    receipt = ingest_message(simulation_envelopes(case.pk)[0], actor=reception)
    return case, reception, doctor, receipt.message_id


class TraceabilityTests(TestCase):
    def setUp(self):
        self.case, self.reception, self.doctor, self.message_id = traceability_fixture()
        self.event_count = OperationalEvent.objects.count()

    def materialize(self):
        return materialize_message(self.case.pk, self.message_id, actor=self.doctor)

    def ready_fixture(self):
        # Fixture only, not a clinical publication service.
        Consultation.objects.filter(pk=self.case.pk).update(status=Consultation.STATUS_READY)

    def create_item(self, source):
        item = SummaryItem.objects.create(
            consultation=self.case, item_key="item-rastreavel-ficticio", section="Seção fictícia",
            label="Item fictício", original_value="Derivado fictício já existente.", attribution="ai",
        )
        item.sources.add(source)
        return item

    def test_materialization_preserves_message_origin_and_creates_one_source(self):
        message = InboundMessage.objects.get(pk=self.message_id)
        original = (message.text, message.declared_at, message.received_at, message.consent_id, message.operator_id)
        before = timezone.now()
        with self.assertNoLogs():
            receipt = self.materialize()
        source = SourceItem.objects.get(pk=receipt.source_id)
        self.assertTrue(receipt.created)
        self.assertEqual(source.inbound_message_id, message.pk)
        self.assertEqual(source.consultation_id, message.consultation_id)
        self.assertEqual(source.body, message.text)
        self.assertEqual(source.sent_at, message.declared_at)
        self.assertEqual(source.author, SourceItem.AUTHOR_SIMULATION)
        self.assertEqual(source.materialized_by_id, self.doctor.pk)
        self.assertGreaterEqual(source.materialized_at, before)
        again = self.materialize()
        self.assertFalse(again.created)
        self.assertEqual(receipt.source_id, again.source_id)
        self.assertEqual(SourceItem.objects.count(), 1)
        message.refresh_from_db()
        self.assertEqual((message.text, message.declared_at, message.received_at, message.consent_id, message.operator_id), original)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, Consultation.STATUS_IN_PROGRESS)
        self.assertEqual(OperationalEvent.objects.count(), self.event_count)
        self.assertFalse(SummaryItem.objects.exists())

    def test_text_audio_image_pdf_provenance_metadata_and_unprocessed_ui(self):
        for payload in [simulation_envelopes(self.case.pk)[0], *simulation_envelopes(self.case.pk)[3:]]:
            inbound = ingest_message(payload, actor=self.reception)
            receipt = materialize_message(self.case.pk, inbound.message_id, actor=self.doctor)
            source = SourceItem.objects.get(pk=receipt.source_id)
            self.assertEqual(source.kind, "message" if payload["kind"] == "text" else payload["kind"])
            self.assertEqual(source.filename, payload.get("media", {}).get("filename", ""))
            self.assertEqual(source.demo_transcript, "")
            self.assertIsNone(source.duration_seconds)
            self.ready_fixture()
            provenance = source_provenance(self.case.pk, source.pk, actor=self.doctor)
            self.assertEqual(provenance["external_event_id"], payload["external_event_id"])
            self.assertEqual(provenance["media"], payload.get("media", {}))
            self.assertEqual(provenance["consent_id"], source.inbound_message.consent_id)
            self.assertEqual(provenance["origin"], "local_simulation")
            self.assertEqual(provenance["contract_version"], "sim.v1")
            self.assertTrue(provenance["is_simulated"])
            # Next ingestion needs collecting state; fixture-only reset.
            Consultation.objects.filter(pk=self.case.pk).update(status=Consultation.STATUS_IN_PROGRESS)
        self.ready_fixture()
        self.client.force_login(self.doctor)
        page = self.client.get(reverse("preconsultas:detail", args=[self.case.slug]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Entrada simulada")
        self.assertContains(page, "arquivo-ficticio.png")
        self.assertContains(page, "sem arquivo processado")
        self.assertNotContains(page, "00:47")
        self.assertEqual(OperationalEvent.objects.count(), self.event_count)

    def test_provenance_read_is_blocked_before_publication(self):
        receipt = self.materialize()
        with self.assertRaises(PermissionDenied):
            source_provenance(self.case.pk, receipt.source_id, actor=self.doctor)
        self.assertEqual(patient_history(self.case.patient_id, actor=self.doctor), ())
        self.assertFalse(SummaryRevision.objects.exists())

    def test_historical_validated_message_can_be_materialized_without_publication(self):
        Consultation.objects.filter(pk=self.case.pk).update(status=Consultation.STATUS_COMPLETED)
        receipt = self.materialize()
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, Consultation.STATUS_COMPLETED)
        with self.assertRaises(PermissionDenied):
            source_provenance(self.case.pk, receipt.source_id, actor=self.doctor)

    def test_reception_admin_unassigned_anonymous_and_inactive_are_denied(self):
        receipt = self.materialize()
        source = SourceItem.objects.get(pk=receipt.source_id)
        self.ready_fixture()
        item = self.create_item(source)
        inactive = get_user_model().objects.get(pk=self.doctor.pk)
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])
        actors = [self.reception, AnonymousUser(), None, inactive,
                  get_user_model().objects.create_user("rastreabilidade-sem-perfil"),
                  get_user_model().objects.create_superuser("rastreabilidade-admin-ficticio", password=None)]
        for actor in actors:
            for action in [
                lambda: materialize_message(self.case.pk, self.message_id, actor=actor),
                lambda: source_provenance(self.case.pk, source.pk, actor=actor),
                lambda: record_summary_revision(self.case.pk, item.pk, actor=actor),
                lambda: summary_revisions(self.case.pk, item.pk, actor=actor),
                lambda: patient_history(self.case.patient_id, actor=actor),
            ]:
                with self.assertRaises(PermissionDenied):
                    action()
        self.assertFalse(SummaryRevision.objects.exists())

    def test_reception_and_admin_routes_never_expose_new_clinical_models(self):
        self.materialize()
        self.client.force_login(self.reception)
        page = self.client.get(reverse("recepcao:preconsultations"))
        self.assertNotContains(page, InboundMessage.objects.get().text)
        self.assertNotContains(page, "summary_revisions")
        for model in [SummaryRevision, SummaryRevisionSource, SourceItem]:
            self.assertFalse(admin.site.is_registered(model))

    def test_outside_clinic_other_doctor_and_forged_context_are_denied(self):
        receipt = self.materialize()
        other = Consultation.objects.create(
            slug="outra-rastreabilidade-ficticia", patient=self.case.patient, doctor=self.case.doctor,
            clinic=self.case.clinic, scheduled_for=timezone.now(), status=Consultation.STATUS_READY,
        )
        for case_id in [other.pk, 999999]:
            with self.assertRaises(PermissionDenied):
                materialize_message(case_id, self.message_id, actor=self.doctor)
            with self.assertRaises(PermissionDenied):
                source_provenance(case_id, receipt.source_id, actor=self.doctor)
        self.case.doctor.clinics.clear()
        with self.assertRaises(PermissionDenied):
            self.materialize()
        self.case.doctor.clinics.add(self.case.clinic)
        other_doctor = get_user_model().objects.create_user("rastreabilidade-outro-medico")
        profile = Doctor.objects.create(name="Outro médico fictício", user=other_doctor)
        profile.clinics.add(self.case.clinic)
        with self.assertRaises(PermissionDenied):
            materialize_message(self.case.pk, self.message_id, actor=other_doctor)
        self.assertEqual(SourceItem.objects.count(), 1)

    def test_invalid_ids_are_denied_without_echoing_payload(self):
        for invalid in [None, True, "conteúdo fictício", 0, 2**63]:
            with self.assertRaises(PermissionDenied):
                materialize_message(self.case.pk, invalid, actor=self.doctor)
            with self.assertRaises(PermissionDenied):
                patient_history(invalid, actor=self.doctor)

    def test_source_model_rejects_cross_consultation_and_unlink_overwrite(self):
        receipt = self.materialize()
        source = SourceItem.objects.get(pk=receipt.source_id)
        source.inbound_message = None
        with self.assertRaises(ValidationError):
            source.save()
        with self.assertRaises(ValidationError):
            source.delete()
        other = Consultation.objects.create(
            slug="fonte-externa-ficticia", patient=self.case.patient, doctor=self.case.doctor,
            clinic=self.case.clinic, scheduled_for=timezone.now(), status="ready",
        )
        with self.assertRaises(ValidationError):
            SourceItem.objects.create(
                consultation=other, source_key="forjada-ficticia", kind="message", author="simulation",
                sent_at=timezone.now(), inbound_message_id=self.message_id,
                materialized_at=timezone.now(), materialized_by=self.doctor,
            )
        self.assertEqual(SourceItem.objects.count(), 1)

    def test_corrupt_input_or_source_provenance_is_rejected(self):
        evidence = InboundMessage.objects.get().consent
        ConsentEvidence.objects.filter(pk=evidence.pk).update(manifestation=ConsentEvidence.DECLINED)
        with self.assertRaises(ValidationError):
            self.materialize()
        ConsentEvidence.objects.filter(pk=evidence.pk).update(manifestation=ConsentEvidence.ACCEPTED)
        receipt = self.materialize()
        SourceItem.objects.filter(pk=receipt.source_id).update(body="Fonte alterada fictícia")
        with self.assertRaises(ValidationError):
            self.materialize()
        self.ready_fixture()
        with self.assertRaises(ValidationError):
            source_provenance(self.case.pk, receipt.source_id, actor=self.doctor)

    def test_source_creation_failure_rolls_back_without_clinical_audit(self):
        real_create = SourceItem.objects.create

        def fail(**kwargs):
            real_create(**kwargs)
            raise IntegrityError("Falha fictícia")

        with patch("preconsultas.traceability.SourceItem.objects.create", side_effect=fail):
            with self.assertRaises(TraceabilityPersistenceError):
                self.materialize()
        self.assertFalse(SourceItem.objects.exists())
        self.assertEqual(InboundMessage.objects.count(), 1)
        self.assertEqual(OperationalEvent.objects.count(), self.event_count)

    def test_revisions_preserve_original_corrections_refs_and_capture_actor(self):
        source = SourceItem.objects.get(pk=self.materialize().source_id)
        item = self.create_item(source)
        self.ready_fixture()
        first_id = record_summary_revision(self.case.pk, item.pk, actor=self.doctor)
        self.assertEqual(record_summary_revision(self.case.pk, item.pk, actor=self.doctor), first_id)
        correction = Correction.objects.create(
            summary_item=item, action="update", previous_value=item.original_value, new_value="Ajuste fictício existente.",
        )
        second_id = record_summary_revision(self.case.pk, item.pk, actor=self.doctor)
        Correction.objects.create(summary_item=item, action="hide", previous_value=correction.new_value)
        third_id = record_summary_revision(self.case.pk, item.pk, actor=self.doctor)
        revisions = summary_revisions(self.case.pk, item.pk, actor=self.doctor)
        self.assertEqual([row["number"] for row in revisions], [1, 2, 3])
        self.assertEqual([row["id"] for row in revisions], [first_id, second_id, third_id])
        self.assertEqual(revisions[0]["presented_value"], item.original_value)
        self.assertEqual(revisions[1]["presented_value"], correction.new_value)
        self.assertTrue(revisions[2]["is_hidden"])
        self.assertEqual(revisions[1]["correction_reference"], correction.pk)
        self.assertEqual(revisions[0]["source_ids"], (source.pk,))
        self.assertEqual(revisions[0]["created_by_id"], self.doctor.pk)
        item.refresh_from_db()
        self.assertEqual(item.original_value, "Derivado fictício já existente.")
        self.assertEqual(OperationalEvent.objects.count(), self.event_count)

    def test_source_reference_changes_create_revision_without_altering_old_set(self):
        source = SourceItem.objects.get(pk=self.materialize().source_id)
        item = self.create_item(source)
        self.ready_fixture()
        record_summary_revision(self.case.pk, item.pk, actor=self.doctor)
        item.sources.clear()  # Existing legacy relation; snapshots keep their own references.
        record_summary_revision(self.case.pk, item.pk, actor=self.doctor)
        revisions = summary_revisions(self.case.pk, item.pk, actor=self.doctor)
        self.assertEqual(revisions[0]["source_ids"], (source.pk,))
        self.assertEqual(revisions[1]["source_ids"], ())

    def test_revision_write_read_and_sources_require_same_authorized_ready_case(self):
        source = SourceItem.objects.get(pk=self.materialize().source_id)
        item = self.create_item(source)
        for action in [record_summary_revision, summary_revisions]:
            with self.assertRaises(PermissionDenied):
                action(self.case.pk, item.pk, actor=self.doctor)
        self.ready_fixture()
        other = Consultation.objects.create(
            slug="outro-resumo-ficticio", patient=self.case.patient, doctor=self.case.doctor,
            clinic=self.case.clinic, scheduled_for=timezone.now(), status="ready",
        )
        with self.assertRaises(PermissionDenied):
            record_summary_revision(other.pk, item.pk, actor=self.doctor)
        external_source = SourceItem.objects.create(
            consultation=other, source_key="fonte-externa-resumo", kind="message", author="patient", sent_at=timezone.now(),
        )
        item.sources.add(external_source)  # Malformed fixture deliberately bypasses service.
        with self.assertRaises(ValidationError):
            record_summary_revision(self.case.pk, item.pk, actor=self.doctor)
        self.assertFalse(SummaryRevision.objects.exists())

    def test_revision_instance_constraints_and_cross_source_reference(self):
        source = SourceItem.objects.get(pk=self.materialize().source_id)
        item = self.create_item(source)
        self.ready_fixture()
        revision = SummaryRevision.objects.get(pk=record_summary_revision(self.case.pk, item.pk, actor=self.doctor))
        with self.assertRaises(ValidationError):
            revision.save()
        with self.assertRaises(ValidationError):
            revision.delete()
        reference = revision.source_references.get()
        with self.assertRaises(ValidationError):
            reference.delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SummaryRevision.objects.filter(pk=revision.pk).update(number=0)
        other = Consultation.objects.create(
            slug="outro-vinculo-ficticio", patient=self.case.patient, doctor=self.case.doctor,
            clinic=self.case.clinic, scheduled_for=timezone.now(), status="ready",
        )
        external = SourceItem.objects.create(
            consultation=other, source_key="outra-ref-ficticia", kind="message", author="patient", sent_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            SummaryRevisionSource.objects.create(revision=revision, source=external)

    def test_partial_reference_failure_rolls_back_revision_and_links(self):
        source = SourceItem.objects.get(pk=self.materialize().source_id)
        item = self.create_item(source)
        another = SourceItem.objects.create(
            consultation=self.case, source_key="outra-fonte-local", kind="message", author="patient", sent_at=timezone.now(),
        )
        item.sources.add(another)
        self.ready_fixture()
        real_create = SummaryRevisionSource.objects.create
        calls = 0

        def fail(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise IntegrityError("Falha fictícia na segunda referência")
            return real_create(**kwargs)

        with patch("preconsultas.traceability.SummaryRevisionSource.objects.create", side_effect=fail):
            with self.assertRaises(TraceabilityPersistenceError):
                record_summary_revision(self.case.pk, item.pk, actor=self.doctor)
        self.assertFalse(SummaryRevision.objects.exists())
        self.assertFalse(SummaryRevisionSource.objects.exists())
        self.assertEqual(item.sources.count(), 2)

    def test_database_uniqueness_preserves_message_revision_and_reference_identity(self):
        source = SourceItem.objects.get(pk=self.materialize().source_id)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SourceItem.objects.create(
                consultation=self.case, inbound_message_id=self.message_id, source_key="duplicata-ficticia",
                kind=source.kind, author=source.author, sent_at=source.sent_at, body=source.body,
                materialized_at=source.materialized_at, materialized_by=self.doctor,
            )
        item = self.create_item(source)
        self.ready_fixture()
        revision = SummaryRevision.objects.get(pk=record_summary_revision(self.case.pk, item.pk, actor=self.doctor))
        values = {field.name: getattr(revision, field.name) for field in revision._meta.fields if field.name != "id"}
        with self.assertRaises(IntegrityError), transaction.atomic():
            SummaryRevision.objects.create(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SummaryRevisionSource.objects.create(revision=revision, source=source)
        self.assertEqual(SourceItem.objects.count(), 1)
        self.assertEqual(SummaryRevision.objects.count(), 1)
        self.assertEqual(SummaryRevisionSource.objects.count(), 1)

    def test_patient_history_excludes_unpublished_other_doctors_and_unlinked_clinics(self):
        self.ready_fixture()
        other_doctor = Doctor.objects.create(name="Outro médico fictício de histórico")
        other_doctor.clinics.add(self.case.clinic)
        other_clinic = Clinic.objects.create(name="Clínica externa fictícia de histórico")
        for slug, doctor, clinic, state in [
            ("outro-medico-historico", other_doctor, self.case.clinic, "ready"),
            ("outra-clinica-historico", self.case.doctor, other_clinic, "ready"),
            ("nao-publicado-historico", self.case.doctor, self.case.clinic, "completed"),
        ]:
            Consultation.objects.create(slug=slug, patient=self.case.patient, doctor=doctor,
                                        clinic=clinic, scheduled_for=timezone.now(), status=state)
        history = patient_history(self.case.patient_id, actor=self.doctor)
        self.assertEqual([row["id"] for row in history], [self.case.pk])
        self.assertEqual(set(history[0]), {"id", "slug", "scheduled_for", "doctor_id", "clinic_id", "status"})
        self.assertEqual(patient_history(999999, actor=self.doctor), ())
        self.case.doctor.clinics.clear()
        with self.assertRaises(PermissionDenied):
            patient_history(self.case.patient_id, actor=self.doctor)

    def test_legacy_seed_remains_idempotent_and_preserves_new_data_and_snapshots(self):
        new_source = SourceItem.objects.get(pk=self.materialize().source_id)
        call_command("load_demo", verbosity=0)  # Temporary test DB ONLY.
        legacy = SourceItem.objects.get(source_key="msg-motivo")
        legacy_case = legacy.consultation
        legacy_case.doctor.user = self.doctor
        self.case.doctor.user = None
        self.case.doctor.save(update_fields=["user"])
        legacy_case.doctor.save(update_fields=["user"])
        provenance = source_provenance(legacy_case.pk, legacy.pk, actor=self.doctor)
        self.assertEqual(provenance, {"legacy": True, "source_id": legacy.pk, "message_id": None})
        item = SummaryItem.objects.get(item_key="medication")
        first_id = record_summary_revision(legacy_case.pk, item.pk, actor=self.doctor)
        Correction.objects.create(summary_item=item, action="update", previous_value=item.original_value,
                                  new_value="Ajuste fictício do legado.")
        second_id = record_summary_revision(legacy_case.pk, item.pk, actor=self.doctor)
        call_command("load_demo", verbosity=0)
        call_command("load_demo", reset_interactions=True, verbosity=0)
        self.assertEqual(SummaryRevision.objects.filter(pk__in=[first_id, second_id]).count(), 2)
        self.assertEqual(SummaryRevision.objects.get(pk=second_id).presented_value, "Ajuste fictício do legado.")
        self.assertFalse(Correction.objects.exists())
        self.assertEqual(InboundMessage.objects.count(), 1)
        self.assertTrue(SourceItem.objects.filter(pk=new_source.pk, inbound_message_id=self.message_id).exists())
        self.assertEqual(SourceItem.objects.filter(inbound_message__isnull=False).count(), 1)
        self.assertEqual(SourceItem.objects.filter(inbound_message__isnull=True).count(), 9)


class TraceabilityConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_materialization_creates_one_source(self):
        case, reception, actor, message_id = traceability_fixture()
        barrier = Barrier(2)

        def worker():
            try:
                user = get_user_model().objects.get(pk=actor.pk)
                barrier.wait(timeout=10)
                return materialize_message(case.pk, message_id, actor=user)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            receipts = [future.result(timeout=20) for future in futures]
        self.assertEqual(len({receipt.source_id for receipt in receipts}), 1)
        self.assertCountEqual([receipt.created for receipt in receipts], [True, False])
        self.assertEqual(SourceItem.objects.count(), 1)
        self.assertEqual(OperationalEvent.objects.count(), 2)

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_identical_snapshots_create_one_revision(self):
        case, reception, actor, message_id = traceability_fixture()
        source = SourceItem.objects.get(pk=materialize_message(case.pk, message_id, actor=actor).source_id)
        Consultation.objects.filter(pk=case.pk).update(status="ready")  # Fixture only.
        item = SummaryItem.objects.create(consultation=case, item_key="snapshot-concorrente",
                                         section="Teste", label="Teste fictício", original_value="Fictício", attribution="ai")
        item.sources.add(source)
        barrier = Barrier(2)

        def worker():
            try:
                user = get_user_model().objects.get(pk=actor.pk)
                barrier.wait(timeout=10)
                return record_summary_revision(case.pk, item.pk, actor=user)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            revision_ids = [future.result(timeout=20) for future in futures]
        self.assertEqual(len(set(revision_ids)), 1)
        self.assertEqual(SummaryRevision.objects.count(), 1)
        self.assertEqual(SummaryRevisionSource.objects.count(), 1)


class TraceabilityMigrationTests(TransactionTestCase):
    def test_upgrade_0007_adds_no_artificial_provenance_or_revisions(self):
        connection = connections["default"]
        before = [("preconsultas", "0007_inboundmessage")]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            old = executor.loader.project_state(before).apps
            case, reception = collecting_fixture()
            message_id = ingest_message(simulation_envelopes(case.pk)[0], actor=reception).message_id
            source = old.get_model("preconsultas", "SourceItem").objects.create(
                consultation_id=case.pk, source_key="fonte-antiga-0007", kind="message", author="patient",
                sent_at=timezone.now(), body="Fonte fictícia anterior ao vínculo.",
            )
            summary = old.get_model("preconsultas", "SummaryItem").objects.create(
                consultation_id=case.pk, item_key="resumo-antigo-0007", section="Teste", label="Teste",
                original_value="Derivado fictício antigo.", attribution="ai",
            )
            summary.sources.add(source)
        finally:
            restored = MigrationExecutor(connection)
            restored.migrate(restored.loader.graph.leaf_nodes())
        self.assertIsNone(SourceItem.objects.get(pk=source.pk).inbound_message_id)
        self.assertIsNone(SourceItem.objects.get(pk=source.pk).materialized_at)
        self.assertEqual(SummaryItem.objects.get().sources.get().pk, source.pk)
        self.assertEqual(InboundMessage.objects.get(pk=message_id).consent.consultation_id, case.pk)
        self.assertFalse(SummaryRevision.objects.exists())
        self.assertEqual(OperationalEvent.objects.count(), 2)
        self.assertEqual(Consultation.objects.get().status, "in_progress")
