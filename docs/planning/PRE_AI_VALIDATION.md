# Evidências reproduzíveis — PR 06

Execução de 17/10/2026, base `640e0350aed3878fe4171f30bdc6e9ad4658f59e`,
branch `chore/pre-ai-handoff`. Dados fictícios; banco temporário do runner.
Resultados/SHAs/PR/CI reais ficam no [ROADMAP](ROADMAP.md) e na descrição/checks
da PR, sem duplicar logs ou antecipar aprovação do HEAD final.

## Resultados registrados

Implementação publicada na [PR #14](https://github.com/Gabriel-J-Oliveira/projeto_pre_consulta/pull/14),
SHA `a8a5156b31023bc6e0fbd4808ac722123eb73884`, sem merge.

| Execução | Backend/ambiente | Resultado |
| --- | --- | --- |
| Regressão inicial dos 219 anteriores | SQLite temporário | 209 aprovados, 10 concorrentes ignorados; 44,387 s |
| Suíte final 219 anteriores +16 novos | SQLite temporário | 223 aprovados, 12 concorrentes ignorados; 235 encontrados, 51,668 s |
| Visual opt-in final | Windows, Node 24.19.0, Playwright 1.62.1, Edge existente detectado, DB temporário/porta dinâmica | 3 testes, oito invocações aprovadas, 57,819 s; desktop/mobile e capturas inspecionadas |
| Seletor de browser Node | Sem DB/Playwright/browser reais nos testes unitários | Oito aprovados |
| Handoff/fake offline | Python 3.14.4 com -S, biblioteca padrão | Dois exemplos executáveis, ai_examples e conformidade de três operações/quatro tipos aprovados, sem Django/site-packages |
| CI da implementação a8a5156 | PostgreSQL 17.11, Python 3.14, serviço descartável | [Run 39039513356](https://github.com/Gabriel-J-Oliveira/projeto_pre_consulta/actions/runs/39039513356): 235 aprovados sem skips, 42,880 s; check/drift/migrate/demo duas vezes aprovados |

A CI acima validou explicitamente a implementação, incluindo os doze ensaios de
concorrência. Este registro documental é um commit posterior; conferir a CI de
seu HEAD final nos checks da PR. Browser/Node unitários foram locais, NÃO CI.
Nenhum banco/servidor preservado foi alterado; três hashes SQLite permaneceram
iguais. Diff e 97 links locais revisados, sem arquivos sensíveis/artefatos no Git.
Primeira rodada visual encontrou referência notes em vez de doctor_notes no novo
harness; corrigida. Inspeção corrigiu timing da captura de animação na recepção.
Todas as repetições finais passaram, sem mudança de regras funcionais.

## Matriz de cenários automatizados

Novos testes em [test_pre_ai_integration.py](../../preconsultas/test_pre_ai_integration.py).
Usam TransactionTestCase e serviços reais; caminho positivo inicia em POST da
recepção, não em ORM que force completed/ready. Setups criam usuários sem senha
utilizável. A escrita hostil em ready é exclusivamente um cenário negativo.

| Cenário | Teste novo (prefixo test_) | Garantia observada |
| --- | --- | --- |
| Fluxo completo A–G | full_reception_consent_ingestion_provenance_three_operations_publication_review | Cadastro HTTP, aceite/versão, quatro tipos de entrada, fontes idempotentes, três operações/ai.v1, POST de publicação, tela, nota/correção/feedback com ator, revisões e fontes/resultado originais; sem rede |
| Reentrega/conflito/ordem | replays_conflicts_equal_content_distinct_ids_and_out_of_order_materialization | Preserva entrada original/operador; IDs distintos e horários declarados fora de ordem; fonte única |
| Aceite ausente/incorreto/recusa | absent_wrong_declined_consent_and_terminal_state_block_the_pipeline | Sem início de coleta, ingestão/processamento ou reabertura após recusa |
| Estado e mídia inválidos | operation_state_gates_and_invalid_media_leave_no_partial_pipeline | Não publica por processamento; rejeita MIME/path/referência e operação fora do estado |
| Contrato/fontes/saída | invalid_contract_source_version_external_reference_and_empty_result_never_publish | Versão ai desconhecida, versão de fonte errada/externa e síntese vazia impedem publicação |
| Retry explícito recuperado | transient_failure_explicit_retry_success_preserves_attempt_then_publishes | Mesma identidade, tentativa anterior preservada e liberação explícita posterior |
| Limite de tentativas | three_attempt_limit_never_retries_automatically_or_publishes | Máximo três, sem ready ou retry automático |
| Finalização indisponível | finalization_failure_preserves_running_and_sanitizes_errors_without_reexecution | Rollback de aceitação, reserva running preservada; erro sem texto clínico, replay não chama fake |
| Rollback da publicação | publication_snapshot_failure_rolls_back_but_keeps_original_execution_and_sources | Nenhum item/publicação/evento parcial; execução/fontes preservadas |
| Rollback/idempotência da revisão | correction_failure_after_write_rolls_back_and_repetition_is_idempotent | Correção e snapshot atômicos; sem revisão duplicada na repetição |
| Escopos de publicação | roles_other_doctor_and_unlinked_clinic_never_publish_or_read | Recepção/admin/outro médico e perda de clínica negados |
| Paciente compartilhado | patient_identity_does_not_expand_history_or_allow_foreign_corrections | Histórico restrito, mensagem/execução/item externo rejeitados |
| Nova fonte após ready | new_materialized_source_invalidates_all_clinical_surfaces_without_state_change | Serviços reais alteram contexto; detalhe/anexo/POST/histórico bloqueados; marcador e resultado preservados |
| Autorização/ready forjado | authorization_loss_and_forged_ready_do_not_grant_new_clinical_access | Flag ORM não publica; conta inativa sem sessão/read/processamento |
| Disputa de estado PostgreSQL | operational_transition_during_processing_invalidates_reserved_result | Fake pausado fora do lock; outra conexão muda estado, duplicata observa running; finalização obsolete |
| Disputa de fontes PostgreSQL | materialization_during_build_requires_new_context_before_publication | Materialização durante build invalida reserva; nova execução/contexto necessários antes de publicar |

Os últimos dois testes pertencem a PreAIConcurrencyTests; os demais a
PreAIIntegrationTests. São 16 novos, somados aos 219 anteriores sem remoções.
SQLite ignora os dois novos e os dez ensaios concorrentes anteriores; não é
evidência de serialização por linha. CI PostgreSQL deve executá-los sem skips.

## Cobertura anterior preservada e complementar

- [Consentimento](../../preconsultas/test_consent.py): evidência estrangeira,
  coerência do evento, versões/recusa e dois testes concorrentes.
- [Ingestão](../../preconsultas/test_ingestion.py): envelope/erros sem payload,
  mídia inválida, replay fora do estado, isolamento e duas disputas de ID/conteúdo.
- [Proveniência](../../preconsultas/test_traceability.py): materializações/snapshots
  concorrentes, fontes externas, metadados, rollback e histórico entre clínicas.
- [Orquestração](../../preconsultas/test_ai_orchestration.py): todas as matrizes de
  estado, provedores/contratos inválidos, escopo revogado durante chamada, execução
  e retry concorrentes, falha de finalização e proibição de atomic externo.
- [Publicação](../../preconsultas/test_publication.py): consentimento incoerente,
  falhas/running/obsolete, attention-only, snapshot rollback, POST/CSRF, autoria
  histórica nula, duas publicações/correções concorrentes e bloqueio persistente.
- [Contrato](../../preconsultas/test_ai_contract.py): harness/fixtures/erros/schema
  estritos e conformidade independente de banco. Autenticação, recepção, pacientes
  e permissões permanecem na suíte completa, não substituídos pelo E2E.
- Testes de upgrade nas suítes acima preservam 0001–0010 sem reiniciar histórico;
  PR 06 não modifica modelos/migrações nem exige 0011.

## Smokes e inspeção visual

[visual_smoke.py](../../preconsultas/visual_smoke.py) é opt-in, NÃO descoberto pela
suíte padrão da CI. Executa scripts existentes em DB temporário/porta dinâmica,
credencial efêmera e capturas UUID ignoradas em artifacts/. Não toca 8000/8001.
Reutiliza seis scripts, com publication_smoke executado também após invalidação:

- dashboard_smoke/browser_smoke: painel e caso legado, desktop/mobile.
- publication_smoke: completed bloqueado, POST explícito, síntese simulada,
  referências, nota/correção/feedback e bloqueio obsoleto de detalhe/anexos/POST.
- reception_smoke: operação, máscara, formulários/filtros e ausência de conteúdo.
- permissions_smoke: recepção e admin técnico sem acesso clínico, em dois perfis.
- patient_registration_smoke: escolha explícita/reutilização sem gravar novo paciente.

Capturas ajudam inspeção humana de layout, não certificam usabilidade ou segurança.
Backend E2E comprova persistência/autoria; browser comprova interação/respostas.
Seleção de navegador tem oito testes Node sem Playwright/DB/navegador reais em
[smoke_browser.test.cjs](../../scripts/smoke_browser.test.cjs). Esses testes não
substituem lançamento real nem aprovam Linux/macOS não executados nesta máquina.
Diagnóstico de dependência ausente significa smoke NÃO executado, nunca aprovado.

CI padrão mantém PostgreSQL 17 e suíte Django, sem browser opt-in nesta entrega:
não há navegador/dependência Node provisionados no workflow atual. Não adicionar
um gate que dependa do desktop pessoal. O helper permite Chromium já provisionado
em execução futura, com autorização/provisionamento explícitos. Nenhum download
automático ocorre. Comandos e configuração: [deploy](../deploy.md#6-testes-e-verificações).

## Limites e revisão humana

Resultado automatizado não aprova contrato/handoff, semântica clínica, prova de
consentimento ou produção. SQL/ORM privilegiado não é fronteira WORM/RLS; não há
certificação de desempenho, recuperação de running, republicação, storage ou
retenção. Estado por capacidade e gates humanos: [matriz de prontidão](READINESS.md).
Não houve homologação real, Notion ou integração com serviços externos.
