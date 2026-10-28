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

---

## Fase 2 — Manual Product Analyzer CLI

### 1. Nome da fase

**Fase 2: CLI de entrada manual (Manual Product Analyzer) ligada ao
motor de scoring da Fase 1.**

### 2. Explicação simples

Na Fase 1, a gente construiu a "calculadora" que transforma notas em uma
nota final — mas só conseguíamos usá-la escrevendo código Python
diretamente. Agora construímos um "atendente" que fica no terminal e
**conversa com você**: ele pergunta o nome do produto, a categoria, e
cada uma das sete notas, uma por vez. Se você digitar algo que não faz
sentido — por exemplo, escrever "abc" onde deveria ser um número, ou um
número maior que 100 — o atendente não trava nem quebra: ele educadamente
avisa "isso não é válido" e pergunta de novo, até você responder certo.

No final, ele entrega um relatório completo no terminal: todas as notas
que você digitou, o detalhe de quanto cada uma "pesou" na conta, a nota
final, o veredito (ex.: "vale investigar") e uma recomendação em
linguagem simples.

É como um garçom que anota seu pedido: ele não cozinha o prato (isso é
trabalho da cozinha, que já existia desde a Fase 1) — ele só coleta o
pedido, confere se faz sentido, e leva para a cozinha calcular. O
"atendente" (CLI) e a "cozinha" (motor de scoring) são peças separadas
de propósito.

### 3. Explicação técnica

Implementamos um **CLI** (*Command-Line Interface*) em `src/main.py`,
que atua como **presentation layer** do sistema — camada responsável
apenas por capturar **user input**, validar, e exibir o resultado, sem
conter nenhuma lógica de negócio (scoring) própria. Toda a lógica de
cálculo continua vindo de `src/models.py` e `src/scoring.py`, reutilizada
sem duplicação (princípio de **separation of concerns**).

A estrutura do módulo segue um fluxo de **control flow** claro:

1. `collect_product()` pergunta nome e categoria (`parse_non_empty_text`
   valida que não estão vazios).
2. `collect_scores()` pergunta as sete notas, usando `parse_score` para
   validar que cada valor é numérico e está entre 0 e 100.
3. `ask()` é a **reusable function** central: recebe um texto de prompt,
   uma função de parsing/validação (`parser`) e uma função de entrada
   injetável (`input_func`, que por padrão é o `input()` real). Ela
   executa um laço `while True` que só termina quando `parser(raw)` não
   levanta `ValueError` — ou seja, implementa a regra "pergunte de novo
   até receber uma resposta válida" sem nunca deixar o programa quebrar
   com uma exceção não tratada.
4. `score_opportunity()` (da Fase 1) calcula o resultado.
5. `format_report()` monta o relatório final como uma string, e `main()`
   apenas imprime essa string — a montagem do texto é separada da
   impressão, o que torna `format_report()` testável sem precisar
   capturar `stdout`.

O truque de **dependency injection** simples em `ask(..., input_func=input)`
é o que torna todo o módulo testável "sem testar `input()` diretamente":
nos testes, passamos uma função falsa (`fake_input`) que devolve valores
pré-definidos de uma lista, simulando um usuário digitando, sem precisar
de um terminal real nem de bibliotecas de mock mais pesadas.

`src/main.py` é também o **application entry point** do projeto neste
momento: o arquivo que você executa para "ligar" o programa
(`python -m src.main`), diferente dos módulos de `src/models.py` e
`src/scoring.py`, que são bibliotecas internas, não pontos de entrada.

### 4. Conexão entre o simples e o técnico

O "atendente que conversa com você" é, tecnicamente, uma **CLI** fazendo
**user input** via `input()`. A regra de "perguntar de novo se a
resposta não fizer sentido" é **input validation** combinada com
**control flow** (um laço que só sai quando o valor é válido) — na
prática, a função `ask()`. A separação entre "atendente" e "cozinha" é o
princípio de **separation of concerns**: o CLI (presentation layer) nunca
calcula o score sozinho, ele sempre chama `score_opportunity()` da
camada de negócio. E o fato de testarmos esse "atendente" sem precisar de
um terminal de verdade é possível porque `ask()`, `collect_product()` e
`collect_scores()` são **reusable functions** que recebem a fonte de
entrada como parâmetro, em vez de depender diretamente do `input()` do
Python.

### 5. O que implementamos na prática

- `src/main.py`:
  - `parse_score(raw)` — valida que o texto é numérico e está entre 0 e
    100.
  - `parse_non_empty_text(raw)` — valida que o texto não está vazio.
  - `ask(prompt_text, parser, input_func=input)` — laço genérico de
    pergunta-valida-repete.
  - `collect_product(input_func=input)` — pergunta nome e categoria.
  - `collect_scores(input_func=input)` — pergunta as sete notas e monta
    um `ComponentScores`.
  - `recommend(classification)` — mapeia a classificação para uma
    recomendação em linguagem simples.
  - `format_report(result)` — monta o relatório final como texto.
  - `main()` — o *entry point*: liga tudo (coleta -> calcula -> imprime).
- `tests/test_main.py` — 18 novos testes cobrindo: parsing de score
  válido/inválido (não numérico e fora do range), parsing de texto
  vazio, retry de `ask()` em múltiplas tentativas inválidas, construção
  de `Product` e `ComponentScores` a partir de inputs simulados,
  conteúdo do relatório final, e recomendação para cada classificação
  (incluindo uma desconhecida).
- `README.md` atualizado com a seção "Phase 2 scope", o comando de
  execução (`python -m src.main`) e um exemplo completo de execução.
- Nenhuma linha de `src/models.py` ou `src/scoring.py` foi alterada —
  a Fase 2 só consome o que já existia.

### 6. Termos técnicos aprendidos

- **termo:** CLI (Command-Line Interface)
  **definição:** interface de usuário baseada em texto, onde o usuário
  digita comandos/respostas no terminal em vez de clicar em botões.
  **como apareceu no projeto:** `src/main.py`, executado com
  `python -m src.main`.

- **termo:** User input
  **definição:** qualquer dado fornecido pelo usuário durante a execução
  do programa, geralmente via teclado.
  **como apareceu no projeto:** as respostas digitadas para nome,
  categoria e as sete notas.

- **termo:** Input validation
  **definição:** (já visto na Fase 1, agora aplicado à entrada
  interativa) verificar se o dado digitado pelo usuário é válido antes
  de aceitá-lo, pedindo novamente em caso de erro em vez de travar.
  **como apareceu no projeto:** `parse_score` e `parse_non_empty_text`,
  usados dentro do laço de `ask()`.

- **termo:** Control flow (fluxo de controle)
  **definição:** a ordem em que as instruções de um programa são
  executadas, incluindo laços (`while`, `for`) e decisões (`if`/`try`/
  `except`).
  **como apareceu no projeto:** o laço `while True` dentro de `ask()`,
  que só termina quando a entrada é válida.

- **termo:** Reusable function (função reutilizável)
  **definição:** função escrita de forma genérica o suficiente para ser
  chamada em múltiplos contextos sem duplicar código.
  **como apareceu no projeto:** `ask()` é usada tanto para pedir texto
  (nome, categoria) quanto para pedir números (as sete notas), só
  trocando o `parser` que recebe.

- **termo:** Separation of concerns (separação de responsabilidades)
  **definição:** princípio de projetar o código em partes que cuidam
  cada uma de uma única responsabilidade, sem se misturar.
  **como apareceu no projeto:** `src/main.py` nunca calcula score — ele
  só coleta dados e chama `score_opportunity()`, que vive em
  `src/scoring.py`.

- **termo:** Application entry point (ponto de entrada da aplicação)
  **definição:** o arquivo/função por onde a execução do programa
  começa quando ele é executado diretamente.
  **como apareceu no projeto:** `src/main.py`, com o bloco
  `if __name__ == "__main__": main()`, executado via
  `python -m src.main`.

- **termo:** Presentation layer (camada de apresentação)
  **definição:** a parte do sistema responsável por interagir com o
  usuário (entrada e saída), mantida separada da lógica de negócio.
  **como apareceu no projeto:** todo o `src/main.py` é camada de
  apresentação; a lógica de negócio (scoring) permanece em
  `src/scoring.py` e `src/models.py`.

- **termo:** Dependency injection (injeção de dependência)
  **definição:** passar uma dependência (como uma função de entrada)
  como parâmetro, em vez de a função depender diretamente de uma
  implementação fixa — isso facilita testes.
  **como apareceu no projeto:** `ask(..., input_func=input)` permite
  substituir o `input()` real por uma função falsa nos testes.

### 7. Comandos/ferramentas usados

```bash
python -m src.main       # executar a CLI
python -m pytest -v      # rodar todos os testes via módulo
pytest -v                # rodar todos os testes direto
```

Ferramentas: Python 3.12, `pytest`, terminal/stdin para testar a CLI
manualmente.

### 8. Como explicar isso para um recrutador ou cliente

"Eu construí uma interface de linha de comando que coleta os dados de um
produto do usuário, valida cada entrada (rejeitando valores inválidos
sem travar o programa) e gera um relatório completo de oportunidade. O
mais importante tecnicamente é que a interface de usuário não contém
nenhuma lógica de negócio — ela só reaproveita o motor de scoring já
testado da fase anterior. Isso significa que, no futuro, posso trocar
essa CLI por uma API web ou um bot, sem precisar tocar na lógica de
cálculo, porque as duas camadas estão desacopladas. Também testei essa
camada de entrada sem depender de um terminal real, usando injeção de
dependência simples."

### 9. O que devo lembrar desta fase

- A camada que **conversa com o usuário** (CLI, e no futuro API ou
  interface web) nunca deve conter a lógica de cálculo — ela só coleta,
  valida e exibe. Isso é **separation of concerns** na prática.
- **Nunca deixar o programa quebrar** por causa de uma entrada inválida
  do usuário: sempre validar e pedir de novo, com uma mensagem clara.
- Para testar código que normalmente chamaria `input()`, a solução mais
  simples é **injetar a função de entrada como parâmetro**
  (`input_func=input`), em vez de usar bibliotecas de mock mais
  complexas — mais simples quase sempre é melhor.
- Separar "montar o texto do relatório" (`format_report`, que retorna
  uma `string`) de "imprimir o texto" (`print(...)` dentro de `main()`)
  é o que permite testar o conteúdo do relatório sem capturar a saída do
  terminal.
- Um **application entry point** bem definido (`main()` +
  `if __name__ == "__main__":`) deixa claro qual é o "botão de ligar" do
  programa, separando-o dos módulos que são apenas bibliotecas internas.
