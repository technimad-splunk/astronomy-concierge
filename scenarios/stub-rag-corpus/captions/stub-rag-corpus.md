# [harness stub] rag_corpus trigger

**Not a vignette.** Phase-3 harness fixture proving the `rag_corpus` trigger:
`play` overlays this folder's `corpus/*.md` onto `agent/knowledge` (adding a new
doc and shadowing one same-named baseline doc, non-destructively); `reset` drops
the overlay and restores the baseline corpus exactly. Real vignette corpora are
authored in Phase 4+.
