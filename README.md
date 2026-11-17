# RAVZ Product Hunter

[![CI](https://github.com/electrocaiorv-boop/ravz-product-hunter/actions/workflows/ci.yml/badge.svg)](https://github.com/electrocaiorv-boop/ravz-product-hunter/actions/workflows/ci.yml)

Sistema em Python que pesquisa e avalia oportunidades de produto no
Mercado Livre Brasil. Ele coleta evidência, pontua sete dimensões com
motores determinísticos e compõe uma nota explicável de 0 a 100 (o
*Opportunity Score*). Um agente de IA com limites decide **o que
pesquisar**; ele nunca calcula, ajusta ou inventa uma nota.

> **Princípio central:** a nota não é probabilidade de venda, não é taxa
> de conversão e não é retorno esperado. É uma heurística determinística
> e provisória: "esta evidência, sob esta ponderação documentada, soma 82
> de 100". O sistema nunca afirma que um produto vai vender.

## O que o sistema faz

- **Sete motores de análise independentes:** Tendência, Demanda,
  Concorrência, Margem, Fornecedor, Logística e Risco. Cada um tem uma
  responsabilidade e não conhece os outros.
- **Composição explicável:** cada componente mostra nota bruta, peso e
  contribuição. Dimensões negativas (Concorrência e Risco) são invertidas
  exatamente uma vez, e evidência correlacionada (Demanda e Tendência
  vêm da mesma chamada ao Google Trends) conta uma vez só.
- **Dado ausente continua ausente:** `None` nunca vira 0, 50 ou "seguro".
  Enquanto falta evidência comercial, a classificação final é retida.
- **Orquestração determinística:** cada provedor é chamado no máximo uma
  vez por execução, e toda falha vira evidência indisponível com motivo
  registrado.
- **Agente de pesquisa com limites:** um LLM escolhe entre quatro
  ferramentas de leitura. Lista fechada de ferramentas, argumentos
  validados em código, orçamento de chamadas, tokens, custo estimado e
  tempo, e todo número que o modelo escreve é conferido contra a
  análise.

## Exemplo de saída

Execução real da opção 11 (análise orquestrada), capturada em
18/11/2026 com Apify e Mercado Livre (OAuth) ambos autenticados. Desde
a Fase 13, Concorrência vem de uma cadeia diferente (categoria → mais
vendidos → ofertas reais) porque `/sites/MLB/search` em si continua
bloqueado por política do Mercado Livre, mesmo autenticado — ver
[`docs/MERCADO_LIVRE_403.md`](docs/MERCADO_LIVRE_403.md). Os valores
vêm de chamadas ao vivo e mudam entre execuções:

```
Evidence resolution (each provider called at most once):
  [ok           ] apify:google-trends           -> trend, demand
                  53 point(s) returned, 53 usable observation(s) from
                  apify:themineworks/google-trends-pro
  [ok           ] mercadolivre:category_catalog -> competition
                  category MLB196208 (Fones de Ouvido): 5 product(s)
                  sampled, 0 skipped
  [not_supplied ] manual:margin                 -> margin
                  no inputs supplied for this run
  ...

Opportunity Score: 72.56 (PARTIAL) (analytical, NOT final)
Component coverage: 45.00%
Commercial validation: INCOMPLETE   (coverage 56.25%)
Operational validation: INCOMPLETE  (coverage 0.00%)
Readiness: INCOMPLETE_EVIDENCE
Final Classification: WITHHELD
Missing COMMERCIAL requirements: margin, risk
Missing OPERATIONAL requirements: supplier, logistics

  demand       raw 85.89 -> opportunity 85.89  x weight 0.30 = 25.77  [commercial]
  trend        raw 59.46 -> NOT COUNTED (correlated evidence -- search-interest family)
  competition  raw 31.54 -> opportunity 68.46  x weight 0.15 = 10.27  [commercial]
```

A saída mostra o comportamento que o projeto existe para garantir:
evidência real pontuada, a falha de um provedor dita com todas as
letras, a evidência duplicada contada uma vez e a recomendação
**retida** em vez de chutada -- mesmo com Concorrência disponível, falta
Margem e Risco para fechar o caso comercial.

## O que está verificado

Situação em 18/11/2026. São níveis diferentes de confiança, e o projeto
não os mistura:

| Parte | Situação |
|---|---|
| Motores, composição, orquestração e laço do agente | Testados offline: 1.310 testes com pytest, sem rede e sem chave de API |
| Google Trends via Apify | Validado ao vivo, com dados reais |
| Mercado Livre — OAuth | Implantado e autorizado (PKCE + relay no Cloudflare Worker). Token real, renovado a cada ~6h (ver [`docs/MERCADO_LIVRE_OAUTH.md`](docs/MERCADO_LIVRE_OAUTH.md)) |
| Mercado Livre — Concorrência | Validado ao vivo pela Fase 13: categoria → mais vendidos → ofertas reais de vendedores. `/sites/MLB/search` em si continua bloqueado por política do Mercado Livre mesmo autenticado — não é usado (ver [`docs/MERCADO_LIVRE_403.md`](docs/MERCADO_LIVRE_403.md)) |
| Agente com LLM (Anthropic) | Laço testado com um modelo roteirizado; integração com o SDK testada contra uma simulação. Nenhuma execução chegou à API real ainda |
| Margem, Fornecedor, Logística e Risco | Entradas manuais. Não existe provedor para esses domínios |

## Como rodar

Requer Python 3.12.

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows; no Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

python -m src.main               # menu com as opções 1 a 12
python -m pytest                 # 1.310 testes, cerca de 6 segundos
```

| Opção | O que faz |
|---|---|
| 1 | Analisador manual (modelo `legacy-v1`) |
| 2 | Busca no Mercado Livre |
| 3 a 9 | Análise de um domínio por vez |
| 10 | Análise integrada sobre quatro cenários ilustrativos |
| 11 | Análise orquestrada: busca a evidência e compõe o resultado |
| 12 | Agente de pesquisa (opcional) |

Credenciais ficam no `.env`, que é ignorado pelo git. Copie
`.env.example` e preencha o que for usar; nenhuma é necessária para os
testes. A opção 12 também pede `pip install anthropic` e uma
`ANTHROPIC_API_KEY`. Sem o pacote ou sem a chave, ela responde
`UNAVAILABLE` e explica o motivo.

## Modelo de pontuação (`integrated-v1`)

| Componente | Peso | Camada | Direção |
|---|---|---|---|
| Interesse de busca (Demanda ou Tendência) | 0,30 | comercial | positiva |
| Concorrência | 0,15 | comercial | negativa |
| Margem | 0,20 | comercial | positiva |
| Fornecedor | 0,12 | operacional | positiva |
| Logística | 0,08 | operacional | positiva |
| Risco | 0,15 | comercial | negativa |

Faixas de classificação: 80 ou mais, *Strong opportunity*; 65 ou mais,
*Worth deeper investigation*; 50 ou mais, *Weak or uncertain*; abaixo de
50, *Reject*. A faixa só é emitida como classificação final quando a
prontidão é `READY`. Os quatro estados de prontidão, em ordem de
precedência: `BLOCKED`, `INCOMPLETE_EVIDENCE`,
`OPERATIONALLY_UNVALIDATED` e `READY`.

Os pesos são constantes documentadas e ajustáveis. Nenhuma foi calibrada
contra resultados reais de venda.

## Arquitetura

```
integrations/                provedores (HTTP só existe aqui)
      |
*_models.py                  contratos de entrada, neutros de provedor
      |
*_analysis.py                pontuação determinística (7 domínios)
      |
opportunity_models.py        contrato canônico
opportunity_integration.py   adaptadores + composição
      |
orchestrator.py              busca a evidência e aciona tudo acima
      |
agent/  +  llm_client.py     LLM escolhe ferramentas e explica
      |
main.py                      só apresentação (CLI)
```

As dependências têm mão única: os motores de domínio não importam uns
aos outros nem o orquestrador, e nada abaixo do agente importa o
agente. Essas fronteiras são conferidas por teste.

## Testes e CI

- 1.310 testes com pytest, todos offline.
- Um verificador de invariantes
  (`.claude/skills/invariant-check/check_invariants.py`) confere o que
  os testes não cobrem: fronteiras de import, pontos de inversão,
  determinismo das camadas de pontuação e ausência de segredos no diff.
- O GitHub Actions roda compilação, verificador de invariantes e testes
  em todo pull request e em todo push na `main`.

## Como o projeto foi construído

Desenvolvimento assistido por IA, com Claude Code. As regras do projeto
ficam em [`CLAUDE.md`](CLAUDE.md). O repositório traz dois agentes de
revisão (`.claude/agents/`), um verificador de invariantes e o CI no
GitHub Actions para conferir as mudanças. Cada fase foi construída e
testada antes da seguinte.

## Documentação

- [`docs/PHASES.md`](docs/PHASES.md): registro fase a fase, com
  fórmulas, decisões e limitações (em inglês).
- [`docs/LEARNING.md`](docs/LEARNING.md): diário de aprendizado, com o
  porquê de cada decisão e exemplos numéricos (em português).
- [`docs/MAINTENANCE.md`](docs/MAINTENANCE.md): rotina de verificação
  das integrações.
- [`docs/MERCADO_LIVRE_403.md`](docs/MERCADO_LIVRE_403.md): diagnóstico
  e plano para o 403 do Mercado Livre.

## Próximos passos

Pendência de validação: primeira execução do agente contra a API real
da Anthropic (exige chave com faturamento próprio).

Planejado e **ainda não implementado**: fornecedores nacionais de
dropshipping, banco de dados e histórico, automação com n8n e
notificações.
