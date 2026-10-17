# Handoff para o desenvolvedor de IA — aguardando aprovação do contrato

[ai.v1](README.md) é a referência normativa única, implementada com fake.
Publicação/CI não equivalem a aprovação humana. D07 autoriza este escopo técnico
fictício, não IA real no backend. Após revisão/aprovação do contrato e seus artefatos,
o segundo desenvolvedor pode trabalhar isolado, SEM aguardar PRs 05/06.

## Fronteiras

- Backend mantém autorização, consentimento, grafo, seleção e versões das fontes,
  snapshots, resultados técnicos, retry, erros, atualidade e publicação explícita simulada.
- IA implementa AIProvider, prompts/perguntas, extração/síntese e qualidade semântica;
  retorna DTO ai.v1, sem acessar banco/serviços Django ou alterar estados.
- Não adicionar HTTP endpoint, rede, modelos reais, fila ou dependência nesta PR.
  Um adaptador futuro só entra na aplicação sob autorização/revisão específica.
- IDs/author/consent no DTO são correlação/metadados, nunca sessão ou prova jurídica.
- Não usar mensagens reais nos fixtures/logs. Não gravar segredo em exemplo/teste.

## Base versionada e contrato normativo

Consolidação PR 06 em `chore/pre-ai-handoff`, sobre a base imutável PR #13,
`640e0350aed3878fe4171f30bdc6e9ad4658f59e`. Esta é a versão de implementação
usada como referência do handoff, não aprovação do outro desenvolvedor. O SHA
publicado/CI desta consolidação constará no [ROADMAP](../planning/ROADMAP.md)
e nos checks da PR. Antes de começar, os dois desenvolvedores devem acordar um
SHA limpo/versionado: não consumir uma branch mutável implicitamente.

Único contrato normativo: [README ai.v1](README.md), com validação executável em
[ai_contract.py](../../preconsultas/ai_contract.py). Não criar DTO alternativo.
O port está em [ai_provider.py](../../preconsultas/ai_provider.py); fixtures e
harness em [ai_conformance.py](../../preconsultas/ai_conformance.py). IDs são
correlação; o adaptador não recalcula versões opacas de fontes nem concede acesso.

## Começar sem banco ou credenciais

Python 3.14, na raiz do checkout versionado. O exemplo funciona até com
`python -S` (sem site-packages): esses módulos só usam biblioteca padrão.
Não requer `django.setup()`, `.env`, migrations, banco, arquivos de mídia ou rede.

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

### Exemplo de adaptador com transporte stubado

Este exemplo é executável offline; o transporte é o fake, NÃO um cliente real.
O port exige três métodos. A implementação futura substitui o transporte somente
no escopo autorizado, sem importar models, serviços ou configurações Django:

```python
from preconsultas.ai_contract import validate_request, validate_response
from preconsultas.ai_conformance import check_provider
from preconsultas.ai_provider import FakeAIProvider

class StubbedProvider:
    provider_id = "adapter-stub"
    provider_version = "example-v1"

    def __init__(self, transport):
        self.transport = transport

    def _call(self, operation, request):
        validate_request(request)
        return validate_response(getattr(self.transport, operation)(request), request)

    def next_question(self, request):
        return self._call("next_question", request)

    def extract_structured(self, request):
        return self._call("extract_structured", request)

    def build_summary(self, request):
        return self._call("build_summary", request)

check_provider(StubbedProvider(FakeAIProvider()), deterministic=True)
```

`next_question` sugere pergunta, não a envia; `extract_structured` retorna itens;
`build_summary` retorna itens e observações para revisão, não laudo. Preservar
cabeçalho/context_id/referências `source_id/version` recebidos. `source_excerpt`
precisa citar literalmente; `derived` não é relato autenticado; mídia sem texto
não autoriza inventar transcrição. Validar schema não certifica semântica clínica.

Falhas de disponibilidade/transitórias usam `ProviderFailure` com os códigos
normativos; não retornar `error_envelope` como resposta de sucesso. Backend
sanitiza exceções, permite retry explícito de falha retryable até três tentativas,
revalida contexto e mantém execuções anteriores. Sem retry automático, rede ou
segredos nos testes. Versionar adaptador se prompts/modelo/configuração mudarem.
Não ampliar limites/campos/basis sem nova versão e acordo do contrato.

O publicador desta trilha aceita somente `provider_id="fake"`: passar no harness
NÃO autoriza integrar/publicar um adaptador real. Essa liberação, avaliação
semântica, segurança, consentimento e requisitos produtivos exigem nova aprovação.

## Testes de conformidade e integração

Procedimento/configuração segura do Django: [deploy](../deploy.md).

```powershell
python -m preconsultas.ai_examples
python manage.py test preconsultas.test_ai_contract
python manage.py test preconsultas.test_ai_orchestration
python manage.py test preconsultas.test_pre_ai_integration
```

`sample_request(operation, kind)` fornece mensagem/áudio/imagem/PDF, sem arquivos.
`check_provider` não importa Django; pode ser chamado de unittest do adaptador.
`test_ai_contract` fornece negativos de versão/campo/tipo/limite/proveniência e
determinismo; `test_ai_orchestration` cobre domínio, persistência, gates, retries,
rollback, obsolescência e concorrência PG. SQLite ignora ensaios com row locks.
Fixtures Django criam usuários fictícios sem senha utilizável em DB temporário,
não são credenciais padrão. Não executar setup/seed/migrate no banco preservado.

A suíte integrada começa no POST da recepção e usa consentimento, transições,
sim.v1, materialização, três operações fake, publicação e revisão reais do código.
Não forja estados para completar o caminho positivo. Backend cobre autorização,
falhas, idempotência e atualidade; o outro desenvolvedor mantém conformidade e
avaliações do adaptador com transporte stubado. Matriz de cenários/evidências:
[validação pré-IA](../planning/PRE_AI_VALIDATION.md).

## Checklist para aprovação do handoff

- Revisar DTOs e limites ai.v1, exemplos completos e política de evolução.
- Concordar com referências verificáveis, citações literais, basis de derivação e
  ausência de diagnóstico/prescrição ou falsa atribuição ao paciente.
- Concordar com limites do port, sem mutação de request, falhas sanitizadas e retry.
- Executar fake/harness e testes negativos com transporte stubado.
- Revisar regras de estados/aceite, completed != ready e leitura clínica separada.
- Registrar aprovação humana e branch de trabalho no ROADMAP; CI não substitui isso.

Registro de aprovação: **PENDENTE**. Revisor, data e SHA aprovados: não informados.
Após aprovação humana, o trabalho independente pode começar no SHA acordado sem
aguardar deploy ou merge das PRs 05/06. Publicar esta consolidação não satisfaz o gate.

Pendentes: qualidade/segurança semântica real, provedor/modelo/prompts produtivos,
retenção/infra D08, consentimento real, cancelamento/recuperação de chamadas travadas
e políticas produtivas de publicação/revisão. A branch PR 05 implementa somente
publicação/revisão SIMULADAS, por médico autorizado, sem mudar port/DTO ai.v1.
O dev IA não promove completed→ready nem altera fontes/atores/gates. O backend
revalida para publicar ainda completed, mantendo o resultado técnico separado
das correções/snapshots médicos. Obsolescência bloqueia consumo; revalidação/
republicação ready permanece pendente. Este handoff NÃO libera pacientes reais.
