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
