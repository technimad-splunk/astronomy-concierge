# Talk track — The Invisible Failure

> **Placeholder.** The full SE talk track is authored in Phase 4 / Phase 6
> (see [`docs/implementation-plan.md`](../../../docs/implementation-plan.md)).

**Vignette 1 — The Invisible Failure** (demo-design §6)

- **Message it proves:** observability oversight — *"you can't measure what you
  can't see."* Failures in GenAI are **soft**: no crash, no stack trace, just a
  wrong or ungrounded answer.
- **Trigger:** a feature flag (`productCatalogStaleData`) makes the
  product-catalog service serve **stale data**, so the concierge confidently
  answers from bad context.
- **Galileo hero moment:** **Context Adherence drops** and the **ungrounded
  claim is pinpointed** in the reasoning trace.
- **Splunk backdrop (the punchline):** **APM dashboards stay GREEN** — the
  infrastructure looks perfectly healthy while the agent is quietly wrong.

## TODO — Phase 4 / Phase 6

- [ ] Write the full SE narration (setup → reveal → reset).
- [ ] Add a **known-good prompt card** to mitigate live nondeterminism (L1).
- [ ] Note dashboard **pre-warming** so the green/anomaly contrast lands on cue (L2).
