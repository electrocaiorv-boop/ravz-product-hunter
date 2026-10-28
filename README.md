# RAVZ Product Hunter

An AI-powered product research and validation system for Mercado Livre
Brazil. It evaluates ecommerce product opportunities across demand, trend,
competition, margin, supplier viability, logistics, and risk, and produces an
explainable **Opportunity Score (0-100)**.

This project is built both as a real research tool and as a portfolio piece
demonstrating AI agents, APIs, automation, and software engineering
practices in Python.

**Core principle:** the system never claims a product is guaranteed to
sell. It only produces a measurable, explainable score based on the data it
is given.

## Phase 1 scope

Phase 1 validates the architecture and scoring engine before any live data
integration. It intentionally does **not** include marketplace scraping,
API integrations, agents, a database, or automation (n8n/MCP) — those come
in later phases.

What Phase 1 provides:

- `src/models.py` — `Product`, `ComponentScores`, and `OpportunityResult`
  data models
- `src/scoring.py` — the weighted scoring engine and opportunity
  classification
- `tests/test_scoring.py` — unit tests covering the scoring math

All scores are supplied manually (e.g. in a script or test) rather than
fetched from a marketplace.

## Phase 2 scope

Phase 2 adds a manual input path on top of the Phase 1 scoring engine: a
terminal CLI that asks the user for a product's data and scores, then
prints a full opportunity report. It still does **not** include any
marketplace scraping, API integrations, agents, a database, or automation
— it reuses the existing `Product`, `ComponentScores`, and
`score_opportunity()` from Phase 1 without duplicating any scoring logic.

What Phase 2 provides:

- `src/main.py` — the Manual Product Analyzer CLI (presentation layer
  only): prompts for product name, category, and the seven component
  scores; validates and re-asks on invalid input; builds and prints the
  final report.
- `tests/test_main.py` — unit tests for the CLI's reusable
  parsing/validation/formatting functions, using an injectable
  `input_func` instead of mocking the real `input()`.

### Run the analyzer

```bash
python -m src.main
```

### Example

```
RAVZ Product Hunter -- Manual Product Analyzer
Enter the product details and scores below.

Product name: Wireless Mouse
Category: Electronics
Demand score (0-100): 85
Trend score (0-100): 70
Competition score (0-100): 40
Margin score (0-100): 60
Supplier score (0-100): 55
Logistics score (0-100): 90
Risk score (0-100): 15

==================================================
OPPORTUNITY REPORT
==================================================
Product: Wireless Mouse
Category: Electronics

Component scores:
  Demand:      85.0
  Trend:       70.0
  Competition: 40.0
  Margin:      60.0
  Supplier:    55.0
  Logistics:   90.0
  Risk:        15.0

Weighted breakdown:
  Demand       contributes 25.5
  Trend        contributes 14.0
  Competition  contributes 9.0
  Margin       contributes 9.0
  Supplier     contributes 5.5
  Logistics    contributes 4.5
  Risk         contributes 4.25

Opportunity Score: 71.75
Classification: Worth deeper investigation

Recommendation: Investigate further before committing.
==================================================
```

If you type an invalid score (non-numeric, or outside 0-100), the CLI
prints `Invalid input: ...` and asks the same question again instead of
crashing.

## Architecture direction

The system is designed to grow into an orchestrator coordinating
specialized agents (Demand, Competition, Trend, Supplier, Margin,
Scoring), each with a single responsibility and returning structured data
instead of prose. Phase 1 builds only the data models and the scoring
engine that every later agent will eventually feed into:

```
Product + ComponentScores -> scoring engine -> OpportunityResult
```

Business logic (the scoring math) is kept separate from integrations
(marketplace APIs, suppliers, trends) so the scoring engine can be tested
and trusted independently of any external data source.

### Scoring model

Final score is a weighted combination of seven 0-100 component scores:

| Dimension   | Weight | Direction |
|-------------|--------|-----------|
| Demand      | 30%    | positive  |
| Trend       | 20%    | positive  |
| Competition | 15%    | negative  |
| Margin      | 15%    | positive  |
| Supplier    | 10%    | positive  |
| Logistics   | 5%     | positive  |
| Risk        | 5%     | negative  |

Competition and Risk are **negative dimensions**: a higher score means more
competition or more risk, so each is inverted (`100 - score`) before being
weighted, instead of being added directly.

### Classification

| Opportunity Score | Classification                 |
|--------------------|---------------------------------|
| 80-100             | Strong opportunity              |
| 65-79.99            | Worth deeper investigation      |
| 50-64.99            | Weak or uncertain opportunity   |
| Below 50            | Reject                          |

## Install

Requires Python 3.12.

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

## Run tests

```bash
pytest
```

`pyproject.toml` configures pytest's `pythonpath` to include the project
root, so `src` resolves as a package whether you run `pytest` or
`python -m pytest`.

## Roadmap

1. Project structure
2. Data models
3. Opportunity scoring engine
4. Manual product input *(current phase)*
5. First real data integration
6. Demand analysis
7. Competition analysis
8. Margin analysis
9. Supplier research
10. Orchestration
11. Database/history
12. n8n automation
13. Notifications
14. Continuous improvement
