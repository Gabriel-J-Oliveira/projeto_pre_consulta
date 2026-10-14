# Motor de estados operacional — proposta demonstrativa

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

actor = get_user_model().objects.get(username="<sua-conta-local-com-perfil>")
case_id = <id-do-registro-ficticio-novo>
transition(case_id, Consultation.STATUS_AWAITING_CONSENT, actor=actor)
transition(case_id, Consultation.STATUS_IN_PROGRESS, actor=actor)
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
