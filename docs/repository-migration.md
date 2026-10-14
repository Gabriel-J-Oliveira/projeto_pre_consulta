# Migração de repositório — 11/10/2026

Repositório atual: `Gabriel-J-Oliveira/projeto_pre_consulta`.
Origem histórica: `projetopreconsulta-stack/preconsulta` e a etapa local do motor
de estados. O repositório anterior e seus checkouts/bancos não foram alterados.

## Código e histórico

A [PR #1](https://github.com/Gabriel-J-Oliveira/projeto_pre_consulta/pull/1)
integrou o projeto completo em `main`, no merge
`be755829a83b54fae4b5c3bb16e8e6110c904785`. Sua CI real passou com PostgreSQL
17.11 e 86 testes. O commit de implementação foi `2b062fb`.

A [PR #7](https://github.com/Gabriel-J-Oliveira/projeto_pre_consulta/pull/7)
conectou o histórico anterior ao atual, no merge
`1e199b4577d8a6c64b30c3744d4bea4adfd308bf`, por um merge de históricos
independentes. A estratégia `ours` conservou a árvore atual: os antigos README,
URLs e formatação não substituem a versão atualizada do novo repositório.
Os nove commits antigos mantêm seus SHAs/autoria e ficam alcançáveis pela história
integrada; não são recriados por cherry-pick nem reescritos por rebase.
Somente a documentação da migração foi alterada nessa etapa. A
[CI desse merge](https://github.com/Gabriel-J-Oliveira/projeto_pre_consulta/actions/runs/38150293707)
passou com PostgreSQL 17.11 e 86 testes. Esta é evidência histórica da base,
não de incrementos novos. Referência conferida novamente em 14/10/2026 na PR 00.

O histórico foi inspecionado antes da publicação: não foram encontrados bancos,
`.env` reais, ambientes virtuais, artefatos, arquivos clínicos binários ou os
padrões de chaves/tokens pesquisados. A inspeção por padrões não substitui uma
auditoria de segurança de produção. Dados demonstrativos continuam fictícios.

## Branches preservadas

| Branch no novo repositório | SHA histórico preservado |
| --- | --- |
| `archive/previous-main` (antiga `main`) | `183e953f1ce1926f9a3fe345510503bd9e9f2644` |
| `chore/prepare-two-dev-environment` | `cc13d98aaa58e055d238a2570858b62f2cccb742` |
| `feature/authentication` | `5e87721aab91d07f53e968a0ffd79de97e0cfc68` |
| `feature/clinic-user-permissions` | `80afb0a6c6f21c3271d9a4baefffcab5b088b2dd` |
| `feature/patient-registration` | `0678e96aa3a297fa70852bf70b86b95c325a7cc0` |
| `feature/preconsultation-state-engine` | `5474f4f46276a2667754517591d2eee8a86cb5e5` |

São referências históricas. Novos cards devem partir de `main` atualizada, não
dessas snapshots, que podem conter links/documentação do repositório anterior.

## Correspondência das PRs

| Origem | Registro no novo repositório |
| --- | --- |
| [Antiga #1 — base colaborativa](https://github.com/projetopreconsulta-stack/preconsulta/pull/1) | [Nova #2](https://github.com/Gabriel-J-Oliveira/projeto_pre_consulta/pull/2) |
| [Antiga #2 — autenticação](https://github.com/projetopreconsulta-stack/preconsulta/pull/2) | [Nova #3](https://github.com/Gabriel-J-Oliveira/projeto_pre_consulta/pull/3) |
| [Antiga #3 — clínicas/permissões/PostgreSQL](https://github.com/projetopreconsulta-stack/preconsulta/pull/3) | [Nova #4](https://github.com/Gabriel-J-Oliveira/projeto_pre_consulta/pull/4) |
| [Antiga #4 — cadastro de pacientes](https://github.com/projetopreconsulta-stack/preconsulta/pull/4) | [Nova #5](https://github.com/Gabriel-J-Oliveira/projeto_pre_consulta/pull/5) |
| Etapa local do motor, sem PR antiga | [Nova #6](https://github.com/Gabriel-J-Oliveira/projeto_pre_consulta/pull/6) |

As PRs #2–#6 foram recriadas como registros históricos e fechadas **sem merge**,
porque a implementação atual já entrou pela PR #1. Conservam as comparações entre
branches e links às descrições originais; as quatro PRs antigas permanecem intactas.
Não são PRs aprovadas ou merges históricos inventados. Números, autoria de PR,
comentários, revisões, aprovações e checks não são transferíveis por essa operação.
Para esses detalhes, consultar as PRs originais vinculadas.

## Fluxo daqui para frente

Use somente `Gabriel-J-Oliveira/projeto_pre_consulta` como destino de novos cards.
Atualize `main` e crie branches curtas por tarefa. README da raiz é o índice;
o guia operacional é [docs/deploy.md](deploy.md), e o contexto autossuficiente
para planejamento fica em [docs/planning/README.md](planning/README.md).

No momento desta migração, a nova `main` não tinha proteção nem rulesets aplicáveis.
O solicitante autorizou explicitamente os merges; nenhuma regra foi removida ou
contornada. Configurar aprovação de outro desenvolvedor e checks obrigatórios
para colaboração continua recomendado e deve ser tratado separadamente.
