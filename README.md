# Lume Saúde — pré-consulta demonstrativa

Protótipo Django da tela **Pré-consulta pronta**, destinado exclusivamente a
apresentações com dados fictícios. Não use este projeto com dados reais de pacientes.

## Instalação local

Requisitos: Python 3.14 e PostgreSQL 17 (a versão usada na CI). O driver
`psycopg[binary]` é instalado pelo `requirements.txt`. SQLite permanece
disponível apenas por seleção explícita para desenvolvimento sem PostgreSQL.

```powershell
git clone https://github.com/projetopreconsulta-stack/preconsulta.git
Set-Location preconsulta
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite `.env` e substitua `DJANGO_SECRET_KEY` por uma chave local aleatória. O
projeto falha com uma mensagem clara se chave, modo debug ou hosts permitidos não
estiverem configurados. `DEBUG=True` é apenas para desenvolvimento local.

Cada desenvolvedor deve manter seu próprio `.env` e banco local. Esses
arquivos, ambientes virtuais, caches, logs e mídias locais estão ignorados pelo Git
e não devem ser compartilhados ou enviados ao repositório.

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
tabelas, content types, permissões e as migrações `0001` a `0004`.
O usuário padrão de Django não mudou. A extração de autenticação não exige
nova migração. Agendamento e prontuário ainda não têm apps; serão criados
quando suas funcionalidades entrarem no escopo. Não há processamento real de IA.

## Configuração do banco

`DB_BACKEND=postgresql` é o padrão. Preencha no `.env` `DB_HOST`,
`DB_PORT`, `DB_NAME`, `DB_USER` e `DB_PASSWORD` com seu ambiente local.
São campos separados, sem URLs contendo credenciais. Variáveis obrigatórias
ausentes ou porta inválida impedem a inicialização. Variáveis definidas no
processo têm precedência sobre o `.env`.

Em um PostgreSQL local disponível, crie um papel e um banco novos, exclusivos
do protótipo; não reutilize um banco com dados existentes. Exemplo com as
ferramentas PostgreSQL, autenticando-se como administrador:

```powershell
createuser --host 127.0.0.1 --port 5432 --username seu_administrador --pwprompt --createdb preconsulta_dev
createdb --host 127.0.0.1 --port 5432 --username seu_administrador --owner preconsulta_dev preconsulta_local
```

Escolha seus próprios nomes no lugar dos exemplos e use-os no `.env`.
`--pwprompt` solicita a senha interativamente, sem colocá-la no comando.
Nenhuma conta ou senha é criada pelo projeto. `CREATEDB` é necessário apenas
para o usuário de desenvolvimento que executa os testes Django, pois eles
criam um banco temporário; não conceda essa permissão à aplicação de produção.

Se Docker já estiver disponível, crie um arquivo local ignorado
`.env.postgres` com `POSTGRES_DB`, `POSTGRES_USER` e
`POSTGRES_PASSWORD` escolhidos por você. Para uma instância descartável:

```powershell
docker run --name preconsulta-dev-pg --rm -d --env-file .env.postgres -p 127.0.0.1:5433:5432 postgres:17
```

O `.env` Django usa `DB_HOST=127.0.0.1`, `DB_PORT=5433` e os mesmos
banco/usuário/senha. O container não usa volumes: `docker stop preconsulta-dev-pg`
descarta seus dados. Nenhum serviço é instalado pelo projeto.

Para trabalhar sem PostgreSQL, escolha `DB_BACKEND=sqlite` no `.env` ou no
ambiente. Somente nessa opção o banco é `db.sqlite3` na raiz da cópia local;
variáveis PostgreSQL não são exigidas. Não existe fallback silencioso.
SQLite não é copiado ou convertido automaticamente: o PostgreSQL começa
com `migrate` e os dados fictícios de `load_demo`. Transferência de registros
locais existentes deve ser planejada separadamente antes da troca de uma
instância em uso.

Nesta máquina, a instância do worktree na porta 8001 usa `DB_BACKEND=sqlite`
explicitamente, preservando banco e contas da validação. PostgreSQL/Docker
local não estavam disponíveis; a validação real PostgreSQL depende de uma
instância disponível ou da CI. Consulte a execução correspondente ao commit
para confirmar o resultado; a configuração do workflow não comprova aprovação.

## Preparar e iniciar

```powershell
python manage.py migrate
python manage.py load_demo
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

`createsuperuser` solicita as credenciais no terminal e armazena somente o hash da
senha pelo mecanismo nativo do Django. Não existe usuário ou senha padrão. Depois do
primeiro acesso, administradores podem cadastrar outros usuários internos pelo admin.

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

Para executar duas instâncias no mesmo host, use bancos em diretórios separados,
portas distintas e nomes de cookies distintos no ambiente da segunda instância:
`DJANGO_SESSION_COOKIE_NAME=preconsulta_8001_session` e
`DJANGO_CSRF_COOKIE_NAME=preconsulta_8001_csrf`. Cookies não são isolados por porta.
Os smokes aceitam `SMOKE_BASE_URL` e credenciais locais via ambiente. Execute
os smokes médico/pré-consulta com uma conta ligada ao médico e o smoke de recepção
com uma conta ligada às clínicas. `permissions_smoke.cjs` aceita `SMOKE_ROLE`
igual a `admin` ou `reception` para conferir bloqueios no navegador.

Acesse:

- Painel médico: <http://127.0.0.1:8000/medico/painel/>
- Pré-consulta pronta: <http://127.0.0.1:8000/medico/pre-consultas/demo/>
- Operação da recepção: <http://127.0.0.1:8000/recepcao/pre-consultas/>

`load_demo` pode ser executado novamente para restaurar os dados-base fictícios:
ele atualiza o caso conhecido, não duplica registros e não apaga notas, correções,
feedback nem dados não relacionados. Não é necessário apagar o banco.

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

- A antecedência de 24, 48 ou 72 horas é apenas demonstrativa.
- Não há regra definitiva de elegibilidade ou liberação de casos incompletos.
- Nenhum convite é agendado ou enviado; eventos de convite existentes são marcados
  como `SIMULADO` e não representam mensagem de WhatsApp.
- A autenticação e os vínculos são verificados no servidor; o endurecimento para
  produção e a política definitiva de elegibilidade de casos continuam pendentes.

Para reiniciar somente as interações do protótipo (notas, correções e feedback),
mantendo o caso, suas fontes e quaisquer dados não relacionados:

```powershell
python manage.py load_demo --reset-interactions
```

## PDFs e MP3 locais

Coloque os arquivos em `demo_media/`, usando os nomes documentados em
[`demo_media/README.md`](demo_media/README.md). O mapeamento central fica em
[`preconsultas/demo_media.py`](preconsultas/demo_media.py). Os binários são ignorados
pelo Git e servidos somente pelo Django local; nenhum upload externo é feito.

Enquanto os arquivos não existirem, o protótipo mantém as referências, mostra um
estado amigável no visualizador e identifica áudio/transcrição como conteúdo
fictício — sem alegar processamento dos arquivos ausentes.

## Verificação

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Os testes usam um banco temporário separado no backend selecionado, sem alterar
o banco local. A suíte verifica idempotência de `load_demo`, preservação de
registros não relacionados e vínculos explícitos.

A CI é configurada para PRs de qualquer branch-base, com PostgreSQL 17
descartável. Executa `check`, verificação de migrações, `migrate`, duas chamadas
de `load_demo` e todos os testes. Os valores no workflow são exclusivamente
do serviço descartável de CI. Configurar o workflow não confirma sua aprovação.

## Colaboração

O desenvolvimento acontece em branches curtas por tarefa, sempre integradas por
Pull Request para `main`, com CI aprovado e revisão do outro desenvolvedor. Consulte
[`CONTRIBUTING.md`](CONTRIBUTING.md) para os padrões de branches, revisão e cuidados
com dados e arquivos locais.
