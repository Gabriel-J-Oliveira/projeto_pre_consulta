# Roadmap de execução Pré-IA

Referência oficial de planejamento, resultados e próximo passo. Atualização:
14/10/2026. Base auditada: `main`, SHA
`1e199b4577d8a6c64b30c3744d4bea4adfd308bf`, confirmado igual ao remoto.
Árvore inicial limpa; origem: `Gabriel-J-Oliveira/projeto_pre_consulta`.

Referências: [conceito e auditoria](README.md), [operação/deploy](../deploy.md),
[estados atuais](../state-engine.md), [histórico da migração](../repository-migration.md),
[política documental](../../CONTRIBUTING.md).

## 1. Identificação, estados e evidências

PR 00–06 são **identificadores lógicos do plano**, não os números das PRs do
GitHub. Não confundir PR 01 deste plano com a integração histórica GitHub #1.
Preencher o número/link real somente quando uma PR for autorizada e criada.

Estados: pendente (não iniciada), em execução (trabalho local), em revisão
(aguardando avaliação, inclusive revisão local explicitamente identificada),
concluído (escopo implementado, validado, revisado/integrado conforme gates),
bloqueado (impedimento concreto registrado). Uma base demonstrativa não conclui
o incremento produtivo correspondente. Não inventar aprovação ou resultado de CI.

| Entrega | Estado | Dependência | Branch proposta/real | PR e commit da entrega |
| --- | --- | --- | --- | --- |
| PR 00 — Preparação/documentação | Em revisão; publicação autorizada | Base auditada | `chore/prepare-pre-ai` (real) | Publicação em andamento; evidências abaixo |
| PR 01 — Domínio/consentimento | Pendente | Revisão da PR 00 + decisões D01–D04 | `feature/pre-ai-domain-consent` (proposta) | Não criados |
| PR 02 — Entrada unificada | Pendente | PR 01 + origem/autorização D05 | `feature/pre-ai-event-ingestion` (proposta) | Não criados |
| PR 03 — Persistência/rastreabilidade | Pendente | PR 02 + escopo longitudinal D06 | `feature/pre-ai-traceability` (proposta) | Não criados |
| PR 04 — Orquestrador/contrato IA | Pendente | PR 03 + contrato/processamento D07 | `feature/pre-ai-orchestration` (proposta) | Não criados |
| PR 05 — Revisão médica | Pendente | PR 04 + liberação clínica D04 | `feature/pre-ai-medical-review` (proposta) | Não criados |
| PR 06 — Testes/handoff | Pendente | PR 05 + critérios operacionais D08 | `chore/pre-ai-handoff` (proposta) | Não criados |

Sequência preservada: 00 → 01 → 02 → 03 → 04 → 05 → 06. Contratos podem ser
discutidos cedo entre os dois desenvolvedores, sem implementar entregas futuras.
Se um incremento exigir subdivisão (ex.: esquema de persistência e armazenamento
privado), registrar novas unidades/gates aqui ANTES de implementá-las e pedir
aprovação; não mudar ordem ou escopo silenciosamente. Não há subdivisão aprovada
nesta PR 00: a ordem solicitada atende às dependências identificadas.

## 2. Gates comuns a todos os incrementos

- Escopo autorizado, decisões necessárias aprovadas e base real confirmada.
- Reutilização de apps/modelos/rotas existentes; migrações aditivas/revisadas
  quando necessárias, sem reset de histórico ou transferência automática de banco.
- Isolamento por médico/consulta e clínica; recepção sem conteúdo clínico;
  administração técnica sem privilégios clínicos implícitos.
- Dados fictícios, nenhuma credencial padrão, nenhum segredo/banco/log publicado.
- Check, drift de migrações, testes e validações específicas executados; CI real
  do SHA publicado quando houver publicação. Falhas/limitações são registradas.
- Atualização documental obrigatória e revisão do outro desenvolvedor antes da
  integração planejada. Hoje a proteção de main não é imposta remotamente.
- Push/abertura de PR/merge só após autorização explícita. Não avançar
  automaticamente para o próximo incremento.

## 3. PR 00 — Preparação e documentação

Objetivo: auditar a base, estabelecer referências oficiais e preparar execução
incremental, sem alterar o runtime.

Escopo: auditoria de arquitetura, domínio, estados, migrações, permissões,
views/URLs, testes, CI, documentação e governança; conceito atualizado; deploy
honesto; roadmap e política contínua em CONTRIBUTING/AGENTS/checklist de PR.

Aceite:

- Base e ausência de mudanças locais iniciais confirmadas; diagnóstico ancorado
  no código, distinguindo implementado, parcial, demonstrativo e ausente.
- Documentos oficiais conectados, sem instruções operacionais concorrentes.
- Decisões não aprovadas listadas, responsabilidades e dependências explícitas.
- Aplicação, esquema, workflow e configurações remotas intactos.
- Validação antes/depois comparada, links locais verificados e diff revisado.
- Revisão documental local favorável; commit/push/PR autorizados pelo solicitante.
  Manter PR aberta para análise, sem merge e sem iniciar PR 01.

Fora do escopo: qualquer implementação 01–06, integração real IA/WhatsApp,
novos modelos/apps/endpoints/telas, proteção remota, bancos ou usuários locais.

## 4. PR 01 — Domínio e consentimento

Reaproveitar `Consultation.status`, grafo/serviço `state_engine`, eventos e scopes.
Não adicionar um segundo estado de pré-consulta. Preservar `ready` legado sem
confundi-lo com `completed` e sem liberar automaticamente os casos incompletos.

Implementação futura, após aprovação:

- Evidências versionadas do consentimento, associadas à consulta, versão do termo,
  origem e momento; distinguir simulação de evidência real. Forma e campos finais
  dependem de D01, não são um modelo aprovado nesta preparação.
- Pré-condições explícitas de transições, atores autorizados e regras de recusa,
  cancelamento/incompletude; não criar retomada/reabertura por suposição.
- Atualização atômica com evento/auditoria; compatibilidade dos registros legados.
- Separação de conclusão operacional e autorização de publicação clínica.

Aceite/testes: consentimento ausente/incorreto/versionado e duplicado; transições
válidas/inválidas; escopo dos atores; rejeição de clínica/consulta forjada; rollback
do evento; migração de registros legados sem autoria/consentimento inventados.
Fixtures simuladas não devem produzir evidência apresentada como consentimento real.

Gates: D01–D04 aprovadas. Não criar login web de pacientes ou WhatsApp nesta etapa.

## 5. PR 02 — Entrada unificada

Criar interface INTERNA de eventos/mensagens, com envelope/identidade/origem
documentados e validação de contexto. Não abrir webhook externo por conveniência.
Reutilizar dados e políticas do domínio, sem tratar `OperationalEvent.event_key`
como mecanismo completo de deduplicação de entrada.

Escopo futuro: mensagens e metadados de mídia, origem/correlação, chave de
idempotência com namespace de origem, deduplicação, simulador determinístico.
Entrada inválida, reentrega e falha parcial não criam fontes/eventos duplicados.
Receber metadado não significa baixar, armazenar, transcrever ou analisar mídia.

Aceite/testes: reentrega da mesma mensagem, mensagens distintas com conteúdo igual,
chaves em origens distintas, payload inválido, autorização por consulta/clínica,
consentimento aplicável, ordem e falha/reexecução. Definir respostas/erros da
interface com D05; não antecipar o envelope final de WhatsApp Cloud API.

Dependência: PR 01; nenhum serviço externo, credencial ou convite real.

## 6. PR 03 — Persistência e rastreabilidade

Reutilizar `SourceItem`, `SummaryItem`, vínculo item–fonte e relações de consulta.
Fonte original deve continuar disponível e não ser sobrescrita pelo resultado
estruturado. O campo `original_value` e correções atuais não bastam como esquema
completo de versões de resultados e entradas.

Escopo futuro: preservação/versionamento, associação a fontes, metadados de
proveniência, histórico longitudinal básico com escopo aprovado e abstração de
armazenamento privado. Não adicionar DOB/prontuário/CRUD de pacientes por arrasto.
Não escolher S3, armazenamento externo ou novo provedor sem decisão D06/D08.

Aceite/testes: múltiplas versões preservadas, referências a fontes da própria
consulta, rejeição de IDs externos, acesso autorizado a mídia e histórico,
recepção/administrador técnico sem conteúdo clínico, coexistência das fixtures
com dados novos. Histórico por paciente não deve liberar consultas de outros
médicos/clínicas; D06 define o recorte antes da implementação.

Dependência: PR 02. Estrutura genérica de versões nesta etapa; schema final de
resultado de IA é acordado em PR 04, evitando contratos concorrentes.

## 7. PR 04 — Orquestrador e contrato da IA

Responsabilidade do backend: interface desacoplada do provedor, contratos
versionados, seleção explícita de provedor fictício, validação técnica dos
resultados e persistência/rastreabilidade. Não assumir que resposta válida
de um modelo autoriza acesso clínico.

Escopo futuro: `FakeAIProvider` determinístico, processamento, erros, tentativas,
idempotência/correlação e consumo de resultados via serviço. Estado técnico de
processamento deve ter propósito próprio documentado; não duplicar o estado
operacional da consulta nem mover regras para views.

Aceite/testes: mesmo input versionado → saída fictícia previsível; contrato
inválido/versão incompatível/fonte externa rejeitados; erro, retry, duplicata e
resultado obsoleto sem corrupção ou publicação; nenhuma chamada de rede real;
persistência de origem e versões. Forma concreta, limites, sincronismo/filas e
política de tentativas exigem D07 — Celery/Redis não são escolhas aprovadas.

Interface do outro desenvolvedor: implementação da IA/prompts, entrevista
adaptativa, extração, síntese/pontos de atenção e validação semântica dos resultados,
respeitando o contrato backend. API, DTOs e formatos finais NÃO existem ainda.

Aceite explícito do contrato da PR 04:

- Contrato de integração versionado, com política de compatibilidade acordada.
- Exemplos fictícios de payloads de entrada e saída.
- Erros e comportamentos esperados documentados, incluindo rejeição, retry,
  duplicação e resultado obsoleto.
- `FakeAIProvider` funcional, determinístico e sem chamadas externas.
- Testes de conformidade reutilizáveis pelo futuro provedor real.
- Fronteiras e responsabilidades de cada desenvolvedor documentadas: backend
  controla autorização, consentimento, domínio, persistência e publicação; IA
  implementa o provedor, prompts e validação semântica dentro do contrato.

Após a aprovação do contrato da PR 04 e entrega desses artefatos, o desenvolvedor
da IA pode iniciar trabalho independente contra os exemplos e testes de
conformidade, SEM aguardar a PR 06. O backend segue PR 05–06 usando o provedor
fictício. Mudanças no contrato exigem coordenação e versionamento; esse início
independente não autoriza integração real no backend, deploy ou acesso clínico.
PR 06 consolida testes/handoff final, não é pré-requisito desse início da IA.

Dependência: PR 03; não integrar modelo real nesta trilha de preparação.

## 8. PR 05 — Consumo e revisão médica

Reaproveitar telas, vínculo resumo–fontes, notas, correções e feedback existentes.
Não reescrever a UI nem liberar acesso só porque um processamento terminou.

Escopo futuro: consumir resultados versionados/validados, publicar clinicamente
com gate D04, permitir revisão preservando fonte original e autoria/trilha de
correções/feedback. Compatibilizar o conteúdo novo com o caso demonstrativo pronto.

Aceite/testes: médico atribuído e clínica vinculada; sem perfil/recepção/administrador
técnico bloqueados; consulta concluída sem publicação bloqueada; resultados/fontes
corretos; autoria e encadeamento de correções auditáveis; ausência de diagnóstico
automático apresentado como decisão clínica. Smokes desktop/mobile proporcionais.

Dependência: PR 04 + decisão explícita de quem/o que publica em `ready`.

## 9. PR 06 — Testes integrados e handoff

Integrar a trilha fictícia: cadastro → consentimento simulado identificado →
entrada unificada → persistência/versionamento → fake processing → gate de
publicação → revisão médica. Verificar falhas sem executar IA/WhatsApp real.

Aceite/testes: duplicatas, retry, inconsistência de versão, rollback, isolamento
entre clínicas/médicos, conteúdo vedado à recepção, arquivos inacessíveis,
consentimento/estado inválido e regressões. Validar concorrência real no PostgreSQL
quando o desenho aprovado exigir, além dos testes atuais de atualização condicional.

Handoff: contrato versionado, exemplos/fixtures fictícios, FakeAIProvider,
procedimento de execução, expectativas/erros, estratégia de versionamento,
evidências de testes/CI e limites do backend entregues ao outro desenvolvedor.
Infra/homologação seguem gates de [deploy](../deploy.md), sem declarar ambientes
provisionados. WhatsApp Cloud API, webhooks reais e recebimento de mídia entram
na sprint posterior, não nesta PR.

## 10. Decisões que exigem aprovação humana

| ID | Decisão pendente | Gate |
| --- | --- | --- |
| D01 | Texto/versões do consentimento, evidência aceitável, representante do paciente e distinção de simulação/real | PR 01 |
| D02 | Quais atores/origens podem executar cada transição em produção | PR 01 |
| D03 | Motivos/critérios de incompletude/cancelamento, eventual retomada/reabertura e timeout | PR 01; nada inferido automaticamente |
| D04 | Critérios/ator de publicação clínica, uso dos casos incompletos e relação entre completed/ready | PR 01 define fronteira; PR 05 implementa publicação |
| D05 | Envelope interno, autenticação de origem, namespace de idempotência e regras de ordenação | PR 02 |
| D06 | Escopo longitudinal por paciente sem ampliar acesso entre médicos/clínicas; retenção/versionamento e mídias | PR 03 |
| D07 | Contratos IA, versão, limites de input/output, retry e execução síncrona/assíncrona | PR 04, acordo com desenvolvedor de IA |
| D08 | Hosting/homologação, armazenamento privado, backup/restore, segurança e critério de prontidão | Antes de deploy; PR 03/06 conforme escopo |
| G01 | Autorizar configuração da proteção main e conceder acesso ao segundo desenvolvedor | Governança; não aplicado em PR 00 |

O roadmap foi solicitado, mas essas regras específicas não foram aprovadas.
Não considerar uma proposta de documentação decisão de produto. Não houve
consulta ao Notion nesta execução; requisitos adicionais precisam de evidência
autorizada ou validação humana, não de suposição.

### D01 — Consentimento versionado, inicialmente simulado

Proposta técnica ainda NÃO aprovada. Alternativas: apenas status/evento;
evidência versionada inicialmente simulada; coleta real integrada desde o início.
Recomendação: evidência versionada vinculada à consulta, identificando versão,
origem, momento e simulação, sem inventar consentimento para registros legados.
Riscos: status isolado não comprova consentimento; simulação confundida com prova;
integração real prematura exige identidade e requisitos ainda não aprovados.
Consequências: migração aditiva e testes de evidência/versão na PR 01; texto do
termo, representação e evidência juridicamente aceitável continuam pendentes.

### D02 — Matriz explícita de transições por ator e origem

Proposta técnica ainda NÃO aprovada. Alternativas: reutilizar permissões genéricas
do simulador; matriz explícita por transição/ator/origem; liberar por staff/admin.
Recomendação: matriz centralizada no domínio, com negação por padrão e escopo de
consulta/clínica, distinguindo simulação de origens futuras autenticadas.
Riscos: matriz incompleta pode bloquear operações; permissões genéricas ou flags
técnicas podem ampliar acesso; origem declarada não comprova identidade.
Consequências: equipe precisa aprovar cada combinação e pré-condição antes da
PR 01; testar negações e auditoria. A matriz não concede acesso clínico.

### D03 — Estados finais sem reabertura ou timeout automático

Proposta técnica ainda NÃO aprovada para o primeiro incremento. Alternativas:
estados finais sem saída; reabertura manual auditada; retomada/timeout automáticos.
Recomendação: manter estados finais sem reabertura e sem timeout automático,
preservando o grafo conservador e o `ready` legado; transições sempre explícitas.
Riscos: operações interrompidas não poderão ser retomadas pelo motor; automações
prematuras podem encerrar ou reabrir casos sem critérios clínicos/operacionais.
Consequências: motivos e critérios de incompletude/cancelamento precisam de
aprovação; eventual retomada e relógios exigem incremento posterior aprovado,
sem inferir uma regra nova nesta preparação.

### D04 — Publicação por serviço autorizado

Proposta técnica ainda NÃO aprovada. Alternativas: promoção automática de
`completed` para `ready`; escrita direta pelas views/ORM; serviço autorizado
com validações e auditoria explícitas de publicação.
Recomendação: serviço autorizado, sem promoção automática de `completed` para
`ready`, validando consentimento aplicável, versão/proveniência dos resultados e
escopo. Ator e critérios finais devem ser aprovados; não são definidos aqui.
Riscos: publicação automática expõe material não validado; escrita dispersa
contorna gates; serviço incompleto pode bloquear liberação legítima.
Consequências: PR 01 preserva a fronteira; PR 05 implementa a publicação após
aprovação. `ready` significa disponível para revisão, não aprovação clínica;
casos incompletos seguem bloqueados até decisão explícita da equipe.

Estas quatro recomendações não constituem decisões jurídicas, clínicas ou
funcionais definitivas. Aprovar publicação da PR 00 não aprova D01–D04.

## 11. Governança Git observada e recomendada

Consulta somente leitura em 14/10/2026: API de proteção de main retornou
`Branch not protected`; rulesets aplicáveis retornaram lista vazia. Nenhuma
configuração remota foi alterada. CI existe, mas não é gate imposto de merge.

Recomendação para duas pessoas, dependente de autorização G01: exigir PR,
aprovação do OUTRO desenvolvedor, invalidar revisões obsoletas/aprovar o último
push, check `Django checks and tests` obrigatório e base atualizada; exigir
resolução de conversas, bloquear force push/exclusão e aplicar também a admins,
sem bypass. Usar branches curtas por tarefa, não por pessoa. Não adicionar checks
inexistentes que bloqueiem PRs. Configuração administrativa somente com pedido
explícito; este plano não a habilita.

## 12. Histórico e validações de execução

Histórico anterior: [mapa de migração](../repository-migration.md).
GitHub #1 integrou o código; GitHub #7 integrou histórico/documentação; #2–#6
são registros fechados sem merge. Não são entregas concluídas do plano Pré-IA.

| Data/etapa | Branch/PR/commit | Resultado e evidência |
| --- | --- | --- |
| 11/10/2026 — base histórica integrada | `main`, GitHub #7, `1e199b4` | [CI 38150293707](https://github.com/Gabriel-J-Oliveira/projeto_pre_consulta/actions/runs/38150293707) aprovada com PostgreSQL 17.11, 86 testes, migrações/demo duas vezes |
| 14/10/2026 — auditoria antes de editar | `main`, mesmo SHA | Check sem problemas; drift sem alterações; 86 testes SQLite aprovados, banco de testes temporário |
| 14/10/2026 — PR 00 preparação, entregue para revisão local | `chore/prepare-pre-ai`, base/HEAD `1e199b4`; sem commit/PR da entrega | Check sem problemas; drift sem alterações; 86 testes SQLite aprovados novamente (antes: 86; depois: 86), sem regressão. 46 links Markdown locais e 12 referências externas GitHub válidas; diff sem whitespace errors |
| 14/10/2026 — finalização autorizada da PR 00 | `chore/prepare-pre-ai`, base `1e199b4`; publicação em andamento | Check sem problemas; drift sem alterações; 86 testes SQLite aprovados em 25,419 s. Revisão dos nove documentos, incluindo três novos; 50 links locais válidos; nenhum código/configuração funcional alterado. CI da entrega ainda não executada neste registro |

Dados/configurações locais existentes foram comparados por hash antes/depois e
permaneceram iguais nos três bancos SQLite encontrados; nenhum `.env` existia
na cópia nova. Código, modelos, migrações, UI, dependências e workflow não mudaram.
Documentos de conceito/deploy foram atualizados, README consolidou navegação e
procedimentos, política foi registrada em CONTRIBUTING/AGENTS/template de PR.
Histórico de migração foi revisado e recebeu referência explícita à PR #7 integrada.
Documento do motor esclareceu que passar actor no shell não é autenticação do
paciente/sessão; somente a redação foi corrigida, sem mudança no serviço/grafo.

Ambiente local desta auditoria: Python da `.venv` já existente no worktree anterior,
executando `manage.py` do NOVO repositório; backend SQLite explícito e variáveis
efêmeras no processo. Não copiadas credenciais/banco; não instalado ambiente novo.
Não encontrados `docker`/`psql` no PATH, portanto sem validação PostgreSQL local.

Smokes browser não executados nesta preparação: nenhuma UI/runtime alterada e
sem manipular conta/banco de validação. Testes Django existentes continuam obrigatórios.
Publicação foi autorizada após revisão favorável; CI da entrega será verificada
após abertura da PR. A CI histórica
da base não é uma execução de `chore/prepare-pre-ai`.
Nenhuma migração, seed, reset/flush, criação de usuário ou reinício de servidor
foi executado no banco/instância de validação. Seeds executados pelos testes
ficaram somente no banco temporário. Check --deploy não foi executado com ambiente
real de homologação/produção inexistente; é gate futuro, não resultado aprovado.

## 13. Problemas conhecidos e próximo passo

Consentimento real/versões, ingestão idempotente, processamento/contratos,
resultados estruturados versionados e release clínico não existem. Rastreabilidade
de fontes/correções é parcial; notas/correções/feedback não registram usuário;
o grafo atual é simulador e `load_demo` sobrescreve fixtures. Arquivos de mídia
são locais, não upload/armazenamento privado de produção. Hardening e deploy
ainda faltam; ver [auditoria conceitual](README.md) e [pendências operacionais](../deploy.md).

Próximo passo: publicar somente a PR 00 autorizada, aguardar CI real e análise
do solicitante antes de integrar. Merge e PR 01 NÃO estão autorizados.
Antes da PR 01, decidir D01–D04 e
formalizar critérios de aceite. Primeiro recorte recomendado: evidência versionada
SIMULADA claramente identificada e pré-condições do serviço existente, sem publicar
ready, alterar acesso a incompletos ou criar transporte/paciente web. Só implementar
esse recorte após aprovação. Não iniciar PR 01 automaticamente.

## 14. Registro obrigatório em cada entrega

Atualizar estado e histórico com data, branch, SHA de base e da entrega quando
existirem, número/link real de PR, escopo executado, testes/backend/resultados,
CI real, decisões aprovadas (quem/quando/referência), falhas, riscos, documentos
revisados e próximo passo. Campos inexistentes devem permanecer explicitamente
“não criado/não executado”; nenhuma funcionalidade concluída sem evidência.
Política permanente: [CONTRIBUTING](../../CONTRIBUTING.md); instruções do agente:
[AGENTS](../../AGENTS.md).
