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

---

## Fase 3 — Integração real com a API do Mercado Livre

> **Correção pós-publicação (verificação independente da documentação
> oficial):** a primeira versão desta seção afirmava que a busca livre
> por texto (`q`) em `/sites/MLB/search` era "o endpoint atualmente
> documentado para busca de itens por texto" e que a autenticação era
> "opcional segundo a documentação oficial". As duas afirmações estavam
> **incorretas** e foram corrigidas abaixo depois de reler a
> documentação oficial atual ("Itens e Buscas", atualizada pelo Mercado
> Livre em 31/08/2026). O endpoint `/sites/{SITE_ID}/search` documenta
> oficialmente apenas busca por `nickname` e `seller_id`, com
> `Authorization: Bearer ACCESS_TOKEN` em todos os exemplos. O parâmetro
> `q` pertence oficialmente a um endpoint diferente (`/products/search`,
> de catálogo/GTIN), não a este. Por isso, o uso de `q` neste projeto é
> classificado como **experimental / não documentado oficialmente**, não
> como um contrato garantido. O campo `available_quantity` também foi
> reclassificado: ele é um **valor de referência em faixas** (bucket), e
> não o estoque exato.

### 1. Nome da fase

**Fase 3: primeira integração externa real (REST API do Mercado Livre)
e camada de manutenção para dependências externas.**

### 2. Explicação simples

Até agora, nosso programa só sabia conversar com a pessoa que está
digitando no teclado. Nesta fase, ensinamos o programa a conversar com
**outro sistema, de outra empresa, do outro lado da internet**: o
Mercado Livre.

Pense numa API como um **garçom em um restaurante**. Você (nosso
programa) não entra na cozinha do Mercado Livre para pegar os dados
você mesmo — você chama o garçom, faz um pedido num formato que o
restaurante entende ("eu queria uma busca pelo termo 'bebedouro
automático para gatos', por favor"), e o garçom volta com um prato
pronto: uma lista de produtos, já organizada. Esse "pedido e resposta"
entre o nosso programa e o Mercado Livre é exatamente o que chamamos de
**request** (pedido) e **response** (resposta).

A resposta vem em um formato de texto chamado **JSON** — como um cardápio
escrito de um jeito bem organizado, com chaves e valores, fácil de um
programa ler. E junto com a resposta, o garçom também diz um "código":
"200" significa "aqui está, tudo certo"; "404" significa "não achei isso
no menu"; "403" significa "não posso te servir isso agora"; "500"
significa "a cozinha quebrou". Isso é o **status code**.

E se o garçom demorar demais para voltar, ou se o restaurante estiver
fechado, nosso programa não pode simplesmente travar e mostrar uma tela
de erro feia para quem está usando — ele precisa dizer, com calma,
"não consegui buscar agora, tente de novo depois". Isso é o que
chamamos de **tratamento de erros** (error handling).

Por fim, aprendemos uma lição importante: **o restaurante pode mudar o
cardápio sem nos avisar**. O Mercado Livre pode, em qualquer momento,
trocar como a busca funciona, exigir uma senha nova, ou simplesmente
bloquear esse tipo de pedido. Por isso criamos um checklist de
manutenção — para revisitar essa conversa com o Mercado Livre
periodicamente e perceber rápido se algo mudou do lado de fora, antes
que isso quebre nosso sistema sem avisar.

De fato, isso aconteceu bem na nossa cara durante esta fase: quando
testamos a busca de verdade (sem nenhuma senha/token configurado), o
Mercado Livre respondeu com "403 Forbidden" — ou seja, o "garçom" nos
recusou o pedido. Isso não significa que nosso código está errado:
pode significar que o restaurante exige uma "credencial" (token) que a
gente não apresentou (já que a documentação oficial mostra token em
todos os exemplos desse tipo de pedido), que ele está bloqueando esse
tipo de pedido vindo do nosso endereço de rede, ou os dois ao mesmo
tempo — ainda não sabemos qual, e documentamos isso honestamente em vez
de inventar uma causa só. De qualquer forma, o nosso programa tratou
isso certinho: não travou, só avisou com uma mensagem clara.

### 3. Explicação técnica

Implementamos a primeira **REST API integration** do projeto, isolada em
`src/integrations/mercadolivre.py` — a única camada do sistema com
permissão para conhecer **HTTP**, **JSON** ou a API do Mercado Livre
(**separation of concerns** / **integration layer**).

- **Endpoint** chamado: `GET https://api.mercadolibre.com/sites/MLB/search?q=...`.
  `MLB` é o `site_id` do Mercado Livre Brasil. **Importante (corrigido):**
  a documentação oficial atual ("Itens e Buscas", atualizada em
  31/08/2026) documenta `/sites/{SITE_ID}/search` **apenas** para busca
  por `nickname` ou `seller_id` — o parâmetro `q` usado aqui **não** faz
  parte desse contrato documentado. O `q` oficialmente documentado
  pertence ao endpoint separado `/products/search` (catálogo/GTIN), que
  este projeto não usa. Por isso classificamos esse uso de `q` como
  **experimental / não documentado oficialmente**, não como "o endpoint
  atual para busca por texto" (como uma versão anterior deste documento
  afirmava incorretamente).
- **HTTP** e **GET request**: usamos a biblioteca `requests` para enviar
  uma requisição `GET` com parâmetros de query (`q`, `limit`) e um
  **timeout** explícito (`DEFAULT_TIMEOUT = 10` segundos), para nunca
  deixar o programa esperando indefinidamente.
- **Status code**: verificamos explicitamente o código HTTP da
  **response**. `200` é tratado como sucesso; qualquer outro código
  (`403`, `404`, `429`, `500`, etc.) levanta uma exceção customizada
  (`MercadoLivreResponseError`) com o código e uma mensagem clara, em vez
  de deixar o programa continuar com dados inválidos.
- **JSON parsing**: a resposta é decodificada com `response.json()`
  dentro de um `try/except` — se vier um JSON malformado, levantamos
  `MercadoLivreDataError` em vez de deixar o `ValueError` do Python
  "estourar" sem contexto.
- **Error handling / custom exceptions**: criamos uma hierarquia própria
  de exceções (`MercadoLivreError` como base, e
  `MercadoLivreTimeoutError`, `MercadoLivreConnectionError`,
  `MercadoLivreResponseError`, `MercadoLivreDataError` como casos
  específicos), para que o resto do sistema (`src/main.py`) só precise
  capturar `MercadoLivreError` uma vez, sem conhecer detalhes de
  `requests` ou de HTTP.
- **Data mapping**: a resposta crua (`dict` vindo do `response.json()`,
  o que chamamos de **raw API response**) é convertida por `_map_item()`
  em um **data model** interno e tipado, `MercadoLivreItem`
  (`@dataclass`) — deliberadamente separado dos modelos de negócio da
  Fase 1 (`Product`, `ComponentScores`, `OpportunityResult`). Campos não
  presentes na resposta da API ficam como `None`, nunca são inventados
  (regra do `CLAUDE.md`: nunca fabricar dados).
- **Authentication (corrigido):** a versão anterior deste documento
  dizia que a documentação oficial descrevia esse endpoint como
  "utilizável sem token". Isso estava errado. A documentação oficial
  atual mostra `Authorization: Bearer ACCESS_TOKEN` em **todos** os
  exemplos de `/sites/{SITE_ID}/search` (para `nickname` e
  `seller_id`) — ou seja, a autenticação deve ser tratada como
  **esperada** para essa família de endpoint, mesmo que isso não esteja
  confirmado especificamente para o uso (não documentado) de `q` feito
  aqui. Na implementação, se a variável de ambiente
  `MERCADO_LIVRE_ACCESS_TOKEN` estiver definida, ela é enviada como
  cabeçalho `Authorization: Bearer <token>` (**bearer token**); se não
  estiver, a requisição segue sem esse cabeçalho (e é mais provável que
  falhe). O token nunca é escrito no código — apenas o nome da variável
  aparece em `.env.example` (**environment variable**).
- **API lifecycle / deprecation**: durante a pesquisa da documentação
  oficial e de relatos de outros desenvolvedores, descobrimos que esse
  mesmo endpoint vem apresentando bloqueios (`403`) para vários
  integradores desde 2024, mesmo com token válido — um sinal de que o
  Mercado Livre pode estar restringindo o acesso de terceiros à busca
  genérica. Isso é **API deprecation/lifecycle awareness**: APIs externas
  mudam de comportamento com o tempo, independente do nosso código.
- **Mock**: todos os testes usam um `requests.get` falso
  (`monkeypatch.setattr(mercadolivre.requests, "get", fake_get)`), para
  simular sucesso, timeout, falha de conexão, cada status code de erro,
  JSON inválido e resposta sem o campo `results` — sem nunca chamar a
  API de verdade durante os testes automatizados.
- **Dependency management**: adicionamos `requests>=2.31` ao
  `requirements.txt`, documentando por que ela é necessária (é o cliente
  HTTP real usado pela integração).
- **Maintenance**: criamos `docs/MAINTENANCE.md`, um checklist (não
  automatizado) para revisar periodicamente se o endpoint, a
  autenticação, os campos da resposta e as dependências ainda estão
  válidos.
- **`available_quantity` não é estoque exato (corrigido)**: a
  documentação oficial descreve esse campo como um **valor de
  referência em faixas** — um estoque real dentro de uma faixa é
  arredondado para o piso daquela faixa antes de ser publicado (ex.:
  estoque real entre 51 e 100 é devolvido como o valor de referência
  `50`). O modelo `MercadoLivreItem` e a exibição no CLI foram
  atualizados para deixar isso explícito, em vez de sugerir que é a
  quantidade exata em estoque.

### 4. Conexão entre o simples e o técnico

O "garçom entre nosso programa e o restaurante Mercado Livre" é,
tecnicamente, a **API** — mais especificamente, uma **REST API** que se
comunica via **HTTP**. O "pedido" que fazemos é o **GET request**
(`requests.get(...)`), e o "prato que volta" é a **response**, cujo
conteúdo vem em **JSON**. O "código que o garçom diz" (200, 403, 404,
500...) é o **status code**, verificado explicitamente no código. "O
garçom recusar o pedido" é exatamente o que vimos na prática: um `403`
tratado por `MercadoLivreResponseError`, sem travar o programa — isso é
**error handling**. "Traduzir o prato para o nosso jeito de organizar a
cozinha" é o **data mapping**: transformar o `dict` bruto da API
(**raw API response**) no nosso próprio modelo (`MercadoLivreItem`). E
"o restaurante pode mudar o cardápio sem avisar" é a razão de existir o
**MAINTENANCE.md**: **dependency management** e **API lifecycle
management** na prática, porque sistemas externos mudam de forma
independente do nosso projeto.

### 5. O que implementamos na prática

- `src/integrations/__init__.py` e `src/integrations/mercadolivre.py`:
  - `search_products(query, limit=10, timeout=10)` — função pública
    única, não expõe detalhes de HTTP para o resto do sistema.
  - `MercadoLivreItem` — `@dataclass` com os campos realmente
    disponíveis na resposta (`item_id`, `title`, `price`, `currency_id`,
    `seller_id`, `category_id`, `condition`, `permalink`,
    `free_shipping`, `available_quantity`).
  - `_map_item()` — mapeamento explícito do JSON bruto para
    `MercadoLivreItem`.
  - Hierarquia de exceções: `MercadoLivreError`,
    `MercadoLivreTimeoutError`, `MercadoLivreConnectionError`,
    `MercadoLivreResponseError` (com `status_code`),
    `MercadoLivreDataError`.
  - Suporte opcional a `MERCADO_LIVRE_ACCESS_TOKEN` via variável de
    ambiente.
- `src/main.py` atualizado com um menu principal:
  ```
  1. Manual Product Analyzer
  2. Search Mercado Livre
  ```
  mantendo 100% do comportamento da Fase 2 (`run_manual_analyzer`), e
  adicionando `run_mercado_livre_search()` e `format_search_results()`
  para a nova opção.
- `tests/test_mercadolivre_integration.py` — 14 testes novos cobrindo
  sucesso, campos ausentes, resultado vazio, timeout, falha de conexão,
  cada status code de erro, JSON malformado, campo `results` ausente, e
  validação de `query`/`limit`.
- `tests/test_main.py` ampliado com testes para o novo menu e para a
  exibição dos resultados de busca.
- `requirements.txt` — adicionado `requests>=2.31`.
- `.env.example` — adicionada a variável `MERCADO_LIVRE_ACCESS_TOKEN`
  (sem valor).
- `README.md` — nova seção "Phase 3 scope" com endpoint, autenticação,
  comando de execução e a limitação encontrada na validação manual.
- `docs/MAINTENANCE.md` — novo checklist de manutenção semanal.

### 6. Termos técnicos aprendidos

- **termo:** API (Application Programming Interface)
  **definição:** um conjunto de regras que permite que um programa peça
  dados ou ações a outro sistema, sem precisar saber como esse sistema
  funciona por dentro.
  **como apareceu no projeto:** a API pública do Mercado Livre, acessada
  em `api.mercadolibre.com`.

- **termo:** REST API
  **definição:** um estilo de API que usa URLs para representar recursos
  (ex.: "um item de busca") e verbos HTTP (GET, POST...) para agir sobre
  eles.
  **como apareceu no projeto:** `GET /sites/MLB/search?q=...` é um
  recurso REST: "busca no site MLB".

- **termo:** HTTP
  **definição:** o protocolo (conjunto de regras de comunicação) usado
  pela internet para pedir e receber recursos, incluindo páginas web e
  respostas de API.
  **como apareceu no projeto:** toda a comunicação com o Mercado Livre
  acontece sobre HTTP, via `requests.get(...)`.

- **termo:** GET request
  **definição:** um tipo de requisição HTTP usada para *pedir* dados sem
  alterá-los no servidor.
  **como apareceu no projeto:** `search_products()` faz um `GET` para
  buscar itens, sem criar nem modificar nada no Mercado Livre.

- **termo:** Endpoint
  **definição:** o caminho específico de uma API que representa um
  recurso ou uma ação (ex.: "/sites/MLB/search").
  **como apareceu no projeto:** `BASE_URL + "/sites/MLB/search"`.

- **termo:** Request / Response
  **definição:** a dupla pedido (o que enviamos) e resposta (o que
  recebemos de volta) que forma toda comunicação HTTP.
  **como apareceu no projeto:** `requests.get(...)` envia o request;
  o objeto retornado é a response, de onde lemos `.status_code` e
  `.json()`.

- **termo:** Status code
  **definição:** um número de três dígitos que resume o resultado de uma
  requisição HTTP (ex.: 200 = sucesso, 403 = proibido, 404 = não
  encontrado, 500 = erro no servidor).
  **como apareceu no projeto:** verificado explicitamente em
  `search_products()`; um `403` real foi observado na validação manual
  desta fase.

- **termo:** JSON (JavaScript Object Notation)
  **definição:** um formato de texto estruturado, baseado em chave e
  valor, usado para trocar dados entre sistemas diferentes.
  **como apareceu no projeto:** a resposta da API do Mercado Livre e sua
  leitura via `response.json()`.

- **termo:** Timeout
  **definição:** um limite de tempo máximo que esperamos por uma resposta
  antes de desistir e tratar como falha.
  **como apareceu no projeto:** `timeout=10` passado para
  `requests.get()`; estourar esse limite levanta
  `MercadoLivreTimeoutError`.

- **termo:** Error handling (tratamento de erros)
  **definição:** capturar e responder a falhas de forma controlada, em
  vez de deixar o programa travar com uma exceção não tratada.
  **como apareceu no projeto:** cada tipo de falha (timeout, conexão,
  status code de erro, JSON inválido) é capturado e transformado em uma
  exceção customizada com mensagem clara.

- **termo:** Data mapping (mapeamento de dados)
  **definição:** transformar dados de um formato/estrutura (geralmente
  externo) para outro formato controlado pela nossa aplicação.
  **como apareceu no projeto:** `_map_item()` transforma o `dict` bruto
  da API em `MercadoLivreItem`.

- **termo:** Integration layer (camada de integração)
  **definição:** um módulo dedicado que isola todo o conhecimento sobre
  um sistema externo, para que o resto da aplicação não precise saber
  como esse sistema funciona.
  **como apareceu no projeto:** `src/integrations/mercadolivre.py` é a
  única parte do projeto que importa `requests` ou conhece a forma do
  JSON do Mercado Livre.

- **termo:** External dependency (dependência externa)
  **definição:** qualquer biblioteca ou serviço de fora do nosso próprio
  código do qual o projeto depende para funcionar.
  **como apareceu no projeto:** a biblioteca `requests` e a própria API
  do Mercado Livre.

- **termo:** Mock
  **definição:** uma versão falsa e controlada de uma dependência (como
  uma chamada de rede), usada em testes para simular comportamentos sem
  depender do sistema real.
  **como apareceu no projeto:** `monkeypatch.setattr(mercadolivre.requests, "get", fake_get)`
  substitui a chamada HTTP real por uma função que devolve respostas
  programadas em cada teste.

- **termo:** Environment variable (variável de ambiente)
  **definição:** um valor configurado fora do código-fonte (no sistema
  operacional ou em um arquivo `.env`), usado para configuração e
  segredos.
  **como apareceu no projeto:** `MERCADO_LIVRE_ACCESS_TOKEN`, lida com
  `os.environ.get(...)`, nunca escrita diretamente no código.

- **termo:** Authentication (autenticação)
  **definição:** o processo de provar, para um sistema, quem está
  fazendo a requisição — geralmente por meio de uma credencial.
  **como apareceu no projeto:** a documentação oficial atual mostra
  token em todos os exemplos de `/sites/{SITE_ID}/search`, então
  tratamos a autenticação como **esperada** para esse endpoint (não como
  "opcional segundo a documentação", correção em relação à versão
  anterior deste texto); no código, o cabeçalho é enviado apenas se um
  token estiver configurado, mas a chamada continua sem travar mesmo sem
  um.

- **termo:** Bearer token
  **definição:** um tipo de credencial enviada no cabeçalho HTTP
  `Authorization: Bearer <token>`, usada para provar que a requisição
  está autorizada.
  **como apareceu no projeto:** enviado apenas se
  `MERCADO_LIVRE_ACCESS_TOKEN` estiver definida no ambiente.

- **termo:** Reference quantity / bucketed data (dado em faixas)
  **definição:** quando uma API publica um valor aproximado dentro de
  uma faixa, em vez do valor exato, geralmente por motivos de
  privacidade competitiva ou de negócio.
  **como apareceu no projeto:** o campo `available_quantity` do Mercado
  Livre não é o estoque exato — um estoque real de 51-100 unidades é
  devolvido como o valor de referência `50`. Isso foi descoberto durante
  a verificação da documentação oficial e corrigido na modelagem
  (`MercadoLivreItem`) e na exibição do CLI.

- **termo:** API deprecation (descontinuação de API)
  **definição:** quando um endpoint ou recurso de uma API para de
  funcionar ou tem seu acesso restringido, geralmente após um aviso
  (nem sempre).
  **como apareceu no projeto:** relatos de terceiros sobre restrições
  crescentes nesse mesmo endpoint desde 2024, e o `403` observado durante
  a validação manual desta fase.

- **termo:** Dependency management (gestão de dependências)
  **definição:** acompanhar, documentar e manter atualizadas as
  bibliotecas externas que o projeto usa.
  **como apareceu no projeto:** `requirements.txt` atualizado com
  `requests>=2.31`, e o checklist de `docs/MAINTENANCE.md` que inclui
  verificar essa dependência periodicamente.

- **termo:** API lifecycle management / maintenance (gestão de ciclo de
  vida de API / manutenção)
  **definição:** o processo contínuo de monitorar se uma integração
  externa continua funcionando como esperado, já que o sistema do outro
  lado pode mudar sem aviso.
  **como apareceu no projeto:** `docs/MAINTENANCE.md`, com um checklist
  semanal e uma cadência recomendada.

### 7. Comandos/ferramentas usados

```bash
python -m src.main                 # executar a CLI (opção 2 = busca)
python -m pytest -v                # rodar todos os testes via módulo
pytest -v                          # rodar todos os testes direto
pip install -r requirements.txt    # instalar requests + pytest
```

Ferramentas: Python 3.12, `requests`, `pytest`, `monkeypatch` (fixture do
`pytest` usada para simular HTTP), pesquisa na documentação oficial do
Mercado Livre.

### 8. Como explicar isso para um recrutador ou cliente

"Eu construí a primeira integração real com uma API externa (Mercado
Livre) de forma isolada: toda a lógica de HTTP, JSON e tratamento de
erros vive em um único módulo, então o resto do sistema nunca depende de
detalhes de implementação de rede. Tratei explicitamente todos os
cenários de falha esperados — timeout, erro de conexão, respostas de erro
HTTP, JSON inválido — para que uma instabilidade externa nunca derrube a
aplicação, apenas gere uma mensagem clara. Testei essa integração
inteiramente com mocks, sem depender da API real estar no ar durante os
testes automatizados. E, como parte do processo de engenharia, documentei
um checklist de manutenção recorrente, porque uma integração com um
sistema de terceiros não é 'escrever uma vez e esquecer' — ela precisa
ser revisitada, e eu já identifiquei, na validação manual desta fase, que
esse endpoint específico está retornando 403 a partir do ambiente onde
testei, o que já está documentado como um item a investigar."

### 9. O que devo lembrar desta fase

- Uma integração externa deve morar em **um único módulo isolado**
  (`src/integrations/mercadolivre.py`) — nenhum outro arquivo do projeto
  deve importar `requests` ou conhecer o formato do JSON da API.
- **Toda chamada de rede pode falhar de várias formas diferentes**
  (timeout, conexão, status code, JSON malformado) — cada uma merece um
  tratamento específico e uma mensagem clara, nunca um traceback cru para
  quem está usando o programa.
- **Nunca fabricar dados**: se um campo não vier na resposta da API, ele
  fica como `None` no nosso modelo — não inventamos um valor plausível.
- **Testar integrações externas com mocks**, nunca com chamadas reais nos
  testes automatizados — isso mantém os testes rápidos, determinísticos e
  independentes da disponibilidade do serviço externo.
- **Sistemas externos mudam sem avisar.** Documentar isso em um
  checklist de manutenção (`docs/MAINTENANCE.md`) não é burocracia — é o
  que evita ser pego de surpresa quando o Mercado Livre mudar algo, e já
  se mostrou necessário nesta própria fase, com o `403` observado na
  validação manual.
- Antes de confiar ou documentar o comportamento de uma API, **verificar
  a documentação oficial atual**, em vez de assumir como ela funciona —
  e, quando a documentação e o comportamento real divergem (como
  aconteceu aqui), documentar os dois lados honestamente, em vez de
  fingir que um deles não existe.

---

## Fase 4 — Dados de tendência (Apify + Google Trends) e análise determinística

### 1. Nome da fase

**Fase 4: primeira fonte de dados de tendência (Apify Actor sobre
Google Trends) e camada de análise de tendência determinística, com um
Trend Score provisório.**

### 2. Explicação simples

Imagine que você quer saber se um produto "está em alta" ou "está
morrendo" nas buscas das pessoas. O Google Trends guarda esse tipo de
informação, mas não existe uma porta oficial e aberta para qualquer um
pegar esses dados sem complicação (a porta oficial do Google ainda só
deixa entrar um grupo pequeno e convidado de desenvolvedores).

Para resolver isso, usamos a **Apify** — pense na Apify como uma
**empresa de entregas**. Nós fazemos um pedido para a Apify ("quero
saber o interesse de busca pelo termo 'bebedouro para gatos' no
Brasil, no último ano"). A Apify manda um "entregador" especializado —
chamado de **Actor**, no caso o `themineworks/google-trends-pro` — para
ir buscar essa informação no Google Trends. O Actor volta com um
**pacote de dados organizados** (um monte de números e textos). A nossa
"camada de integração" (`src/integrations/apify_trends.py`) é quem abre
esse pacote, confere se está tudo certo, e traduz para o formato interno
que o resto do nosso sistema entende. Só depois disso, uma segunda parte
do sistema — a "calculadora de tendência"
(`src/trend_analysis.py`) — pega esses números já traduzidos e calcula,
de forma sempre igual para a mesma entrada (**determinística**): a
média de interesse, se está subindo ou caindo, o quanto está subindo ou
caindo, e o quão instável é essa curva.

Um detalhe importante: o número que o Google Trends dá (de 0 a 100) não
é "quantidade de pessoas que buscaram" — é como um **termômetro
relativo**: 100 significa "o pico de interesse daquele próprio termo",
não "cem buscas" nem "o termo mais buscado do mundo". Comparar o número
100 de um produto com o número 100 de outro produto diferente não
significa que os dois têm a mesma demanda real.

Também aconteceu algo real e interessante nesta fase: ao testar de
verdade, a Apify respondeu com o código HTTP **201** em vez do 200 que a
gente esperava — e nosso primeiro código tratou isso como um erro! Foi
só testando com dados reais que a gente descobriu e corrigiu esse
detalhe. Isso mostra por que validar com a API de verdade é tão
importante, mesmo depois de escrever todos os testes com dados falsos.

### 3. Explicação técnica

Implementamos a primeira fonte de **time series** de interesse de busca
do projeto, através de uma **integration layer** isolada
(`src/integrations/apify_trends.py`) que fala com uma **SaaS API**
de terceiros (a Apify), nunca expondo HTTP, tokens ou JSON cru para o
resto do sistema.

- **Third-party API / SaaS API**: a Apify é uma plataforma paga (SaaS)
  que executa "Actors" sob demanda e devolve os resultados via uma API
  REST oficial e documentada. Nós chamamos
  `POST https://api.apify.com/v2/actors/themineworks~google-trends-pro/run-sync-get-dataset-items`
  usando `requests` puro — sem SDK.
- **Actor**: uma unidade de automação hospedada na infraestrutura da
  Apify, escrita por terceiros (`themineworks`), que por dentro faz o
  trabalho de raspar o Google Trends. A Apify-plataforma é oficial e
  estável; o Actor específico é não-oficial e tem risco de manutenção
  próprio (documentado em `docs/MAINTENANCE.md`, incluindo um período de
  confiabilidade degradada registrado desde 2026-07-30 por limitação de
  taxa do lado do Google).
- **API token**: a autenticação usa `Authorization: Bearer
  <APIFY_API_TOKEN>` — nunca em query string, nunca hardcoded. O token é
  carregado de `.env` via `python-dotenv` (`src/config.py`, já criado na
  etapa anterior) e nunca é impresso ou logado.
- **Integration layer / data mapping / schema**: a resposta crua da
  Apify é uma lista de "linhas" (dataset items), algumas sendo o
  relatório real (`keyword`, `interest_over_time`, `interest_by_region`,
  `related_queries`...) e outras sendo linhas especiais
  (`_type: "error"`, `"summary"`, `"info"`) que precisam ser
  identificadas e ignoradas (ou tratadas como erro, no caso de
  `"error"`) antes de qualquer mapeamento. Só as linhas de relatório
  real são convertidas, por `_map_report_row()`, para o nosso **schema**
  interno e neutro (`src/trend_models.py`: `TrendData`, `TrendPoint`,
  `TrendRegion`, `RelatedQuery`) — este schema não sabe nada sobre
  Apify, só sobre "o que é um dado de tendência" de forma genérica.
- **Relative index / normalization**: os valores de `interest_over_time`
  (0-100) são um índice relativo, normalizado pelo próprio Google em
  relação ao pico de interesse daquele termo específico — não é volume
  absoluto de busca, e não é comparável entre termos diferentes sem
  cuidado. Documentamos isso extensivamente nos docstrings e no README
  para que ninguém confunda "100" com "o produto mais buscado do
  Brasil".
- **Moving/recent average**: `src/trend_analysis.py` divide a série em
  duas metades (período anterior e período recente) e calcula a média
  de cada uma -- uma forma simples e determinística de comparar "como
  estava" com "como está agora", sem precisar de bibliotecas de séries
  temporais mais pesadas.
- **Percentage change**: `(recent_average - previous_average) /
  previous_average * 100` -- a variação percentual entre as duas
  médias, usada tanto para classificar a direção (`growing` / `stable`
  / `declining`, com limiares de +-10% documentados e fáceis de mudar)
  quanto como um dos ingredientes do Trend Score.
- **Volatility**: o desvio padrão (`statistics.pstdev`) dos valores da
  série -- um número alto significa uma curva "nervosa", que sobe e
  desce muito, o que reduz nossa confiança no sinal e é usado como uma
  penalidade no Trend Score.
- **Deterministic analysis**: dado o mesmo `TrendData`, `analyze_trend()`
  sempre devolve exatamente o mesmo resultado -- sem aleatoriedade, sem
  chamada a LLM, sem depender da hora do relógio. Isso é o que torna
  essa camada 100% testável com dados fixos.
- **Provisional scoring model / calibration**: criamos um Trend Score de
  0 a 100, combinando crescimento, nível de interesse recente, uma
  direção sustentada e uma penalidade de volatilidade -- mas ele é
  explicitamente rotulado **PROVISIONAL** em todo lugar que aparece,
  porque ainda não foi validado contra vendas reais. Os pesos e escalas
  da fórmula são constantes isoladas no topo do módulo, pensadas para
  serem recalibradas (**calibration**) depois, sem reescrever a lógica.
- **Vendor dependency / rate limiting**: dependemos de um fornecedor
  (Apify) e, por trás dele, de um Actor não-oficial sujeito à limitação
  de taxa do Google (**rate limiting**) -- por isso a arquitetura
  mantém `trend_analysis.py` completamente alheio a quem fornece os
  dados, permitindo troca de fornecedor sem reescrever a análise.

### 4. Conexão entre o simples e o técnico

A "empresa de entregas" é a **SaaS API** da Apify; o "entregador
especializado" é o **Actor**; o "pedido que fazemos" é a chamada HTTP
autenticada com o **API token**; o "pacote de dados organizados" é a
resposta crua da Apify, que nossa **integration layer** abre e traduz
(**data mapping**) para o nosso próprio **schema** interno. O
"termômetro relativo" de 0 a 100 é o **relative index**
(**normalization** feita pelo próprio Google). A "calculadora de
tendência" que sempre dá a mesma resposta para a mesma entrada é a
**deterministic analysis**; "subiu ou caiu, e quanto" é a
**moving/recent average** e o **percentage change**; "quão nervosa é a
curva" é a **volatility**. E o fato de termos descoberto, testando de
verdade, que a Apify responde com `201` em vez de `200` é exatamente por
que validação com dados reais (não só mocks) continua sendo parte do
processo de engenharia, mesmo com testes automatizados passando 100%.

### 5. O que implementamos na prática

- `src/trend_models.py` — modelos internos neutros: `TrendPoint`,
  `TrendRegion`, `RelatedQuery`, `TrendData`. Não sabem nada sobre
  Apify.
- `src/integrations/apify_trends.py` — `fetch_trend_data(query, geo="BR",
  timeframe="today 12-m")`, hierarquia de exceções
  (`ApifyTrendsConfigurationError`, `ApifyTrendsTimeoutError`,
  `ApifyTrendsConnectionError`, `ApifyTrendsResponseError`,
  `ApifyTrendsDataError`, `ApifyTrendsActorError`), filtragem de linhas
  especiais (`_type` em `error`/`summary`/`info`), e a correção do `2xx`
  (não só `200`) descoberta na validação em tempo real.
- `src/trend_analysis.py` — `analyze_interest_series()` /
  `analyze_trend()`, `TrendMetrics`, limiares de direção, e a fórmula do
  Trend Score provisório, tudo documentado no docstring do módulo.
- `src/main.py` — nova opção `3. Analyze Trend` no menu, perguntando
  termo de busca, geo (padrão `BR`) e timeframe (padrão `today 12-m`),
  exibindo o relatório completo e o aviso sobre valores relativos.
- `tests/test_trend_analysis.py` — 10 testes determinísticos (série
  fortemente crescente, levemente crescente, estável, em queda, volátil,
  curta, vazia, com zeros, com valores ausentes, delegação
  `analyze_trend`).
- `tests/test_apify_trends_integration.py` — 17 testes com
  `requests.post` e o token totalmente mockados (sucesso, sucesso com
  `201`, linha de erro do Actor, apenas linhas de resumo/info, token
  ausente, timeout, erro de conexão, cada status HTTP de erro, JSON
  malformado, dataset vazio, schema inesperado, query vazia).
- Validação real feita com o token de verdade: `bebedouro automatico
  gatos` (quase sem sinal, 1 ponto não-zero em 53) e `bebedouro para
  gatos` (dados ricos: 53 pontos, 12 buscas relacionadas "top", 2
  "rising", 27 regiões) -- custo confirmado de $0.0025 por consulta.
- `docs/MAINTENANCE.md` e `README.md` atualizados com o status real
  desta integração, incluindo o risco documentado de confiabilidade
  degradada do Actor desde 2026-07-30.

### 6. Termos técnicos aprendidos

- **termo:** Third-party API / SaaS API
  **definição:** uma API fornecida por uma empresa externa, geralmente
  como um serviço pago (Software as a Service), que executa trabalho
  por nós em troca de uma chamada autenticada.
  **como apareceu no projeto:** a Apify, chamada via sua API REST
  oficial para executar o Actor de Google Trends.

- **termo:** Actor (Apify)
  **definição:** uma unidade de automação hospedada na Apify, escrita
  por um desenvolvedor (que pode ser a própria Apify ou um terceiro),
  que executa uma tarefa específica (aqui, raspar o Google Trends) e
  devolve um dataset.
  **como apareceu no projeto:** `themineworks/google-trends-pro` —
  identificado na URL da API como `themineworks~google-trends-pro`.

- **termo:** API token
  **definição:** uma credencial que identifica e autoriza quem está
  fazendo uma chamada a uma API, geralmente enviada em um cabeçalho
  HTTP.
  **como apareceu no projeto:** `APIFY_API_TOKEN`, carregado de `.env`
  via `python-dotenv`, enviado como `Authorization: Bearer <token>`,
  nunca impresso, logado ou commitado.

- **termo:** Integration layer
  **definição:** um módulo dedicado que isola todo o conhecimento sobre
  um sistema externo específico, traduzindo sua resposta para um
  formato interno antes de qualquer outra parte do sistema tocar nela.
  **como apareceu no projeto:** `src/integrations/apify_trends.py` é o
  único arquivo que conhece a Apify, o Actor, e o JSON cru que ele
  devolve.

- **termo:** Data mapping / Schema
  **definição:** a transformação de uma estrutura de dados externa
  (schema de origem) para uma estrutura de dados própria (schema
  interno), extraindo apenas os campos que realmente existem.
  **como apareceu no projeto:** `_map_report_row()` converte o JSON cru
  da Apify em `TrendData`; linhas com `_type` especial (`error`,
  `summary`, `info`) são identificadas pelo schema e tratadas à parte
  (nunca mapeadas como se fossem um relatório real).

- **termo:** Time series (série temporal)
  **definição:** uma sequência de valores associados a pontos no tempo,
  geralmente ordenada cronologicamente.
  **como apareceu no projeto:** `interest_over_time`, a lista de
  `TrendPoint` (data + valor) que alimenta toda a análise de tendência.

- **termo:** Relative index / Normalization
  **definição:** um valor reescalado em relação a um ponto de
  referência (aqui, o pico de interesse do próprio termo) em vez de ser
  uma contagem absoluta.
  **como apareceu no projeto:** os valores de 0 a 100 do Google Trends —
  documentados exaustivamente como "não é volume absoluto de busca".

- **termo:** Moving/recent average (média móvel/recente)
  **definição:** a média de um subconjunto mais recente de uma série,
  usada para comparar "agora" com "antes" sem precisar de toda a
  história.
  **como apareceu no projeto:** `recent_average` e `previous_average`,
  calculados dividindo a série em duas metades.

- **termo:** Percentage change (variação percentual)
  **definição:** a diferença relativa entre dois valores, expressa como
  porcentagem do valor de referência.
  **como apareceu no projeto:** `percentage_change =
  (recent_average - previous_average) / previous_average * 100`, usado
  para classificar a direção da tendência.

- **termo:** Volatility (volatilidade)
  **definição:** uma medida de quão dispersos/instáveis são os valores
  de uma série, geralmente o desvio padrão.
  **como apareceu no projeto:** `statistics.pstdev(values)`, usado como
  penalidade no Trend Score provisório para séries "nervosas".

- **termo:** Deterministic analysis (análise determinística)
  **definição:** um cálculo cujo resultado depende apenas dos dados de
  entrada, sempre o mesmo para a mesma entrada -- sem aleatoriedade, sem
  IA generativa, sem depender do relógio.
  **como apareceu no projeto:** `src/trend_analysis.py` inteiro, testado
  com 10 casos fixos que sempre produzem o mesmo resultado.

- **termo:** Provisional scoring model / Calibration
  **definição:** um modelo de pontuação documentado e ajustável, mas
  explicitamente rotulado como "ainda não validado", com parâmetros
  isolados para facilitar a recalibração futura (ajuste de pesos usando
  dados reais).
  **como apareceu no projeto:** o Trend Score de 0-100, rotulado
  "PROVISIONAL" em todo lugar que aparece, com pesos/escalas como
  constantes de módulo fáceis de mudar depois.

- **termo:** Vendor dependency (dependência de fornecedor)
  **definição:** depender de uma empresa/serviço externo para uma
  funcionalidade, aceitando o risco de que esse fornecedor mude ou
  descontinue o serviço.
  **como apareceu no projeto:** a dependência da Apify e, por trás
  dela, de um Actor de terceiros não-oficial — mitigada mantendo
  `trend_analysis.py` sem nenhum conhecimento de quem fornece os dados.

- **termo:** Rate limiting (limitação de taxa)
  **definição:** uma restrição imposta por um serviço sobre quantas
  chamadas podem ser feitas em um período de tempo, geralmente para
  proteger a infraestrutura ou cumprir políticas de uso.
  **como apareceu no projeto:** o Actor da Apify sofre limitação de taxa
  do lado do Google, com confiabilidade degradada documentada desde
  2026-07-30.

### 7. Comandos/ferramentas usados

```bash
python -m src.main          # executar a CLI (opção 3 = Analyze Trend)
python -m pytest -v         # rodar todos os testes via módulo
pytest -v                   # rodar todos os testes direto
```

Ferramentas: Python 3.12, `requests`, `python-dotenv`, `pytest`,
`monkeypatch`, conta Apify + token real para a validação em tempo real,
pesquisa de documentação oficial (Apify, Google Trends, Wikipedia
Pageviews) para a avaliação de fontes.

### 8. Como explicar isso para um recrutador ou cliente

"Eu avaliei formalmente três fontes de dados de tendência antes de
escrever qualquer código -- API oficial do Google (inacessível, ainda
em alpha fechado), uma biblioteca não-oficial popular (que eu
efetivamente testei e descobri que nem roda neste ambiente, por causa de
uma política de segurança do Windows bloqueando uma dependência nativa)
e a Wikipedia (oficial, mas não serve para produtos de ecommerce
específicos) -- e escolhi a Apify como a opção comprovadamente
executável, de baixo custo e com dados realmente relevantes. Construí a
integração isolada da lógica de análise, então a fonte de dados pode
trocar no futuro sem reescrever a matemática. Testei toda a lógica com
mocks, e também validei com uma chamada real, onde descobri e corrigi um
detalhe real da API (código HTTP 201 em vez de 200) que nenhum mock
teria revelado. O resultado final é um Trend Score explicável e
provisório, claramente rotulado como não validado, pronto para ser
recalibrado quando tivermos dados de vendas reais."

### 9. O que devo lembrar desta fase

- **Avaliar fontes de dados antes de escrever código** evitou que eu
  construísse uma integração em torno de uma biblioteca
  (`pytrends`) que nem roda no ambiente real do projeto -- descobri isso
  testando de verdade, não assumindo.
- **Separar a fonte de dados da lógica de análise** (`trend_models.py` +
  `trend_analysis.py` sem nenhum import de Apify) é o que permite trocar
  de fornecedor no futuro sem tocar na matemática.
- **Valores de 0-100 do Google Trends são relativos, não absolutos** --
  documentar isso de forma proeminente evita que alguém confunda "100"
  com "demanda real alta".
- **Testar com mocks não substitui validar com a API real**: só a
  chamada real revelou que a Apify devolve `201`, não `200`, em caso de
  sucesso -- um detalhe que nenhum teste com dados falsos teria pego.
- **Um score provisório precisa ser rotulado como provisório em todo
  lugar que aparece** (CLI, README, docstring) -- isso evita que alguém
  (inclusive eu mesmo, no futuro) trate um número ainda não validado
  como se fosse definitivo.
- **Documentar o risco de fornecedor explicitamente** (Actor não-oficial,
  confiabilidade degradada desde 2026-07-30) é o que torna esse risco
  gerenciável -- ele fica visível e revisável, em vez de escondido
  dentro do código.

### Adendo — Bug real em produção após o commit da Fase 4

Depois de a Fase 4 já estar commitada, uma execução real da CLI com
`bebedouro para gatos` devolveu buscas relacionadas, buscas em alta e
interesse regional normalmente, mas `interest_over_time` foi mapeado
para **zero observações**, sem nenhum erro aparecer. Isso contradizia a
validação anterior, que tinha visto 53 pontos para o mesmo tipo de
consulta.

**O que é "schema drift" (desvio de schema):** é quando uma API ou um
serviço externo muda, com o tempo, o formato dos dados que devolve --
um campo que renomeia, um valor que passa a vir embrulhado de um jeito
diferente -- sem necessariamente avisar ou documentar a mudança. É
diferente de um "bug" no sentido tradicional: o fornecedor não quebrou
nada do lado dele (ou pode nem ter mudado nada), mas o **formato**
mudou (ou varia) de um jeito que nosso código não esperava.

**O que eu descobri ao investigar:** tentei reproduzir o problema com
chamadas reais, novas, para a mesma consulta -- quatro vezes seguidas.
Em todas as quatro, a Apify devolveu o formato esperado (`date`,
`value`, `formatted_value`) com dados reais e corretos. Ou seja, **não
consegui reproduzir um formato permanentemente diferente**. A conclusão
mais honesta, baseada em evidência (e não em suposição), é
**inconsistência do Actor** (`actor inconsistency`): como o
Actor já tem um risco documentado de confiabilidade degradada desde
2026-07-30 por limitação de taxa do Google, é plausível que, numa
chamada específica, só a parte de `interest_over_time` tenha falhado
silenciosamente (talvez um valor em um formato que meu código não
soubesse interpretar), enquanto as outras partes (`related_queries`,
`interest_by_region`) funcionaram. Até reproduzi essa "inconsistência
entre seções" de novo durante a correção: numa chamada, `interest_over_time`
veio completo e `related_queries` veio vazio -- o mesmo Actor, a mesma
consulta, resultado diferente.

**Por que mocks não substituem testes de integração ao vivo:** todos os
nossos testes com `requests.post` mockado continuavam passando 100%
durante esse incidente -- porque um mock só testa "o código reage
corretamente ao formato que EU disse que ele receberia". Ele nunca pode
nos avisar que o fornecedor começou a mandar um formato diferente (ou
inconsistente) na vida real. É exatamente por isso que o
`CLAUDE.md` e esta prática de engenharia pedem validação manual com a
API de verdade em cada fase -- os mocks garantem que a lógica interna
está certa; só uma chamada real garante que a suposição sobre o formato
externo continua válida.

**A correção aplicada (hotfix):** mesmo sem conseguir reproduzir o
formato quebrado, fiz duas mudanças defensivas em
`src/integrations/apify_trends.py`:
1. `_coerce_interest_value()` passou a aceitar um formato real e
   documentado do Google Trends em que o valor de um ponto vem como uma
   lista de um elemento (`[36]`) em vez de um número simples (`36`) --
   isso acontece quando o Google compara múltiplos termos ao mesmo
   tempo, e o Actor pode nem sempre "desembrulhar" isso para nós.
2. Mais importante: `_map_report_row()` agora **levanta um erro claro**
   (`ApifyTrendsDataError`) se `interest_over_time` chegar com pontos,
   mas **nenhum** deles tiver um valor que conseguimos interpretar como
   número -- em vez de silenciosamente devolver "zero observações" sem
   avisar nada. O bug real não era "não ter dados" (que já tratávamos
   bem) -- era "ter dados, mas falhar ao interpretar, e ninguém ficar
   sabendo disso".

**Teste de regressão (`regression test`):** adicionamos dois testes em
`tests/test_apify_trends_integration.py` usando um formato reduzido e
sanitizado (só os campos necessários para o mapeamento, sem nenhum dado
sensível): um simula o valor-em-lista (`[36]`) e confirma que agora é
interpretado corretamente; o outro simula pontos presentes mas
impossíveis de interpretar, e confirma que agora isso levanta
`ApifyTrendsDataError` em vez de devolver silenciosamente zero
observações. Um teste de regressão existe exatamente para isso: "se
esse bug específico voltar a acontecer, um teste automatizado vai
quebrar e avisar, em vez de passar escondido".

**Bug de produção / hotfix:** esse incidente é um exemplo real de
**production bug** (um problema descoberto depois do código já estar
em uso/commitado, não durante o desenvolvimento) e de **hotfix** (uma
correção direcionada, aplicada rapidamente, focada em resolver o
sintoma relatado com segurança -- sem reescrever a arquitetura). A
camada de integração continua isolada (`trend_analysis.py` não mudou
nada), o que confirma, na prática, por que separar a fonte de dados da
lógica de análise valeu a pena: a correção ficou inteiramente contida
em um único arquivo.

---

## Fase 5 — Análise de Demanda determinística (Demand Score provisório)

### 1. Nome da fase

**Fase 5: camada de Demand Analysis determinística, transformando
sinais reais de mercado em um Demand Score explicável e provisório --
ainda sem agente de IA.**

### 2. Explicação simples

Imagine um **detetive** investigando se um produto está realmente em
alta demanda. O detetive não tem uma câmera que filma todo mundo
comprando o produto (isso seria "saber a demanda exata") -- ele só tem
**pistas**: "o número de buscas por esse termo está subindo", "tem
gente buscando termos parecidos", "o interesse aparece em várias
regiões do Brasil, não só numa cidade".

Uma pista sozinha é fraca. Se só uma pista aponta numa direção, o
detetive fica com uma suspeita, não uma certeza. Mas se **várias pistas
independentes** apontam para o mesmo lugar -- buscas subindo, muitas
buscas parecidas, interesse espalhado pelo país -- a conclusão fica bem
mais forte.

Por isso, nesta fase, criamos **dois números**, não um só:

- O **Demand Score**: "qual é a conclusão do detetive?" (quão forte
  parece a demanda, de 0 a 100).
- O **Confidence Score**: "quantas pistas de verdade o detetive tinha
  na mão para chegar a essa conclusão?" (de 0 a 100).

Um produto pode ter Demand Score 80 com Confidence 35 (uma pista forte,
mas só uma) -- isso é bem diferente de Demand Score 80 com Confidence 90
(várias pistas fortes e independentes apontando pro mesmo lugar). Tratar
os dois casos como "a mesma coisa" seria enganoso -- e é exatamente por
isso que nunca misturamos esses dois números em um só.

Hoje, só temos uma "fonte de pistas" funcionando de verdade (o Google
Trends, via Apify) -- a outra fonte possível (Mercado Livre) está
bloqueada, como já vimos na Fase 3. Isso significa que, por mais forte
que o sinal do Google Trends pareça, o Confidence Score nunca pode ser
muito alto agora -- faltam pistas independentes para confirmar. Isso
não é um defeito do nosso código: é a verdade honesta sobre quanta
evidência realmente temos.

### 3. Explicação técnica

Implementamos a primeira camada de **demand proxy** determinística do
projeto, separada em duas responsabilidades:

- `src/demand_models.py` — modelo neutro `DemandSignals` (as
  **features** derivadas, já numéricas) e `build_demand_signals()`
  (monta o modelo a partir de `TrendData`/`TrendMetrics` já mapeados da
  Fase 4, e de uma lista opcional de `MercadoLivreItem` da Fase 3).
- `src/demand_analysis.py` — `analyze_demand()`, que não importa nada
  de HTTP, Apify ou Mercado Livre: só recebe `DemandSignals` e devolve
  `DemandAnalysisResult`.

Cada campo de `DemandSignals` é um **feature** (um dado derivado,
pronto para ser usado em cálculo), nunca o dado cru da API. Um sinal
indisponível fica como `None` -- nunca um valor inventado.

- **Proxy / Demand proxy**: como não existe um jeito direto de medir
  "demanda real", usamos **proxies** -- sinais indiretos que, juntos,
  sugerem demanda. `recent_search_interest` é um proxy forte (reflete
  atenção de busca agora); `rising_query_count` isolado é um proxy
  fraco (pode ser uma pequena base que "explodiu" sem significar muito).
- **Signal / Feature**: cada número derivado que alimenta a análise
  (`trend_score`, `related_query_count`, `regional_spread`...) é um
  **signal** (sinal de mercado) transformado em **feature** (um valor
  numérico pronto para cálculo).
- **Derived metric**: `trend_contribution`, `breadth_contribution`,
  `regional_contribution` e `marketplace_contribution` não vêm direto
  de nenhuma API -- são **métricas derivadas**, calculadas a partir dos
  sinais brutos por fórmulas documentadas.
- **Evidence coverage / Source quality**: `source_coverage` mede
  quantas das duas famílias de fonte possíveis (tendência,
  marketplace) realmente contribuíram dados nesta consulta --
  `confidence_score` usa isso como metade do seu peso, porque a
  **qualidade da evidência** importa tanto quanto o número final.
- **Confidence score**: um número GERAL, separado do Demand Score, que
  mistura `source_coverage` (50%), quantos dos 4 grupos de componente
  estão presentes (30%) e o volume de observações de tendência (20%).
  Sempre calculável, mesmo que seja zero.
- **Deterministic scoring**: dado o mesmo `DemandSignals`, `analyze_demand()`
  sempre devolve o mesmo resultado -- sem IA generativa, sem
  aleatoriedade.
- **Missing data / Uncertainty**: um componente ausente (`None`) é
  **excluído** da média ponderada do Demand Score (os pesos são
  renormalizados sobre o que sobrou) -- nunca tratado como zero, porque
  "não sabemos" é diferente de "sabemos que é fraco". Isso é
  justamente o que torna a **incerteza** visível em vez de escondida
  dentro de um número só.
- **Provisional scoring model / Calibration**: assim como o Trend Score
  da Fase 4, o Demand Score e o Confidence Score são rotulados
  **PROVISIONAL** -- os pesos/escalas são constantes de módulo, feitas
  para serem recalibradas depois de validar contra dados reais de
  vendas.

### 4. Conexão entre o simples e o técnico

O "detetive com várias pistas" é, tecnicamente, um sistema de **demand
proxies**: cada pista (busca subindo, buscas parecidas, interesse
regional) é um **signal**, transformado em **feature** numérica. "Uma
pista sozinha é fraca" é o motivo pelo qual nenhum componente pode
dominar o Demand Score (pesos máximos de 40%/25%/20%/15%, e o
`rising_query_count` -- a pista mais fraca -- entra com meio peso dentro
do seu próprio componente). "Quantas pistas o detetive tinha na mão" é
exatamente o **Confidence Score**: calculado a partir de
**evidence coverage** (`source_coverage`) e completude dos dados, nunca
a partir da força da conclusão em si. E "um produto pode ter Demand
Score 80 e Confidence 35" é a separação entre **conclusão** (Demand
Score) e **evidência** (Confidence Score) que esta fase exige.

### 5. O que implementamos na prática

- `src/demand_models.py`:
  - `DemandSignals` — `query`, `geo`, `trend_score`, `trend_direction`,
    `average_search_interest`, `recent_search_interest`,
    `trend_observation_count`, `related_query_count`,
    `rising_query_count`, `regional_spread`,
    `marketplace_sample_size` (renomeado depois da revisão de
    modelagem -- ver adendo abaixo), `price_dispersion`,
    `source_coverage`, `notes` -- com validação de faixa em
    `__post_init__` (mesmo padrão da Fase 1).
  - `build_demand_signals()` — monta `DemandSignals` a partir de
    `TrendData`/`TrendMetrics` (Fase 4) e/ou `MercadoLivreItem` (Fase
    3), documentando honestamente qualquer fonte ausente em `notes`.
- `src/demand_analysis.py`:
  - `analyze_demand()` — calcula `trend_contribution`,
    `breadth_contribution`, `regional_contribution`,
    `marketplace_contribution`, o Demand Score (média ponderada só
    sobre os componentes disponíveis) e o Confidence Score (sempre
    calculável).
  - `DemandAnalysisResult` -- inclui `observed`, `derived` e
    `unavailable` para a transparência de evidência pedida no CLI.
- `src/main.py` — nova opção `4. Analyze Demand`, que tenta a Fase 4
  (tendência) e a Fase 3 (marketplace) **independentemente** -- uma
  falha em uma não bloqueia a outra -- e exibe o relatório completo com
  a seção Observado/Derivado/Indisponível.
- `tests/test_demand_models.py` e `tests/test_demand_analysis.py` — 23
  testes determinísticos cobrindo demanda forte com alta e baixa
  confiança, demanda fraca, demanda crescente mas nichada, demanda
  estável e ampla, dados esparsos, dados de marketplace ausentes,
  sinais totalmente vazios, e valores inválidos.
- Validação real feita ao vivo: numa chamada, o Actor devolveu um erro
  interno (`"No data returned"`) -- tratado corretamente como
  indisponível, sem travar; na chamada seguinte, Demand Score 26.95,
  Confidence Score 67.50, com `related_query_count` e `regional_spread`
  vindo como 0 (não indisponíveis) -- mostrando a diferença real entre
  "sabemos que é zero" e "não sabemos".

### 6. Termos técnicos aprendidos

- **termo:** Proxy
  **definição:** um sinal indireto, mais fácil de medir, usado como
  substituto de algo que não conseguimos medir diretamente.
  **como apareceu no projeto:** interesse de busca é usado como proxy
  de demanda real, já que não temos acesso a vendas reais.

- **termo:** Signal (sinal)
  **definição:** qualquer dado observável que carrega informação
  relevante para a pergunta que estamos tentando responder.
  **como apareceu no projeto:** `trend_score`, `related_query_count`,
  `regional_spread` são todos sinais de mercado.

- **termo:** Demand proxy
  **definição:** um proxy especificamente usado para estimar demanda de
  um produto, sem medir vendas diretamente.
  **como apareceu no projeto:** todos os campos de `DemandSignals` são,
  coletivamente, os demand proxies deste projeto.

- **termo:** Confidence score
  **definição:** um número que representa o quanto confiamos em uma
  conclusão, baseado na quantidade e qualidade da evidência -- separado
  da força da própria conclusão.
  **como apareceu no projeto:** `DemandAnalysisResult.confidence_score`,
  calculado a partir de `source_coverage`, completude dos componentes e
  volume de observações.

- **termo:** Evidence coverage (cobertura de evidência)
  **definição:** a proporção de fontes de evidência possíveis que
  realmente contribuíram dados para uma análise.
  **como apareceu no projeto:** `source_coverage = sources_available /
  TOTAL_SOURCE_FAMILIES` -- hoje, no máximo 0.5, porque só uma das duas
  fontes possíveis está disponível.

- **termo:** Feature
  **definição:** um valor numérico derivado, pronto para ser usado em
  um cálculo ou modelo -- a "matéria-prima processada" da análise.
  **como apareceu no projeto:** cada campo de `DemandSignals` é uma
  feature derivada de dados brutos da Fase 3/4.

- **termo:** Derived metric (métrica derivada)
  **definição:** um valor calculado a partir de outros dados, não
  observado diretamente de nenhuma fonte externa.
  **como apareceu no projeto:** `trend_contribution`,
  `breadth_contribution`, `regional_contribution` e
  `marketplace_contribution` -- nenhum vem direto de uma API.

- **termo:** Deterministic scoring (pontuação determinística)
  **definição:** um cálculo de pontuação cujo resultado depende
  apenas dos dados de entrada -- sempre o mesmo para a mesma entrada.
  **como apareceu no projeto:** `analyze_demand()` inteiro, testado com
  23 casos fixos.

- **termo:** Calibration (calibração)
  **definição:** o processo de ajustar os parâmetros de um modelo
  (pesos, escalas) usando dados reais, depois que o modelo já está em
  uso.
  **como apareceu no projeto:** todas as constantes de peso em
  `src/demand_analysis.py` são isoladas no topo do módulo exatamente
  para serem recalibradas depois, sem reescrever a lógica.

- **termo:** Missing data (dado ausente)
  **definição:** a ausência honesta de um valor, representada
  explicitamente (`None`), em vez de um valor inventado ou um zero
  enganoso.
  **como apareceu no projeto:** `marketplace_sample_size=None`
  enquanto o Mercado Livre estiver bloqueado -- excluído do cálculo, não
  tratado como zero.

- **termo:** Uncertainty (incerteza)
  **definição:** o grau em que uma conclusão pode estar errada por
  falta de evidência suficiente -- distinto da conclusão em si.
  **como apareceu no projeto:** representada explicitamente pelo
  Confidence Score, nunca misturada dentro do Demand Score.

- **termo:** Source quality (qualidade da fonte)
  **definição:** o quão confiável e completa é uma fonte de dados
  específica, independente de quantas fontes existem.
  **como apareceu no projeto:** discutido na avaliação de fontes da
  Fase 5 -- o Actor da Apify tem qualidade variável (inconsistência
  documentada na Fase 4), o que reduz a confiança mesmo quando os dados
  chegam.

### 7. Comandos/ferramentas usados

```bash
python -m src.main          # executar a CLI (opção 4 = Analyze Demand)
python -m pytest -v         # rodar todos os testes via módulo
pytest -v                   # rodar todos os testes direto
```

Ferramentas: Python 3.12, `pytest`, `monkeypatch`, reaproveitamento das
integrações já existentes (Apify/Google Trends da Fase 4, Mercado Livre
da Fase 3) sem nenhuma dependência nova.

### 8. Como explicar isso para um recrutador ou cliente

"Eu construí uma camada de análise de demanda totalmente determinística
-- sem IA generativa -- que combina os sinais de mercado que já tínhamos
integrado (tendência de busca via Google Trends, e marketplace via
Mercado Livre) em um Demand Score explicável. O ponto mais importante
de design é a separação entre 'quão forte parece a demanda' (Demand
Score) e 'quanta evidência real sustenta essa conclusão' (Confidence
Score) -- dois números que nunca devem ser confundidos, porque hoje só
temos uma fonte de dados confiável, então qualquer conclusão forte vem
necessariamente com confiança limitada. Isso é transparência de
verdade: o relatório final separa explicitamente o que foi observado, o
que foi derivado por cálculo, e o que simplesmente não temos como saber
-- nunca fabricando um número para preencher uma lacuna."

### 9. O que devo lembrar desta fase

- **Nunca misturar "quão forte" com "quanta certeza"** em um único
  número -- são perguntas diferentes, e tratá-las como uma só esconde
  informação crítica de quem for usar o resultado.
- **Um componente ausente deve ser excluído, não zerado** -- "não
  sabemos" e "sabemos que é fraco" são situações completamente
  diferentes, e confundi-las distorce o resultado.
- **Nenhuma pista (proxy) sozinha deve dominar a conclusão** -- por
  isso cada componente tem um peso máximo, e a pista mais fraca
  (`rising_query_count`) pesa menos ainda dentro do seu próprio grupo.
- **Reaproveitar integrações já existentes** (Fases 3 e 4) em vez de
  construir uma nova é tanto mais simples quanto mais honesto -- a
  avaliação de fontes desta fase mostrou que não precisávamos (e não
  devíamos) inventar uma fonte nova só para ter mais dados.
- **Confidence baixa não é um bug** -- é a representação honesta de
  que só temos uma fonte de dados funcionando agora. Melhorar isso
  significa restaurar o Mercado Livre, não forçar o número a subir.
- **Separar o modelo de dados (`demand_models.py`) da lógica de
  cálculo (`demand_analysis.py`)** -- o mesmo padrão arquitetural das
  Fases 1 e 4 -- é o que permite adicionar uma nova fonte de demanda no
  futuro (ex.: um Demand Agent) sem reescrever a matemática de
  pontuação.

### Adendo — Revisão de modelagem antes do commit (3 bugs corrigidos)

Antes de comitar a Fase 5, fizemos uma revisão de modelagem e
encontramos três problemas reais de design -- nenhum deles exigia
código novo complexo, mas todos exigiam pensar com mais cuidado sobre o
que cada número realmente significa.

**1. Zero observado vs. indisponível/não confiável**

A Fase 4 já tinha provado que o Actor da Apify pode devolver uma seção
vazia (`related_queries` ou `interest_by_region`) enquanto outras
seções, na mesma chamada, vêm cheias. O código original da Fase 5
tratava `len(related_queries) == 0` como "zero buscas relacionadas" --
um sinal real de pouca demanda. Mas isso está errado: uma lista vazia
pode significar duas coisas completamente diferentes:

- **(A) zero observado**: o provedor rodou essa seção com sucesso e o
  resultado real é zero (ex.: um termo tão nichado que realmente não
  tem buscas relacionadas).
- **(B) indisponível/não confiável**: o provedor falhou, omitiu ou foi
  inconsistente nessa seção especificamente -- não sabemos se o valor
  real é zero ou não.

Confundir (A) com (B) é um erro de modelagem sério: ele faz um "não
sei" virar um "sei que é fraco", o que distorce a conclusão sem
nenhuma base real. A correção foi adicionar metadados de
disponibilidade por seção em `TrendData`
(`related_queries_available`, `regional_interest_available`,
`interest_over_time_available`), calculados pela camada de integração
(`src/integrations/apify_trends.py`) -- a única camada com acesso à
resposta crua da Apify para tomar essa decisão. Hoje, como o Actor não
nos dá nenhum sinal explícito de sucesso/falha por seção, usamos a
melhor heurística disponível: **lista vazia = indisponível**, lista
com qualquer conteúdo = disponível (e confiável, mesmo que os valores
dentro dela sejam zero). Isso é uma escolha deliberadamente
conservadora, documentada como tal -- não é uma certeza absoluta, é a
opção mais honesta dado o que realmente temos para decidir.

**2. Confidence Score alto demais para uma única família de fonte**

Uma execução real em produção (antes da correção) devolveu Demand
Score 26.95 com Confidence Score 67.50 -- usando **só uma** família de
fonte (tendência via Apify; o Mercado Livre estava bloqueado). Um
Confidence de 67.5 parece "evidência razoavelmente forte", mas na
real­idade só tínhamos um único "testemunho".

Isso revela a diferença entre dois conceitos que a fórmula antiga
misturava sem querer:

- **Data completeness (completude de dados)**: de tudo que UMA fonte
  poderia nos contar, quanto dela recebemos de fato? (`interest_over_time`
  + `related_queries` + `interest_by_region`, todos vindos da MESMA
  chamada à Apify/Google Trends.)
- **Source independence (independência de fonte)** / **evidence
  diversity (diversidade de evidência)**: quantas fontes DIFERENTES e
  **correlacionadas entre si** (`correlated evidence`) confirmam a
  mesma conclusão?

`interest_over_time`, `related_queries` e `interest_by_region` são
**evidência correlacionada**: todos vêm do mesmo Google Trends, pela
mesma chamada do mesmo Actor. Ter os três completos é ótima
*completude* -- mas não são três testemunhas independentes, são uma
testemunha só, cujo depoimento ouvimos até o fim. Só uma fonte
realmente diferente (o Mercado Livre, por exemplo) seria uma segunda
testemunha de verdade.

A fórmula antiga somava `source_coverage` (peso 50%) com completude
(30%) e volume (20%) como três parcelas aditivas -- isso deixava
completude e volume "compensarem" a falta de uma segunda fonte,
inflando o Confidence. A correção trocou isso por um modelo em duas
etapas:

```
internal_quality_score = 0.6 * completeness_score + 0.4 * volume_score
coverage_cap            = 100 * source_coverage
confidence_score        = min(internal_quality_score, coverage_cap)
```

Com 1 de 2 famílias de fonte, `coverage_cap = 50` -- o Confidence
**nunca** passa de 50, não importa quão completos ou volumosos sejam
os dados daquela única fonte. Com 2 de 2, o teto sobe para 100. Isso é
exatamente **por que a confiança precisa ser limitada pela cobertura de
fontes independentes**: completude mede "quanto ouvimos de uma
testemunha"; cobertura mede "quantas testemunhas diferentes temos" --
e nenhuma quantidade de detalhe extra transforma uma testemunha em
duas.

**3. `marketplace_result_count` não era uma contagem total**

O campo se chamava "contagem de resultados de marketplace", mas na
verdade era `len(search_products(query))` -- o número de itens
devolvidos em UMA página da API, limitado pelo parâmetro `limit`
(padrão 10). Isso nunca foi uma contagem total de anúncios no
marketplace -- é só o tamanho da página que pedimos. Usar isso como
sinal de demanda estaria, na prática, pontuando nosso próprio
parâmetro de busca, não o mercado real. Renomeamos o campo para
`marketplace_sample_size` (nome honesto) e o excluímos
permanentemente do cálculo do Demand Score, até que exista um campo
real de contagem total extraído da resposta do Mercado Livre.

**Validação ao vivo após a correção:** rodamos `bebedouro para gatos`
de novo, sem repetir a tentativa em busca de um resultado "bonito". O
Actor devolveu `related_queries` vazio de novo (mais uma confirmação de
que essa inconsistência é contínua, não resolvida) -- mas agora o
relatório mostrou "Breadth: not available" corretamente, em vez de
pontuar zero. Demand Score 60.40, Confidence Score exatamente 50.00
(no teto de 1-de-2-fontes) -- confirmado à mão com a fórmula.

**Termos novos desta revisão:**

- **Correlated evidence (evidência correlacionada)**: múltiplos sinais
  que vêm, na raiz, da mesma fonte/observação -- não contam como
  confirmações independentes umas das outras.
- **Source independence (independência de fonte)**: o grau em que
  diferentes sinais vêm de fontes genuinamente separadas, sem
  compartilhar a mesma origem de dados.
- **Evidence diversity (diversidade de evidência)**: ter múltiplas
  fontes independentes, não múltiplos detalhes da mesma fonte.
- **Observed zero vs. unavailable/missing**: a diferença entre "o
  provedor confirmou que é zero" e "não sabemos o valor porque essa
  parte falhou ou foi omitida" -- tratar os dois como a mesma coisa é
  um erro de modelagem, não um detalhe menor.

---

## Fase 6 — Análise de Concorrência determinística (Competition Score provisório)

### 1. Nome da fase

**Fase 6: camada de Competition Analysis determinística, estimando o
quão difícil o ambiente competitivo parece para um novo vendedor --
ainda sem agente de IA, reaproveitando as lições de confiança da Fase
5.**

### 2. Explicação simples

Imagine que você está pensando em abrir uma loja numa rua nova. Antes
de decidir, você caminha por um **quarteirão** (uma única rua, um só
lado, um pedaço pequeno da cidade) e observa: quantas lojas tem nesse
quarteirão, se os preços são todos parecidos, se é sempre o mesmo dono
aparecendo em várias lojas, se todas oferecem frete grátis, se os nomes
das lojas se parecem muito entre si.

Isso te dá pistas úteis! Mas seria um erro enorme concluir "esse
quarteirão tem 10 lojas, então a cidade inteira tem só 10 lojas de
concorrência." Você só viu **um quarteirão**, não a cidade inteira. Essa
é exatamente a diferença entre uma **amostra** (`sample`) e o **mercado
total** (`total market`) -- e é o cuidado central desta fase.

Assim como na Fase 5 separamos "quão forte parece a demanda" de "quanta
evidência temos", aqui separamos dois números parecidos:

- **Competition Score**: "quão difícil esse mercado parece, pelo que
  conseguimos observar?" (0 = parece fácil, 100 = parece muito
  concorrido)
- **Confidence Score**: "quanta certeza real temos nessa conclusão?"

Um produto pode ter Competition Score 85 com Confidence 30 -- isso
significa "pelo que vimos nesse quarteirão, parece bem concorrido, mas
só vimos um quarteirão pequeno, então não tenha certeza absoluta disso."

### 3. Explicação técnica

Implementamos a primeira camada de **competition proxy** determinística
do projeto, com a mesma separação arquitetural das Fases 4 e 5:

- `src/competition_models.py` — modelo neutro `CompetitionSignals` e
  `build_competition_signals()`, que recebe uma lista (possivelmente
  vazia) de `MercadoLivreItem` já buscada pela Fase 3.
- `src/competition_analysis.py` — `analyze_competition()`, sem nenhum
  import de HTTP, Apify ou Mercado Livre: só recebe `CompetitionSignals`
  e devolve `CompetitionAnalysisResult`.

- **Market saturation / listing saturation**: o quanto o mercado parece
  "cheio" de anúncios concorrentes. Medimos isso de um jeito honesto:
  se a amostra devolvida for **menor** que o `limit` pedido, sabemos com
  certeza (não é estimativa!) que aquele é o total real -- a API já
  devolveu tudo que existia. Se a amostra **atingir** o `limit`, só
  sabemos "existem pelo menos esse tanto", nunca o total.
- **Sample bias / page-limited sample**: toda a análise desta fase vem
  de uma única chamada de API, limitada a ~10 itens por padrão. Isso é
  uma amostra, com todo o viés que uma amostra pequena carrega -- nunca
  tratamos `marketplace_sample_size` como uma medida do mercado
  completo.
- **Seller concentration / Sample concentration**: contamos quantos
  `seller_id` distintos aparecem na amostra. Se poucos vendedores
  dominam a amostra, chamamos isso de **sample concentration**
  ("concentração NA AMOSTRA"), nunca de **market share**
  ("participação de mercado") -- não temos dados para afirmar isso, só
  para descrever o que vimos nesses ~10 itens.
- **Market share vs. sample share**: `market share` seria "que fração
  de TODAS as vendas reais do mercado pertence a esse vendedor" --
  informação que não temos e nunca fabricamos. O que calculamos é
  `unique_seller_ratio`, uma fração da AMOSTRA, não do mercado.
- **Price dispersion / Standard deviation / Coefficient of variation**:
  calculamos `price_min`, `price_max`, `price_mean`, `price_median`, e
  `price_dispersion` como o **coeficiente de variação**
  (`desvio padrão / média`) -- preferido ao desvio padrão bruto porque
  é comparável entre produtos de preços muito diferentes (R$10 vs
  R$1000).
- **Commoditization / Price crowding**: aqui tomamos uma decisão de
  modelagem deliberada e documentada: dispersão de preço **baixa**
  (preços muito parecidos entre vendedores) é tratada como
  **price crowding** -- um sinal de que o produto está
  **comoditizado** (todo mundo vendendo quase pela mesma coisa, difícil
  se diferenciar). Dispersão **alta** é tratada como mercado
  segmentado (variações de produto, não necessariamente "mais
  concorrência"). Isso é o oposto do que alguém assumiria
  ingenuamente ("preços muito diferentes = mercado caótico e
  competitivo") -- por isso documentamos o raciocínio com cuidado.
- **Confiança limitada por independência de amostra, não por
  completude de features**: a lição central da Fase 5 era "múltiplas
  features da MESMA fonte não são confirmações independentes".
  Aqui ela aparece de um jeito um pouco diferente: como só existe UMA
  família de fonte possível (Mercado Livre, sem um "Google Trends da
  concorrência"), o risco não é "1 de 2 fontes" -- é "5 features, todas
  calculadas da MESMA pequena amostra de ~10 itens". Por isso o teto de
  confiança (`MAX_CONFIDENCE_SINGLE_SOURCE = 55`) não depende de quantas
  das 5 features conseguimos calcular, mas também do **tamanho da
  amostra** em si -- ter as 5 features de uma amostra de 2 itens não
  deveria inspirar a mesma confiança que ter as 5 features de uma
  amostra de 10.
- **Deterministic analysis**: dado o mesmo `CompetitionSignals`,
  `analyze_competition()` sempre devolve o mesmo resultado -- sem IA
  generativa, sem embeddings, sem aleatoriedade. A duplicação de
  títulos, por exemplo, é verificada por comparação EXATA de texto
  normalizado (`strip().lower()` + espaços colapsados), não por
  similaridade semântica de IA -- exatamente como pedido nesta fase
  ("no embeddings, no LLM similarity yet").

### 4. Conexão entre o simples e o técnico

O "quarteirão" é a **amostra** (`marketplace_sample_size`); a "cidade
inteira" é o **mercado total** (`total_result_count`), que quase nunca
conseguimos conhecer de verdade -- só nos casos raros em que a amostra
devolvida é menor que o limite pedido. "O mesmo dono aparecendo em
várias lojas" é a **sample concentration** (`unique_seller_ratio`
baixo), nunca uma afirmação de **market share**. "Todos os preços
parecidos" é **price crowding** (baixa `price dispersion` /
**coefficient of variation**), interpretado com cuidado como
possível **comoditização**, não assumido automaticamente como "mais
concorrência". E "só vi um quarteirão, não posso ter certeza sobre a
cidade" é exatamente o **Confidence Score**, limitado por
**independência de amostra** -- a mesma ideia central da Fase 5
(**correlated evidence** não vale como **source independence**),
aplicada aqui à escala de uma única chamada de API em vez de duas
famílias de fonte.

### 5. O que implementamos na prática

- `src/competition_models.py`:
  - `CompetitionSignals` — `query`, `marketplace_sample_size`,
    `total_result_count`, `seller_count`, `unique_seller_ratio`,
    `price_min/max/mean/median`, `price_dispersion`,
    `free_shipping_ratio`, `condition_distribution`,
    `duplicate_title_ratio`, `source_coverage`, `notes` -- com
    validação de faixa em `__post_init__`, incluindo a regra
    `total_result_count >= marketplace_sample_size`.
  - `build_competition_signals()` — calcula cada campo só a partir dos
    itens que realmente têm aquele dado (preço, vendedor, frete,
    condição, título), documentando honestamente qualquer sinal
    ausente em `notes`.
- `src/competition_analysis.py`:
  - `analyze_competition()` — calcula `seller_concentration`,
    `listing_saturation`, `price_crowding`, `duplicate_listing`,
    `shipping` (pesos 0.30/0.25/0.20/0.15/0.10), o Competition Score
    (média ponderada só sobre componentes disponíveis) e o Confidence
    Score (capado em 55 para a única fonte existente).
- `src/main.py` — nova opção `5. Analyze Competition`, buscando até 10
  itens no Mercado Livre e exibindo Observado/Derivado/Indisponível.
- `tests/test_competition_models.py` e `tests/test_competition_analysis.py`
  -- 33 testes determinísticos cobrindo amostra de alta/baixa
  concorrência, vendedores concentrados/diversos, preços
  agrupados/dispersos, sinais ausentes (preço/vendedor/frete),
  duplicação de títulos, amostra vazia, falha de fonte, zero observado
  vs. indisponível, confiança com uma única fonte, e amostra limitada
  por página nunca tratada como total.
- Validação real feita ao vivo: Mercado Livre respondeu `403` (mesmo
  bloqueio de todas as fases anteriores) -- o relatório mostrou
  corretamente `Competition Score: not available`, `Confidence Score:
  0.00`, sem travar e sem inventar nada, exatamente como a avaliação de
  fontes desta fase já previa antes de rodar.

### 6. Termos técnicos aprendidos

- **termo:** Competition proxy
  **definição:** um sinal indireto usado para estimar o quão difícil é
  competir em um mercado, sem medir diretamente "dificuldade".
  **como apareceu no projeto:** concentração de vendedores, dispersão
  de preço, prevalência de frete grátis, duplicação de títulos.

- **termo:** Market saturation (saturação de mercado)
  **definição:** o quão "cheio" um mercado parece estar de produtos/
  anúncios concorrentes.
  **como apareceu no projeto:** `listing_saturation_contribution`,
  derivada do tamanho da amostra em relação ao limite pedido.

- **termo:** Seller concentration (concentração de vendedores)
  **definição:** o quão poucos vendedores distintos dominam um
  conjunto de anúncios.
  **como apareceu no projeto:** `100 * (1 - unique_seller_ratio)`.

- **termo:** Sample concentration vs. Market share
  **definição:** concentração observada DENTRO de uma amostra pequena
  (`sample concentration`) é diferente de participação real no mercado
  total (`market share`) -- a primeira é honesta de afirmar com uma
  amostra pequena; a segunda não.
  **como apareceu no projeto:** `unique_seller_ratio` é explicitamente
  documentado como medida de amostra, nunca de mercado.

- **termo:** Price dispersion (dispersão de preço)
  **definição:** o quanto os preços de uma amostra variam entre si.
  **como apareceu no projeto:** medida como coeficiente de variação
  (`price_dispersion`).

- **termo:** Standard deviation (desvio padrão)
  **definição:** uma medida de quão espalhados estão os valores em
  torno da média.
  **como apareceu no projeto:** usado dentro do cálculo do coeficiente
  de variação (`statistics.pstdev`).

- **termo:** Median (mediana)
  **definição:** o valor do meio de um conjunto ordenado -- menos
  sensível a valores extremos do que a média.
  **como apareceu no projeto:** `price_median`, calculado junto com a
  média para dar uma visão mais robusta do preço típico.

- **termo:** Coefficient of variation (coeficiente de variação)
  **definição:** o desvio padrão dividido pela média -- uma medida de
  dispersão relativa, comparável entre escalas de preço diferentes.
  **como apareceu no projeto:** `price_dispersion = pstdev(prices) /
  mean(prices)`, usado em vez do desvio padrão bruto por ser comparável
  entre produtos de preços muito diferentes.

- **termo:** Commoditization (comoditização)
  **definição:** quando um produto se torna tão padronizado que
  vendedores diferentes competem quase só por preço, sem diferenciação.
  **como apareceu no projeto:** interpretação de baixa dispersão de
  preço como possível sinal de comoditização (`price crowding`).

- **termo:** Price crowding (aglomeração de preço)
  **definição:** quando muitos vendedores oferecem o mesmo produto a
  preços muito parecidos.
  **como apareceu no projeto:** `price_crowding_contribution`, alta
  quando a dispersão de preço é baixa.

- **termo:** Sample bias (viés de amostra)
  **definição:** a distorção que acontece quando se tira conclusões
  gerais a partir de uma amostra pequena e não necessariamente
  representativa.
  **como apareceu no projeto:** o motivo central pelo qual o Confidence
  Score desta fase tem um teto baixo (55) mesmo com dados completos.

- **termo:** Page-limited sample (amostra limitada por página)
  **definição:** uma amostra cujo tamanho é artificialmente limitado
  pelo parâmetro de paginação de uma API, não pelo tamanho real dos
  dados.
  **como apareceu no projeto:** `marketplace_sample_size`, nunca igual
  a `total_result_count` a menos que a amostra já tenha vindo menor que
  o limite pedido.

- **termo:** Source independence (independência de fonte)
  **definição:** o grau em que diferentes sinais vêm de fontes
  genuinamente separadas, sem compartilhar a mesma origem de dados --
  conceito trazido da Fase 5.
  **como apareceu no projeto:** usado para explicar por que 5 features
  da mesma amostra não valem como 5 confirmações independentes.

- **termo:** Correlated evidence (evidência correlacionada)
  **definição:** múltiplos sinais que vêm, na raiz, da mesma
  fonte/observação -- não contam como confirmações independentes entre
  si.
  **como apareceu no projeto:** todas as 5 dimensões de competição
  vêm da mesma chamada de API, por isso não multiplicam a confiança.

- **termo:** Confidence score
  **definição:** um número que representa o quanto confiamos em uma
  conclusão, separado da força da própria conclusão.
  **como apareceu no projeto:** `CompetitionAnalysisResult.confidence_score`,
  capado em 55 mesmo com dados completos, porque a amostra é única.

- **termo:** Missing vs. observed zero
  **definição:** a diferença entre "não sabemos o valor" (`None`) e "o
  valor real observado é zero".
  **como apareceu no projeto:** `free_shipping_ratio = 0.0` (todos os
  itens têm frete grátis `False`, um zero real) é diferente de
  `free_shipping_ratio = None` (nenhum item tinha esse campo
  preenchido) -- testado explicitamente.

- **termo:** Evidence quality (qualidade da evidência)
  **definição:** o quão boa e completa é a evidência disponível,
  independente de quantas fontes existem.
  **como apareceu no projeto:** `internal_quality_score`, misturando
  completude (quantos componentes temos) e adequação de amostra
  (quão grande é a amostra que temos).

- **termo:** Deterministic analysis (análise determinística)
  **definição:** um cálculo cujo resultado depende apenas dos dados de
  entrada -- sempre o mesmo para a mesma entrada, sem IA generativa.
  **como apareceu no projeto:** `analyze_competition()` inteiro,
  incluindo a duplicação de títulos por comparação exata de texto
  normalizado, sem embeddings nem similaridade por IA.

### 7. Comandos/ferramentas usados

```bash
python -m src.main          # executar a CLI (opção 5 = Analyze Competition)
python -m pytest -v         # rodar todos os testes via módulo
pytest -v                   # rodar todos os testes direto
```

Ferramentas: Python 3.12, `pytest`, `monkeypatch`, `statistics`
(`pstdev`, `fmean`, `median`), `collections.Counter` (para contagem de
vendedores/condições/títulos duplicados) -- nenhuma dependência nova.

### 8. Como explicar isso para um recrutador ou cliente

"Eu construí uma camada de análise de concorrência totalmente
determinística, sem IA generativa e sem embeddings, que estima o quão
difícil um mercado parece para um novo vendedor a partir de uma amostra
de anúncios do Mercado Livre. O ponto mais importante de design é a
honestidade sobre o que uma amostra pequena pode e não pode dizer: eu
nunca trato o tamanho da amostra como o tamanho do mercado total, e o
Confidence Score tem um teto deliberadamente baixo porque todas as
features vêm da mesma chamada de API -- cinco ângulos do mesmo
quarteirão, não cinco quarteirões diferentes. Quando a fonte de dados
está fora do ar (como aconteceu na validação real desta fase, com o
Mercado Livre retornando 403), o sistema não inventa um número -- ele
reporta honestamente que não há evidência suficiente, com Confidence
zero."

### 9. O que devo lembrar desta fase

- **Uma amostra nunca é o mercado total** -- essa é a lição mais
  importante desta fase, e ela já apareceu, de forma diferente, na
  Fase 5 (`marketplace_sample_size` vs. `total_result_count`). O mesmo
  erro de modelagem pode aparecer em formas diferentes; vale a pena
  revisitar lições antigas ao desenhar uma fase nova, em vez de
  assumir que cada fase precisa redescobrir o problema do zero.
- **Múltiplas features da mesma fonte não multiplicam confiança** --
  mesmo quando a fonte é única (sem "1 de 2 famílias" para comparar), o
  princípio se aplica através do tamanho da amostra: mais ângulos do
  mesmo bloco não valem mais do que o próprio bloco.
- **Interpretar sinais exige cuidado direcional**: dispersão de preço
  baixa não é automaticamente "bom" ou "ruim" -- aqui foi interpretada
  como comoditização (ruim para diferenciação), uma escolha documentada
  explicitamente, não uma verdade universal.
- **Nomear com honestidade importa**: `sample concentration` em vez de
  `market share`; `marketplace_sample_size` em vez de
  `marketplace_result_count` -- o nome de um campo é, ele mesmo, uma
  afirmação sobre o que os dados significam.
- **Falha de fonte não deve gerar número fabricado**: quando o Mercado
  Livre retornou 403 na validação real, o sistema reportou
  `Competition Score: not available` -- exatamente o comportamento que
  a avaliação de fontes já tinha previsto antes de qualquer linha de
  código ser escrita.

### Adendo — Revisão de hardening antes do commit (2 bugs de modelagem)

Antes de comitar a Fase 6, encontramos dois problemas reais de
modelagem -- e, curiosamente, o próprio texto que escrevemos na
avaliação de fontes desta fase (seção 1) já tinha previsto exatamente a
regra que o código violou. Isso é uma lição por si só: escrever a regra
não é o mesmo que aplicá-la em todo lugar do código.

**1. `listing_saturation` pontuava o nosso próprio parâmetro de busca**

A avaliação de fontes da Fase 6 já tinha dito, antes de qualquer linha
de código: "`marketplace_sample_size` não deve ser usado como sinal
direto de tamanho de mercado, porque é limitado pelo nosso próprio
`limit` pedido." Mas o componente `listing_saturation_contribution`
implementado fazia exatamente isso -- comparava `marketplace_sample_size`
com o `limit` pedido e pontuava "página cheia = mercado mais saturado."

Isso é o problema de **request limit não ser um sinal de mercado**: se
eu peço "me traga até 10 lojas" e me trazem exatamente 10, isso não me
diz quantas lojas existem na cidade -- só me diz "existem pelo menos
10". O número "10" que eu vejo é, em parte, o número que EU escolhi
pedir, não um fato sobre o mundo. Usar esse número para calcular
"quão saturado está o mercado" é basicamente medir a minha própria
pergunta e fingir que medi a resposta.

A correção: `listing_saturation_contribution` agora é **sempre `None`**,
excluído permanentemente do Competition Score (o espaço de peso
continua reservado, documentado, para o dia em que tivermos um campo
real de total do provedor). Testamos com regressão: amostras de 5, 10 e
50 itens, com as mesmas features de concorrência, agora produzem
**exatamente o mesmo** Competition Score -- prova de que o tamanho da
amostra, isolado, não pode mais mover o número.

**2. Inferir `total_result_count` a partir de `sample < limit` parecia
válido, mas não era**

A versão anterior desta fase assumia: "se a API devolveu menos itens do
que eu pedi, então aquilo é tudo que existe." Isso parece
matematicamente razoável -- e é exatamente por isso que é um exemplo
perfeito de **uma inferência que parece matematicamente válida, mas é
semanticamente inválida** (`why an inference can be mathematically
valid-looking but semantically invalid`). A lógica "menos que o limite
= é tudo" só funciona se duas garantias forem verdadeiras ao mesmo
tempo:

1. A contagem que eu vejo (`len(mapped_items)`) é EXATAMENTE a mesma
   contagem que o provedor usou internamente para decidir quantos
   resultados existem (**mapped item count vs. raw result count**) --
   nosso `search_products()` devolve objetos `MercadoLivreItem` já
   **mapeados**, não a lista bruta nem os metadados de paginação do
   provedor. Hoje, por acaso, o código mapeia 1 para 1 -- mas nada
   garante isso para sempre; é um detalhe de implementação, não um
   contrato.
2. O provedor realmente fez uma busca completa/exaustiva, e não
   aplicou nenhum filtro, limite de qualidade, ou corte silencioso
   antes de devolver a resposta.

Chamamos isso de **abstraction information loss** (perda de informação
na abstração): cada camada que transformamos os dados (resposta bruta
→ JSON → objetos `MercadoLivreItem` mapeados) pode descartar
informação que a camada anterior tinha -- nesse caso, os metadados de
**paginação** (**pagination metadata**) que o Mercado Livre
provavelmente devolve (um campo `paging.total`, por exemplo), mas que
nosso `_map_item()` nunca extraiu nem preservou. Uma vez que a
informação é descartada numa camada, nenhuma camada posterior pode
recuperá-la por inferência -- só pode adivinhar.

Essa é a diferença entre **provider metadata** (um fato que o próprio
provedor afirma, como um campo `total` explícito na resposta) e
**derived inference** (uma conclusão que NÓS calculamos a partir de
outros números, mesmo que pareça razoável). Só o primeiro tipo é seguro
de usar como "total"; o segundo, aqui, não era.

A correção: `total_result_count` agora é **sempre `None`**, até que um
campo real de total do provedor seja extraído e mapeado (o que ainda
não acontece hoje).

**A analogia que resume os dois problemas:**

> Se eu pedir para alguém trazer **no máximo 10 lojas** de uma cidade, e
> essa pessoa trouxer 10, eu só sei que existem **pelo menos 10**.
>
> Se ela trouxer 7, eu ainda **não posso** automaticamente afirmar que a
> cidade inteira tem exatamente 7 lojas -- a menos que a fonte me diga
> explicitamente que a busca foi exaustiva e completa.
>
> A nossa integração atual não preserva essa garantia.

**Validação ao vivo após a correção:** rodamos a opção 5 de novo contra
o Mercado Livre de verdade. Ele continua devolvendo `403` (mesmo
bloqueio de todas as fases anteriores) -- o relatório mostrou
corretamente `Competition Score: not available`, `Confidence Score:
0.00`, sem travar e sem inventar nada.

**Termos novos desta revisão:**

- **Sample size is not market saturation**: o tamanho de uma amostra
  (quantos itens vieram numa resposta) nunca deve ser confundido com o
  quão "saturado" ou "cheio" está o mercado real.
- **Request limit is not a market signal**: um parâmetro que NÓS
  escolhemos ao fazer a chamada (`limit=10`) não é um fato sobre o
  mundo -- é uma escolha nossa, e não deveria aparecer como se fosse
  uma medição.
- **Pagination metadata**: os campos que uma API usa para descrever
  "quantos resultados existem no total" e "em que página estamos" --
  diferentes dos próprios itens de dados.
- **Provider metadata vs. derived inference**: um fato que o provedor
  afirma diretamente (`total: 743` num campo da resposta) é mais
  confiável do que uma conclusão que nós calculamos a partir de outros
  números, mesmo que o cálculo pareça razoável.
- **Abstraction information loss**: cada camada de transformação de
  dados pode descartar informação que existia na camada anterior; essa
  informação não pode ser recuperada depois por inferência.
- **Mapped item count vs. raw result count**: a quantidade de objetos
  que NÓS conseguimos mapear com sucesso não é necessariamente igual à
  quantidade de resultados que o provedor realmente tinha.
- **Sample-level evidence vs. population-level claim**: uma observação
  feita sobre uma amostra pequena (`sample-level`) nunca deve ser
  apresentada como uma afirmação sobre o grupo inteiro
  (`population-level`) sem evidência extra que justifique isso.
- **Sample ≠ population**: a amostra que observamos e a população real
  (o mercado inteiro) são coisas diferentes -- confundi-las é o erro
  central desta fase, em duas formas distintas (saturação de listagem e
  inferência de total).
- **Por que uma inferência pode parecer matematicamente válida mas ser
  semanticamente inválida**: a aritmética "sample < limit → total =
  sample" está correta SE as premissas forem verdadeiras -- o erro não
  está na matemática, está em assumir premissas (mapeamento 1-para-1,
  busca exaustiva) que o nosso sistema nunca verificou nem garantiu.
