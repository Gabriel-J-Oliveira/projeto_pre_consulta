# Motor de estados e consentimento — simulação pré-IA

O serviço `preconsultas.state_engine.transition` centraliza as transições.
Reutiliza `Consultation.status`: não há segundo campo de estado. Não integra
LLM, WhatsApp, transcrição nem armazenamento externo. Não há endpoint público
ou botões de transição; a validação manual é feita no shell administrativo, com
User ativo explícito passado ao serviço e origem `local_simulation`. O serviço
valida os vínculos desse actor, não autentica uma sessão no shell nem comprova
a identidade/consentimento do paciente. O shell requer acesso administrativo local.

## Estados e compatibilidade

| Conceito | Valor persistido | Compatibilidade |
| --- | --- | --- |
| Registrada | `not_started` | Mantém o rótulo existente “Não iniciada” |
| Aguardando consentimento | `awaiting_consent` | Novo |
| Consentimento recusado | `consent_declined` | Existente |
| Em coleta | `in_progress` | Mantém o rótulo existente “Em andamento” |
| Aguardando confirmação do paciente | `awaiting_patient` | Novo |
| Concluída | `completed` | Novo; não libera acesso clínico |
| Incompleta | `incomplete` | Existente; acesso clínico continua bloqueado |
| Cancelada | `cancelled` | Novo |
| Pronta (legado) | `ready` | Preserva casos demonstrativos e acesso médico atual |

Não se converte `ready` em `completed` nem se altera o estado dos registros
existentes. `ready` continua sujeito ao médico atribuído e à clínica vinculada;
não pode ser produzido por este serviço. Concluir a coleta não prova consentimento
real, não gera síntese e não autoriza abrir conteúdo clínico.

## Grafo permitido nesta simulação

```text
registrada → aguardando consentimento → em coleta → aguardando confirmação → concluída
aguardando consentimento → consentimento recusado
em coleta / aguardando confirmação → incompleta
qualquer estado não terminal acima → cancelada
```

Além do caminho principal, registrada, aguardando consentimento, em coleta e
aguardando confirmação podem passar a cancelada. Em coleta e aguardando confirmação
podem passar a incompleta. Recusada, incompleta, cancelada, concluída e pronta
legada não têm saídas nesta proposta conservadora. Repetição do mesmo estado,
saltos e estados desconhecidos são rejeitados sem evento nem mudança.

As transições são explícitas, sem agendamento, timeout ou cálculo de elegibilidade.
O estado incompleta não implica conteúdo suficiente nem liberação ao médico.
Este grafo serve à simulação local; regras definitivas de automação e reabertura
dependem de confirmação do produto.

## Consentimento versionado e matriz da simulação (PR 01)

D01–D04 aprovadas pelo solicitante em 14/10/2026 apenas para o escopo técnico
pré-IA fictício. Não são validação jurídica/clínica nem matriz de produção.

`ConsentEvidence` associa consulta, referência `term_version` (até 80 caracteres),
manifestação `accepted`/`declined`, momento, origem `local_simulation`, marca
`is_simulated=True`, operador interno e evento operacional exclusivo. Não existe
campo que declare esse operador como paciente autenticado. A versão é uma
referência técnica fictícia; não há catálogo de termos jurídicos aprovados.

Serviço interno `preconsultas.consent.record_simulated_consent`: somente enquanto
aguardando consentimento, uma manifestação por consulta/versão. Repetir ou inverter
essa versão é rejeitado, sem sobrescrita; outra versão pode ser registrada enquanto
o estado permitir. Histórico e eventos anteriores são preservados. Aceite não
inicia coleta; recusa grava evidência e encerra em `consent_declined` na mesma
transação, impossibilitando usar aceite anterior ou reabrir o fluxo.

O motor exige `consent_version` explícita para coleta/recusa: deve corresponder à
evidência mais recente da mesma consulta, com manifestação apropriada, simulação
e evento/operador/origem consistentes. Não existe seleção silenciosa de termo
nem aceite inventado para fixtures. Os demais passos mantêm o grafo anterior.

| Origem | Ator simulado autorizado | Transição/ação | Pré-condição adicional |
| --- | --- | --- | --- |
| `local_simulation` | Médico atribuído, com clínica vinculada OU recepção da clínica | Registrada → aguardando consentimento | Escopo e usuário ativo |
| `local_simulation` | Mesmos perfis e escopos | Registrar aceite/recusa | Aguardando consentimento; versão válida e não repetida |
| `local_simulation` | Mesmos perfis e escopos | Aguardando consentimento → em coleta | Última evidência de aceite; versão explícita correspondente |
| `local_simulation` | Mesmos perfis e escopos | Aguardando consentimento → recusada | Última evidência de recusa; serviço de registro executa atomicamente |
| `local_simulation` | Mesmos perfis e escopos | Em coleta → aguardando confirmação; confirmação → concluída | Aresta do grafo, sem confirmação real inferida |
| `local_simulation` | Mesmos perfis e escopos | Coleta/confirmação → incompleta; não terminais → cancelada | Transição explícita; nenhuma falha técnica dispara encerramento |
| Qualquer | Admin técnico sem vínculo, sem perfil, inativo, anônimo, fora do escopo | Qualquer ação | Negada |
| Outra origem | Qualquer ator | Qualquer ação | Negada |
| `local_simulation` | Qualquer ator | Sair de terminal ou produzir `ready` | Negada |

Perfis duplos somam somente seus vínculos explícitos. Política centralizada em
`TRANSITION_POLICY`, com negação por padrão; não autoriza conteúdo clínico.
Estados legados em coleta/confirmação podem seguir as arestas existentes, sem
retrocriar evidências. Novas entradas em coleta passam obrigatoriamente pelo gate.
`ready` permanece apenas legado; serviço de publicação será tratado na PR 05.

Migração aditiva `0006_simulated_consent_evidence`: tabela nova, unicidade por
consulta/versão e constraints de manifestação/simulação, mais tipo de evento.
Não contém backfill ou alteração dos estados/dados existentes. Evidências não
podem ser sobrescritas/excluídas por métodos de instância e protegem referências
de consulta/operador/evento contra exclusão; não são registradas no Admin. Essa
proteção de aplicação NÃO é armazenamento WORM: SQL/QuerySet privilegiados ainda
podem alterar dados e devem ficar fora dos fluxos de domínio.

## Escopo, transação e auditoria

- Usuário ativo com perfil médico pode atuar apenas em consultas atribuídas a seu
  cadastro e em suas clínicas. Recepção pode simular somente registros operacionais
  das clínicas vinculadas. Perfis independentes somam seus escopos explícitos.
- Staff/superusuário sem vínculo não ganha acesso. IDs inexistentes ou fora do
  escopo recebem a mesma negação, sem revelar estado ou dados de outra clínica.
- `select_for_update` serializa atualizações no PostgreSQL. A atualização também
  verifica o estado anterior; SQLite não oferece o mesmo bloqueio por linha.
- Estado e `OperationalEvent` são gravados numa transação. Uma falha no evento
  desfaz a mudança. Cada evento guarda estado anterior/novo, usuário, origem e
  data/hora real, com `is_simulated=True` e sem conteúdo clínico.
  Eventos do motor não recebem o deslocamento de datas usado nas fixtures.
- A migração 0005 acrescenta metadados opcionais aos eventos e escolhas de estado.
  Eventos antigos ficam com origem/estados vazios e usuário nulo, sem inventar autoria.
- `load_demo` continua um bootstrap explícito de fixtures, não uma chamada ao motor.
  Não o execute para testar transições sobre o banco de validação: ele restaura
  os estados dos casos demonstrativos existentes.

## Validação manual

Use uma conta local já existente com perfil de recepção ou médico. Não use o
superusuário sem perfil e não crie credenciais padrão. No worktree, configure o
mesmo ambiente de desenvolvimento conforme README e execute:

```powershell
python manage.py migrate
python manage.py shell
```

Escolha uma pré-consulta **fictícia nova**, cadastrada no formulário da recepção,
para não alterar casos-base. No shell, substitua os placeholders pelo usuário
autorizado e ID desse registro (nenhuma senha é necessária):

```python
from django.contrib.auth import get_user_model
from preconsultas.models import Consultation
from preconsultas.state_engine import transition
from preconsultas.consent import record_simulated_consent
from preconsultas.models import ConsentEvidence

actor = get_user_model().objects.get(username="<sua-conta-local-com-perfil>")
case_id = <id-do-registro-ficticio-novo>
transition(case_id, Consultation.STATUS_AWAITING_CONSENT, actor=actor)
record_simulated_consent(case_id, term_version="sim-v1", manifestation=ConsentEvidence.ACCEPTED, actor=actor)
transition(case_id, Consultation.STATUS_IN_PROGRESS, actor=actor, consent_version="sim-v1")
transition(case_id, Consultation.STATUS_AWAITING_PATIENT, actor=actor)
transition(case_id, Consultation.STATUS_COMPLETED, actor=actor)
```

Recarregue a recepção na porta 8001 e abra o registro: estado e eventos `SIMULADO`
aparecem na linha do tempo. O médico atribuído vê o estado no painel, sem link
de abertura clínica. Tentar saltar de registrada para concluída levanta
`InvalidTransition`; tentar ID fora do vínculo levanta `PermissionDenied`.

## Decisões pendentes

Não estão definidos: prova real de consentimento e confirmação, permissões de
transição em produção, motivos e critérios para cancelar/incompletar, reabertura,
retomada após recusa, timeout, geração/revisão de síntese e promoção para pronta.
Nenhuma dessas decisões é implementada como automação ou autorização clínica.
Uma interface de transições ou origem real deve ser aprovada separadamente.

Testes cobrem rollback de evidência/eventos/estado e upgrade 0005→0006 sem
consentimento inventado. Dois testes concorrentes usam conexões reais e barreira
no PostgreSQL (duplicação de versão e início de coleta); são ignorados no SQLite,
que não tem bloqueio de linha. SQLite aprovado não comprova essa concorrência.

## Interface com ingestão (PR 02)

`ingestion.ingest_message` reutiliza `lock_scoped_consultation` e `require_consent`,
sem mudar o grafo, `Consultation.status` ou eventos do motor. Ingestão (inclusive
replay) exige coleta e último aceite simulado/versão explícita; não preenche
consentimento de casos legados. O lock da consulta coordena ingestão, estado e
consentimento no PostgreSQL. A entrada privada referencia a evidência usada,
sem texto clínico em OperationalEvent. Não é transformação em fonte clínica.
Contrato: [contexto](planning/README.md#16-contrato-de-ingestão-pr-02--d05-restrita-à-simulação).
