# RAVZ Product Hunter

## Objective

Build an AI-powered product research and validation system focused initially on Mercado Livre Brazil.

The system must identify promising products, evaluate demand, competition, trends, supplier viability, estimated margins, logistical risk, and generate a final opportunity score.

The project must be designed both as:

1. A real tool for product research and ecommerce opportunities.
2. A professional portfolio project demonstrating AI agents, APIs, automation, Python, data analysis, MCP, n8n, and software engineering practices.

---

## Core Principle

Never claim that a product has a guaranteed probability of selling.

The system must work with measurable indicators and produce an:

**Opportunity Score from 0 to 100**

The score must be explainable and based on collected data.

---

## Initial Architecture

The system will evolve into multiple specialized agents.

### Orchestrator Agent

Coordinates the workflow and decides which agents need to run.

### Demand Agent

Responsible for analyzing product demand.

Possible signals:

- marketplace search results
- number of listings
- sales indicators when available
- reviews
- ranking
- search interest
- historical signals

### Competition Agent

Analyzes:

- number of competing sellers
- price concentration
- dominant sellers
- review concentration
- listing quality
- market saturation

### Trend Agent

Analyzes whether demand appears to be:

- growing
- stable
- declining
- seasonal

Possible sources may include Google Trends or other available data sources.

### Supplier Agent

Searches for viable Brazilian suppliers.

Preferred supplier characteristics:

- Brazilian operation
- verifiable company information
- reliable reputation
- product availability
- low or no minimum order quantity
- fast shipping
- dropshipping or cross-docking compatibility when possible
- competitive wholesale price
- recurring inventory

### Margin Agent

Calculates estimated unit economics.

Must consider when applicable:

- supplier cost
- selling price
- marketplace fees
- shipping
- taxes or estimated fiscal costs
- packaging
- operational costs
- estimated profit
- estimated margin percentage

Never hide costs simply to make an opportunity appear attractive.

### Scoring Agent

Generates the final Opportunity Score.

Initial conceptual weighting:

- Demand: 30%
- Trend: 20%
- Competition: 15%
- Margin: 15%
- Supplier quality: 10%
- Logistics: 5%
- Risk: 5%

These weights are provisional and may change after validation.

---

## Opportunity Classification

Initial classification:

- 80–100: Strong opportunity
- 65–79: Worth deeper investigation
- 50–64: Weak or uncertain opportunity
- Below 50: Reject unless there is a strategic reason

The score must include an explanation.

---

## Output Example

Each evaluated product should eventually produce structured output similar to:

Product:
Category:
Source:

Demand score:
Competition score:
Trend score:
Supplier score:
Margin score:
Logistics score:
Risk score:

Estimated supplier cost:
Estimated sale price:
Estimated marketplace fees:
Estimated profit:
Estimated margin:

Opportunity Score:

Recommendation:

Evidence:
Risks:
Assumptions:
Next actions:

---

## Development Rules

### Code Quality

- Prefer simple and readable code.
- Use Python as the primary backend language.
- Use type hints where useful.
- Use modular architecture.
- Avoid unnecessary abstraction.
- Avoid premature optimization.
- Keep business rules separate from integrations.
- Write reusable functions.
- Add tests for important scoring and financial calculations.

### Agent Design

Agents must have clearly defined responsibilities.

Do not create a single giant agent responsible for everything.

Whenever possible, agents should return structured data rather than unstructured prose.

Prefer JSON-compatible Python dictionaries or typed models.

### Data Integrity

Never fabricate:

- sales volume
- supplier information
- prices
- reviews
- marketplace metrics
- margins
- API responses

If information cannot be retrieved, explicitly mark it as unavailable.

Clearly distinguish:

- observed data
- estimated data
- inferred data

### Security

Never commit secrets to Git.

Secrets must be stored in environment variables.

Examples:

- API keys
- tokens
- passwords
- private URLs
- webhook secrets

Use `.env` locally.

Only `.env.example` may be committed.

### External Integrations

Potential integrations include:

- Mercado Livre APIs
- Google Trends
- Apify
- supplier websites
- search APIs
- n8n
- databases
- notification channels

Do not add an external integration without documenting:

1. why it is needed
2. what data it provides
3. authentication requirements
4. cost implications
5. rate limits when known

---

## Development Strategy

Build incrementally.

Do not attempt to build the entire system in one step.

Development order:

1. Project structure
2. Data models
3. Opportunity scoring engine
4. Manual product input
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

Each stage must work before moving to the next.

---

## Current Phase

Phase 1:

Create a minimal but professional foundation.

The first working version must accept manually supplied product metrics and calculate an explainable Opportunity Score.

Do not implement marketplace scraping or complex autonomous browsing yet.

The priority is validating the architecture and scoring engine first.

---

## Git Practice

Use small, meaningful commits.

Examples:

- `chore: initialize project structure`
- `feat: add product opportunity model`
- `feat: implement scoring engine`
- `test: add scoring engine tests`
- `feat: integrate mercado livre data`
- `feat: add supplier research agent`

Never commit `.env`.

---

## Portfolio Goal

This repository should clearly demonstrate knowledge of:

- Python
- REST APIs
- JSON
- AI agents
- LLM orchestration
- MCP
- automation
- n8n
- data processing
- ecommerce analytics
- Git
- GitHub
- software architecture
- testing
- secure credential handling

Code and documentation must be understandable by another developer reviewing the repository during a hiring process.