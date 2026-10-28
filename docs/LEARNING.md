# LEARNING.md — Diário de Aprendizado do RAVZ Product Hunter

Este arquivo documenta, fase por fase, o que foi construído neste projeto e
o que o autor deveria aprender de **AI Engineering** e **Software
Engineering** em cada etapa. As explicações são em português, mas os termos
técnicos em inglês são mantidos, porque é assim que você vai encontrá-los no
mercado, em documentações e em entrevistas.

Cada fase segue sempre a mesma estrutura:

1. Nome da fase
2. Explicação simples
3. Explicação técnica
4. Conexão entre o simples e o técnico
5. O que implementamos na prática
6. Termos técnicos aprendidos
7. Comandos/ferramentas usados
8. Como explicar isso para um recrutador ou cliente
9. O que devo lembrar desta fase

---

## Fase 1 — Fundação do projeto e motor de scoring

### 1. Nome da fase

**Fase 1: Fundação do projeto, modelos de dados e motor de Opportunity
Score (weighted scoring engine).**

### 2. Explicação simples

Imagina que você quer decidir se vale a pena abrir uma banca para vender um
produto novo. Você não tem bola de cristal, mas pode olhar várias pistas:
"tem muita gente procurando esse produto?", "tem muito concorrente
vendendo a mesma coisa?", "a procura está crescendo ou caindo?", "dá lucro
de verdade depois de pagar tudo?".

Cada uma dessas pistas é uma "nota de 0 a 100", como uma prova escolar.
Depois, a gente combina essas notas com **pesos diferentes** — porque
algumas pistas importam mais que outras — e chega em uma **nota final
única**, de 0 a 100, chamada de *Opportunity Score*. Essa nota final é
traduzida em um "veredito": "ótima oportunidade", "vale investigar",
"fraca" ou "rejeitar".

É como calcular a média final de um aluno quando cada prova tem um peso
diferente (prova de matemática vale mais que o trabalho em grupo, por
exemplo) — só que aqui, duas das "provas" (concorrência e risco) são
provas em que **tirar nota alta é ruim**, não bom. Então antes de somar,
a gente "inverte" essa nota.

Nesta fase, ainda não buscamos essas notas na internet ou no Mercado
Livre — nós mesmos digitamos as notas à mão, só para provar que o
"calculador" (o motor de scoring) funciona certo antes de conectar dados
reais.

### 3. Explicação técnica

Construímos a fundação (*project foundation*) de um sistema de scoring
determinístico (*deterministic logic*) em Python 3.12, seguindo
arquitetura modular com separação clara entre:

- **Data models** (`src/models.py`): três `dataclasses` imutáveis em
  responsabilidade — `Product` (dados de identificação do produto),
  `ComponentScores` (os inputs de scoring, 0–100 por dimensão, com
  *input validation* feita em `__post_init__`) e `OpportunityResult`
  (o output final, contendo o score, a classificação e o breakdown por
  dimensão, para que o resultado seja *explainable*).
- **Scoring engine** (`src/scoring.py`): uma função pura
  (`calculate_opportunity_score`) que implementa um **weighted scoring
  engine** com pesos fixos (Demand 30%, Trend 20%, Competition 15%,
  Margin 15%, Supplier 10%, Logistics 5%, Risk 5%), e uma função
  `classify()` que mapeia o score final para uma categoria usando limiares
  (*thresholds*) fixos (80/65/50).
- **Inversão de dimensões negativas**: `competition` e `risk` são
  armazenadas na mesma convenção que as demais (quanto maior, mais daquilo
  existe), mas o *scoring engine* aplica `100 - score` antes de multiplicar
  pelo peso — isolando essa regra de negócio dentro da camada de cálculo,
  e não dentro do modelo de dados.
- **Lógica determinística**: dado o mesmo `ComponentScores`, o resultado é
  sempre exatamente o mesmo — não há aleatoriedade, não há chamada a LLM,
  não há I/O. Isso é o que torna o motor 100% testável.
- **Test suite** (`tests/test_scoring.py`): 27 testes unitários escritos
  com `pytest`, cobrindo casos extremos (*perfect opportunity*,
  *terrible opportunity*), limites exatos de classificação (*boundary
  testing*), validação de inputs inválidos, inversão de competição/risco,
  e o cálculo matemático exato do weighted sum.
- **Configuração de ambiente** (`pyproject.toml`): metadados do projeto
  (`requires-python = ">=3.12"`) e configuração do `pytest`
  (`pythonpath`, `testpaths`), garantindo que os testes rodem de forma
  confiável tanto com `pytest` quanto com `python -m pytest`.
- **Controle de versão**: o projeto vive dentro de um **Git repository**
  local, versionado com **commits** pequenos e descritivos, preparado para
  ser publicado em um **GitHub repository** remoto.

### 4. Conexão entre o simples e o técnico

A "prova escolar com pesos diferentes" da explicação simples é, em termos
técnicos, um **weighted scoring engine** — uma soma ponderada
(`Σ score_i * weight_i`). A ideia de "duas provas em que nota alta é
ruim" é o conceito de **dimensões negativas** (*negative dimensions*),
resolvido tecnicamente invertendo o valor (`100 - score`) antes de
ponderar. E "ainda não buscamos nada na internet, só digitamos à mão" é,
tecnicamente, a decisão de arquitetura de manter esta fase **sem
integrações externas**, para validar a lógica de negócio (o motor de
scoring) isoladamente de qualquer fonte de dados — o mesmo princípio por
trás de **unit tests** e de **lógica determinística**: testar a regra de
negócio sem depender de rede, banco de dados ou tempo real.

### 5. O que implementamos na prática

- `src/models.py` — `Product`, `ComponentScores` (com validação 0–100),
  `OpportunityResult`.
- `src/scoring.py` — `WEIGHTS`, `NEGATIVE_DIMENSIONS`,
  `calculate_opportunity_score()`, `classify()`, `score_opportunity()`.
- `tests/test_scoring.py` — 27 testes cobrindo: opportunity perfeita,
  opportunity péssima, 8 limites de classificação, 14 casos de score
  inválido (acima/abaixo do range, nos 7 campos), inversão de
  competição/risco, cálculo exato do weighted sum, e construção completa
  do `OpportunityResult`.
- `pyproject.toml` — metadados do projeto + configuração do `pytest`
  (`pythonpath = ["."]`, `testpaths = ["tests"]`), permitindo rodar
  `pytest` direto da raiz do repositório sem erros de import.
- `requirements.txt` — apenas `pytest` como dependência (de
  desenvolvimento/teste).
- `README.md` — explicação do projeto, escopo da Fase 1, instruções de
  instalação e execução de testes, roadmap das próximas fases.
- `.env.example` / `.gitignore` — preparados desde o início para nunca
  expor segredos (API keys) no repositório.

### 6. Termos técnicos aprendidos

- **termo:** `dataclass`
  **definição:** decorador do Python que gera automaticamente `__init__`,
  `__repr__` e `__eq__` para uma classe que serve principalmente para
  guardar dados.
  **como apareceu no projeto:** `Product`, `ComponentScores` e
  `OpportunityResult` em `src/models.py` são todas `@dataclass`.

- **termo:** Data model
  **definição:** representação estruturada de um conceito do domínio
  (aqui, "um produto", "um conjunto de notas", "um resultado final").
  **como apareceu no projeto:** separação explícita entre dado bruto do
  produto, inputs de scoring e resultado final — três modelos distintos
  em vez de um único objeto genérico.

- **termo:** Input validation
  **definição:** garantir que os dados recebidos respeitam as regras
  esperadas antes de serem usados, rejeitando dados inválidos o quanto
  antes.
  **como apareceu no projeto:** `__post_init__` em `ComponentScores`
  levanta `ValueError` se qualquer score estiver fora do intervalo 0–100.

- **termo:** Weighted scoring engine
  **definição:** sistema que calcula uma nota final combinando várias
  notas parciais, cada uma multiplicada por um peso que reflete sua
  importância relativa.
  **como apareceu no projeto:** `WEIGHTS` + `calculate_opportunity_score()`
  em `src/scoring.py`.

- **termo:** Negative dimension (dimensão negativa)
  **definição:** uma métrica em que um valor alto deve reduzir o
  resultado final, em vez de aumentá-lo.
  **como apareceu no projeto:** `competition` e `risk` são invertidas
  (`100 - score`) antes de entrarem na soma ponderada.

- **termo:** Classification / thresholds
  **definição:** mapear um valor numérico contínuo para categorias
  discretas, usando pontos de corte fixos.
  **como apareceu no projeto:** `classify()` mapeia o score final para
  "Strong opportunity", "Worth deeper investigation", "Weak or uncertain
  opportunity" ou "Reject" usando os limiares 80/65/50.

- **termo:** Deterministic logic (lógica determinística)
  **definição:** código cujo resultado depende apenas dos inputs — mesma
  entrada sempre gera a mesma saída, sem aleatoriedade e sem efeitos
  colaterais externos.
  **como apareceu no projeto:** todo o motor de scoring não usa
  aleatoriedade, data/hora, rede ou qualquer chamada externa — é possível
  testá-lo com total confiança.

- **termo:** Unit test (teste unitário)
  **definição:** teste automatizado que verifica uma unidade pequena e
  isolada de código (geralmente uma função), de forma rápida e repetível.
  **como apareceu no projeto:** cada função de `test_scoring.py` testa um
  comportamento específico de `calculate_opportunity_score`, `classify`
  ou `score_opportunity`.

- **termo:** Boundary testing (teste de limite)
  **definição:** testar especificamente os valores exatamente nas bordas
  de uma regra (por exemplo, 79.99 vs 80), onde bugs de "maior que" vs
  "maior ou igual a" costumam se escconder.
  **como apareceu no projeto:**
  `test_classification_boundaries` testa 80, 79.99, 65, 64.99, 50, 49.99.

- **termo:** `pytest`
  **definição:** framework de testes em Python que descobre e executa
  funções de teste automaticamente, com relatórios claros de
  passou/falhou.
  **como apareceu no projeto:** ferramenta usada para rodar todos os 27
  testes de `test_scoring.py`.

- **termo:** `pyproject.toml`
  **definição:** arquivo padrão (PEP 518/621) usado para declarar
  metadados de um projeto Python e configurar ferramentas (como o
  `pytest`) em um único lugar.
  **como apareceu no projeto:** define `requires-python` e a seção
  `[tool.pytest.ini_options]` com `pythonpath` e `testpaths`.

- **termo:** Virtual environment (ambiente virtual)
  **definição:** uma instalação isolada do Python e de suas bibliotecas,
  separada do Python "global" do sistema, para evitar conflito entre
  projetos.
  **como apareceu no projeto:** instruções no `README.md` para criar um
  `.venv` antes de instalar `requirements.txt`.

- **termo:** Git
  **definição:** sistema de controle de versão (*version control
  system*) que registra o histórico de mudanças de um projeto ao longo
  do tempo, permitindo voltar, comparar e ramificar o código.
  **como apareceu no projeto:** o projeto já é um **Git repository**
  local (`.git/`), com um `.gitignore` configurado desde o início para
  nunca versionar `.env` ou ambientes virtuais.

- **termo:** Commit
  **definição:** um "retrato" (snapshot) salvo e identificado do estado
  do código em um determinado momento, acompanhado de uma mensagem
  explicando o que mudou e por quê.
  **como apareceu no projeto:** a prática definida no `CLAUDE.md` é fazer
  commits pequenos e descritivos (ex.: `feat: implement scoring engine`),
  um por etapa concluída.

- **termo:** Repository (repositório)
  **definição:** a pasta do projeto rastreada pelo Git, contendo todo o
  histórico de commits.
  **como apareceu no projeto:** `ravz-product-hunter` é o repositório
  local deste projeto.

- **termo:** GitHub
  **definição:** serviço de hospedagem remota de repositórios Git na
  nuvem, usado para backup, colaboração e para mostrar o portfólio
  publicamente.
  **como apareceu no projeto:** o repositório local ainda será publicado
  (*pushed*) para o GitHub como parte do objetivo de portfólio deste
  projeto.

### 7. Comandos/ferramentas usados

```bash
python --version                  # confirmar Python 3.12
python -m venv .venv               # criar ambiente virtual
pip install -r requirements.txt    # instalar pytest
python -m pytest -v                # rodar testes via módulo
pytest -v                          # rodar testes direto (via pyproject.toml)
```

Ferramentas: Python 3.12, `pytest`, `pyproject.toml`, Git (repositório
local), editor de código, terminal.

### 8. Como explicar isso para um recrutador ou cliente

"Eu construí a base de um sistema de decisão (*decision-support system*)
que transforma várias métricas de um produto em uma única nota de
oportunidade, de forma explicável e testada. Separei claramente os dados
de entrada, a lógica de cálculo e o resultado final — isso facilita
manutenção e testes. Antes de conectar qualquer API externa, validei a
lógica de negócio com uma suíte de 27 testes automatizados, incluindo
casos extremos e valores de borda, garantindo que o cálculo do score está
correto e é determinístico antes de depender de dados reais do
Mercado Livre."

### 9. O que devo lembrar desta fase

- Separar **dados** (models) de **lógica** (scoring) de **integrações**
  (ainda não existem) é o que torna um sistema fácil de testar e de
  evoluir.
- Uma dimensão pode usar a mesma escala (0–100) que as outras e ainda
  assim ter efeito **inverso** no resultado final — a inversão é
  responsabilidade da camada de cálculo, não do modelo de dados.
- **Testar antes de integrar**: validar a lógica de negócio com dados
  manuais e testes automatizados, antes de depender de qualquer fonte de
  dados externa (API, scraping, banco de dados).
- Testes de **limite** (boundary tests) são tão importantes quanto
  testes de caso "normal" — é onde erros de `>` vs `>=` se esondem.
- Um arquivo de configuração como `pyproject.toml` resolve, de forma
  simples, problemas de ambiente (como `pytest` não encontrar o pacote
  `src`), sem precisar de "gambiarras" como manipular `sys.path` dentro
  do código.
- Projeto, desde o commit zero, já pensa em segurança (`.gitignore`,
  `.env.example`) e em processo (commits pequenos e descritivos) — hábitos
  que valem tanto para um projeto pessoal quanto profissional.
