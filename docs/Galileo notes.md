# Galileo notes

Galileo is a Gen AI reliability platform, the trust layer for Gen AI applications.

## problem definition

Gen AI applications are based on fundamentally probebailistic models. They are inherently unreliable and a trust layer is needed to use this technology in production.

### challenges with Gen AI:

_in development_

- feedback is hard to implement
- manual evals of quality

_in production_

- curating a high-quality test set is a pain
- AI assisted evaluations are not reliable enough.
- at scale, ai assisted evals are expensive
- at scale, no way to firewall outputs

### Reliability challenges:

- eval accuracy
    - 1 in 3 evals are wrong
- observability oversight
    - can't measure what you can't see
- guardrail control
    - can't govern without accurate coverage

### why agent observability matters and is different from 'traditional' APM

- AI Agentes are becoming part of strategic and business processes
- AI agents are non-deterministic
- Failures are soft, no crashes no errors, but (not so) sobtle degraded quality
- Errors compound in multi step agents
- Traditional APM tells you nothing about the contents of responses

AI observability

- captures every step of an agents reasoning
    - tool calls, retrieval etc.
- Sessions -> traces -> spans
- Enrich with metrics (safety, llm as a judge)

Metrics, are quality metrics. Is the agent doing what it should be doing?

## What is eval engineering and why does it matter?

Eval engineering is the practice of creating rules and matrics that provide insights into the workings of an AI Agent application. It is critical for reliability because it provides a way to understand how well an AI Agent is performing, and whether it is meeting its objectives. Without eval engineering, it is difficult to know if an AI Agent is working as intended, or if it is degrading in quality over time.

## Galileo multi agent architecture

It can plug in 1st party agents, develeoped by the company itself, as well as 3rd party agents, like copilot add galileo guardrails
