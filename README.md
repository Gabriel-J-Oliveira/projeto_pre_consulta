# Lume Saúde — pré-consulta demonstrativa

Protótipo Django da tela **Pré-consulta pronta**, destinado exclusivamente a
apresentações com dados fictícios. Não use este projeto com dados reais de pacientes.

Para planejamento em outro chat de IA, use o arquivo autossuficiente
[Contexto do projeto](docs/planning/README.md), com arquitetura, funcionalidades,
permissões, estados, cadeia de branches e decisões ainda pendentes.

Referências oficiais da trilha Pré-IA:

- [Conceito e auditoria técnica](docs/planning/README.md).
- [Ambientes, instalação, testes e deploy](docs/deploy.md).
- [Roadmap 00–06 e histórico de execução](docs/planning/ROADMAP.md).
- [Contrato técnico simulado ai.v1](docs/ai/README.md) e [handoff para IA](docs/ai/handoff.md).
- [Política de colaboração/documentação](CONTRIBUTING.md) e [instruções do agente](AGENTS.md).

PR 00 é preparação documental. A cadeia empilhada PRs 01–06 implementa partes
simuladas da trilha, ainda em revisão, sem merge ou IA/WhatsApp reais. Contrato
e handoff da PR 04 precisam de aprovação humana; CI/publicação não a substituem.
Publicação/revisão da PR 05 são somente simuladas e explícitas, com dados fictícios;
ready não é aprovação clínica. Fluxo/gates e compatibilidade estão no contexto.
PR 06 consolida [evidências integradas](docs/planning/PRE_AI_VALIDATION.md) e
[matriz de prontidão](docs/planning/READINESS.md), sem liberar produção ou aprovar
automaticamente o handoff do outro desenvolvedor.

A base histórica está integrada em `main`; os incrementos empilhados ainda não.
O [registro da migração de repositório](docs/repository-migration.md)
documenta as branches históricas, os commits preservados e a correspondência das PRs.

## Instalação local

Python 3.14 e PostgreSQL 17 são as referências atuais; SQLite é uma opção local
explícita. Siga a [instalação e configuração de ambiente](docs/deploy.md), que é
a fonte única dos procedimentos e variáveis suportadas. Cada desenvolvedor mantém
seu próprio `.env` e banco, não publicados. Não sobrescrever configurações ou
dados locais para repetir o bootstrap. O ambiente continua exclusivamente fictício.

## Estrutura e decisão de modularização

- `medprep/`: composição do projeto, configuração e seleção do banco.
- `accounts/`: app sem modelos de domínio, com formulário, views/URLs de
  login/logout, testes e template `accounts/templates/accounts/login.html`.
- `preconsultas/`: domínio de pré-consulta e IA, com modelos, migrações,
  autorização, Admin, views, URLs médicas/operacionais, dados fictícios e
  templates em `preconsultas/templates/preconsultas/`.

Autenticação foi extraída para reduzir sua mistura com as telas do domínio.
`accounts` consulta somente a função pública de destino pós-login em
`preconsultas.permissions`, sem consultar diretamente os modelos clínicos.
O domínio não importa views de autenticação. URLs, namespaces, estilo,
CSRF, mensagens e critérios de autorização permanecem iguais.

Clínicas, médicos e perfis de recepção permanecem em `preconsultas`, preservando
tabelas, content types, permissões e o histórico de migrações `0001` a `0005`.
O usuário padrão de Django não mudou. A extração de autenticação não exige
nova migração. Agendamento e prontuário ainda não têm apps; serão criados
quando suas funcionalidades entrarem no escopo. Não há processamento real de IA.

## Configuração do banco

PostgreSQL é padrão, sem fallback; SQLite exige `DB_BACKEND=sqlite`. Não há
conversão automática nem cópia de bancos pelo Git. Preparação do PostgreSQL,
variáveis e migrações estão em [deploy](docs/deploy.md); evidências por backend/SHA
estão no [ROADMAP](docs/planning/ROADMAP.md). Banco local da validação é preservado.

## Preparar e iniciar

Use a [inicialização demonstrativa](docs/deploy.md), distinguindo banco novo de
validação já existente. Não há usuários/senhas padrão; configure os vínculos
abaixo após criar uma conta explicitamente. `runserver` não é produção.

## Vínculos e permissões internos

O usuário padrão do Django permanece em uso. No Admin, vincule a conta médica
ao cadastro em **Doctors** e mantenha suas clínicas em `Doctor.clinics`.
O médico só vê consultas atribuídas ao seu cadastro, em clínicas vinculadas.
Sem cadastro ou sem clínicas, o acesso médico é negado.

Para recepção, crie um **Reception profile** para a conta e selecione suas
clínicas. A lista, filtros e cadastro operacional usam somente essas clínicas,
incluindo a validação de POST no servidor. Esse vínculo não libera resumo,
conversa, transcrição, áudio, anexos ou ações médicas.

Staff ativo entra no Admin, mas a gestão dos cadastros depende das permissões
nativas de Django para usuários, clínicas, médicos e perfis de recepção.
Superusuários podem gerenciá-los. Nenhum modelo clínico ou paciente é exposto
no Admin. Ser staff/superusuário, isoladamente, não dá acesso clínico.
Os vínculos são explícitos e independentes: possuir um deles não cria o outro.
Não existem contas padrão, vínculo automático para contas antigas ou login de pacientes.

A migração adiciona campos/tabela de vínculos sem apagar os registros anteriores.
Após migrar, configure os vínculos antes de usar as telas. `load_demo` não cria
usuários nem concede acesso.

Rotas, execução de instâncias separadas, cookies, configuração dos smokes e
limites de `load_demo` estão em [deploy](docs/deploy.md). Consulte essa referência
operacional antes de executar comandos sobre um banco de validação existente.

Os horários da agenda demonstrativa usam deslocamentos em relação à data local
configurada no Django. Assim, para a médica demonstrativa, cinco casos permanecem
em “Hoje” e um em “Amanhã” mesmo com a passagem dos dias. A recepção inclui ainda
um atendimento de um segundo médico para demonstrar o filtro e os vínculos entre
profissionais e clínicas. A execução idempotente de `load_demo` mantém também as
datas persistidas alinhadas ao dia local, sem duplicar consultas ou eventos.

A recepção reutiliza esses mesmos agendamentos e mostra apenas dados e eventos
operacionais. Novos cadastros começam como `Não iniciada`, exigem no servidor um
vínculo médico–clínica cadastrado e não criam fontes, respostas ou resumos clínicos.

No formulário manual, informe somente nome e telefone para identificar o paciente.
Ao enviar, correspondências por nome completo (Unicode NFKC, espaços normalizados
e sem distinção de maiúsculas) **e** telefone (somente dígitos) exigem uma escolha:
reutilizar um dos registros apresentados ou criar um novo. Só aparecem pacientes
com consultas em clínicas vinculadas à recepção, e o servidor revalida a seleção.
Sem correspondência, um novo paciente é criado. Não há mesclagem automática,
unicidade de telefone nem busca por telefone isolado. A transação inclui paciente,
pré-consulta e eventos operacionais; nenhum convite real é enviado.

## Regras ainda provisórias

O [motor de estados operacional](docs/state-engine.md) reutiliza `Consultation.status`
e registra transições explícitas no serviço de domínio, com auditoria e isolamento.
É somente uma simulação local: “Concluída” não equivale a “Pronta” nem libera
conteúdo clínico. A documentação descreve o grafo, compatibilidade e validação
manual no shell. Não há endpoint ou integração real para mudanças de estado.

- A antecedência de 24, 48 ou 72 horas é apenas demonstrativa.
- Não há regra definitiva de elegibilidade ou liberação de casos incompletos.
- Nenhum convite é agendado ou enviado; eventos de convite existentes são marcados
  como `SIMULADO` e não representam mensagem de WhatsApp.
- A autenticação e os vínculos são verificados no servidor; o endurecimento para
  produção e a política definitiva de elegibilidade de casos continuam pendentes.

Para reiniciar interações do protótipo, consulte os limites de seed/reset em
[deploy](docs/deploy.md). Essa operação pode apagar notas, correções e feedback
do caso-base e só deve ser feita mediante pedido explícito, não para validar esta PR.

## PDFs e MP3 locais

Coloque os arquivos em `demo_media/`, usando os nomes documentados em
[`demo_media/README.md`](demo_media/README.md). O mapeamento central fica em
[`preconsultas/demo_media.py`](preconsultas/demo_media.py). Os binários são ignorados
pelo Git e servidos somente pelo Django local; nenhum upload externo é feito.

Enquanto os arquivos não existirem, o protótipo mantém as referências, mostra um
estado amigável no visualizador e identifica áudio/transcrição como conteúdo
fictício — sem alegar processamento dos arquivos ausentes.

## Verificação

Comandos, CI e limites dos smokes estão em [deploy](docs/deploy.md). A suíte
usa banco temporário; a CI usa PostgreSQL 17. Registre resultados reais no
[ROADMAP](docs/planning/ROADMAP.md), distinguindo execução local e checks GitHub.
Não usar configuração do workflow como prova de aprovação ou de prontidão para produção.

## Colaboração

O desenvolvimento acontece em branches curtas por tarefa, sempre integradas por
Pull Request para `main`, com CI aprovado e revisão do outro desenvolvedor. Consulte
[`CONTRIBUTING.md`](CONTRIBUTING.md) para os padrões de branches, revisão e cuidados
com dados e arquivos locais.
