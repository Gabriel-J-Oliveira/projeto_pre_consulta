from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from .ai_orchestration import current_result, execute
from .ai_provider import FakeAIProvider
from .models import (AIExecution, ClinicalPublication, ConsentEvidence, Consultation, Correction, Doctor,
                     DoctorNote, Feedback, OperationalEvent, SourceItem, SummaryItem, SummaryRevision)
from .publication import PublicationError, publication_candidate, publish_consultation, review_action
from .test_ai_orchestration import orchestration_fixture
from .traceability import patient_history, source_provenance, summary_revisions


def publication_fixture():
    case, reception, actor, source_id = orchestration_fixture()
    Consultation.objects.filter(pk=case.pk).update(status="completed")
    execution = execute(case.pk, "build_summary", actor=actor)
    return case, reception, actor, source_id, execution.execution_id


class PublicationTests(TestCase):
    def setUp(self):
        self.case, self.reception, self.actor, self.source_id, self.execution_id = publication_fixture()
        self.before_events = OperationalEvent.objects.count()

    def publish(self):
        return publish_consultation(self.case.pk, self.execution_id, actor=self.actor)

    def assert_unpublished(self):
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, "completed")
        self.assertFalse(ClinicalPublication.objects.exists())
        self.assertFalse(SummaryItem.objects.exists())
        self.assertFalse(SummaryRevision.objects.exists())
        self.assertEqual(OperationalEvent.objects.count(), self.before_events)

    def test_publish_atomic_audit_links_and_idempotence_preserve_technical_source(self):
        execution = AIExecution.objects.get(pk=self.execution_id)
        original = deepcopy(execution.result)
        source = dict(SourceItem.objects.get(pk=self.source_id).__dict__)
        with self.assertNoLogs():
            first = self.publish()
            again = self.publish()
        self.assertTrue(first.created)
        self.assertFalse(again.created)
        self.assertEqual(first.publication_id, again.publication_id)
        publication = ClinicalPublication.objects.get()
        self.assertEqual(publication.actor_id, self.actor.pk)
        self.assertEqual(publication.doctor_id, self.case.doctor_id)
        self.assertEqual(publication.execution_id, self.execution_id)
        self.assertEqual(publication.result_snapshot, original)
        self.assertTrue(publication.is_simulated)
        self.assertEqual(publication.event.previous_status, "completed")
        self.assertEqual(publication.event.next_status, "ready")
        self.assertEqual(publication.event.occurred_at, publication.published_at)
        self.assertNotIn(original["result"]["items"][0]["text"], publication.event.detail)
        execution.refresh_from_db()
        self.assertEqual(execution.result, original)
        self.assertEqual(SourceItem.objects.get(pk=self.source_id).body, source["body"])
        item = SummaryItem.objects.get()
        self.assertEqual(item.publication_id, publication.pk)
        self.assertEqual(item.sources.get().pk, self.source_id)
        self.assertEqual(item.revisions.count(), 1)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, "ready")
        self.assertEqual(current_result(self.case.pk, self.execution_id, actor=self.actor), original)

    def test_completed_cannot_read_and_candidate_returns_only_id(self):
        self.assertEqual(publication_candidate(self.case.pk, actor=self.actor), self.execution_id)
        with self.assertRaises(PermissionDenied):
            current_result(self.case.pk, self.execution_id, actor=self.actor)
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(reverse("preconsultas:detail", args=[self.case.slug])).status_code, 403)
        page = self.client.get(reverse("preconsultas:dashboard"))
        self.assertContains(page, "Publicar síntese simulada")
        self.assertNotContains(page, SourceItem.objects.get(pk=self.source_id).body)
        self.assert_unpublished()

    def test_ready_without_publication_or_explicit_legacy_marker_blocked_everywhere(self):
        Consultation.objects.filter(pk=self.case.pk).update(status="ready")
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(reverse("preconsultas:detail", args=[self.case.slug])).status_code, 403)
        with self.assertRaises(PermissionDenied):
            source_provenance(self.case.pk, self.source_id, actor=self.actor)
        self.assertEqual(patient_history(self.case.patient_id, actor=self.actor), ())
        self.assertNotContains(self.client.get(reverse("preconsultas:dashboard")), f'href="/medico/pre-consultas/{self.case.slug}/"')

    def test_profiles_and_clinic_doctor_assignment_are_checked_again(self):
        staff = get_user_model().objects.create_user("tecnico-publicacao-ficticio", is_staff=True, is_superuser=True)
        other = get_user_model().objects.create_user("outro-publicador-ficticio")
        other_doctor = Doctor.objects.create(user=other, name="Outro médico fictício")
        other_doctor.clinics.add(self.case.clinic)
        for actor in (self.reception, staff, other, AnonymousUser()):
            with self.assertRaises(PermissionDenied):
                publish_consultation(self.case.pk, self.execution_id, actor=actor)
        self.case.doctor.clinics.clear()
        with self.assertRaises(PermissionDenied):
            self.publish()
        self.assert_unpublished()

    def test_missing_or_corrupted_consent_blocks_and_rolls_back(self):
        evidence = ConsentEvidence.objects.get(consultation=self.case)
        ConsentEvidence.objects.filter(pk=evidence.pk).update(manifestation="declined")
        with self.assertRaises(PublicationError):
            self.publish()
        self.assert_unpublished()
        ConsentEvidence.objects.filter(pk=evidence.pk).update(manifestation="accepted")
        OperationalEvent.objects.filter(pk=evidence.event_id).update(actor=None)
        with self.assertRaises(PublicationError):
            self.publish()
        self.assert_unpublished()

    def test_only_current_successful_build_summary_same_consultation_can_publish(self):
        for status in ("failed", "running", "obsolete"):
            AIExecution.objects.filter(pk=self.execution_id).update(status=status)
            with self.assertRaises(PublicationError):
                self.publish()
            self.assert_unpublished()
        AIExecution.objects.filter(pk=self.execution_id).update(status="succeeded", operation="extract_structured")
        with self.assertRaises(PublicationError):
            self.publish()
        AIExecution.objects.filter(pk=self.execution_id).update(operation="build_summary")
        with self.assertRaises(PermissionDenied):
            publish_consultation(self.case.pk, 999999, actor=self.actor)
        other = Consultation.objects.create(slug="publicacao-outra-ficticia", doctor=self.case.doctor,
                                            clinic=self.case.clinic, patient=self.case.patient,
                                            scheduled_for=timezone.now(), status="completed")
        with self.assertRaises(PermissionDenied):
            publish_consultation(other.pk, self.execution_id, actor=self.actor)
        self.assert_unpublished()

    def test_invalid_versions_references_and_changed_sources_do_not_publish(self):
        original = AIExecution.objects.get(pk=self.execution_id).result
        for mutate in (lambda r: r.update(contract_version="ai.v2"),
                       lambda r: r["result"]["items"][0]["references"][0].update(source_id=999999)):
            altered = deepcopy(original)
            mutate(altered)
            AIExecution.objects.filter(pk=self.execution_id).update(result=altered)
            with self.assertRaises(PublicationError):
                self.publish()
            self.assert_unpublished()
        AIExecution.objects.filter(pk=self.execution_id).update(result=original)
        SourceItem.objects.filter(pk=self.source_id).update(body="Fonte fictícia alterada.")
        with self.assertRaises(PublicationError):
            self.publish()
        self.assert_unpublished()

    def test_empty_summary_or_attention_only_not_published(self):
        class EmptyFake(FakeAIProvider):
            def __init__(self, attention):
                super().__init__()
                self.attention = attention
                self.provider_version = "1.attention-only" if attention else "1.empty"

            def build_summary(self, request):
                result = super().build_summary(request)
                result["result"]["attention_points"] = deepcopy(result["result"]["items"]) if self.attention else []
                result["result"]["items"] = []
                return result

        for attention in (False, True):
            self.execution_id = execute(self.case.pk, "build_summary", actor=self.actor, provider=EmptyFake(attention)).execution_id
            with self.assertRaises(PublicationError):
                self.publish()
            self.assert_unpublished()

    def test_failure_after_items_or_snapshot_rolls_back_every_write(self):
        with patch("preconsultas.publication.record_summary_revision", side_effect=DatabaseError("PRIVATE DETAIL")):
            with self.assertRaises(PublicationError) as caught:
                self.publish()
        self.assertNotIn("PRIVATE", str(caught.exception))
        self.assert_unpublished()

    def test_attention_is_traced_and_uses_distinct_global_keys(self):
        class AttentionFake(FakeAIProvider):
            provider_version = "1.attention"

            def __init__(self):
                super().__init__()
                self.provider_version = "1.attention"

            def build_summary(self, request):
                result = super().build_summary(request)
                attention = deepcopy(result["result"]["items"][0])
                attention.update(text="Observação fictícia para avaliação médica.", basis="derived")
                result["result"]["attention_points"] = [attention]
                return result

        self.execution_id = execute(self.case.pk, "build_summary", actor=self.actor, provider=AttentionFake()).execution_id
        self.publish()
        self.assertEqual(SummaryItem.objects.count(), 2)
        self.assertEqual(len(set(SummaryItem.objects.values_list("item_key", flat=True))), 2)
        self.assertEqual(SummaryItem.objects.filter(publication_kind="attention").get().sources.get().pk, self.source_id)
        self.client.force_login(self.actor)
        page = self.client.get(reverse("preconsultas:detail", args=[self.case.slug]))
        self.assertContains(page, "Publicação SIMULADA")
        self.assertContains(page, "Pontos para revisão médica")
        self.assertContains(page, "Síntese simulada")

    def test_notes_corrections_feedback_have_actor_and_snapshots_are_atomic(self):
        self.publish()
        item = SummaryItem.objects.get()
        note = review_action(self.case.pk, actor=self.actor, action="note", data={"text": "Nota fictícia."})
        correction = review_action(self.case.pk, actor=self.actor, action="correction", data={
            "summary_item_id": item.pk, "action": "update", "new_value": "Ajuste fictício."})
        feedback = review_action(self.case.pk, actor=self.actor, action="feedback", data={"kind": "useful", "summary_item_id": item.pk})
        self.assertEqual([note.actor_id, correction.actor_id, feedback.actor_id], [self.actor.pk] * 3)
        self.assertEqual(item.revisions.count(), 2)
        repeated = review_action(self.case.pk, actor=self.actor, action="correction", data={
            "summary_item_id": item.pk, "action": "update", "new_value": "Ajuste fictício."})
        self.assertEqual(repeated.pk, correction.pk)
        self.assertEqual(item.revisions.count(), 2)
        latest = item.revisions.latest("number")
        self.assertEqual(latest.presented_value, "Ajuste fictício.")
        self.assertEqual(latest.correction_reference, correction.pk)
        self.assertEqual(latest.created_by_id, self.actor.pk)
        self.assertEqual(summary_revisions(self.case.pk, item.pk, actor=self.actor)[0]["number"], 1)
        with patch("preconsultas.publication.record_summary_revision", side_effect=DatabaseError):
            with self.assertRaises(PublicationError):
                review_action(self.case.pk, actor=self.actor, action="correction", data={
                    "summary_item_id": item.pk, "action": "update", "new_value": "Não persistir."})
        self.assertEqual(Correction.objects.count(), 1)
        self.assertEqual(item.revisions.count(), 2)

    def test_stale_publication_denies_every_read_write_and_link_without_changing_state(self):
        self.publish()
        item = SummaryItem.objects.get()
        SourceItem.objects.filter(pk=self.source_id).update(body="Contexto fictício mudou.")
        self.client.force_login(self.actor)
        routes = [("get", reverse("preconsultas:detail", args=[self.case.slug]), {}),
                  ("post", reverse("preconsultas:detail_note", args=[self.case.slug]), {"text": "Nota"}),
                  ("post", reverse("preconsultas:detail_correction", args=[self.case.slug]),
                   {"summary_item_id": item.pk, "action": "update", "new_value": "Ajuste"}),
                  ("post", reverse("preconsultas:detail_feedback", args=[self.case.slug]), {"kind": "useful"})]
        for method, url, data in routes:
            self.assertEqual(getattr(self.client, method)(url, data).status_code, 403)
        for reader in (lambda: source_provenance(self.case.pk, self.source_id, actor=self.actor),
                       lambda: summary_revisions(self.case.pk, item.pk, actor=self.actor),
                       lambda: current_result(self.case.pk, self.execution_id, actor=self.actor)):
            with self.assertRaises(PermissionDenied):
                reader()
        self.assertEqual(patient_history(self.case.patient_id, actor=self.actor), ())
        self.assertContains(self.client.get(reverse("preconsultas:dashboard")), "nova validação explícita")
        self.assertFalse(DoctorNote.objects.exists())
        self.assertFalse(Correction.objects.exists())
        self.assertFalse(Feedback.objects.exists())
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, "ready")
        self.assertEqual(ClinicalPublication.objects.count(), 1)
        with self.assertRaises(PermissionDenied):
            self.publish()

    def test_stale_direct_attachment_urls_are_blocked(self):
        pdf = SourceItem.objects.create(consultation=self.case, source_key="publicacao-pdf-ficticio", kind="pdf",
                                        author="simulation", sent_at=timezone.now(), body="Referência fictícia.", filename="ficticio.pdf")
        self.execution_id = execute(self.case.pk, "build_summary", actor=self.actor).execution_id
        self.publish()
        self.client.force_login(self.actor)
        url = reverse("preconsultas:attachment_status", args=[pdf.source_key])
        self.assertEqual(self.client.get(url).status_code, 200)
        SourceItem.objects.filter(pk=pdf.pk).update(description="Metadado alterado.")
        for name in ("attachment_status", "attachment_content"):
            self.assertEqual(self.client.get(reverse(f"preconsultas:{name}", args=[pdf.source_key])).status_code, 403)

    def test_http_post_csrf_authentication_and_invalid_ids(self):
        url = reverse("preconsultas:publish", args=[self.case.slug])
        self.assertEqual(self.client.post(url, {"execution_id": self.execution_id}).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.actor)
        self.assertEqual(client.get(url).status_code, 405)
        self.assertEqual(client.post(url, {"execution_id": self.execution_id}).status_code, 403)
        client.get(reverse("preconsultas:dashboard"))
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post(url, {"execution_id": "invalid", "csrfmiddlewaretoken": token}).status_code, 409)
        self.assertEqual(client.post(url, {"execution_id": self.execution_id, "csrfmiddlewaretoken": token}).status_code, 302)
        self.client.force_login(self.reception)
        self.assertEqual(self.client.post(url, {"execution_id": self.execution_id}).status_code, 403)

    def test_item_from_other_case_and_invalid_review_rejected(self):
        self.publish()
        for action, data in [("correction", {"summary_item_id": 99999, "action": "update", "new_value": "Fictício"}),
                             ("feedback", {"summary_item_id": 99999, "kind": "useful"})]:
            with self.assertRaises(PermissionDenied):
                review_action(self.case.pk, actor=self.actor, action=action, data=data)
        with self.assertRaises(ValidationError):
            review_action(self.case.pk, actor=self.actor, action="note", data={"text": ""})
        self.assertFalse(DoctorNote.objects.exists())
        self.assertFalse(Correction.objects.exists())

    def test_publication_instance_cannot_be_overwritten_or_deleted(self):
        self.publish()
        publication = ClinicalPublication.objects.get()
        with self.assertRaises(ValidationError):
            publication.save()
        with self.assertRaises(ValidationError):
            publication.delete()


    def test_detected_obsolescence_is_sticky_even_if_content_is_restored(self):
        self.publish()
        source = SourceItem.objects.get(pk=self.source_id)
        original = source.body
        SourceItem.objects.filter(pk=source.pk).update(body="Versão fictícia alterada.")
        with self.assertRaises(PermissionDenied):
            source_provenance(self.case.pk, source.pk, actor=self.actor)
        publication = ClinicalPublication.objects.get()
        self.assertIsNotNone(publication.requires_validation_at)
        self.assertEqual(publication.validation_requested_by_id, self.actor.pk)
        SourceItem.objects.filter(pk=source.pk).update(body=original)
        with self.assertRaises(PermissionDenied):
            source_provenance(self.case.pk, source.pk, actor=self.actor)
        self.assertEqual(AIExecution.objects.get(pk=self.execution_id).status, "obsolete")


class PublicationConcurrencyTests(TransactionTestCase):
    def race(self, worker):
        barrier = Barrier(2)

        def run():
            try:
                barrier.wait(timeout=10)
                return worker()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return [f.result(timeout=25) for f in [pool.submit(run) for _ in range(2)]]

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_initial_publication_creates_one_event_and_presentation(self):
        case, _, actor, _, execution_id = publication_fixture()
        receipts = self.race(lambda: publish_consultation(case.pk, execution_id,
                                                        actor=get_user_model().objects.get(pk=actor.pk)))
        self.assertEqual(len({r.publication_id for r in receipts}), 1)
        self.assertCountEqual([r.created for r in receipts], [True, False])
        self.assertEqual(ClinicalPublication.objects.count(), 1)
        self.assertEqual(SummaryItem.objects.count(), 1)
        self.assertEqual(OperationalEvent.objects.filter(kind="ready").count(), 1)

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_corrections_have_ordered_previous_values_and_snapshots(self):
        case, _, actor, _, execution_id = publication_fixture()
        publish_consultation(case.pk, execution_id, actor=actor)
        item = SummaryItem.objects.get()
        from uuid import uuid4
        self.race(lambda: review_action(case.pk, actor=get_user_model().objects.get(pk=actor.pk), action="correction",
                                       data={"summary_item_id": item.pk, "action": "update", "new_value": uuid4().hex}))
        corrections = list(item.corrections.order_by("created_at", "pk"))
        self.assertEqual(corrections[0].previous_value, item.original_value)
        self.assertEqual(corrections[1].previous_value, corrections[0].new_value)
        self.assertEqual(list(item.revisions.values_list("number", flat=True)), [1, 2, 3])


class PublicationMigrationTests(TransactionTestCase):
    def test_upgrade_0009_marks_only_known_seed_and_keeps_old_authorship_null(self):
        from django.core.management import call_command
        call_command("load_demo", verbosity=0)  # Temporary test DB only.
        connection = connections["default"]
        executor = MigrationExecutor(connection)
        before = [("preconsultas", "0009_ai_orchestration")]
        executor.migrate(before)
        try:
            old = executor.loader.project_state(before).apps
            case = old.get_model("preconsultas", "Consultation").objects.get(slug="demo-pronta")
            other = old.get_model("preconsultas", "Consultation").objects.create(slug="ready-sem-publicacao",
                    patient_id=case.patient_id, doctor_id=case.doctor_id, clinic_id=case.clinic_id,
                    status="ready", scheduled_for=timezone.now())
            old.get_model("preconsultas", "DoctorNote").objects.create(consultation_id=case.pk, text="Nota antiga fictícia.")
            old.get_model("preconsultas", "Feedback").objects.create(consultation_id=case.pk, kind="useful")
            item = old.get_model("preconsultas", "SummaryItem").objects.filter(consultation_id=case.pk).first()
            old.get_model("preconsultas", "Correction").objects.create(summary_item_id=item.pk, action="update",
                    previous_value=item.original_value, new_value="Correção antiga fictícia.")
        finally:
            restored = MigrationExecutor(connection)
            restored.migrate(restored.loader.graph.leaf_nodes())
        self.assertTrue(Consultation.objects.get(pk=case.pk).legacy_demo)
        self.assertFalse(Consultation.objects.get(pk=other.pk).legacy_demo)
        self.assertIsNone(DoctorNote.objects.get().actor_id)
        self.assertIsNone(Feedback.objects.get().actor_id)
        self.assertIsNone(Correction.objects.get().actor_id)
        self.assertFalse(ClinicalPublication.objects.exists())
        self.assertFalse(AIExecution.objects.exists())
