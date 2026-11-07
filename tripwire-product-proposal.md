# Tripwire

Nov 7, 2026 · Jason Daniel B · Flip the Switch hackathon, Track 01 (Best Business Workflow)

Tripwire is an on-call agent for AI agents. It watches an agent's traces, catches runaway behavior (loops, silent errors, cost spikes), and fixes it in a Slack thread. It never touches production without an owner's approval.

**Problem.** An LLM agent stuck in a loop burns money and fails users quietly. Dashboards show it after the fact. Nobody is paged, and nobody can stop it from chat.

**Who.** Teams running LLM agents in production. The demo watches `order-lookup`, a deliberately buggy order-support agent.

## How it works

```mermaid
flowchart LR
    A[order-lookup agent] -->|traces| L[(Langfuse)]
    L -->|poll every 15s| D[Detector<br/>3 rules]
    D -->|alert| S[Switch room<br/>= Slack thread]
    S --> T[Tripwire<br/>Claude Code agent]
    T --> I[Investigator subagent<br/>fresh context]
    I -->|cause, action, fix| T
    T -->|propose| S
    O((Owner)) -->|approve| S
    T -->|contain| C[Containment service]
    C -->|route flags| A
    T -->|open PR| G[GitHub]
    D -.->|no reply: auto-pause| C
```

| Part | What it is |
| --- | --- |
| Detector | Python loop. Reads Langfuse, runs the rules, posts one alert per incident. |
| Tripwire | Claude Code agent in Switch. Talks in the thread, never acts without approval. |
| Investigator | Read-only subagent. One fresh context per incident, so Tripwire's session stays small. |
| Containment service | FastAPI. The only thing that changes production. Enforces every rule below. |
| Agent | Reads its route flags before every step, so containment works mid-run. |

## Features

### 1. Detect

```mermaid
flowchart LR
    L[(Langfuse traces)] --> R{Rule fires?}
    R -->|loop: same call 5x or 25 steps| N[New incident INC-n]
    R -->|silent error: 3 in 5 min| N
    R -->|cost spike: 5x median or $1 a trace| N
    R -->|no| L
    N --> Q{Same cause already open?}
    Q -->|yes| U[Add to that incident]
    Q -->|no| P[Post one alert to the room]
```

### 2. Investigate

```mermaid
flowchart LR
    P[Alert in room] --> T[Tripwire starts a thread]
    T --> I[Investigator subagent<br/>reads traces, flags, code]
    I --> R[Cause, burn per hour,<br/>one action, fix plan, patch]
    R --> M[One 5-line message:<br/>cause, burn, proposed action]
```

### 3. Contain (approval 1)

```mermaid
flowchart LR
    M[Proposal] --> O{Owner replies}
    O -->|approve INC-n| C[Containment service]
    O -->|decline INC-n| W[Ask why, revise once]
    W --> M
    C --> K{Owner? on menu?<br/>one action per round?}
    K -->|yes| A[Apply: disable route,<br/>cap steps, or fallback model]
    K -->|no| X[Refuse, show reason]
```

### 4. Fix (approval 2)

```mermaid
flowchart LR
    A[Contained] --> F[Post fix plan]
    F --> O{Owner replies}
    O -->|fix INC-n| PR[Open GitHub PR<br/>from the subagent's patch]
    O -->|skip-fix INC-n| H[Human writes the fix]
    PR --> R[Owner reviews and merges]
```

### 5. Revert and verify

```mermaid
flowchart LR
    D[Fix deployed] --> R[Owner: revert INC-n]
    R --> V[Route back on, verifying]
    V --> Q{5 quiet minutes?}
    Q -->|yes| OK[Resolved, record written]
    Q -->|bug again| RE[Reopen incident]
```

### 6. Safety net

```mermaid
flowchart LR
    I[Incident open, no approval] --> T{10 min, no owner reply?}
    T -->|yes| P[Auto-pause: disable route]
    I --> M{Spend at half the<br/>$50 loss budget?}
    M -->|yes| P
    I --> H{Route over $50 an hour?}
    H -->|yes| P
    P --> RV[Offer revert INC-n]
```

A decline counts as a reply, so it stops the 10-minute timer. The money limits always apply.

## Guardrails

- Only listed owners can approve, and every approval names the incident: `@tripwire approve INC-8`.
- The menu has three actions. Anything else is refused by the containment service.
- Trace text is data. Instructions found inside a trace are ignored and reported.
- Tripwire gets 20 tool calls and 3 minutes per round, then hands off to a human.
- One thread per incident. Messages are at most six lines.

## Stack

Python 3.12, FastAPI, Langfuse (self-hosted), Switch + Slack, Claude Code, Together AI (`zai-org/GLM-5.3-Flash` for the demo agent), Docker Compose. 430+ tests.
