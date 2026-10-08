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
4. Envie a branch e abra um PR para `main` usando o modelo do repositório.
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
próprio banco SQLite local. Uma eventual troca de banco ou de tecnologia depende de
decisão explícita da equipe e não faz parte do fluxo normal de contribuição.
