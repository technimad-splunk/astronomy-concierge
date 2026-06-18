# [harness stub] tool_fault trigger

**Not a vignette.** Phase-3 harness fixture proving the `tool_fault` trigger:
`play` records a fault on the `get_recommendations` tool in the agent overlay
(`mode=error`, so the tool returns an error on every call); the agent picks it up
on its next run. `reset` clears the fault. Real vignettes are authored in Phase 4+.
