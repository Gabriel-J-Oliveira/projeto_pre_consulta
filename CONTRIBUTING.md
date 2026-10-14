# Como contribuir

Este repositório é mantido por dois desenvolvedores. Toda alteração deve ser curta,
revisável e integrada por Pull Request (PR) para `main`.

## Fluxo de trabalho

1. Atualize sua cópia local de `main` antes de iniciar uma tarefa.
2. Crie uma branch específica para a tarefa:
   - `feature/<card>-<descricao>` para funcionalidades;
   - `fix/<card>-<descricao>` para correções;
   - `chore/<descricao>` para manutenção e configuração.
3. Faça commits pequenos, com mensagens que expliquem a intenção da alteração.
4. Após autorização explícita do solicitante, envie a branch e abra um PR para
   `main` usando o modelo do repositório. Não publique por inferência.
5. Aguarde o CI e solicite a revisão do outro desenvolvedor.
6. Resolva comentários e mantenha o PR atualizado antes da integração.

Não crie branches permanentes por pessoa e não envie commits diretamente para
`main`. Force push em `main` não é permitido. Em uma branch de tarefa, evite
reescrever histórico depois que a revisão começar.

## Critérios para o PR

- Explique o problema e a solução de forma objetiva.
- Inclua somente arquivos relacionados à tarefa.
- Execute `python manage.py check` e `python manage.py test` localmente.
- Confirme que não há migrações pendentes com
  `python manage.py makemigrations --check --dry-run` quando modelos forem afetados.
- Não altere telas ou comportamento fora do escopo do PR.
- Exija uma aprovação do outro desenvolvedor e o CI aprovado antes do merge.

## Segurança e dados

Nunca versione `.env`, `db.sqlite3`, ambientes virtuais, logs, mídias locais,
credenciais, tokens, documentos reais ou dados pessoais/de pacientes. Os dados de
demonstração devem permanecer claramente fictícios. Se houver dúvida sobre a origem
de um arquivo ou dado, não o inclua no commit e registre a questão no PR.

Cada desenvolvedor deve criar seu próprio `.env` a partir de `.env.example` e seu
próprio banco PostgreSQL local conforme o README. SQLite é uma opção explícita
para quem não dispõe de PostgreSQL. Não compartilhe bancos ou credenciais.
Mudanças futuras de tecnologia dependem de decisão da equipe.

## Documentação contínua obrigatória em TODO incremento

Antes de implementar, leia o [conceito](docs/planning/README.md),
[deploy](docs/deploy.md), [ROADMAP](docs/planning/ROADMAP.md) e [AGENTS](AGENTS.md).
Audite o estado real e reutilize o que já existe. Não iniciar outro incremento
automaticamente; decisões não aprovadas e diferenças de base devem ser relatadas.

Ao finalizar cada entrega:

1. Atualize conceito/arquitetura quando domínio, arquitetura ou comportamento mudarem.
2. Atualize deploy quando dependências, configuração, migrações ou operação mudarem.
3. Atualize SEMPRE o ROADMAP com estado, branch, SHA/PR reais quando existirem,
   testes/backend/resultados, decisões, limitações, problemas e próximo incremento.
4. Atualize o README principal só para informações relevantes e links.
5. Registre quando conceito/deploy foram revisados e não exigiram alteração.
6. Não declarar concluído sem implementação, validação e gates de revisão/integração
   acordados. “Em revisão local” não significa PR publicada ou CI executada.
7. Não duplicar procedimentos nem criar instruções concorrentes: deploy é a fonte
   operacional; conceito é a fonte arquitetural; ROADMAP registra execução.

Não invente número de PR, SHA futuro, aprovação ou sucesso de CI. PR 00–06 são
IDs do plano, não números GitHub. Se a validação não puder ser executada, registre
a causa. Mudanças documentais também passam por check, drift e suíte existentes.
Pausa para revisão significa parar antes do incremento seguinte; publicação e
merge precisam de autorização própria, sem contornar proteção.

## Governança remota: situação e recomendação

Em 14/10/2026, `main` não tem proteção/rulesets aplicáveis. O padrão de revisão
descrito aqui é política da equipe, não garantia de bloqueio no GitHub. CI existente
tem o check `Django checks and tests`, executado em PRs de qualquer base.

Recomendação, somente após autorização administrativa: PR obrigatória, uma
aprovação do outro desenvolvedor, revisão válida após último push, CI aprovada
e base atualizada, conversas resolvidas, bloqueio de force push/exclusão e sem
bypass de admins. Não adicionar checks sem implementação. Nenhuma dessas regras
foi habilitada pela PR 00; registrar decisão/execução futura no ROADMAP.
