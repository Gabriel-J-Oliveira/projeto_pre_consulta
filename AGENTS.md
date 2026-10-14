# Instruções para trabalho neste repositório

## Antes de implementar

- Leia `CONTRIBUTING.md`, `docs/planning/README.md`, `docs/planning/ROADMAP.md`
  e `docs/deploy.md`. Consulte `docs/state-engine.md` quando tocar no domínio.
- Confira branch, HEAD, remoto, árvore de trabalho e referência de base solicitada.
  Preserve alterações locais e o histórico; nunca use reset destrutivo ou force push.
- Trabalhe em branch curta por incremento, a partir da base autorizada. Não
  implemente o próximo incremento automaticamente nem reescreva funcionalidades
  existentes sem necessidade comprovada.
- Não faça push, abra PR, faça merge ou altere configurações remotas sem autorização
  explícita do solicitante. Autorização de um incremento não vale para os seguintes.
- A PR 00 (`chore/prepare-pre-ai`) limita-se à auditoria e documentação. Não alterar
  models, migrações, endpoints, templates, UI ou regras de negócio nessa preparação.

## Documentação contínua obrigatória

Ao finalizar CADA incremento, siga a política de `CONTRIBUTING.md`:

1. Atualize conceito/arquitetura quando domínio ou comportamento mudarem.
2. Atualize deploy quando dependências, configuração, migrações ou operação mudarem.
3. Atualize SEMPRE o ROADMAP com estado, branch, PR/commit quando existirem, testes,
   resultados, decisões, limitações e próximo passo. Não invente identificadores.
4. Atualize README principal somente para informações relevantes e navegação.
5. Se um documento não precisar de mudança, registre essa avaliação no ROADMAP;
   não copie procedimentos para criar versões concorrentes.
6. Não marque uma entrega concluída sem implementação, validação e os gates de
   revisão/integração acordados. Distinga validação local de CI executada no GitHub.

## Limites permanentes

- Somente dados fictícios; nunca publicar `.env`, bancos, credenciais ou documentos
  reais. Não ler nem imprimir segredos em logs, comandos ou respostas.
- Preserve dados/configurações locais. Testes usam banco temporário; não executar
  `flush`, `load_demo` ou reset de interações no banco de validação por conveniência.
- Reutilize User nativo e `Doctor.clinics`. Não conceda acesso clínico por flags de
  staff/superusuário, identidade de paciente ou mudança de estado operacional.
- Recepção só vê operação das clínicas vinculadas, não fontes/conversa/resumos.
- `completed` não é `ready`. O consentimento atual é simulado; não é evidência real.
- Não integrar IA/WhatsApp/transcrição nem decidir infraestrutura ou novas regras
  de produto enquanto estiverem fora do incremento autorizado.
- Execute `check`, `makemigrations --check --dry-run`, testes Django e validações
  proporcionais à mudança. Reporte falhas, limitações e resultados reais.
