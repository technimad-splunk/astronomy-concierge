# Store FAQ (OVERLAY variant — shadows the baseline doc of the same name)

This file has the SAME filename as a baseline knowledge doc
(`agent/knowledge/store-faq.md`), so the `rag_corpus` overlay shadows the baseline
copy while it is active — proving same-name replacement is non-destructive (the
baseline file on disk is never modified; reset restores it exactly).

## Stub marker
HARNESS_STUB_FAQ_SHADOW_ACTIVE — this is fixture text, not real store policy.
