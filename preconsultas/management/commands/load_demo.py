from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from preconsultas.models import (
    Clinic,
    Consultation,
    Correction,
    Doctor,
    DoctorNote,
    Feedback,
    OperationalEvent,
    Patient,
    SourceItem,
    SummaryItem,
)


class Command(BaseCommand):
    help = "Cria ou atualiza o caso fictício da pré-consulta sem apagar outros dados."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-interactions",
            action="store_true",
            help="Remove somente notas, correções e feedback do caso demo.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        clinic, _ = Clinic.objects.update_or_create(
            name="Clínica Horizonte — Unidade Jardins",
            defaults={},
        )
        second_clinic, _ = Clinic.objects.update_or_create(
            name="Centro Médico Aurora — Unidade Itaim",
            defaults={},
        )
        doctor, _ = Doctor.objects.update_or_create(
            display_registration="CRM-SP 000000 (fictício)",
            defaults={"name": "Dra. Helena Costa"},
        )
        doctor.clinics.add(clinic, second_clinic)
        second_doctor, _ = Doctor.objects.update_or_create(
            display_registration="CRM-SP 111111 (fictício)",
            defaults={"name": "Dr. André Souza"},
        )
        second_doctor.clinics.add(second_clinic)
        patient, _ = Patient.objects.update_or_create(
            name="Marina Alves (paciente fictícia)",
            defaults={"age": 42, "phone": "11987651234"},
        )

        today = timezone.localdate()

        def slot(day_offset, hour, minute=0):
            return timezone.make_aware(
                datetime.combine(
                    today + timedelta(days=day_offset),
                    datetime.min.time().replace(hour=hour, minute=minute),
                ),
                timezone.get_current_timezone(),
            )

        consultation, _ = Consultation.objects.update_or_create(
            slug="demo-pronta",
            defaults={
                "patient": patient,
                "doctor": doctor,
                "clinic": clinic,
                "scheduled_for": slot(0, 14, 30),
                "appointment_type": "Consulta clínica",
                "contact_lead_hours": 48,
                "status": Consultation.STATUS_READY,
                "demo_day_offset": 0,
            },
        )

        schedule_rows = [
            ("demo-nao-iniciada", "Camila Nunes (paciente fictícia)", 35, "11911112222", doctor, clinic, 0, 9, 0, "Primeira consulta", Consultation.STATUS_NOT_STARTED),
            ("demo-em-andamento", "Rafael Martins (paciente fictício)", 58, "11922223333", doctor, second_clinic, 0, 10, 30, "Retorno clínico", Consultation.STATUS_IN_PROGRESS),
            ("demo-recepcao-andre", "Paulo Mendes (paciente fictício)", 44, "11933334444", second_doctor, second_clinic, 0, 13, 15, "Cardiologia", Consultation.STATUS_NOT_STARTED),
            ("demo-incompleta", "Joana Ribeiro (paciente fictícia)", 29, "11944445555", doctor, clinic, 0, 16, 0, "Consulta clínica", Consultation.STATUS_INCOMPLETE),
            ("demo-consentimento-recusado", "Beatriz Lima (paciente fictícia)", 51, "11955556666", doctor, second_clinic, 0, 17, 30, "Teleconsulta", Consultation.STATUS_CONSENT_DECLINED),
            ("demo-amanha", "Lucas Prado (paciente fictício)", 46, "11966667777", doctor, second_clinic, 1, 11, 0, "Consulta clínica", Consultation.STATUS_NOT_STARTED),
        ]
        for (
            slug,
            patient_name,
            age,
            phone,
            appointment_doctor,
            appointment_clinic,
            day_offset,
            hour,
            minute,
            appointment_type,
            status,
        ) in schedule_rows:
            schedule_patient, _ = Patient.objects.update_or_create(
                name=patient_name,
                defaults={"age": age, "phone": phone},
            )
            Consultation.objects.update_or_create(
                slug=slug,
                defaults={
                    "patient": schedule_patient,
                    "doctor": appointment_doctor,
                    "clinic": appointment_clinic,
                    "scheduled_for": slot(day_offset, hour, minute),
                    "appointment_type": appointment_type,
                    "contact_lead_hours": 48,
                    "status": status,
                    "demo_day_offset": day_offset,
                },
            )

        source_rows = [
            {
                "source_key": "msg-abertura",
                "kind": "message",
                "author": "ai",
                "sent_at": datetime(2026, 9, 12, 9, 2),
                "body": "Olá, Marina. Vou organizar as informações que você quiser compartilhar antes da consulta. Este é um ambiente demonstrativo.",
            },
            {
                "source_key": "msg-motivo",
                "kind": "message",
                "author": "patient",
                "sent_at": datetime(2026, 9, 12, 9, 4),
                "body": "Quero conversar sobre um desconforto abdominal que aparece depois das refeições há cerca de três semanas. Também tenho sentido estufamento.",
            },
            {
                "source_key": "audio-sintomas",
                "kind": "audio",
                "author": "patient",
                "sent_at": datetime(2026, 9, 12, 9, 7),
                "body": "Mensagem de áudio enviada pela paciente.",
                "description": "Relato sobre frequência do desconforto e fatores percebidos.",
                "duration_seconds": 47,
                "demo_transcript": "[Transcrição fictícia de demonstração] O desconforto costuma começar depois do almoço ou do jantar. Ainda não consegui perceber um alimento específico e não medi a intensidade.",
            },
            {
                "source_key": "msg-medicamentos",
                "kind": "message",
                "author": "patient",
                "sent_at": datetime(2026, 9, 12, 9, 10),
                "body": "Uso levotiroxina 50 mcg pela manhã. Não uso outros medicamentos contínuos. Tenho alergia conhecida a dipirona.",
            },
            {
                "source_key": "msg-antecedentes",
                "kind": "message",
                "author": "patient",
                "sent_at": datetime(2026, 9, 12, 9, 13),
                "body": "Tenho hipotireoidismo acompanhado. Fiz retirada da vesícula em 2019. Minha mãe tem diabetes tipo 2.",
            },
            {
                "source_key": "pdf-exames-laboratoriais",
                "kind": "pdf",
                "author": "patient",
                "sent_at": datetime(2026, 9, 12, 9, 16),
                "body": "Anexei exames laboratoriais de agosto para contextualização.",
                "filename": "exames_laboratoriais_agosto.pdf",
                "description": "Exames laboratoriais — referência fictícia; arquivo ainda não fornecido.",
            },
            {
                "source_key": "pdf-ultrassom-abdominal",
                "kind": "pdf",
                "author": "patient",
                "sent_at": datetime(2026, 9, 12, 9, 17),
                "body": "Também anexei um ultrassom abdominal antigo.",
                "filename": "laudo_ultrassom_abdominal.pdf",
                "description": "Ultrassom abdominal — referência fictícia; arquivo ainda não fornecido.",
            },
            {
                "source_key": "pdf-relatorio-gastro",
                "kind": "pdf",
                "author": "patient",
                "sent_at": datetime(2026, 9, 12, 9, 18),
                "body": "Este é um relatório de uma consulta anterior com gastroenterologista.",
                "filename": "relatorio_gastroenterologia.pdf",
                "description": "Relatório anterior — referência fictícia; arquivo ainda não fornecido.",
            },
            {
                "source_key": "msg-pendente",
                "kind": "message",
                "author": "ai",
                "sent_at": datetime(2026, 9, 12, 9, 21),
                "body": "Obrigada. Ficaram sem confirmação: intensidade do desconforto, alterações intestinais e data exata do último acompanhamento do hipotireoidismo.",
            },
        ]

        sources = {}
        for row in source_rows:
            defaults = row.copy()
            source_key = defaults.pop("source_key")
            defaults["consultation"] = consultation
            defaults["sent_at"] = timezone.make_aware(defaults["sent_at"])
            source, _ = SourceItem.objects.update_or_create(
                source_key=source_key,
                defaults=defaults,
            )
            sources[source_key] = source

        summary_rows = [
            ("overview", "Visão geral", "Contexto reunido", "Paciente relata desconforto abdominal pós-refeições há cerca de três semanas, acompanhado de estufamento. As informações abaixo foram organizadas pela IA para revisão médica.", "ai", ["msg-motivo", "audio-sintomas"]),
            ("reason", "Motivo e contexto", "Queixa principal relatada", "Desconforto abdominal após almoço ou jantar, com estufamento; alimento desencadeante e intensidade ainda não definidos.", "patient", ["msg-motivo", "audio-sintomas"]),
            ("medication", "Medicamentos", "Uso contínuo", "Levotiroxina 50 mcg pela manhã.", "patient", ["msg-medicamentos"]),
            ("allergy", "Alergias", "Alergia informada", "Dipirona.", "patient", ["msg-medicamentos"]),
            ("comorbidity", "Comorbidades", "Condição acompanhada", "Hipotireoidismo.", "patient", ["msg-antecedentes"]),
            ("history", "Antecedentes", "Histórico familiar", "Mãe com diabetes tipo 2.", "patient", ["msg-antecedentes"]),
            ("surgery", "Tratamentos e cirurgias", "Cirurgia relatada", "Colecistectomia em 2019.", "patient", ["msg-antecedentes"]),
            ("exams", "Exames e documentos", "Materiais citados", "Três documentos foram referenciados pela paciente. Os arquivos ainda não foram fornecidos e não foram analisados.", "ai", ["pdf-exames-laboratoriais", "pdf-ultrassom-abdominal", "pdf-relatorio-gastro"]),
            ("pending-intensity", "Informações pendentes ou incertas", "Intensidade e evolução", "Intensidade, progressão e impacto nas atividades não foram informados.", "ai", ["audio-sintomas", "msg-pendente"]),
            ("pending-bowel", "Informações pendentes ou incertas", "Outros sintomas", "Alterações do hábito intestinal e outros sintomas associados não foram confirmados.", "ai", ["msg-pendente"]),
            ("investigate-pattern", "Pontos para investigação pelo médico", "Caracterização do padrão", "Esclarecer frequência, duração, intensidade, fatores de melhora/piora e sintomas associados.", "ai", ["msg-motivo", "audio-sintomas"]),
            ("investigate-followup", "Pontos para investigação pelo médico", "Acompanhamento prévio", "Confirmar a data e o contexto do último acompanhamento do hipotireoidismo.", "ai", ["msg-antecedentes", "msg-pendente"]),
        ]

        for order, (item_key, section, label, value, attribution, source_keys) in enumerate(summary_rows, 1):
            item, _ = SummaryItem.objects.update_or_create(
                item_key=item_key,
                defaults={
                    "consultation": consultation,
                    "section": section,
                    "label": label,
                    "original_value": value,
                    "attribution": attribution,
                    "display_order": order,
                },
            )
            item.sources.set([sources[key] for key in source_keys])

        demo_consultations = Consultation.objects.filter(slug__startswith="demo-")
        for demo_consultation in demo_consultations:
            appointment_at = timezone.localtime(demo_consultation.scheduled_for)
            event_specs = [
                (
                    OperationalEvent.KIND_CREATED,
                    appointment_at - timedelta(days=3),
                    "Registro fictício criado na agenda operacional.",
                    False,
                ),
                (
                    OperationalEvent.KIND_INVITE_PLANNED,
                    appointment_at - timedelta(days=3) + timedelta(minutes=5),
                    (
                        f"Contato previsto para {demo_consultation.contact_lead_hours} horas antes "
                        "— antecedência demonstrativa."
                    ),
                    False,
                ),
            ]
            if demo_consultation.status in {
                Consultation.STATUS_IN_PROGRESS,
                Consultation.STATUS_READY,
                Consultation.STATUS_INCOMPLETE,
                Consultation.STATUS_CONSENT_DECLINED,
            }:
                event_specs.append(
                    (
                        OperationalEvent.KIND_INVITE_SIMULATED,
                        appointment_at - timedelta(days=2),
                        "SIMULADO — nenhum WhatsApp ou mensagem externa foi enviado.",
                        True,
                    )
                )
            if demo_consultation.status == Consultation.STATUS_CONSENT_DECLINED:
                event_specs.append(
                    (
                        OperationalEvent.KIND_CONSENT_DECLINED,
                        appointment_at - timedelta(days=2) + timedelta(minutes=18),
                        "Consentimento não concedido no fluxo fictício.",
                        False,
                    )
                )
            elif demo_consultation.status in {
                Consultation.STATUS_IN_PROGRESS,
                Consultation.STATUS_READY,
                Consultation.STATUS_INCOMPLETE,
            }:
                event_specs.append(
                    (
                        OperationalEvent.KIND_AWAITING_CONSENT,
                        appointment_at - timedelta(days=2) + timedelta(minutes=8),
                        "Convite demonstrativo aberto; consentimento ainda aguardado.",
                        False,
                    )
                )
                event_specs.append(
                    (
                        OperationalEvent.KIND_INTERVIEW_IN_PROGRESS,
                        appointment_at - timedelta(days=1),
                        "Entrevista fictícia iniciada pelo paciente.",
                        False,
                    )
                )
            if demo_consultation.status == Consultation.STATUS_READY:
                event_specs.append(
                    (
                        OperationalEvent.KIND_READY,
                        appointment_at - timedelta(hours=2),
                        "Fluxo operacional concluído; conteúdo disponível somente ao perfil médico.",
                        False,
                    )
                )
            elif demo_consultation.status == Consultation.STATUS_INCOMPLETE:
                event_specs.append(
                    (
                        OperationalEvent.KIND_INCOMPLETE,
                        appointment_at - timedelta(hours=1),
                        "Entrevista fictícia encerrada com informações pendentes.",
                        False,
                    )
                )

            for event_kind, occurred_at, detail, is_simulated in event_specs:
                OperationalEvent.objects.update_or_create(
                    event_key=f"{demo_consultation.slug}-{event_kind}",
                    defaults={
                        "consultation": demo_consultation,
                        "kind": event_kind,
                        "occurred_at": occurred_at,
                        "detail": detail,
                        "is_simulated": is_simulated,
                    },
                )

        if options["reset_interactions"]:
            DoctorNote.objects.filter(consultation=consultation).delete()
            Feedback.objects.filter(consultation=consultation).delete()
            Correction.objects.filter(summary_item__consultation=consultation).delete()
            self.stdout.write("Interações do caso demo reiniciadas; demais dados foram preservados.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Caso demo pronto: {consultation.slug} "
                f"({len(source_rows)} fontes, {len(summary_rows)} itens de resumo)."
            )
        )
