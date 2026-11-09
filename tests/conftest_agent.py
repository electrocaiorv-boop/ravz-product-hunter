"""Shared offline fixtures for the Phase 12B agent tests.

No test in this phase touches the network, and none needs an
`ANTHROPIC_API_KEY`. The LLM is a scripted fake and the providers are
fixtures, so the whole loop is exercised deterministically.
"""

from src.integrations.mercadolivre import MercadoLivreItem
from src.trend_models import TrendData, TrendPoint

GROWING = [20, 30, 42, 55, 70, 88]


def make_trend_fetcher(counter=None, values=None):
    def fetcher(query, geo="BR", timeframe="today 12-m"):
        if counter is not None:
            counter.append((query, geo, timeframe))
        points = [
            TrendPoint(date=f"w{i}", value=v, formatted_value=None)
            for i, v in enumerate(values if values is not None else GROWING)
        ]
        return TrendData(
            query=query, geo=geo, timeframe=timeframe,
            retrieved_at="2026-01-01T00:00:00Z",
            interest_over_time=points, interest_by_region=[],
            related_top_queries=[], related_rising_queries=[],
            source="fixture:controlled", interest_over_time_available=True,
            related_queries_available=False, regional_interest_available=False,
        )

    return fetcher


def make_marketplace_searcher(counter=None, count=5, titles=None):
    def searcher(query, limit=10):
        if counter is not None:
            counter.append((query, limit))
        return [
            MercadoLivreItem(
                item_id=f"MLB{i}",
                title=(titles[i] if titles and i < len(titles) else f"Item {i}"),
                price=100.0 + i * 9, currency_id="BRL", seller_id=i % 3,
                category_id="MLB1000", condition="new", permalink=None,
                free_shipping=i % 2 == 0, available_quantity=50,
            )
            for i in range(count)
        ]

    return searcher


class ScriptedLLM:
    """A fake model that replays a fixed list of turns.

    Each scripted turn is `{"text": str, "tool_calls": [...]}`. Token
    counts default to small realistic values so budget accounting is
    exercised without arithmetic noise.
    """

    def __init__(self, turns, model="claude-sonnet-5"):
        self.model = model
        self._turns = list(turns)
        self.calls = 0
        self.seen_systems = []
        self.seen_messages = []

    def complete(self, *, system, messages, tools):
        self.calls += 1
        self.seen_systems.append(system)
        self.seen_messages.append(list(messages))
        if not self._turns:
            return {"text": "done", "tool_calls": [],
                    "input_tokens": 100, "output_tokens": 10}
        turn = dict(self._turns.pop(0))
        turn.setdefault("text", "")
        turn.setdefault("tool_calls", [])
        turn.setdefault("input_tokens", 500)
        turn.setdefault("output_tokens", 50)
        return turn


class ExplodingLLM:
    model = "claude-sonnet-5"

    def __init__(self, exc):
        self._exc = exc

    def complete(self, *, system, messages, tools):
        raise self._exc
