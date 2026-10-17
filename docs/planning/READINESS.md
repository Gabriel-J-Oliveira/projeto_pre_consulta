# Matriz de prontidão — trilha pré-IA

Avaliação de 17/10/2026, PR 06 sobre `640e0350aed3878fe4171f30bdc6e9ad4658f59e`.
Somente demonstração com dados fictícios. Não é homologação, certificação de
segurança ou autorização clínica/jurídica. Estado das PRs/SHAs/resultados reais:
[ROADMAP](ROADMAP.md). Evidências por cenário: [validação](PRE_AI_VALIDATION.md).

Classificações: **testado** = implementação com evidência automatizada no recorte;
**parcial** = implementação com lacunas; **demo** = somente simulação;
**aprovação** = revisão humana pendente; **desenvolvimento** = não implementado;
**não produtivo** = não autorizado para uso real. Classificações podem coexistir:
testado não implica seguro/provisionado em produção.

| Área | Classificação | Entrega e limite/gate |
| --- | --- | --- |
| Cadastro e reutilização explícita | Testado / demo | Nome+telefone, escolha e escopo da recepção; sem portal/prontuário ou identidade real |
| Consentimento versionado | Testado / demo | Evidência técnica/operador/versão; não é prova jurídica nem paciente autenticado |
| Estados operacionais | Testado / demo | Grafo explícito, terminais sem reabertura/timeout; critérios reais pendentes |
| Autorização médico/clínica/recepção | Testado / parcial | Gates no servidor, admin sem acesso clínico implícito; não é RLS/WORM ou auditoria de segurança produtiva |
| Publicação | Testado / demo | Médico atribuído, build_summary fake atual, publicação atômica; ready não é aprovação clínica |
| Revisão médica | Testado / demo | Autoria e snapshots/correções; sem assinatura/laudo/prontuário |
| Entrada interna sim.v1 | Testado / demo | Texto/referências de mídia, operador simulado; sem webhook/canal público |
| Idempotência | Testado | IDs compostos, replay/conflito; namespace/autenticação de canal real pendentes |
| Proveniência/versionamento | Testado / parcial | Vínculos/snapshots/hash de contexto; SQL privilegiado e seed legado não são imutabilidade produtiva |
| Contrato ai.v1 | Testado / aprovação | Schema/erros/exemplos/harness; revisão do outro desenvolvedor ainda pendente |
| FakeAIProvider | Testado / demo | Três operações offline; nenhuma LLM/transcrição real |
| Handoff de IA real | Aprovação / desenvolvimento | Pacote entregue para revisão, adaptação/avaliação semântica reais fora desta trilha |
| WhatsApp real | Desenvolvimento / não produtivo | Sem credenciais, envio, webhook ou coleta de mídia |
| PostgreSQL CI | Testado no SHA identificado | Serviço 17 descartável; conferir run/HEAD no relatório, nunca inferir sucesso pelo YAML |
| Banco de desenvolvimento | Parcial | PostgreSQL por ambiente, SQLite explícito; nenhum banco/conta pessoal distribuído |
| Homologação | Desenvolvimento / não produtivo | Não provisionada/validada |
| Hospedagem/servidor produtivo | Desenvolvimento / não produtivo | runserver/WSGI entrypoint não constituem implantação |
| HTTPS/domínio/proxy | Desenvolvimento / não produtivo | Sem configuração TLS/cookies/HSTS aprovada |
| Segredos e credenciais | Parcial / não produtivo | .env ignorado, placeholders; gestão/rotação produtivas pendentes |
| Storage privado/mídia real | Desenvolvimento / não produtivo | Só metadados e mapeamento demonstrativo local; sem upload/download externo |
| Backup e restauração | Desenvolvimento / não produtivo | Nenhum restore produtivo ensaiado; frequência/RPO/RTO não definidos |
| Observabilidade | Desenvolvimento / não produtivo | Erros/auditoria operacionais sanitizados não são monitoramento/alertas/SLAs |
| Retenção e exclusão | Aprovação / desenvolvimento | Sem prazo ou política jurídica inventados; armazenamento protegido exige desenho próprio |
| Recuperação de running interrompido | Desenvolvimento | Reserva preservada para investigação; sem lease/timeout/retry cego ou limpeza automática |
| Revalidação/republicação ready | Aprovação / desenvolvimento | Obsolescência bloqueia e preserva histórico; não há reabertura/republicação automática |
| Segurança e privacidade | Parcial / não produtivo | Isolamento testado não substitui threat model, hardening, limites de login e revisão independente |
| Aprovação clínica/jurídica | Aprovação / não produtivo | Simulação e validação estrutural não certificam conteúdo, consentimento ou uso assistencial |
| Governança/revisão Git | Aprovação / parcial | PRs empilhadas abertas, sem merge; revisão do outro dev e configuração de proteção são gates humanos |

## D08: recorte aprovado versus pendente

O prompt atribui a 14/10/2026 a aprovação do recorte de testes/documentação/handoff;
esta execução ocorre em 17/10/2026. Não estende a aprovação para hosting,
homologação, produção, armazenamento, backup/restore, segurança jurídica/clínica,
retenção, custos ou SLA. Essas decisões exigem proposta, aprovação e validação
separadas; não têm valores predefinidos neste documento.

Próximo passo humano: revisar o diff incremental PR 06 e o contrato/handoff,
registrar revisor/data/SHA e decidir integração na ordem das dependências, com
CI/approvals válidos em cada base. Nenhum merge, implantação ou integração real
é autorizado pela publicação desta matriz. O dev IA pode trabalhar isolado no
contrato aprovado/SHA acordado sem esperar merges 05/06 ou ambiente produtivo.
