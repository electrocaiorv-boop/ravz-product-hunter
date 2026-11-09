"""Phase 12B: the bounded agentic control layer.

The division of labour is strict and is the whole point of this package:

    the LLM decides WHAT TO LOOK AT
    the deterministic engines decide WHAT IT MEANS

Nothing in this package calculates, re-weights, inverts or overrides a
business score. Every number an agent reports traces to a domain engine
or to `compose_opportunity()`, and that traceability is enforced by
`guards.verify_provenance()` rather than trusted.
"""
