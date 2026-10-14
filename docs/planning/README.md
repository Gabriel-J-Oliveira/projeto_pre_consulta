# Contexto do projeto de pré-consulta para planejamento com IA

Referência conceitual oficial, auditada em **14/10/2026** sobre a base
`1e199b4577d8a6c64b30c3744d4bea4adfd308bf`, preparada a partir do código e da documentação
do repositório público `Gabriel-J-Oliveira/projeto_pre_consulta`. Este arquivo é
autossuficiente para ser anexado a um chat de planejamento. Descreve o que existe,
o que é demonstrativo e o que ainda depende de decisão. A sequência Pré-IA foi
solicitada pela equipe; suas regras específicas e interfaces ainda exigem aprovação.
Não contém credenciais, dados pessoais, banco local ou documentos de pacientes.

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
- `SummaryItem`: itens estruturados, atribuição e referências às fontes.
- `DoctorNote`, `Correction`, `Feedback`: interações médicas persistidas.
- `OperationalEvent`: linha do tempo operacional. Eventos do motor guardam
  estado anterior/novo, origem, usuário, data/hora real e marca de simulação.

Migrações `0001`–`0003` preservam o protótipo original; `0004` acrescenta vínculos
internos; `0005_operational_state_engine` acrescenta metadados opcionais de eventos
e escolhas de estado. Não há migração de dados que transforme os estados antigos.

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

Fluxo planejado: criar branches curtas por card a partir da `main` integrada,
abrir PRs, aguardar CI real e revisão humana. Proteção/rulesets não estavam
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
DTOs, assinatura do provider, payload JSON, filas, limites e formatos finais NÃO
estão definidos aqui. FakeAIProvider ainda não foi implementado.

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
| Consentimento versionado | Ausente | Não há termo/evidência/versionamento; status/evento não bastam como prova |
| Entrada interna unificada e simulador | Ausente | Não existe serviço de ingestão; fontes são semeadas por `load_demo` |
| Idempotência de entrada | Ausente | Slugs/event_key únicos e seed idempotente não deduplicam envelopes/mensagens de origem |
| Fontes, vínculo item–fonte e correções | Parcial | `SourceItem`, `SummaryItem.sources`, `Correction`; ações preservam original, mas não há imutabilidade/versionamento completo e fixtures são atualizáveis |
| Resultados estruturados e histórico longitudinal | Ausente como pipeline aprovado | Não há lote/versão de resultado/processamento; não liberar todos os atendimentos só por patient_id |
| Mídias privadas | Parcial/demonstrativo | Mapeamento local + FileResponse autorizado, teste de bytes fictícios; sem upload, retenção ou storage privado provisionado |
| Orquestrador/contratos/FakeAIProvider | Ausente | Não há camada de provedor ou processamento/retentativa; começar com contrato/fake depois da persistência |
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
nem declarar conclusão/CI por configuração ou intenção. A publicação da PR 00
foi autorizada após revisão local; merge e início da PR 01 permanecem não autorizados.
