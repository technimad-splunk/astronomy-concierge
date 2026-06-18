# [harness stub] prompt_overlay trigger

**Not a vignette.** Phase-3 harness fixture proving the `prompt_overlay` trigger:
`play` writes this folder's `overlay/stub-injection.txt` to the agent prompt
overlay seam (appended to the system prompt on the agent's next run); `reset`
clears it. The payload is deliberately benign. Real injection/PII payloads for the
Firewall vignette are authored in Phase 4+.
