# Handoff para o desenvolvedor de IA — aguardando aprovação do contrato

[ai.v1](README.md) é a referência normativa única, implementada com fake.
Publicação/CI não equivalem a aprovação humana. D07 autoriza este escopo técnico
fictício, não IA real no backend. Após revisão/aprovação do contrato e seus artefatos,
o segundo desenvolvedor pode trabalhar isolado, SEM aguardar PRs 05/06.

## Fronteiras

- Backend mantém autorização, consentimento, grafo, seleção e versões das fontes,
  snapshots, resultados técnicos, retry, erros, atualidade e publicação futura.
- IA implementa AIProvider, prompts/perguntas, extração/síntese e qualidade semântica;
  retorna DTO ai.v1, sem acessar banco/serviços Django ou alterar estados.
- Não adicionar HTTP endpoint, rede, modelos reais, fila ou dependência nesta PR.
  Um adaptador futuro só entra na aplicação sob autorização/revisão específica.
- IDs/author/consent no DTO são correlação/metadados, nunca sessão ou prova jurídica.
- Não usar mensagens reais nos fixtures/logs. Não gravar segredo em exemplo/teste.

## Começar sem banco ou credenciais

```python
from preconsultas.ai_conformance import sample_request, check_provider
from preconsultas.ai_provider import FakeAIProvider
from preconsultas.ai_contract import validate_response

request = sample_request('build_summary')
provider = FakeAIProvider()
response = provider.build_summary(request)
validate_response(response, request)
check_provider(provider, deterministic=True)
```

Para seu adaptador: `check_provider(adapter_com_transporte_stubado)` verifica todas
as operações, entrada não mutada, formatos e referências contra mensagens e mídias
fictícias. `deterministic=True` é exigência do fake, não promessa de determinismo de
uma LLM futura. Testes não devem precisar de rede ou credenciais de modelos.
Harness não certifica qualidade clínica; acrescentar avaliações semânticas fictícias
ao adaptador em seu próprio escopo aprovado, preservando gates do backend.

## Testes de conformidade e integração

Procedimento/configuração segura do Django: [deploy](../deploy.md).

```powershell
python -m preconsultas.ai_examples
python manage.py test preconsultas.test_ai_contract
python manage.py test preconsultas.test_ai_orchestration
```

`sample_request(operation, kind)` fornece mensagem/áudio/imagem/PDF, sem arquivos.
`check_provider` não importa Django; pode ser chamado de unittest do adaptador.
`test_ai_contract` fornece negativos de versão/campo/tipo/limite/proveniência e
determinismo; `test_ai_orchestration` cobre domínio, persistência, gates, retries,
rollback, obsolescência e concorrência PG. SQLite ignora ensaios com row locks.
Fixtures Django criam usuários fictícios sem senha utilizável em DB temporário,
não são credenciais padrão. Não executar setup/seed/migrate no banco preservado.

## Checklist para aprovação do handoff

- Revisar DTOs e limites ai.v1, exemplos completos e política de evolução.
- Concordar com referências verificáveis, citações literais, basis de derivação e
  ausência de diagnóstico/prescrição ou falsa atribuição ao paciente.
- Concordar com limites do port, sem mutação de request, falhas sanitizadas e retry.
- Executar fake/harness e testes negativos com transporte stubado.
- Revisar regras de estados/aceite, completed != ready e leitura clínica separada.
- Registrar aprovação humana e branch de trabalho no ROADMAP; CI não substitui isso.

Pendentes: qualidade/segurança semântica real, provedor/modelo/prompts produtivos,
retenção/infra D08, consentimento real, cancelamento/recuperação de chamadas travadas
e políticas produtivas de publicação/revisão. A branch PR 05 implementa somente
publicação/revisão SIMULADAS, por médico autorizado, sem mudar port/DTO ai.v1.
O dev IA não promove completed→ready nem altera fontes/atores/gates. O backend
revalida para publicar ainda completed, mantendo o resultado técnico separado
das correções/snapshots médicos. Obsolescência bloqueia consumo; revalidação/
republicação ready permanece pendente. Este handoff NÃO libera pacientes reais.
