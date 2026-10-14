# Contexto do projeto de pré-consulta para planejamento com IA

Referência conceitual oficial, auditada em **14/10/2026** sobre a base
`1e199b4577d8a6c64b30c3744d4bea4adfd308bf`, preparada a partir do código e da documentação
do repositório público `Gabriel-J-Oliveira/projeto_pre_consulta`. Este arquivo é
autossuficiente para ser anexado a um chat de planejamento. Descreve o que existe,
o que é demonstrativo e o que ainda depende de decisão. A sequência Pré-IA foi
solicitada pela equipe; suas regras específicas e interfaces ainda exigem aprovação.
Atualização PR 01: base empilhada `47092e62196ae3705ece7246be3199c0d1b0a6de`,
branch `feature/pre-ai-domain-consent`; D01–D04 aprovadas em 14/10/2026 somente
para simulação técnica pré-IA. PR 00/#8 e PR 01 não estão integradas à main.
Atualização PR 02: branch empilhada `feature/pre-ai-event-ingestion`, base PR #9,
SHA `fae081e3796a780a0d5878338393585c86b4e6f3`. Ingestão técnica autorizada;
D05 é proposta restrita ao simulador, não contrato definitivo de canal real.
Atualização PR 03: D06 aprovada expressamente pelo solicitante em 14/10/2026
para o recorte técnico fictício do prompt; branch `feature/pre-ai-traceability`
baseada em PR #10, SHA `76818a0acd49f72bda518ca65ea6e43beb306bc5`. Sem merge.
Não contém credenciais, dados pessoais, banco local ou documentos de pacientes.

Atualização PR 04: D07 aprovada tecnicamente pelo solicitante em 14/10/2026,
exclusivamente fictícia; `feature/pre-ai-orchestration`, base PR #11 no SHA
`6f91164ba8cb66c97c4a6daff159d6bf6fbffdb3`. Contrato e handoff em revisão,
não aprovados só por publicação. Nenhum merge, IA real ou início de PR 05.

## 1. Produto e estágio atual

O objetivo é apoiar a preparação de consultas médicas: a recepção registra uma
pré-consulta, o paciente participa da coleta e confirmação de informações, e o
médico revisa o material antes do atendimento. A interface demonstra conversa,
fontes, anexos e síntese estruturada, incluindo ajustes e apontamentos médicos.

**Hoje é um protótipo com dados exclusivamente fictícios**, não um sistema em
produção ou pronto para receber dados reais. As telas operacionais e médicas,
autenticação, isolamento e persistência local existem. Coleta real com paciente,
LLM, WhatsApp, transcrição e infraestrutura externa não estão integrados.
Exibir uma “síntese da IA” no protótipo não significa que uma LLM foi executada.

Não há URL pública de produção confirmada. A validação nesta máquina usa a porta
8001 em um worktree separado, com SQLite explícito e banco próprio preservado.
A cópia principal da porta 8000 deve permanecer independente; disponibilidade
de um servidor local não deve ser inferida apenas pela documentação.

## 2. Tecnologias e arquitetura preservadas

- Python 3.14; `Django==6.1.1`.
- `python-dotenv==1.2.3` para configuração local.
- PostgreSQL como backend padrão por ambiente, driver `psycopg[binary]==3.3.6`.
- PostgreSQL 17 no serviço descartável de CI. SQLite somente com seleção explícita.
- Templates Django, CSS e JavaScript existentes; sem reescrita de frontend.
- Usuário padrão de Django, autenticação por sessão e proteção CSRF nativas.

Organização:

```text
medprep/           configuração, composição de URLs e seleção do banco
accounts/          autenticação: views, URLs, testes e template próprios
preconsultas/      domínio: modelos, forms, views, URLs, permissões e estados
                   templates/preconsultas/, migrations/, management/commands/
static/preconsultas/  estilos e comportamento das telas
scripts/           smoke tests de navegador com Playwright/Edge
docs/state-engine.md  proposta detalhada e validação do motor de estados
```

`accounts` não tem modelos de domínio. Consulta a função pública de destino
pós-login em `preconsultas.permissions`, sem duplicar as políticas do domínio.
Os modelos continuam em `preconsultas`; não foram movidos entre apps e não foi
reiniciado o histórico de migrações. Não existem apps vazios para agendamento ou
prontuário: serão criados somente quando essas funcionalidades entrarem no escopo.

## 3. Modelo de dados e vínculos

- `Clinic`: cadastro de clínica.
- `Doctor`: cadastro médico, `user` opcional OneToOne com User nativo e
  `clinics` ManyToMany já existente. Não criar uma segunda relação médico–clínica.
- `ReceptionProfile`: User OneToOne e clínicas ManyToMany.
- `Patient`: nome, telefone e campo legado opcional de idade. O fluxo manual
  aprovado usa **somente nome e telefone**, sem acrescentar idade/nascimento.
- `Consultation`: paciente, médico, clínica, slug, data/hora, tipo de atendimento,
  antecedência demonstrativa, estado e deslocamento de data das fixtures.
- `SourceItem`: fontes fictícias de mensagem, áudio e PDF; texto/transcrição
  demonstrativa e metadados locais.
  PR 03 acrescenta tipo imagem e origem de simulação; vínculo OneToOne opcional
  à mensagem recebida, momento/operador da materialização. Legados continuam nulos.
- `SummaryItem`: itens estruturados, atribuição e referências às fontes.
- `DoctorNote`, `Correction`, `Feedback`: interações médicas persistidas.
- `OperationalEvent`: linha do tempo operacional. Eventos do motor guardam
  estado anterior/novo, origem, usuário, data/hora real e marca de simulação.
- `ConsentEvidence` (PR 01): consulta, referência da versão apresentada,
  manifestação simulada, origem, momento, operador interno e evento exclusivo.
  Não representa identidade autenticada do paciente ou prova jurídica.
- `InboundMessage` (PR 02): entrada privada durável, com namespace/versão/tipo,
  texto OU metadados de mídia, horários declarado/real, operador e evidência
  simulada aplicável. Não é `SourceItem` e não é exposta à recepção ou ao Admin.
- `SummaryRevision` e `SummaryRevisionSource` (PR 03): snapshots explícitos do
  item de resumo existente e suas fontes, com revisão, chave lógica, momento e
  operador da captura. Não geram resumo nem definem payload de resultado da IA.
- `AIExecution`, `AIAttempt`, `AIExecutionSource` (PR 04): execução técnica privada,
  tentativas explícitas e referência fonte/versão, independentes de SummaryRevision.
  Request e resultado validado permanecem privados; não aparecem no Admin/UI.

Migrações `0001`–`0003` preservam o protótipo original; `0004` acrescenta vínculos
internos; `0005_operational_state_engine` acrescenta metadados opcionais de eventos
e escolhas de estado. Não há migração de dados que transforme os estados antigos.
`0006_simulated_consent_evidence` acrescenta tabela/constraints de consentimento
e tipo de evento, sem backfill de manifestações ou alteração de estados legados.
`0007_inboundmessage` acrescenta somente tabela e constraints de entrada, sem
converter fontes/resumos existentes ou criar mensagens para registros históricos.
`0008_source_provenance_summary_revisions` acrescenta vínculos opcionais às fontes,
escolhas de imagem/simulação e tabelas de snapshots/referências. Sem backfill.
`0009_ai_orchestration` cria somente as três tabelas técnicas/constraints, sem
backfill de execuções, alteração de domínio ou migração de dados legados.

## 4. Autenticação e autorização são separadas

Login e logout existem para usuários **internos**, não para pacientes. Login
inválido retorna mensagem genérica; `next` externo é rejeitado; logout exige POST
e CSRF. Rotas internas, anexos e ações médicas são protegidos no servidor.

- Médico acessa somente consultas atribuídas ao seu cadastro e em clínicas
  vinculadas. Outra consulta da mesma clínica não se torna acessível por isso.
- Recepção opera somente nas clínicas de seu perfil e vê nome, telefone
  mascarado, agenda, estado e eventos operacionais. Não vê resumo, conversa,
  respostas, áudio, transcrição, anexos ou ações clínicas, nem por URL direta.
- Administração técnica gerencia contas e cadastros permitidos, sem acesso
  clínico implícito. `is_staff` ou superusuário não substituem vínculos.
- Django Admin mantém usuários/grupos, clínicas, médicos e perfis de recepção;
  pacientes e modelos clínicos não são registrados, inclusive para superusuário.
- Sem perfil/vínculo, acesso é negado. Perfis médico e recepção são independentes.

Um usuário que consegue acessar o Admin, mas recebe 403 nas outras telas, pode
estar corretamente bloqueado por falta de perfil. A solução é conferir vínculos,
não remover a autorização nem conceder acesso clínico global a administradores.

## 5. Telas e funcionalidades implementadas

Rotas principais, relativas à URL da instância:

- `/accounts/login/`: login interno.
- `/medico/painel/`: agenda demonstrativa, filtros e estados operacionais.
- `/medico/pre-consultas/demo/`: caso-base pronto.
- `/medico/pre-consultas/<slug>/`: consulta atribuída e autorizada.
- `/recepcao/pre-consultas/`: lista operacional e formulário lateral de cadastro.
- `/admin/`: gestão técnica restrita.

As telas médicas oferecem visualização de síntese/fontes e registro de notas,
correções e feedback. Anexos são arquivos demonstrativos locais ignorados pelo
Git; arquivos ausentes recebem estado amigável, sem alegar processamento real.
Todas as telas internas mantêm saída por POST. Não há portal do paciente.

## 6. Cadastro manual e reutilização explícita de pacientes

O formulário da recepção valida vínculo médico–clínica no servidor. Procura
candidatos somente quando **nome completo normalizado e telefone normalizado**
coincidem, dentro dos pacientes que já têm consultas em clínicas autorizadas.

Nome: Unicode NFKC, espaços normalizados e casefold, sem remoção de acentos.
Telefone: somente dígitos, com 10 ou 11 dígitos conforme a validação atual.

Havendo correspondências, o formulário exige escolher explicitamente um registro
ou criar novo. Sem correspondência, cria novo. A escolha é validada no servidor e
reconsultada antes de persistir. Não há reutilização por telefone isolado,
telefone único, mesclagem automática nem CRUD separado de pacientes.

Paciente novo, pré-consulta e eventos operacionais são criados em transação.
Reutilizar não altera a identidade do paciente existente. O registro começa em
`not_started`; nenhum convite real é enviado. A antecedência de 24/48/72 horas
continua demonstrativa, sem agendamento real.

## 7. Motor de estados: proposta local, não automação de produção

Reutiliza `Consultation.status`. Não cria um segundo estado. O serviço
`preconsultas.state_engine.transition(id, destino, actor=usuario)` centraliza
as transições, verifica escopo e usuário ativo, rejeita saltos e grava estado e
evento atomicamente. Origem habilitada: apenas `local_simulation`.
O serviço `record_simulated_consent` registra uma manifestação por consulta/versão
somente aguardando consentimento. Aceite deixa o estado aguardando; recusa grava
evidência/eventos e estado terminal atomicamente. Versões anteriores não são
sobrescritas. Início de coleta exige a última evidência de aceite e referência
de versão explícita `consent_version`; versão ausente/divergente é rejeitada.
A matriz simulada preserva médico atribuído/clínica e recepção/clínica, nega
admin sem vínculo, outras origens e atores sem escopo. Detalhes no
[motor](../state-engine.md); a matriz de produção permanece pendente.

| Conceito | Valor persistido |
| --- | --- |
| Registrada, mantendo o rótulo legado “Não iniciada” | `not_started` |
| Aguardando consentimento | `awaiting_consent` |
| Consentimento recusado | `consent_declined` |
| Em coleta, mantendo o rótulo legado “Em andamento” | `in_progress` |
| Aguardando confirmação do paciente | `awaiting_patient` |
| Concluída | `completed` |
| Incompleta | `incomplete` |
| Cancelada | `cancelled` |
| Pronta, estado legado de liberação clínica | `ready` |

Caminho principal: registrada → aguardando consentimento → em coleta → aguardando
confirmação → concluída. Consentimento pode ser recusado enquanto aguardado.
Coleta ou confirmação podem passar a incompleta. Estados não terminais desse
fluxo podem passar a cancelada. Estados finais não têm saídas nesta proposta.

**Concluída não equivale a Pronta.** O motor não produz `ready`; preserva os casos
prontos legados e não libera conteúdo clínico por mudança operacional.
`incomplete` também continua bloqueado clinicamente. Todas as transições são
simulações explícitas: não constituem prova de consentimento real do paciente.

Há bloqueio de linha no PostgreSQL e atualização condicionada ao estado anterior.
Falha de persistência do evento desfaz a mudança. Eventos novos não recebem o
deslocamento de datas das fixtures. Eventos antigos preservam seus dados e não
ganham autoria inventada. Não há rota HTTP ou botão de transição nesta etapa;
a validação manual está em `docs/state-engine.md`.

## 8. Operação e evidências técnicas

[docs/deploy.md](../deploy.md) é a referência única para instalação, variáveis
suportadas, PostgreSQL/SQLite, migrações, testes e preparação de homologação.
Cada desenvolvedor tem seu próprio `.env` e banco, não publicados. Não existe
fallback silencioso, conversão automática de banco nem implantação confirmada.

Resultados por entrega e backend ficam no [ROADMAP](ROADMAP.md), não são inferidos
da configuração do workflow. A base tem 86 testes, cobrindo autenticação/CSRF,
permissões, cadastro, rollback e estados. A CI real da `main` de referência passou
com PostgreSQL 17.11 e 86 testes em 11/10/2026; isso não é uma execução da PR 00.

## 9. Colaboração, branches e publicação

Equipe de dois desenvolvedores, branches curtas por tarefa e revisão entre eles;
sem branches permanentes por pessoa. Não usar force push nem contornar proteção.
Este repositório foi iniciado vazio para receber o protótipo existente, mantendo
o código validado, sem copiar bancos ou arquivos locais. O histórico Git foi
preservado posteriormente, junto às branches e registros das etapas antigas.
A origem técnica foi o snapshot `5474f4f` da antiga branch
`feature/preconsultation-state-engine`; não é uma reescrita da aplicação.

Fluxo atual:

```text
main (projeto completo: autenticação, permissões, pacientes e motor de estados)
  ← novas branches curtas por card
```

As antigas PRs #1–#4 permanecem intactas no repositório anterior, sem bloquear
este repositório. A nova PR #1 foi mesclada em `main`, reunindo todos os módulos.
As novas PRs #2–#6 são registros históricos fechados sem merge, não entregas
pendentes nem aprovações transferidas. As branches antigas preservam seus SHAs;
a antiga `main` está em `archive/previous-main`. Consulte
`docs/repository-migration.md` para o mapa e o histórico.

Fluxo padrão: branches curtas a partir da `main` integrada. Exceção autorizada
em 14/10/2026: PR 01 empilhada sobre `chore/prepare-pre-ai`, dependente de #8,
sem aguardar seu merge. Nenhum merge autorizado; aguardar CI real e revisão.
Proteção/rulesets não estavam
configurados na nova `main` durante a migração; configurá-los é uma pendência
para colaboração, não uma regra que tenha sido removida ou contornada.
Consultar `CONTRIBUTING.md` e a proteção atual; a autorização do solicitante para
merge não substitui os requisitos de revisão/checks do GitHub.

## 10. Decisões de produto e tarefas futuras

Não tratar os pontos abaixo como já aprovados ou implementados:

- Coleta real e prova/versionamento do consentimento e da confirmação do paciente.
- Permissões de transição em produção, interface para operar o motor e origens reais.
- Critérios/motivos de incompletude e cancelamento, timeout, retomada e reabertura.
- Elegibilidade clínica dos casos incompletos e liberação de conteúdo.
- Geração, revisão e promoção da síntese para `ready`, sem confundir coleta concluída
  com conteúdo pronto para revisão médica.
- Integração LLM, WhatsApp, transcrição, jobs, tentativas, idempotência e falhas externas.
- Armazenamento externo, upload, retenção e proteção de documentos reais.
- Agendamento completo, prontuário e eventual experiência do paciente.
- Hardening, gestão de segredos, backup, observabilidade, implantação e conformidade
  para uso com dados reais. A arquitetura atual não constitui certificação disso.
- Otimização da busca normalizada de pacientes em grande volume.

Não houve leitura atual do Notion para este snapshot. Novas regras devem ser
confirmadas com a equipe e com documentos de produto autorizados, sem preencher
lacunas por suposição. Planejamento pode propor alternativas, não marcá-las como
decisões já tomadas nem declarar cards concluídos.

## 11. Como usar este contexto em outro chat

Anexe este arquivo e descreva o objetivo do planejamento. Peça que a IA separe:
implementado, demonstrativo, pendente de validação técnica e pendente de decisão
de produto. Para cada card, solicite escopo, dependências, critérios de aceite,
testes, riscos e decisões necessárias, preservando as permissões já acordadas.

Antes de orientar uma implementação, confira o SHA e os arquivos atuais: este
documento é um snapshot, não sincronização automática do código ou do Notion.
Não envie `.env`, SQLite, senhas, tokens, documentos privados ou dados de pacientes
ao chat. Mais contexto técnico pode ser obtido no README da raiz,
`docs/state-engine.md`, testes e arquivos do domínio — sempre sem segredos.

## 12. Divisão de responsabilidades e limites da trilha Pré-IA

O produto-alvo é SaaS Pré Consulta. “Lume Saúde” permanece a identidade visual
demonstrativa existente; PR 00 não faz rebranding ou muda telas. Multi-clínica
hoje significa vínculos e filtros no servidor, não um novo modelo de tenant
ou isolamento por schemas PostgreSQL. Não redesenhar essa arquitetura por suposição.

Desenvolvedor de backend (solicitante): domínio/regras, consentimento/estados,
entrada unificada, persistência/versionamento/rastreabilidade, orquestração
determinística, contratos de integração, provedor fictício, consumo/publicação
e revisão médica, testes, segurança, infraestrutura e documentação.

Outro desenvolvedor (IA): modelos reais, entrevista adaptativa/perguntas,
extração/estruturação, resumos/pontos de atenção, prompts e validação semântica
dos resultados. O backend também valida formato, versão, fontes, contexto,
idempotência e autorização; essas garantias não são delegadas à IA.

Sprint posterior: WhatsApp Cloud API, webhooks/mensagens reais e recebimento de
mídia. Agora, nenhuma chamada real a LLM, WhatsApp, transcrição ou storage externo.
Não implementar portal de pacientes, apps vazios de agendamento/prontuário,
dados reais ou substituição ampla de tecnologias dentro desta preparação.

## 13. Fluxo-alvo e interface de IA — planejamento, não implementação

Fluxo-alvo da trilha: cadastro → evidência versionada de consentimento → entrada
de mensagens/eventos simulados → fontes preservadas e dados versionados →
orquestração determinística/FakeAIProvider → validação de resultado → publicação
clínica controlada → revisão médica/correções/feedback. Gates e dependências
ficam no [ROADMAP](ROADMAP.md). Hoje o cadastro e o simulador de estados existem;
coleta/consentimento reais, pipeline e publicação de resultados novos não existem.

Interface prevista (a acordar com o desenvolvedor de IA em PR 04): o backend
entrega contexto/fontes autorizados e versionados, por um contrato independente
do provedor; o adaptador retorna resultado estruturado com versão e proveniência.
O backend valida e persiste ou rejeita, registrando falha/tentativa sem liberar
conteúdo clínico. Retentativa/execução técnica não é estado operacional duplicado.
Na auditoria inicial DTOs e fake não existiam. A branch PR 04 agora implementa
`ai.v1`, Protocol/FakeAIProvider e orquestrador síncrono, sem filas. Referência
normativa única: [contrato IA](../ai/README.md); revisão/aprovação ainda pendentes.

Após aprovação do contrato da PR 04 e seus artefatos de conformidade, a IA pode
ser desenvolvida independentemente, sem aguardar PR 06; o backend continua com
o fake. Critérios e responsabilidades constam no [ROADMAP](ROADMAP.md).

A IA não gerencia autenticação, escopos médico/clínica, consentimento, status
autoritativo, persistência direta, entrega de mensagens ou liberação `ready`.
Resultado gerado não constitui diagnóstico nem decisão de publicação. Esses
limites devem orientar contrato e testes futuros, não criar endpoints nesta PR 00.

## 14. Auditoria técnica da base: reutilizar, não reimplementar

Auditoria de 14/10/2026; classificação por recurso, não certificação de produção.
Evidências apontam para arquivos revisados na base `1e199b4`:

| Recurso | Situação | Evidência e lacuna |
| --- | --- | --- |
| Apps e composição | Implementado | `medprep`, `accounts`, `preconsultas`, URLs/views/templates por app; preservar limites |
| Sessão, login, logout/CSRF, next seguro | Implementado | `accounts/views.py`, `accounts/tests.py`; não criar outro login |
| Escopo médico/recepção/Admin | Implementado | `permissions.py`, views, `admin.py`, `test_permissions.py`; não é isolamento completo de SaaS em produção |
| Cadastro/reutilização explícita | Implementado | `forms.py`, `test_patient_registration.py`; nome+telefone, escopo e transação; busca normalizada em Python pode precisar de otimização |
| Grafo e auditoria de estados | Demonstrativo, serviço implementado | `state_engine.py`, `test_state_engine.py`; só local_simulation, sem endpoint ou evidência real de consentimento |
| Consentimento versionado | Simulado na branch PR 01; ausente na base auditada | ConsentEvidence/consent.py, referência de versão e evento auditado; não é termo jurídico ou consentimento real |
| Entrada interna unificada e simulador | Simulada na branch PR 02; ausente na base auditada | ingestion.py/ingestion_simulator.py; entradas duráveis privadas, nenhuma transformação em fontes clínicas |
| Idempotência de entrada | Implementada para local_simulation na PR 02 | Chave origem/consulta/ID, comparação canônica, row lock PostgreSQL e unicidade; namespace real pendente |
| Fontes, vínculo item–fonte e correções | Parcial; proveniência de novas fontes na PR 03 | Fonte materializada aponta para InboundMessage; legados sem vínculo inventado, fixtures atualizáveis. Captura de correções explícita, não pipeline integrado |
| Resultados estruturados e histórico longitudinal | Snapshots/histórico restrito na PR 03; pipeline IA ausente | SummaryRevision captura estrutura atual, não schema de IA. Histórico somente ready do médico atribuído/clínica; patient_id não amplia escopo |
| Mídias privadas | Parcial/demonstrativo | Mapeamento local + FileResponse autorizado, teste de bytes fictícios; sem upload, retenção ou storage privado provisionado |
| Orquestrador/contratos/FakeAIProvider | Simulado na branch PR 04; ausente na main auditada | ai.v1/port/fake, execução privada/retry/obsolescência; sem publicação ou modelo real |
| Revisão médica | Parcial | Views/templates de notas/correções/feedback existem; sem ator registrado nesses modelos, versionamento de saída/publicação ou controle completo de concorrência |
| Pronta versus concluída | Fronteira preservada, liberação futura ausente | Views só abrem ready; motor não produz ready; fixtures e ORM podem definir estado, não há serviço de publicação validada |
| PostgreSQL, SQLite explícito, migrações | Implementado | `database.py`, requirements, `0001`–`0005`; base validada em CI, sem transferência automática de dados |
| Testes e CI | Implementado com lacunas | 86 testes, PostgreSQL 17 em CI; falta E2E pipeline novo, concorrência real, smokes browser no workflow e deploy validation |
| Produção/homologação | Ausente | WSGI entrypoint não é provisionamento; faltam hardening, servidor, static pipeline, backup/restore e monitoramento |
| Governança Git | Documentada, não imposta remotamente | main sem proteção/rulesets; CI existente, revisão do outro dev recomendada, habilitação depende de autorização |

Riscos transversais: flags de usuário não substituem vínculo; compartilhamento de
Patient não amplia escopo clínico; eventos operacionais devem continuar sem payload
clínico; source/result versionados não podem sobrescrever origem; preservar fixtures
sem tratá-las como dados do pipeline. Correções concorrentes e autoria completa
merecem validação no incremento de revisão, não correção oportunista nesta PR 00.

O grafo de simulação aceita transições por perfis vinculados, mas não verifica
consentimento real. No shell, o caller passa um User ativo; o serviço verifica
escopo, não autentica uma sessão ou a identidade do paciente. O shell é uma
ferramenta administrativa, não uma entrada pública. Essa política não está
aprovada para produção. Agendamento
demonstrativo usa deslocamento de data; não reutilizá-lo como relógio de auditoria.
As migrações não trazem um contrato para processamento externo ou isolamento
longitudinal. Nenhuma dessas lacunas requer reescrever modelos/UI na PR 00.

## 15. Referências oficiais e documentação contínua

- Este arquivo: conceito, arquitetura, responsabilidades e implementado versus alvo.
- [Deploy](../deploy.md): única fonte dos procedimentos/configuração de ambiente.
- [ROADMAP](ROADMAP.md): sequência 00–06, gates, decisões, execução e evidências.
- [Motor atual](../state-engine.md): grafo/validação manual do simulador existente.
- [Migração de repositório](../repository-migration.md): histórico preservado, não backlog.
- [CONTRIBUTING](../../CONTRIBUTING.md): governança e política permanente de atualização.
- [AGENTS](../../AGENTS.md): leitura e atualização obrigatórias para execuções do Codex.

Ao terminar cada incremento, aplicar a política de CONTRIBUTING: atualizar conceito
e deploy conforme impacto, registrar SEMPRE resultado/próximo passo no ROADMAP e
manter o README da raiz como navegação. Não manter guias operacionais conflitantes
nem declarar conclusão/CI por configuração ou intenção. Publicação da PR 01
empilhada foi autorizada; a execução atual autoriza também PR 02 empilhada,
sem merge. Posteriormente, D06 e a implementação/publicação da PR 03 empilhada foram
autorizadas expressamente. Posteriormente o prompt PR 04 aprovou D07 técnica e
implementação/publicação empilhada; merge e PR 05 não estão autorizados.

## 16. Contrato de ingestão PR 02 — D05 restrita à simulação

Canal é o transporte futuro (não implementado). Mensagem/evento recebido é uma
entrada durável `InboundMessage`, não um evento operacional de estado. Fonte
clínica `SourceItem` é outra entidade: transformar entradas em fontes versionadas
pertence à PR 03. Nenhuma chamada externa, arquivo binário, transcrição ou síntese.

Serviço interno `preconsultas.ingestion.ingest_message(payload, actor=operador)`.
O operador vem do contexto interno, nunca do payload. Somente perfis/vínculos da
PR 01; sessão HTTP/paciente não é autenticada por esse serviço de shell/testes.
Consulta inexistente/externa recebe `PermissionDenied` uniforme. Todas as chamadas,
inclusive reentregas, exigem escopo atual, `in_progress` e último aceite simulado
consistente com `consent_version`, reutilizando `require_consent` da PR 01.
Caso legado em coleta sem evidência não recebe consentimento inventado e é negado.

Exemplo fictício completo (ID substituído pela consulta isolada de teste):

```json
{
  "origin": "local_simulation",
  "contract_version": "sim.v1",
  "consultation_id": 123,
  "external_event_id": "sim-text-1",
  "kind": "text",
  "declared_at": "2026-01-01T12:01:00Z",
  "consent_version": "sim-v1",
  "text": "Mensagem exclusivamente fictícia."
}
```

Para `audio`, `image` ou `pdf`, substituir `text` por `media` com exatamente
`reference`, `mime_type`, `filename`, `size_bytes`. Referência é identificador
opaco fictício, não URL/caminho. Exemplo: `{"reference":"sim-media-audio",
"mime_type":"audio/mpeg","filename":"arquivo-ficticio.mp3","size_bytes":1024}`.

Limites técnicos v1 do simulador, NÃO limites aprovados de WhatsApp/produção:

- Consulta: inteiro positivo de 64 bits, nunca booleano/string.
- ID/referência: até 120 caracteres ASCII alfanuméricos, ponto, `_`, `:`, `-`;
  primeiro caractere alfanumérico. Texto: até 8000 caracteres, não vazio/branco.
- Versão de consentimento: até 80 caracteres e correspondência explícita.
- Horário declarado: ISO 8601 com timezone; normalizado UTC, sem assumir ordem
  de entrega. Horário real de recebimento é gerado pelo servidor.
- Nome de mídia: até 180 caracteres, sem controles/separadores de caminho;
  tamanho declarado inteiro positivo até 25 MiB (metadado, não arquivo recebido).
- MIME: áudio mpeg/ogg/wav; imagem jpeg/png/webp; PDF application/pdf.
- Campos desconhecidos, identidade de paciente/operador, binários, texto misturado
  com mídia, URL, versão incompatível e estruturas inválidas são rejeitados.

Idempotência: constraint única `(origin, consultation_id, external_event_id)` e
bloqueio da consulta compartilhado com os serviços de consentimento/estado no
PostgreSQL. Mesmo ID/conteúdo: `redelivered`; conteúdo diferente: `conflict`, sem
sobrescrever. IDs distintos com conteúdo igual e IDs iguais em consultas distintas
são entradas válidas. Recebimento original/operador nunca são sobrescritos.

Equivalência usa JSON canônico em memória, com chaves ordenadas, delimitadores
estáveis e horário declarado convertido a UTC com microssegundos. Inclui versão,
tipo, texto exato, metadados e versão do consentimento; exclui horário gerado,
operador e IDs internos. Espaços/Unicode do texto não são normalizados; mudanças
reais de texto/metadados/horário declarado são conflito. Não há campo genérico
de payload armazenado ou segunda máquina de estados.

Retorno `IngestionReceipt`: apenas `status` (`created`, `redelivered`, `conflict`),
`message_id` interno e `is_simulated=True`. Nunca retorna texto, mídia ou hashes.
Contrato inválido: `InvalidEnvelope`, mensagem genérica/código `invalid_envelope`;
estado/consentimento: `InvalidTransition`; escopo: `PermissionDenied`;
falha de banco: `IngestionPersistenceError` sanitizado e rollback. Não há logs de
payload nem novo `OperationalEvent`; operador/momento/evidência ficam na entrada
privada. Isso não autoriza leitura clínica pela recepção/admin.

Entradas fora de ordem preservam horário declarado e ordem de recebimento,
sem reordenar estados. O simulador interno retorna fixtures fixas e replays;
execução segura em banco temporário está em [deploy](../deploy.md). Não cria
usuários, consentimento ou consultas automaticamente; testes fazem setup explícito.

Pendências para canais reais: autenticação/origem, namespace por conta/integrador,
limites/mídias, semântica de ordem/reentrega após encerramento, identidade e
retenção. Proteção de métodos de instância não é WORM; SQL/QuerySet privilegiados
podem alterar dados. D06 foi aprovada para o recorte simulado da seção 17;
isso não aprova contratos ou retenção de canais reais.

## 17. Proveniência e revisões PR 03 — D06 técnica aprovada

Escopo fictício aprovado pelo solicitante em 14/10/2026: materialização, associação
entrada–fonte, snapshots da estrutura atual e histórico restrito. Sem IA,
publicação clínica, prontuário, transporte ou armazenamento externo. D08 mantém
retenção/infra produtivas pendentes; D07 define contrato final da IA na PR 04.

Interfaces internas de `preconsultas.traceability`:

- `materialize_message(consultation_id, message_id, actor=medico)`: médico ativo,
  consulta atribuída e clínica vinculada; mensagem da MESMA consulta, contrato e
  evidência simulada persistida válidos. Uma mensagem → uma fonte, OneToOne único,
  transação e lock da consulta PostgreSQL. Repetição retorna mesma fonte, sem
  sobrescrita. Retorna apenas `MaterializationReceipt(source_id, created)`.
- A entrada histórica validada pode ser materializada depois da coleta, sem
  alterar estado nem conceder leitura. A autorização aqui é de escrita interna;
  não é liberação de conteúdo ao operador/recepção. Médico é o perfil habilitado
  neste recorte, não staff/admin por privilégio técnico. Futuro ator automático
  precisará de contrato/autorização explícitos em incremento posterior.
- `source_provenance(consultation_id, source_id, actor=medico)`: exige clínica,
  médico atribuído E `ready`. Retorna IDs/origem/versão/horários/operadores/mídia
  da entrada original por vínculo, não copia ou reinterpreta identidade do paciente.
  Para legado retorna `legacy=True, message_id=None`, sem inventar mensagem.
- `record_summary_revision(consultation_id, item_id, actor=medico)`: exige leitura
  clínica `ready`; captura um SummaryItem já existente, sem gerar/alterar resumo
  ou correção. Retorna ID da revisão. Conteúdo/referências observados iguais são
  idempotentes; mudanças acrescentam revisão numerada, nunca sobrescrevem anterior.
- `summary_revisions(consultation_id, item_id, actor=medico)`: mesmo gate `ready`,
  devolve snapshots e IDs de fontes da própria consulta. IDs forjados/inexistentes
  ou fora de escopo recebem negação uniforme; referências inconsistentes rejeitadas.
- `patient_history(patient_id, actor=medico)`: lista metadados das consultas `ready`
  já atribuídas ao médico em clínicas vinculadas. Não consulta paciente fora do
  escopo, não prefetch de fontes e não inclui outros médicos ou casos inéditos,
  incompletos/cancelados/concluídos sem publicação. Mesmo patient_id não é permissão.

SourceItem mantém texto/horário declarado; metadados de mídia, horário real de
ingestão, origem, ID externo, operador simulador, consentimento e versão ficam
preservados em InboundMessage/ConsentEvidence. Materialização registra operador
e momento próprios. Autor de apresentação é “Entrada simulada”, não paciente
autenticado nem IA executada. Novas referências de mídia não têm duração/transcrição
inventadas, download ou arquivo binário; tipo imagem é apenas referência.
Nenhum conteúdo clínico entra em OperationalEvent, logs ou erros operacionais.

Modelagem de versões: SummaryRevision guarda consulta, SummaryItem e sua chave
lógica estável, número, data/operador, seção/rótulo/atribuição/valor original,
valor apresentado e ocultação existentes. Correção é referência numérica de
snapshot, NÃO autoria retroativa nem FK que impeça o reset demonstrativo. A última
correção/último update são capturados conforme a apresentação atual. Tabela
SummaryRevisionSource preserva fontes com FK protegida e unicidade; serviço e
validação de modelo rejeitam referências entre consultas. Não há JSON genérico,
DTO de IA, prompt ou diagnóstico aprovado nesta modelagem: é versionamento da
estrutura existente, independente de D07. Contrato real pode exigir evolução aditiva.

As views médicas antigas não disparam snapshots automaticamente: integrar captura
ao fluxo de revisão/publicação, com autoria/concorrência completas, fica na PR 05.
Os locks serializam os NOVOS serviços entre si; não certificam concorrência de
todos os escritores legados/ORM. Sem endpoints novos nem exposição no Admin.

Legados permanecem editáveis pelo load_demo e sem vínculo artificial. Somente
fontes materializadas têm proteção de sobrescrita/desvínculo nos métodos de
instância. Revisões preservam valores/referências próprios mesmo quando fixtures
restauram valores/correções. Fontes legadas ainda podem ser atualizadas pelo seed;
não tratá-las como evidência imutável de produção. SQL/QuerySet/bulk privilegiados
podem contornar validações de aplicação (incluindo integridade entre consultas);
FKs/unicidades não são WORM nem políticas completas de retenção.

## 18. Orquestração PR 04 — D07 técnica fictícia aprovada

`ai_orchestration.execute(consultation_id, operation, actor=medico, provider=fake,
retry=False)` valida médico ativo atual/consulta/clínica, estado permitido por
operação e último aceite simulado consistente. Seleciona somente fontes da consulta
e valida sua origem; todas entram no contexto versionado, inclusive conteúdo de
legados mutáveis. Não inclui nome/telefone/patient_id no DTO.

Reserva sob lock da consulta/fontes PostgreSQL com identity única, cria tentativa
e referências e encerra transação. Chama port fora do lock; nova transação revalida
escopo/estado/aceite/contexto antes de persistir resultado. Provider não autentica
nem publica. Retorno é só ExecutionReceipt com IDs/status/contagem/código sanitizado.
Recepção/admin sem médico continuam negados; nenhuma falha altera status operacional.

AIExecution/AIAttempt/AIExecutionSource mantêm request privado, contexto e provedor
versionados, fontes/versões, tentativas, resultado validado ou código sanitizado e
horários/atores. Não reutilizam SummaryRevision nem escrevem SummaryItem/Correction.
Execução mesma identidade é idempotente; retry explícito só transitório/indisponível,
máximo 3 tentativas. Concorrente recebe running, sem duplicar resultado aceito.
Mudança material cria outra execução; obsoletos são preservados, nunca consumidos
como atuais. `current_result` exige médico/clínica/ready e revalida contexto, output
e referências no momento de uso; completed continua sem leitura/publicação.

FakeAIProvider determinístico implementa três operações e cenários inválido/
indisponível/transitório, sem dependências/rede. Cita textos fictícios literalmente,
não inventa análise de mídia, diagnóstico ou transcrição. Contrato `ai.v1`, exemplos,
limites de operação/estado, port e testes independentes de Django estão em
[docs/ai](../ai/README.md), sem duplicar referência operacional/roadmap.

Limites: capturas técnicas privadas não integram UI/publicação; não há timeout,
fila ou recuperação automática de reserva running após crash/falha finalização.
Locks/constraints não são WORM/RLS contra ORM/SQL privilegiados ou certificação
semântica clínica. D08 e recuperação produtiva permanecem pendentes. IA independente
só após aprovação humana do [handoff](../ai/handoff.md), sem aguardar PR 05/06.
