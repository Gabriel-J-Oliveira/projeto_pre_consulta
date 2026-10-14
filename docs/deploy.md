# Ambientes, execução e preparação de deploy

Referência operacional oficial. Auditoria de 14/10/2026 sobre a base
`1e199b4577d8a6c64b30c3744d4bea4adfd308bf`. Este documento não provisiona
infraestrutura, não instala serviços e não transforma o protótipo em produção.
Conceito: [planejamento](planning/README.md). Execução: [ROADMAP](planning/ROADMAP.md).

## 1. Situação real dos ambientes

| Ambiente | Situação e evidência |
| --- | --- |
| Desenvolvimento SQLite | Opção explícita; suíte de 86 testes executada na auditoria, em banco temporário |
| Validação demonstrativa anterior | Worktree separado, porta 8001 e SQLite local; dados preservados, disponibilidade deve ser conferida em cada sessão |
| PostgreSQL local | Não executado nesta auditoria; `psql`/Docker não encontrados no PATH. Isso não prova ausência de toda instalação possível |
| CI PostgreSQL 17 | Execução real da base: [run 38150293707](https://github.com/Gabriel-J-Oliveira/projeto_pre_consulta/actions/runs/38150293707), sucesso, PostgreSQL 17.11 e 86 testes |
| Homologação | Não provisionada/validada; procedimento de preparação abaixo é proposto |
| Produção | Não há implantação ou URL pública de aplicação confirmada; pendências de segurança e operação abaixo |

Os bancos, `.env`, contas e mídias não acompanham clones do Git. Não copiar o
banco de validação para homologação/produção nem substituir dados existentes.
`runserver` é desenvolvimento, não servidor de produção.

## 2. Pré-requisitos e instalação local

Requisitos atuais: Python 3.14, Git, PostgreSQL 17 para o backend padrão;
`requirements.txt` fixa Django 6.1.1, python-dotenv 1.2.3 e psycopg[binary] 3.3.6.
SQLite pode ser escolhido explicitamente quando PostgreSQL não estiver disponível.
Não migrar tecnologias ou instalar serviços sem necessidade e autorização.

Para clone NOVO, com exemplos PowerShell:

```powershell
git clone https://github.com/Gabriel-J-Oliveira/projeto_pre_consulta.git
Set-Location projeto_pre_consulta
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

Em checkout já existente, preserve `.venv`, `.env` e banco; não repetir bootstrap
por cima deles. Configure `.env` em editor local, sem anexá-lo ao chat ou ao Git.
Escolha credenciais próprias e chave secreta aleatória de alta entropia. Não há
conta/senha padrão. Variáveis do processo têm precedência sobre `.env`.

## 3. Variáveis realmente suportadas

| Variável | Uso atual |
| --- | --- |
| `DJANGO_SECRET_KEY` | Obrigatória; valor local/protegido, nunca publicado |
| `DJANGO_DEBUG` | Obrigatória; True somente em desenvolvimento. False não basta para habilitar produção |
| `DJANGO_ALLOWED_HOSTS` | Lista separada por vírgula; obrigatória, wildcard `*` rejeitado |
| `DB_BACKEND` | `postgresql` é o padrão; `sqlite` precisa ser explícito. Não há fallback silencioso |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Obrigatórias no PostgreSQL; porta entre 1 e 65535. Senha não é normalizada |
| `DEMO_MEDIA_ROOT` | Diretório local de mídias demonstrativas, padrão `demo_media` |
| `DJANGO_SESSION_COOKIE_NAME`, `DJANGO_CSRF_COOKIE_NAME` | Nomes de cookies; diferenciar instâncias no mesmo host, pois cookies não se isolam por porta |

`.env.example` contém apenas placeholders. Flags de HTTPS, cookies seguros,
HSTS/proxy e política de senha NÃO são configuráveis pelas variáveis acima;
não inventar suporte por `.env` que o código ainda não lê. Essas alterações
exigem incremento técnico próprio antes de qualquer exposição real.

## 4. PostgreSQL de desenvolvimento e migrações

Use um banco e usuário próprios para o protótipo, nunca banco de pacientes ou
produção. Se PostgreSQL já estiver disponível e houver autorização, exemplos
com ferramentas nativas (substitua os nomes fictícios pelas escolhas locais):

```powershell
createuser --host 127.0.0.1 --port 5432 --username seu_administrador --pwprompt --createdb preconsulta_dev
createdb --host 127.0.0.1 --port 5432 --username seu_administrador --owner preconsulta_dev preconsulta_local
```

`--pwprompt` solicita a senha interativamente. `CREATEDB` serve ao usuário local
que roda testes, pois Django cria banco temporário; não concedê-lo ao runtime
de produção. Não registrar senhas em comandos/logs nem URLs de conexão.

Se Docker JÁ existir, uma opção descartável, ainda não executada nesta auditoria:

```powershell
docker run --name preconsulta-dev-pg --rm -d --env-file .env.postgres -p 127.0.0.1:5433:5432 postgres:17
```

Prepare antes `.env.postgres` local ignorado, com os nomes de variáveis
`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, sem credenciais padrão.
Configure os campos DB no `.env` Django com o mesmo banco/usuário/senha e porta
5433. O exemplo não usa volume: parar esse container remove seus dados; NÃO é
um desenho de persistência/backup para homologação ou produção.

Com o backend escolhido e configurado:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py showmigrations preconsultas --plan
python manage.py migrate
```

Migrações de domínio existentes: `0001`–`0005`; não apagar, renumerar, fazer
`--fake` ou reiniciar o histórico. PR 00 não cria/aplica migração. SQLite usa
`db.sqlite3` da cópia atual; transferência de dados para PostgreSQL não é
automática nem está aprovada como operação desta preparação.

## 5. Dados fictícios, contas e inicialização

Somente em banco demonstrativo novo ou com autorização para restaurar fixtures:

```powershell
python manage.py load_demo
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

`load_demo` é idempotente, cria fontes/sínteses fictícias e não cria usuários.
Atualiza também estados/datas dos casos-base; não usá-lo para testar o motor sobre
registros cujo estado se deseja preservar. `--reset-interactions` apaga notas,
correções e feedback do caso-base; não executar sem pedido explícito. Não usar `flush`.

`createsuperuser` solicita credenciais e usa hash nativo. Conta técnica só entra
no Admin; acesso às telas depende de vínculos explícitos. Configure User em
Doctor e suas clínicas para médico, ou ReceptionProfile/clínicas para recepção.
Um 403 para superusuário sem perfil é esperado, não motivo para retirar proteção.

Rotas de validação: `/accounts/login/`, `/medico/painel/`,
`/medico/pre-consultas/demo/`, `/recepcao/pre-consultas/` e `/admin/`.
Casos incompletos/concluídos operacionalmente não liberam conteúdo clínico.

Para outra cópia local, escolha porta disponível (ex.: 8001), banco separado e
cookies de nomes distintos no processo dessa instância. Não parar nem reconfigurar
uma instância usada pelo solicitante sem necessidade/autorização. Encerrar um
`runserver` de terminal com Ctrl+C; para processo em background, identificar
primeiro o PID/porta/cópia corretos e encerrar apenas esse processo.

## 6. Testes e verificações

No ambiente configurado de desenvolvimento/teste, nunca com conexão de produção:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Django usa banco temporário no backend escolhido. Não apontar o teste para um
banco de validação como `TEST.NAME`, nem usar `--keepdb` sobre dados preservados.
No PostgreSQL, o usuário de teste precisa poder criar o banco de teste.

Smokes existentes, opcionais nesta PR documental: `browser_smoke.cjs`,
`dashboard_smoke.cjs`, `reception_smoke.cjs`, `permissions_smoke.cjs` e
`patient_registration_smoke.cjs`. Requerem Node/Playwright e Edge no caminho
atualmente fixado pelos scripts. Não constituem smokes portáveis de deploy.
Forneça `SMOKE_BASE_URL`, `SMOKE_USERNAME`, `SMOKE_PASSWORD` apenas no ambiente,
sem imprimir valores; use conta já configurada e perfil apropriado. O smoke de
permissões usa `SMOKE_ROLE`; o de pacientes exige os campos `SMOKE_PATIENT_*`,
`SMOKE_DOCTOR_ID` e `SMOKE_CLINIC_ID` documentados no próprio script. O smoke de
pré-consulta registra interações demonstrativas; não rodá-lo indiscriminadamente
sobre o banco de validação. Registre scripts realmente executados no ROADMAP.

## 7. CI existente e gates propostos

`.github/workflows/ci.yml`: Python 3.14, PostgreSQL 17 descartável; executa check,
drift de migrações, migrate, duas cargas de demo e toda a suíte. PRs de qualquer
base disparam CI; pushes apenas para `main`. Nome do check: `Django checks and tests`.
Valores do serviço são exclusivos de CI, não contas padrão da aplicação.

A CI não faz deploy, smoke browser, backup/restore, validação de HTTPS ou ensaio
de concorrência real. Check aprovado não comprova prontidão para dados reais.
Publicação da PR 00 autorizada após revisão local; resultados da CI da entrega
serão registrados no ROADMAP, sem inferir aprovação da configuração do workflow.
Evidência histórica da base e resultados locais ficam no [ROADMAP](planning/ROADMAP.md).

## 8. Atualização e rollback — procedimento proposto

Não executado em homologação/produção, pois esses ambientes não estão provisionados.

1. Confirmar SHA alvo, CI, revisão, alterações de dependências e plano das migrações.
2. Em checkout limpo, atualizar sem sobrescrever trabalho local (`git fetch` e
   atualização fast-forward da branch apropriada). Registrar SHA anterior.
3. Fazer backup PRIVADO do banco/mídias do ambiente, e confirmar que restauração
   foi ensaiada em ambiente separado. Não gravar dumps no Git ou enviá-los ao chat.
4. Planejar janela/manutenção, instalar dependências do SHA, aplicar migrações
   revisadas e executar validações de configuração, login, escopos e anexos.
5. Reiniciar somente a instância alvo usando o processo de deploy que ainda será
   escolhido, observar erros e registrar resultado no ROADMAP.

Rollback de código só é seguro se compatível com o esquema/dados atuais; usar
o SHA anterior validado em checkout limpo/separado, sem reset destrutivo. Reversão
de migração pode apagar dados (ex.: auditoria de 0005); não oferecer um downgrade
automático. Exige plano específico e autorização, com restore privado validado
ou correção progressiva. Nunca recriar banco, fazer flush ou restaurar backup
por cima de dados novos sem conciliação e decisão humana.

## 9. Homologação e produção — ainda pendentes

Antes de homologar, aprovar hosting e processo WSGI, banco persistente separado,
gestão de segredos, TLS/domínio/proxy, distribuição de estáticos, armazenamento
privado de mídias, backup/restore e coleta de logs sem conteúdo clínico. Não há
Gunicorn, Dockerfile, manifestos de cloud ou pipeline de deploy implementados.
`WSGI_APPLICATION` existir não significa um serviço WSGI provisionado.

Antes de expor a instância, executar `python manage.py check --deploy` sob a
configuração REAL proposta e investigar os avisos. Hoje faltam configuração
de HTTPS/cookies seguros/HSTS, `STATIC_ROOT`/pipeline de `collectstatic`, política
de validação de senha (`AUTH_PASSWORD_VALIDATORS=[]`), limites de login, retenção,
observabilidade e restore ensaiado. Não alterar essas configurações na PR 00.

Homologação da trilha Pré-IA usa dados fictícios e provedores simulados. Produção
com pacientes reais depende de segurança, conformidade, consentimento e processo
operacional aprovados. Revisão documental, CI e `DEBUG=False` não substituem esses gates.

## 10. Manutenção deste documento

Atualizar dependências/variáveis/procedimentos quando mudarem, segundo a
[política de contribuição](../CONTRIBUTING.md). Registrar sempre no ROADMAP
o que foi executado, em qual backend/SHA, resultados e limitações; separar
planejamento de infraestrutura efetivamente provisionada.
