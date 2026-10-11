# Contexto do projeto de pré-consulta para planejamento com IA

Snapshot técnico de **11/10/2026**, preparado a partir do código e da documentação
do repositório público `Gabriel-J-Oliveira/projeto_pre_consulta`. Este arquivo é
autossuficiente para ser anexado a um chat de planejamento. Descreve o que existe,
o que é demonstrativo e o que ainda depende de decisão; não é um backlog aprovado.
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

## 8. Configuração e validação técnica

O README da raiz contém instalação detalhada. Cada desenvolvedor tem seu próprio
ambiente, `.env`, chave local e banco; nada disso é publicado. Variáveis:
`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DB_BACKEND`,
`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DEMO_MEDIA_ROOT` e,
para instâncias paralelas, nomes distintos de cookies de sessão/CSRF.

PostgreSQL é o padrão; não há fallback silencioso. SQLite requer
`DB_BACKEND=sqlite`. Não existe conversão automática do SQLite para PostgreSQL.
Migrações preservam histórico e dados; transferência entre bancos é outra tarefa.

Com o ambiente configurado, executar:

```text
python manage.py migrate
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Para ambiente demonstrativo novo: `python manage.py load_demo`, criação explícita
de conta via `createsuperuser`, configuração dos vínculos no Admin e `runserver`.
`load_demo` é idempotente e não cria usuários. Restaura fixtures e estados-base;
não deve ser usado para validar transições em registros que se deseja preservar.
Os testes Django usam banco temporário separado do banco de validação.

A suíte atual contém 86 testes, incluindo autenticação/CSRF, permissões, cadastro,
rollback, matriz de transições, auditoria e compatibilidade. Na etapa anterior,
86 testes passaram em SQLite; em 11/10/2026, `check`, verificação de migrações
e os 86 testes foram executados novamente e aprovados antes do commit local.
Smokes existentes cobrem telas médicas, recepção, bloqueios e escolha de paciente
em desktop/mobile. Smokes de navegador usam contas explicitamente vinculadas.

A CI aceita PRs de qualquer base e usa PostgreSQL 17 descartável: instalação,
`check`, migrações pendentes, `migrate`, `load_demo` duas vezes e testes.
As PRs #3 e #4 do repositório anterior tiveram CI aprovada antes deste snapshot; isso não valida o novo
commit do motor. Só uma execução real correspondente ao SHA confirma aprovação.
PostgreSQL não foi validado localmente nas etapas anteriores.

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
