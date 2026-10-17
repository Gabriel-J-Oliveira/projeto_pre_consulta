# Integração de IA — contrato técnico simulado ai.v1

Referência oficial da PR 04, D07 aprovada pelo solicitante em 14/10/2026 somente
para dados fictícios. Contrato implementado para **revisão**; publicação não aprova
handoff, segurança clínica ou integração real. Sem rede, LLM, WhatsApp, transcrição,
filas, publicação, novos endpoints ou interfaces. [Handoff](handoff.md).

Consolidação PR 06: contrato/limites ai.v1 e port permanecem INALTERADOS sobre
`640e0350aed3878fe4171f30bdc6e9ad4658f59e`. [Handoff versionado](handoff.md)
reúne início offline, adaptador stubado e gates humanos; [evidências integradas](../planning/PRE_AI_VALIDATION.md)
conectam processamento à publicação/revisão da PR 05. Publicar testes não aprova
handoff, uso real ou segurança semântica.

## Portas e responsabilidades

`preconsultas.ai_provider.AIProvider` é um Protocol sem imports Django:

```python
class AIProvider(Protocol):
    provider_id: str
    provider_version: str
    def next_question(self, request: dict) -> dict: ...
    def extract_structured(self, request: dict) -> dict: ...
    def build_summary(self, request: dict) -> dict: ...
```

Identificadores de provedor/versão: 1–120 caracteres, primeiro alfanumérico;
demais ASCII alfanuméricos ou `._:-`. Backend seleciona o objeto explicitamente
por `execute(..., provider=adaptador)`; ausência usa `FakeAIProvider()`. Sem nova
variável de ambiente/factory dinâmica. Identidade não vem de usuário HTTP/payload.
O futuro adaptador não importa models/services nem acessa o banco: recebe apenas
DTO, retorna DTO ou lança `ProviderFailure`. Nunca define autorização ou estado.

Backend controla médico/clínica/consulta, aceite simulado atual, fontes, contexto,
validação, persistência, tentativas e atualidade. IA controla prompts e qualidade
semântica dentro do contrato; a validação estrutural NÃO certifica diagnóstico,
ausência de alucinações ou segurança médica. Na branch PR 05, publicação simulada
é serviço do backend autorizado explicitamente por médico; nunca ação do port.

## Requisição normativa

Validador: `preconsultas.ai_contract.validate_request`. Todos os campos abaixo
são obrigatórios, objetos têm EXATAMENTE as chaves declaradas. JSON somente;
booleano não é inteiro; não há coerção, campos desconhecidos ou fallback de versão.

| Objeto/campo | Tipo e limite |
| --- | --- |
| request | `contract_version`, `operation`, `context_id`, `consultation_id`, `consent`, `sources` |
| contract_version | literal `ai.v1` |
| operation | `next_question`, `extract_structured` ou `build_summary` |
| context_id | SHA-256 hexadecimal minúsculo, 64 caracteres |
| consultation_id | inteiro 1..2^63−1; correlação, NÃO autorização |
| consent | exatamente `id` (mesmo limite de inteiro), `version` (texto 1..80) |
| sources | array 1..100, IDs únicos em ordem crescente; todas da própria consulta |
| cada source | `source_id`, `version`, `kind`, `author`, `text`, `media`, `provenance` |
| source_id/version | ID positivo / hash de conteúdo-metadados-proveniência, 64 hex |
| kind | `message`, `audio`, `image`, `pdf` |
| author | `patient`, `ai` (rótulos legados) ou `simulation`; não prova identidade/IA real |
| text | texto até 8000, ou vazio para mídia sem conteúdo; mensagem exige não vazio |
| media | null para mensagem/legado sem referência, ou objeto com quatro campos abaixo |
| media.reference | identificador opaco 1..120 conforme regra de token; NÃO URL/path |
| media.mime_type | áudio mpeg/ogg/wav, imagem jpeg/png/webp, PDF application/pdf, coerente com kind |
| media.filename | texto até 180, sem `/`, `\` ou controles |
| media.size_bytes | inteiro 1..25 MiB; tamanho DECLARADO, não binário recebido |
| provenance | null para legado, ou exatamente `message_id`, `consent_id`, `input_contract`, `origin`, `external_event_id` |
| message_id/consent_id | IDs positivos da entrada/evidência original |
| input_contract/origin | `sim.v1` / `local_simulation` |
| external_event_id | token 1..120 conforme regra de identificador |

Texto não vazio significa `strip()` não vazio. NUL, controles (exceto newline,
tab e CR em texto) e surrogates Unicode são rejeitados. Null em provenance é
LEGADO, não ausência de autorização: backend valida consulta e aceite atual.
Consentimento original da mensagem permanece na proveniência; o atual governa
processamento. Nenhum nome/telefone/patient_id/conta/segredo vai ao provedor.
Mídia materializada só contém referência; backend não inventa transcrição.
Legado pode fornecer a transcrição demonstrativa já existente, sem análise real.

### Identidade/versionamento

Fonte é versionada pelo hash de snapshot de todos os campos observados: ID/consulta,
chave, tipo/autor, horário, body, filename, description, duration, demo_transcript,
materialização/ator e entrada original (conteúdo/mídia/horários/operador/consentimento/
contrato/ID externo/origem). O provedor trata `source.version` como token opaco;
não tem os metadados privados necessários para recalculá-lo. Fontes legadas editáveis
mudam a versão ao mudar conteúdo ou metadados, mesmo mantendo ID.

`context_id = SHA256(JSON canônico de request SEM context_id)`. Canonização Python:
`json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
allow_nan=False)`, bytes ASCII. Inclui consulta, operação, consentimento e todas as
fontes/versões/textos/mídias. Não inclui relógio da tentativa nem estado operacional:
estado é gate independente; publicar futuramente não muda por si só conteúdo.

Identidade persistida: hash de `{context, provider, provider_version}`. Mudanças
materiais criam outra execução; anteriores são preservadas. Versionar adaptador
quando prompts/modelo/configuração alterarem comportamento relevante. Não trocar
provedor/configuração silenciosamente sob o mesmo identificador.

## Respostas normativas

Exatamente `contract_version`, `operation`, `context_id`, `result`. Cabeçalho deve
corresponder à requisição. Backend usa `validate_response` independente do provedor.

- `next_question.result`: exatamente `question` (texto 1..1000), `references`.
  Sugestão somente; sem envio ou avanço de coleta.
- `extract_structured.result`: exatamente `items` (array 0..50).
- `build_summary.result`: exatamente `items` e `attention_points` (cada array 0..50).
  Atenção neutra e fundamentada para avaliação médica; não diagnóstico/prescrição.
- Cada item: exatamente `key` (token 1..120, único por array), `text` (1..2000),
  `basis` (`source_excerpt`, `derived`, `simulation`), `references`.
- References: array 1..100, IDs únicos; cada referência exatamente `source_id` e
  `version`, pertencentes à requisição, com versão idêntica. Nem item nem pergunta
  podem referenciar outra consulta ou fonte ausente.
- `source_excerpt`: texto deve ser substring literal de pelo menos uma fonte
  referenciada. `derived` identifica transformação, NUNCA declaração autenticada
  do paciente; `simulation` explicita demonstração. Validação semântica de derivação
  e avaliação clínica permanecem responsabilidade humana/provedor e gates futuros.

Arrays vazios são permitidos quando nada puder ser extraído. Não inventar valores
ausentes para satisfazer schema. Não executar links/mídias ou interpretar DTO como
instrução para acessar rede, alterar domínio ou conceder permissões.

## Exemplos completos e fixtures executáveis

Fixture estável em `preconsultas.ai_conformance.sample_request`. Exemplo completo
de requisição de pergunta (IDs fictícios, hash da fixture opaco):

```json
{
  "contract_version": "ai.v1",
  "operation": "next_question",
  "consultation_id": 123,
  "consent": {"id": 10, "version": "sim-v1"},
  "sources": [{
    "source_id": 1,
    "version": "e12fdf0b852a8c929de54a7e958b24af4269f388610906e5c5c20e9a8348d321",
    "kind": "message", "author": "simulation",
    "text": "Informação exclusivamente fictícia.", "media": null,
    "provenance": {"message_id": 2, "consent_id": 10, "input_contract": "sim.v1",
      "origin": "local_simulation", "external_event_id": "sim-1"}
  }],
  "context_id": "e6036d541b7f2a51be737783a7afb798690b24aa735f1803359ff471e0f8c5e7"
}
```

Resposta completa:

```json
{
  "contract_version": "ai.v1", "operation": "next_question",
  "context_id": "e6036d541b7f2a51be737783a7afb798690b24aa735f1803359ff471e0f8c5e7",
  "result": {"question": "SIMULAÇÃO: deseja acrescentar alguma informação fictícia?",
    "references": [{"source_id": 1,
      "version": "e12fdf0b852a8c929de54a7e958b24af4269f388610906e5c5c20e9a8348d321"}]}
}
```

Para extração a requisição completa mantém todos os campos acima, troca operation
por `extract_structured` e context_id por
`16ec1aee9fb0d21a4dc1394c18d1f8797d5ede85e60fef2152ed593321957f41`.
Para síntese troca por `build_summary` e
`22b4220606ae917d5af473a0e9bc99b2be7f5e05baaad1a48511b58d8a51165d`.
As respostas completas respectivas:

```json
{
  "contract_version": "ai.v1", "operation": "extract_structured",
  "context_id": "16ec1aee9fb0d21a4dc1394c18d1f8797d5ede85e60fef2152ed593321957f41",
  "result": {"items": [{"key": "source-1", "text": "Informação exclusivamente fictícia.",
    "basis": "source_excerpt", "references": [{"source_id": 1,
      "version": "e12fdf0b852a8c929de54a7e958b24af4269f388610906e5c5c20e9a8348d321"}]}]}
}
```

```json
{
  "contract_version": "ai.v1", "operation": "build_summary",
  "context_id": "22b4220606ae917d5af473a0e9bc99b2be7f5e05baaad1a48511b58d8a51165d",
  "result": {"items": [{"key": "source-1", "text": "Informação exclusivamente fictícia.",
    "basis": "source_excerpt", "references": [{"source_id": 1,
      "version": "e12fdf0b852a8c929de54a7e958b24af4269f388610906e5c5c20e9a8348d321"}]}],
    "attention_points": []}
}
```

Gerar DTOs COMPLETOS das três requisições/respostas/erros, offline, sem Django/DB:

```powershell
python -m preconsultas.ai_examples
```

Também existem fixtures `sample_request(operation, kind='audio'|'image'|'pdf')`.
Exemplos são dados fictícios estáveis, não contas ou resultados do banco local.

## Erros e tentativas

Provedor Python lança `ProviderFailure('provider_unavailable'|'transient_failure')`;
backend descarta mensagem/traceback/payload inválido. Exceções desconhecidas viram
`provider_failure`, sem retentativa. Contrato retorna `ContractError` com código
genérico. DTO portátil de erro (não sucesso, não armazenar conteúdo bruto):

```json
{
  "contract_version": "ai.v1", "operation": "next_question",
  "context_id": "e6036d541b7f2a51be737783a7afb798690b24aa735f1803359ff471e0f8c5e7",
  "error": {"code": "transient_failure", "retryable": true,
    "message": "Falha técnica de IA; nenhum conteúdo publicado."}
}
```

`error_envelope(request, code)` produz esse formato; o port Python usa exceções,
não retorna um envelope de erro no lugar de resposta. Códigos de contrato:
`invalid_contract`, `unsupported_version`, `context_mismatch`, `invalid_provenance`.
Só indisponibilidade/transitória são retryable. Orquestrador também tem códigos
`precondition_failed`, `authorization_changed`, `obsolete_context`,
`persistence_failure`, `transaction_boundary`. `PermissionDenied` uniforme para fora de escopo.

Mesma solicitação retorna recibo existente; não repete automaticamente chamada.
`retry=True` explícito só após falha retryable, no máximo 3 tentativas TOTAIS,
revalidando escopo/gates/fontes. Sem espera, backoff, timeout ou scheduler automático.
Contrato/proveniência/versão inválidos não são retryable. Fonte mudou: nova execução,
não tentativa da versão antiga. Chamada concorrente em andamento retorna `running`.

Reserva e finalização são transações separadas: provedor não mantém lock aberto.
`execute` usa blocos duráveis e rejeita caller envolvido em outra transação atomic
(`transaction_boundary`), antes da reserva/chamada. Não envolver em atomic externo
ou futura view ATOMIC_REQUESTS sem marcar a entrada como não atômica.
Falha parcial da reserva desfaz execução/referências/tentativa; falha da finalização
desfaz aceitação e deixa reserva/tentativa `running`, preservadas para investigação.
Crash também deixa `running`; não há recuperação automática ou reexecução cega.
Recuperação segura/leases/timeouts exigem desenho posterior, não apagar linhas.

## Persistência e obsolescência

AIExecution guarda consulta/operação/contrato/provedor/versão/identidade, request
privado, estado técnico (`running`, `succeeded`, `failed`, `obsolete`), resultado
validado, código sanitizado, criador/horários. AIAttempt preserva número/ator/horários,
estado/código e apenas resposta estruturalmente validada. AIExecutionSource vincula
fontes com versão observada. Snapshot de request preserva fontes legadas anteriores.
Unicidade de identity e execução/número e bounds de tentativa no banco.

Contexto alterado enquanto provedor executa: tentativa/execução `obsolete`, resultado
validado preservado só para auditoria, nunca atual. Perda de autorização: falha,
resposta descartada. Mudança posterior: `current_result` revalida request/refs/output.
No fluxo legado explícito marca obsolete e retorna None; no publicado, o gate
da PR 05 nega leitura, registra necessidade de validação e marca obsolete,
preservando a publicação. Versões anteriores não são promovidas novamente.
SQL/QuerySet privilegiado ainda pode alterar dados: não é WORM nem RLS produtivo.
Locks da consulta/fontes e constraints serializam os novos serviços no PostgreSQL;
SQLite não comprova concorrência. Escritores legados ainda merecem integração futura.

## Gates de processamento e leitura

| Operação | Estados aceitos |
| --- | --- |
| next_question | in_progress |
| extract_structured | in_progress, awaiting_patient, completed, ready |
| build_summary | completed, ready |

Proposta técnica conservadora implementada no escopo D07, sem alterar grafo.
TODAS exigem médico ativo atual, consulta atribuída/clínica vinculada, última
evidência consistente de aceite simulado e fontes válidas não vazias. Legados sem
aceite não ganham evidência inventada. Recepção/staff/admin sem médico não processam.
Processamento de completed é escrita técnica com recibo de IDs, não leitura clínica.
`execute` retorna somente execution_id/status/attempt_count/error_code; não conteúdo,
hash ou texto. `current_result` só médico/clínica e ready, revalidando aceite e
atualidade; nenhuma mudança automática de Consultation.status/SummaryItem/Correction/
SummaryRevision, nenhum OperationalEvent com dados clínicos ou log de payload.

### Fronteira de consumo e publicação na PR 05

Backend usa `_validated_result` INTERNAMENTE para revalidar ai.v1/contexto/fontes
antes de publicação em completed, sob escopo de médico atribuído/clínica. Essa
função não autoriza leitura e não é endpoint do provedor. O port, DTO e fake não
mudaram; nenhuma promoção automática foi acrescentada ao orquestrador.

`publication.publish_consultation` exige build_summary fake sucedido e atual,
aceite consistente e >=1 item de síntese. Publicação inicial, fontes/itens,
snapshots, auditoria sem conteúdo e completed→ready são atômicos. Pontos de
atenção isolados não bastam; ready significa revisão, não aprovação clínica.
ClinicalPublication mantém execução/resultado/contexto originais e referências.
UI não exibe resultado técnico antes da confirmação. Novo caso ready sem
publicação válida não ganha leitura; somente fixtures legadas explicitamente
identificadas mantêm o fluxo anterior. Current_result de caso publicado só
retorna sua execução selecionada e atual; não abre outras saídas técnicas.

Detalhes/fontes/anexos/revisão/histórico revalidam publicação e atualidade.
Obsolescência detectada preserva auditabilidade e registra necessidade de nova
validação; execução obsolete e marcador de publicação impedem reabertura por
mera restauração do contexto. Não altera status operacional, não republica ready.
Correções médicas não modificam output do port ou fonte: actor e snapshots
apresentacionais ficam separados do resultado técnico. Especificação do fluxo:
[conceito PR 05](../planning/README.md#19-publicação-e-revisão-pr-05--complemento-d04-aprovado).

## Evolução

ai.v1 é estrito: adicionar/retirar campo, ampliar semântica ou limites exige nova
versão e negociação/testes explícitos; não ignorar campos extras como compatibilidade.
Backend rejeita versões desconhecidas. Contextos/resultados antigos preservam versão;
evolução de schema será aditiva. Integração real necessita autorização própria,
revisão semântica/segurança, credenciais privadas, consentimento real, limites de rede
e retenção D08. PR 05/06 não são pré-requisitos para o dev de IA trabalhar isolado
**após aprovação do contrato/handoff**, mas seguem necessárias para pipeline completo.
