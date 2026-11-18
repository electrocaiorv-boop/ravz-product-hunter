# RAVZ Product Hunter — Visão geral do projeto

> Documento vivo. Atualizar a cada fase: estado, fases, bloqueios e próximos passos.
> **Última atualização:** 18/11/2026 (permissões do app no DevCenter revisadas e reautorizadas; pendência de segurança do OAuth encerrada)

Repositório: https://github.com/electrocaiorv-boop/ravz-product-hunter
Pasta local: `C:\Users\caios\ravz-product-hunter`

## 1. O que queremos construir

Um sistema de inteligência comercial que encontra produtos para vender no Mercado Livre com:

- demanda consistente;
- **concorrência administrável** — produtos que dá para vender mesmo havendo concorrentes;
- **fornecedores brasileiros confiáveis, com dropshipping nacional** (operação sem estoque próprio);
- margem positiva, logística viável e riscos conhecidos.

Dois objetivos ao mesmo tempo: uma ferramenta real para gerar receita (uso próprio da RAVZ) e um projeto técnico de portfólio (Python, APIs, automação, engenharia de software, agentes de IA).

**Princípio central:** nenhuma nota é probabilidade de venda. São heurísticas determinísticas, documentadas e ainda não calibradas contra vendas reais. A IA decide o que pesquisar e explica resultados; quem calcula são motores determinísticos e testáveis.

## 2. Como funciona

Fontes (Mercado Livre, Google Trends via Apify, dados de fornecedor) → sete motores (Tendência, Demanda, Concorrência, Margem, Fornecedor, Logística, Risco) → Opportunity Score 0–100 com cobertura de evidências → classificação final só quando o estado é `READY` → agente de pesquisa com IA (escolhe evidências dentro de limites).

### Pesos (`integrated-v1`)

| Dimensão | Peso |
|---|---|
| Interesse de busca (Demanda/Tendência, mesma família de evidência) | 30% |
| Margem | 20% |
| Concorrência (invertida) | 15% |
| Risco (invertido) | 15% |
| Fornecedor | 12% |
| Logística | 8% |

| Nota | Leitura |
|---|---|
| 80–100 | Oportunidade forte |
| 65–79,99 | Merece investigação |
| 50–64,99 | Fraca ou incerta |
| < 50 | Rejeitar |

## 3. Fases

| Fase | Entrega | Situação |
|---|---|---|
| 1 — Scoring Engine | Modelos, pesos, Opportunity Score | Concluída |
| 2 — Manual Analyzer | CLI de análise manual | Concluída |
| 3 — Mercado Livre API | Cliente HTTP e mapeamento | Implementada; **busca bloqueada pelo ML (ver §5)** |
| 4 — Trend Analysis | Google Trends via Apify | Concluída, validada ao vivo |
| 5 — Demand Analysis | Demanda + confiança | Concluída (notas provisórias) |
| 6 — Competition Analysis | Preços, vendedores, frete da amostra | Concluída; fonte ao vivo pela Fase 13 (catálogo de categoria, não mais `/sites/MLB/search`) |
| 7 — Margin Analysis | Margem com custos e taxas | Concluída (entradas manuais) |
| 8 — Supplier Analysis | Fornecedor, estoque, MOQ, dropshipping | Concluída (**entradas manuais, sem busca de fornecedor**) |
| 9 — Logistics Analysis | Armazenagem, transporte, perdas | Concluída (entradas manuais) |
| 10 — Risk Analysis | Sazonalidade, devolução, regulatório | Concluída (entradas manuais) |
| 11 — Opportunity Integration | Composição dos sete motores | Concluída |
| 12A — Orchestration | Busca evidências e integra | Concluída |
| 12B — AI Research Agent | Agente com LLM, limites e verificações | Na `main` (a1abd82); **sem chamada real de LLM ainda** |
| OAuth Mercado Livre | PKCE + relay no Cloudflare Worker + refresh | **Na `main`** (PR #5, merge `0f2cb6d`, 18/11/2026); implantado e autorizado em 17/11/2026 |
| **13 — Fonte de concorrência por catálogo** | Concorrência via categoria → mais vendidos → vendedores por produto | **Na `main`** (PR #5, merge `0f2cb6d`, 18/11/2026) |

## 4. Fase 13 — Fonte de concorrência por catálogo

**Por quê:** a busca `/sites/MLB/search` é bloqueada pelo Mercado Livre para aplicativos comuns (§5). Sem ela, a Concorrência fica indisponível e a análise nunca chega a `READY`.

**Como (implementado):** palavra-chave → `/sites/MLB/domain_discovery/search` (categoria) → `/highlights/MLB/category/{id}` (top N mais vendidos) → para cada entrada: `/products/{id}` + `/products/{id}/items` (produto de catálogo: nome + ofertas reais) ou `/items/{id}` (anúncio avulso, tipo `ITEM`). Máximo **2 + 2×top_n** requisições por análise (top_n padrão = 5 → até 12; teto rígido top_n ≤ 10 → até 22), sequenciais, sem concorrência, sem retry.

**Arquivos:**
- `src/integrations/mercadolivre_catalog.py` (novo) — toda a cadeia HTTP: `discover_category`, `fetch_category_highlights`, `fetch_product_detail`, `fetch_product_offers`, `fetch_item_detail`, `sample_category_competition`. Falha em 1 produto/item não aborta a amostra — ele é descartado com motivo registrado em `skipped`, e os demais seguem.
- `src/competition_models.py` — nova função `build_competition_signals_from_category_sample`; `build_competition_signals` (fonte antiga) intocada.
- `src/competition_analysis.py` — única mudança real: `sample_adequacy_score` passa a usar `products_sampled/top_n` quando a amostra vem do catálogo.
- `src/orchestrator.py` — para de chamar `/sites/MLB/search` ao vivo (decisão aprovada); novo provider `mercadolivre:category_catalog` alimenta só a Concorrência (Demanda nunca pesou essa evidência: `marketplace_contribution` é permanentemente `None`).
- `src/agent/tools.py` / `src/agent/runner.py` — a ferramenta `search_marketplace` do agente (Fase 12B) continua intocada, apontando pro endpoint antigo por conta própria; só o seam que ligava `run_full_analysis` à busca antiga foi removido.
- `tests/fixtures/mercadolivre_catalog/` — captura real (17/11/2026, só leitura) usada nos testes offline.

**Regras aplicadas:**
- As ofertas de `/products/{id}/items`/`/items/{id}` são anúncios reais de vendedores. Catálogo (`/products/search`) nunca substitui anúncios — nem é chamado.
- A busca antiga fica no código como fonte indisponível (`mercadolivre.py`/`search_products`), não é apagada, só não é mais chamada pelo orchestrator.
- Tipo de highlight não reconhecido (ex.: `USER_PRODUCT`, visto ao vivo na posição 14 da amostra real) é descartado com motivo, nunca um endpoint adivinhado.
- Nome do produto é obrigatório: catálogo/item sem nome resolvido é descartado da amostra (não só do relatório).
- `seller_concentration` por produto usa `1 / nº de vendedores distintos` (índice HHI assumindo participação igual entre eles), **não** `vendedores únicos / total de ofertas` — ver correção abaixo. Média entre produtos de catálogo; itens avulsos (`kind=ITEM`) ficam fora dessa média e da de `price_crowding` (uma oferta única leria como "concentração mínima", quando na verdade não há nenhum concorrente catalogado), mas entram em frete/contexto.
- `price_crowding` por produto é a dispersão de preço dentro do produto, média entre produtos de catálogo. Produto de catálogo com 1 oferta: `price_crowding` dele é `None` (dispersão não é definida com 1 ponto); `seller_concentration` entra normalmente (1 vendedor → índice 1.0, concentração máxima).
- `duplicate_title_ratio` fica permanentemente `None` nessa fonte: ofertas do mesmo produto compartilham o nome por construção, então duplicidade mediria o agrupamento, não anúncios templated.
- `official_store_id` é mapeado (confirmado presente em `/products/{id}/items`) e reportado por produto como observação (sim/não/desconhecido) — não entra em nenhuma nota ainda.
- Tabela observada por produto (nome, nº ofertas, nº vendedores distintos, preço min/max, loja oficial, % frete grátis) exposta em `observed["product_table"]`, para decisão humana de onde buscar fornecedor.
- Determinismo, tri-state (desconhecido ≠ zero), teto de confiança (55, fonte única), sem retries silenciosos, sem logar token — mantidos.

**Correção de lógica (18/11/2026, antes da aprovação):** a primeira versão reaproveitou `vendedores_únicos / total_de_ofertas` por produto — a mesma fórmula da amostra plana antiga. Essa razão é quase sempre ≈1.0 nessa amostra (o Mercado Livre não retorna duas ofertas do mesmo vendedor para o mesmo produto de catálogo), então ela não carrega sinal de concentração nenhum, e no caso extremo (1 oferta) lia 1/1=1.0 como "zero concentração" — o oposto do que significa um produto com um único vendedor. O resultado ao vivo original (`competition_score=14.47`, "fácil") contradizia a própria observação registrada no `LEARNING.md` no mesmo dia (produtos oficiais de marca com 1-2 ofertas cada). Corrigido para `seller_concentration_index = média(1/nº_vendedores_distintos)` por produto — o HHI de participação igual, documentado em `src/competition_models.py`. `unique_seller_ratio` fica `None` para essa fonte (não foi reaproveitado com outro significado).

**Critério de aprovação — resultado (atualizado após a correção, 18/11/2026):**
- Suíte inteira passando: **1310 passed, 1 skipped**.
- Execução real com "fone bluetooth": Concorrência **disponível** — categoria `MLB196208` (Fones de Ouvido), 5 produtos amostrados (Soundcore P20i/P30i, "Pro 4" genérico, Xiaomi Redmi Buds 6 Play, Samsung Galaxy Buds Core), `competition_score=31.54` (antes da correção: 14.47), `confidence_score=55.0` (teto da fonte única). `seller_concentration_index=0.413` — mistura de produtos de marca com 1 vendedor e produtos genéricos com 70-100 vendedores. Ver tabela por produto na seção 5.
- Nenhuma regressão detectada nas Fases 1–12B; `invariant-check` → PASS, 0 FAIL, 0 WARN.
- `.gitattributes` adicionado (`* text=auto eol=lf`) depois de detectar que vários arquivos alterados nesta sessão foram salvos em CRLF; todos convertidos de volta para LF antes da aprovação.
- **Aprovada por Caio em 18/11/2026.** Commitada em 3 commits (correções do Passo 0, `.gitattributes`, Fase 13), enviada no PR #5 e revisada. CI verde, sem conflito com a `main`. **Mesclada na `main`** com merge commit (sem squash, mesmo padrão dos merges da Fase 12A/12B) em `0f2cb6d`; branch `feat/mercadolivre-oauth` mantida no remoto.

## 5. Estado real — 17/11/2026

### Mercado Livre (validado ao vivo com token OAuth real)

| Endpoint | Resultado | Leitura |
|---|---|---|
| `GET /sites/MLB` | 200 | Autenticação funcionando |
| `GET /sites/MLB/search?q=` | **403** | Bloqueio de política do ML para apps comuns, relatado por vários desenvolvedores desde o início de 2026; sem caminho oficial de liberação conhecido. Não esperar. |
| `GET /sites/MLB/domain_discovery/search` | 200 | "fone bluetooth" → Fones de Ouvido (MLB196208) |
| `GET /highlights/MLB/category/MLB196208` | 200 | 20 mais vendidos |
| `GET /products/{id}` | 200 | Detalhe do produto (1º: Soundcore P20i, Anker) |
| `GET /products/{id}/items` | 200 | 2 ofertas de vendedores nesse produto |

**Fase 13 implementada e validada ao vivo (17-18/11/2026):** para "fone bluetooth", a cadeia completa (`domain_discovery` → `highlights` → `/products/{id}` + `/products/{id}/items`, top_n=5) retorna Concorrência **disponível**: categoria `MLB196208` (Fones de Ouvido), 5 produtos amostrados com nome real. A amostra real também revelou um tipo de highlight não documentado (`USER_PRODUCT`), tratado como não suportado e descartado com motivo — nunca um endpoint adivinhado.

Resultado após a correção da fórmula de concentração (18/11/2026): `competition_score=31.54`, `confidence_score=55.0`, `seller_concentration_index=0.413`.

| Produto | Ofertas | Vendedores distintos | Preço min | Preço max | Loja oficial | % frete grátis |
|---|---|---|---|---|---|---|
| Fone De Ouvido Soundcore by Anker P20i... | 1 | 1 | 129,00 | 129,00 | sim | 100% |
| Fone De Ouvido Bluetooth... Pro 4... | 72 | 70 | 10,00 | 3382,00 | sim | 22% |
| Fone de Ouvido Bluetooth 5.4 soundcore P30i... | 1 | 1 | 196,00 | 196,00 | sim | 100% |
| Fone De Ouvido Sem Fio Xiaomi Redmi Buds 6 Play | 100 | 90 | 57,61 | 99,00 | sim | 85% |
| Samsung Galaxy Buds Core branco | 30 | 24 | 228,40 | 699,00 | sim | 100% |

A faixa de preço do "Pro 4" (R$ 10 a R$ 3.382 dentro do mesmo `product_id`) é ruído do catálogo do Mercado Livre, não um erro deste projeto — reportado como observado, não suavizado nem descartado.

### OAuth
- Worker publicado: `https://ravz-ml-oauth.ravztech.workers.dev` (callback `/api/mercadolivre/callback`), sem DNS do ravztech.com.br.
- Conta autorizada; token salvo em `.secrets/` (fora do git). Access token dura ~6 h: `python -m src.integrations.mercadolivre_oauth refresh`.
- **Permissões do app revisadas no DevCenter em 18/11/2026 e reautorizado.** Hoje o app só tem acesso a: "Usuários" (leitura e escrita — campo obrigatório do próprio Mercado Livre, não editável) e "Publicação e sincronização" (leitura). Todo o resto, sem acesso. O escopo `write`/`admin:*:read-write` que aparecia no token vem exclusivamente do campo obrigatório de Usuários; "Publicação e sincronização" (o que afetaria anúncios/estoque) é só leitura. **Pendência de segurança encerrada** — o Product Hunter nunca publica nem escreve em anúncio, e o escopo de escrita restante não é algo que o projeto escolheu nem pode remover.

### Correções de 17/11/2026 (não commitadas, aguardando revisão)
- Testes de handoff de token tinham vencimento fixo (09/11/2026) e passaram a falhar depois dessa data → relógio fixado nos testes.
- Diagnóstico lia só a variável de ambiente e mostrava "NOT configured" com token salvo → usa `resolve_access_token()`.
- `tests/conftest.py`: isola o `.secrets/` real dos testes.
- `probe_ml_alternativas.py`: script de diagnóstico dos endpoints alternativos (exige `--i-approve-live-read-only-requests`, mesmo padrão do diagnóstico oficial).
- Suíte: **1.257 passando** na branch do OAuth.

### Outras pendências
- Agente Anthropic: validar a primeira chamada real (exige chave de API com faturamento próprio).
- PR #4 (README curto + `docs/PHASES.md`) ainda aberto.
- Fornecedor: só entrada manual — maior lacuna para o objetivo de dropshipping nacional.

## 6. Próximos passos (em ordem)

1. **PR #4** (README curto + `docs/PHASES.md` + Fases 12A-12B no LEARNING) — próximo passo. Conflita com o que a Fase 13 mesclou em `docs/LEARNING.md` (ambos só adicionam conteúdo, mas no mesmo ponto do fim do arquivo); confirmado por simulação local de merge em 18/11/2026. Vai precisar de rebase/resolução do conflito antes de mesclar.
2. **Melhoria futura na tabela por produto (Fase 13):** hoje "loja oficial" é sim/não **por produto** (sim se QUALQUER oferta daquele produto tiver `official_store_id`) — com isso, "sim" aparece quase sempre, mesmo quando a maioria das ofertas é de revendedor comum. Falta: (a) quantas das N ofertas daquele produto são de loja oficial (ex.: "2 de 72"), e (b) se a oferta de **menor preço** é de loja oficial ou não — essa é a pergunta que decide se vale tentar competir por preço ou se o concorrente mais barato já é a marca. Nenhuma das duas precisa de requisição nova; é reprocessar `product_table`/`ProductObservation` com os dados já coletados.
3. **Fase 14 (proposta)** — Fornecedores nacionais de dropshipping: pesquisar quem tem catálogo/API no Brasil e ligar à Fase 8, cruzando produto ↔ fornecedor ↔ custo ↔ prazo, com margem automática.
4. Primeira chamada real do agente Anthropic.
5. Análise comercial completa de um produto real (custos, taxas e frete atualizados) e teste de venda com capital mínimo.
6. Depois: banco de dados e histórico, pesquisa em lote e ranking, n8n e alertas.

~~Permissões só de leitura no app do Mercado Livre~~ — revisado e reautorizado em 18/11/2026, ver §5. Pendência encerrada.

## 7. Regra de trabalho

Cada fase tem início e escopo definidos, implementação, testes, critério objetivo de aprovação, documentação e encerramento formal. Nada de commit ou push sem aprovação. Este documento é atualizado ao abrir e ao encerrar cada fase.

## Histórico deste documento
- 18/11/2026 (permissões) — Caio revisou e reautorizou as permissões do app no DevCenter: só "Usuários" (leitura e escrita, campo obrigatório do ML, não editável) e "Publicação e sincronização" (leitura); resto sem acesso. Pendência de segurança do §5 encerrada; removida de §6.
- 18/11/2026 (merge) — PR #5 revisado por Caio: CI verde, sem conflito com a `main`. Mesclado com merge commit (sem squash) em `0f2cb6d`, branch remota mantida. OAuth do Mercado Livre e Fase 13 agora na `main`. Checado por simulação local: PR #4 vai conflitar com a Fase 13 em `docs/LEARNING.md` (ambos só adicionam, no mesmo ponto do fim do arquivo) — registrado em §6 como próximo passo, PR #4 não foi tocado.
- 18/11/2026 (aprovação) — Caio aprovou a Fase 13. Commitada em 3 partes (correções do Passo 0, `.gitattributes`, Fase 13) e enviada em PR para `main` (merge pendente de revisão). Registrada em §6 a melhoria futura: % de ofertas de loja oficial por produto e se a oferta mais barata é de loja oficial.
- 18/11/2026 — Correção de lógica revisada pelo usuário antes da aprovação: `seller_concentration` por produto estava invertida para produtos de 1 vendedor (lia como "zero concentração"). Corrigida para `1/nº_vendedores` (HHI de participação igual), mapeado `official_store_id`, adicionada tabela observada por produto. Suíte 1310 passed + 1 skipped. `.gitattributes` adicionado (LF) depois de arquivos terem sido salvos em CRLF nesta sessão; todos convertidos de volta. Nova execução real: `competition_score=31.54` (antes: 14.47). Ainda aguardando aprovação para commit/push.
- 17/11/2026 23h — Fase 13 implementada pelo Claude Code: novo provider de concorrência por catálogo, orchestrator parou de chamar a busca bloqueada, suíte 1301 passed + 1 skipped, `invariant-check` PASS. Execução real com "fone bluetooth" confirmou Concorrência disponível com nomes de produto. Aguardando aprovação para commit/push.
- 17/11/2026 21h30 — Passo 0 revisado pelo Claude Code: as 4 correções aprovadas, suíte 1256 passed + 1 skipped. Probe passou a exigir a flag de aprovação. Fase 13 liberada.
- 17/11/2026 — Versão inicial na pasta do projeto, a partir da visão geral anterior + validações ao vivo do dia (OAuth, endpoints do ML, abertura da Fase 13).
