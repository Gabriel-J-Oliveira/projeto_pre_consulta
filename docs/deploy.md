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

Migrações de domínio nesta branch PR 05: `0001`–`0010`; não apagar, renumerar, fazer
`--fake` ou reiniciar o histórico. PR 00 não cria/aplica migração. SQLite usa
`db.sqlite3` da cópia atual; transferência de dados para PostgreSQL não é
automática nem está aprovada como operação desta preparação.

PR 01 acrescenta `0006_simulated_consent_evidence`, sem migração de dados ou
backfill. Aplicar com `migrate` somente na cópia/banco que receber esse incremento,
após revisar `migrate --plan`; não migrar a instância preservada em outra branch
para validar este trabalho. Reverter 0006 remove a tabela de evidências: não
executar rollback sobre evidências existentes sem plano e autorização.
Validação interna por shell e consentimento simulado: [motor](state-engine.md).
Não há nova variável, credencial, dependência ou serviço externo.

PR 02 acrescenta `0007_inboundmessage` sobre 0006, somente tabela/constraints.
Não cria mensagens históricas nem transforma SourceItem/SummaryItem. Upgrade
incremental validado por teste em banco temporário. Reverter 0007 remove entradas
duráveis: não reverter sobre dados preservados sem plano/autorização. Nenhuma
dependência, variável de ambiente, endpoint ou serviço novo é necessário.

PR 03 acrescenta `0008_source_provenance_summary_revisions`: campos de origem
opcionais em SourceItem, escolhas de imagem/simulação e tabelas de snapshots.
Não cria entradas/fontes/revisões para registros existentes. Revisar migrate
--plan e aplicar somente no banco/cópia que receber a branch; não executar nas
instâncias preservadas para validar. Reversão apaga tabelas/vínculos de origem:
exige plano/autorização se houver dados. Sem nova configuração ou dependência.
`load_demo` mantém legados sem vínculos artificiais, preserva fontes materializadas
e snapshots; seu reset demonstrativo ainda apaga correções, não os snapshots.

### Validação isolada da rastreabilidade

```powershell
python manage.py test preconsultas.test_traceability
```

Runner cria banco temporário, consulta fictícia, operador de recepção vinculado,
médico atribuído, aceite simulado e entrada. Testa materialização, mídia como
metadado, reentrega, snapshots, escopos, rollback e upgrade 0007→0008. Dois novos
testes concorrentes usam PostgreSQL; SQLite os ignora. Nenhum usuário padrão,
endpoint ou processo de IA criado. Não executar setup por shell no banco preservado.
Interfaces/justificativa do modelo: [conceito, seção 17](planning/README.md#17-proveniência-e-revisões-pr-03--d06-técnica-aprovada).

### Orquestrador/fake — execução isolada PR 04

`0009_ai_orchestration` cria AIExecution/AIAttempt/AIExecutionSource e constraints,
sem alteração/backfill de domínio, execuções antigas ou tabelas de resumo. Revisar
plano e aplicar só no banco/cópia autorizados para esse incremento. Upgrade 0008→0009
é ensaiado no banco de testes, não no SQLite preservado. Reverter 0009 apaga auditoria
técnica: sem downgrade automático ou autorização para apagar execuções existentes.
Nenhuma dependência, variável de ambiente, credencial ou serviço novo.

Com ambiente de testes configurado (SQLite explícito ou PG descartável):

```powershell
python -m preconsultas.ai_examples
python manage.py test preconsultas.test_ai_contract preconsultas.test_ai_orchestration
```

O primeiro comando imprime somente fixtures fixas fictícias, sem Django/DB/rede.
O segundo usa banco temporário, perfis explícitos e aceite simulado; não cria contas
ou senhas padrão. Não executar setup por shell, seed ou migração no banco preservado.
Dois testes novos concorrentes precisam PostgreSQL; ignorados no SQLite, não confundir
com aprovação de concorrência. CI existente PG17 em qualquer base executa toda suíte.
Execuções `running` após interrupção/falha de finalização exigem investigação humana;
sem timeout/recuperação/retry automático e sem remoção de linhas por conveniência.
Port/fake/contrato/retry e limites: [referência IA](ai/README.md).

### Publicação/revisão simuladas — PR 05

`0010_clinical_publication` acrescenta ClinicalPublication, vínculo de itens,
actor nullable em notas/correções/feedback e identificação de fixture legada.
Autoria anterior permanece nula; nenhum aceite, execução, publicação histórica
ou fonte é inventado. RunPython marca SOMENTE o caso-base ready conhecido com
identidade fictícia, fontes/síntese do seed e sem ingestão/execução; outros ready
permanecem bloqueados. A operação não altera seus estados nem apaga conteúdo.
load_demo marca sua fixture explicitamente, continua ferramenta de bootstrap,
nunca executar no banco preservado para validar essa entrega.

Revisar migrate --plan e aplicar apenas no banco/cópia autorizados para PR 05.
Upgrade 0009→0010 é ensaiado no banco temporário dos testes. Downgrade remove
auditoria/campos de autoria: requer plano/autorização, sem rollback automático.
Não há nova dependência Python/configuração/credencial/serviço externo.

```powershell
python manage.py test preconsultas.test_publication
python manage.py test
```

Testes criam completed/aceite fictícios e execução fake; médico atribuído/clínica
publica pelo serviço ou POST/CSRF do painel. Conteúdo só abre após publicação.
Serviço não chama provedor nem cria usuário padrão. Testes PG ensaiam publicação
inicial e correções concorrentes; ignorados no SQLite, não confundir com aprovação.
Publicação obsoleta é preservada/bloqueada; marca momento/usuário de necessidade
de validação e execução obsolete. Nenhuma mudança de estado ou republicação automática.

Smokes médicos opt-in reutilizam scripts existentes com Node/Playwright/Edge:

```powershell
python manage.py test preconsultas.visual_smoke
```

Esse módulo NÃO é descoberto pela suíte padrão/CI. StaticLiveServerTestCase cria
banco temporário e porta livre (não 8000/8001); credencial aleatória só no processo
de teste, sem imprimir/salvar segredo ou credencial padrão. Executa dashboard_smoke,
browser_smoke e publication_smoke em desktop/mobile; seed/feedback/correção somente
no banco TEMPORÁRIO. Capturas de dados fictícios em subdiretórios UUID de artifacts/
ignorados; não incluir no commit. Node deve resolver Playwright instalado (NODE_PATH
do runtime local se necessário); não é nova dependência da aplicação/CI. Referência
Windows de Edge permanece a dos smokes existentes. Nenhum servidor preservado é parado.

### Simulador de ingestão — somente banco fictício isolado

Use o ambiente de testes configurado acima, nunca conexão de produção, e execute:

```powershell
python manage.py test preconsultas.test_ingestion.IngestionTests.test_out_of_order_preserves_declared_and_arrival_order
python manage.py test preconsultas.test_ingestion
```

O runner cria/remove banco temporário e fixtures fictícias com operador sem senha
utilizável, perfil/clínica, aceite simulado e coleta iniciada explicitamente.
`ingestion_simulator.run_simulation` envia texto fora de ordem, duplicata e mídia,
e repete a sequência para conferir idempotência. Não cria contas padrão nem envia
mensagens. Não executar a função por shell no banco preservado; sua interface
recebe uma consulta e não consegue comprovar que seus dados sejam fictícios.
Contrato e retornos: [contexto conceitual, seção 16](planning/README.md#16-contrato-de-ingestão-pr-02--d05-restrita-à-simulação).
Concorrência no PostgreSQL usa testes com conexões/barreira; no SQLite são ignorados.

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

A CI não faz deploy, smoke browser, backup/restore ou validação de HTTPS. PR 01
inclui dois ensaios concorrentes de domínio no PostgreSQL; isso não constitui
teste de carga nem validação completa de produção. Check aprovado não comprova
prontidão para dados reais.
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
