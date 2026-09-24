# Jev Usage Documentation

Research on Jev (TypeSafe AI) for use in an AI-native, multi-agent Graph Engineering setup.

- Research date: 2026-09-24
- Model version at research date: `jev-1.13.0` (released 2026-09-15, early access)
- Language: ASD-STE100 Simplified Technical English
- Status: research input for brainstorming. This document does not contain design decisions.

---

## 1. Summary

1. Jev is a "System One" decision model. It does not generate text or code.
2. You send a **state** (text or JSON) and a set of typed **questions**. Jev returns typed answers with probabilities.
3. Jev is **not an agent**. It cannot read files, call tools, or act. Code must build the state and act on the answer.
4. TypeSafe says clearly: Jev is not a replacement for the LLM in Claude Code or Codex.
5. Thus, Jev cannot be a node (a subagent) in the graph like Codex or Lovable. Jev can be a **decision function on the edges** of the graph: a router, a gate, or a check.
6. Jev is very cheap: $0.042 per 1M input tokens. Output tokens are free. The cost target (< $2 per project) is easy to meet.
7. Jev is fast: approximately 70 ms to 500 ms per call.
8. Jev is good at narrow, common-sense judgments. Jev is bad at math, dates, counting, multi-hop reasoning, large state, and text generation.
9. A strong community rule: "Facts go to code. Judgments go to Jev. Only facts can block." (Canny project)

---

## 2. What Jev is

### 2.1 Core model

| Item | Value |
|---|---|
| Vendor | TypeSafe AI (founder: Diogo Almeida, ex-OpenAI, RLHF / ChatGPT research) |
| Launch | 2026-09-15, early access. Open signup since 2026-09-20 with $5 credit |
| Model class | "System One model" (name from Kahneman, *Thinking, Fast and Slow*) |
| Training | "Reinforcement Learning for Calibrated Decisions" (RLCD). Architecture not disclosed |
| Input | Text only: string, JSON object, or array of text values |
| Output | Typed answers + probabilities (+ confidence for Choice and Score) |
| Endpoint | `POST https://api.typesafe.ai/v1/systemone` |
| Other providers | OpenRouter (`typesafe/jev-1.13`), Cloudflare AI, Vercel AI Gateway, Netlify AI Gateway |

### 2.2 The three primitives (question types)

| Type | Use it for | Returns |
|---|---|---|
| **Choice** | Select one option from a defined set (max. 255 options) | `choice`, `probabilities`, `confidence` |
| **Score** | Rate the state on ordered, described levels | `score`, `probabilities`, `confidence` |
| **Noul** | Get the probability that a statement is true | `noul` (0 to 1). No confidence field |

Rules for all three types:

- One request can contain many questions of mixed types.
- Jev evaluates each question in parallel and in isolation against the same state.
- One question cannot see the answer of another question.
- More questions add almost no latency. Each question adds only its own tokens.
- Question IDs are for your code. Jev does not see them. Put the full meaning into `instructions`.
- You can point a question at a part of the state with a backtick path, for example `` `task.acceptance_criteria[2]` ``.
- `instructions` and `criteria` can be strings or JSON objects (for example `what`, `not_for`, `examples`).

### 2.3 Example request and response

Request:

```json
{
  "model": "jev-1.13.0",
  "state": {
    "task_title": "Add login page",
    "task_body": "Users need a login form with email and password."
  },
  "questions": {
    "lane": {
      "type": "choice",
      "instructions": "Which part of the system does `task_body` change?",
      "criteria": {
        "frontend": "UI pages, components, styles",
        "backend": "API, database, business logic",
        "infra": "Docker, CI/CD, deployment"
      }
    },
    "needs_grooming": {
      "type": "noul",
      "instructions": "Does `task_body` leave the expected behavior unclear?"
    }
  }
}
```

Response (shape):

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "lane": { "type": "choice", "choice": "frontend", "confidence": 0.81,
              "probabilities": { "frontend": 0.87, "backend": 0.12, "infra": 0.01 } },
    "needs_grooming": { "type": "noul", "noul": 0.74 }
  },
  "usage": { "input_tokens": 210, "output_tokens": 40 }
}
```

Note: the numbers above are an illustration. They are not a real Jev result.

### 2.4 Confidence

- `confidence` shows how concentrated the probability distribution is. 1.0 means all probability is on one option.
- Confidence is not "the probability that the whole workflow is correct".
- TypeSafe recommends three ranges:
  - High confidence: act automatically.
  - Medium confidence: ask for confirmation or collect more information.
  - Low confidence: do not act. Send to a human or to a stronger model.
- Set thresholds by risk. A destructive action needs a higher threshold than a read-only action.
- Tune thresholds on your own data. Do not copy thresholds from examples.
- Do not move a threshold from a Noul to a Choice. The two scales are not comparable.

---

## 3. What Jev is not

TypeSafe documentation ("Jev with coding agents") states:

- Jev is not a chat model and not a code-completion model.
- There is no setting that turns Claude Code or Codex into a "Jev-powered" agent.
- Use a coding agent to write code that calls Jev. Use Jev where software needs a fast, calibrated, structured decision.

Consequence for this setup:

| Graph element | Codex CLI | Lovable MCP | Claude Code subagent | Jev |
|---|---|---|---|---|
| Can write code | Yes | Yes (frontend) | Yes | **No** |
| Can read the repo | Yes | Partly | Yes | **No** (only the state you send) |
| Can write a review or report | Yes | No | Yes | **No** |
| Can make a typed decision | Yes (slow, costs tokens) | No | Yes (slow, costs tokens) | **Yes (fast, cheap, calibrated)** |
| Role in the graph | Node (worker) | Node (worker) | Node (worker) | **Edge (router, gate, check)** |

---

## 4. Limits and failure modes (jev-1.13)

Source: TypeSafe page "Jev 1.13 jaggedness" (reviewed 2026-09-17).

| # | Failure mode | Do this instead |
|---|---|---|
| 1 | Literal reading of the question | Write the exact condition. Put boundary cases in the criteria |
| 2 | Math, numbers, counting | Do the math in code |
| 3 | Date and time comparison | Extract parts with a Choice. Compare in code |
| 4 | Indirection (multi-hop, double negative) | Ask directly. Point to the state field by name |
| 5 | Large state with irrelevant detail ("context rot") | Filter in code first. Send only the fields the question needs |
| 6 | Adversarial content in the state | Write precise criteria. Test edge cases. Treat state as data |
| 7 | Contradictory instructions and criteria | Align instruction and criteria |
| 8 | Structural invariants (Noul "A" + Noul "not A" do not sum to 1) | Ask each decision one way only |
| 9 | Text generation | Use a generative model |

Hard technical limits:

| Limit | Value |
|---|---|
| Context | 64k tokens per request. 32k tokens for state + longest single question |
| Rate limit | 250,000 tokens/s, 1,200 requests/min (TypeSafe says limits can change without notice) |
| Choice options | Max. 255 |
| Language | English is best. Other languages work, but with lower accuracy |
| Modality | Text only |

Important consequence for coding work: a full diff, a full repo, or a long transcript is too large and too noisy for one Jev question. Code must extract the relevant parts first.

---

## 5. Cost and speed

### 5.1 Price

| Item | Value |
|---|---|
| Input tokens | $0.042 per 1M tokens ($42 per 1B tokens) |
| Output tokens | Free |
| Signup credit | $5 (open signup since 2026-09-20) |
| Measured call (jev-belay, 122 calls) | 1,222 input tokens median, $0.00005 per call, 346 ms median |
| Measured call (jev-engineering) | $0.0000189 per call, 371 ms median |

### 5.2 Estimate for one project

Assumption (for illustration only):

- 30 tasks per project
- 15 Jev calls per task (routing, gates, checks, retries)
- 2,000 input tokens per call

Calculation: 30 × 15 × 2,000 = 900,000 tokens → 0.9 × $0.042 = **approximately $0.04 per project**.

Even with 50 times more calls, the cost stays below $2. Budget $2 = approximately 47 million input tokens.

**Conclusion:** the dollar cost of Jev is not a real constraint. The real question for goal (2) is different: does Jev **reduce Claude Code and Codex usage** (subscription usage windows), or does it only add calls?

### 5.3 Where token savings can come from

Jev itself does not save tokens. Savings come only when a Jev decision **stops** expensive LLM work. Examples from the community:

| Mechanism | How it saves Claude/Codex usage | Example project |
|---|---|---|
| Skip unnecessary steps | A simple task skips PM grooming or a second review | intent routing (TypeSafe pattern) |
| Model / effort routing | Easy tasks go to a smaller model or lower reasoning effort | Switchboard, jev-router, Jevonian, opencode-jev-orchestrator |
| Keep content out of context | Jev filters files or tool results before they enter the LLM context | winnow, fast-jev-compaction, agent-fastpath |
| Stop bad loops early | Jev detects "stuck" or "off track" and stops the loop | Foreman, pi-warden |
| Avoid wasted QA cycles | A cheap check catches an unverified "done" before a full QA run | jev-belay, Canny |

Where token costs can **increase**:

- The orchestrator LLM must build the state for Jev. If Claude writes the state, Claude spends tokens.
- An MCP tool call costs orchestrator tokens (tool schema + call + result).
- A hook or a script that builds the state from files with code costs no LLM tokens.

---

## 6. Integration surfaces for Claude Code and Codex

| Surface | Who decides to call Jev | Who builds the state | LLM token cost of the decision | Best for |
|---|---|---|---|---|
| **Hook** (Stop, PreToolUse, UserPromptSubmit, SubagentStop) | Code (always runs) | Code (reads transcript, files, git) | None | Gates that must always run |
| **CLI script** (for example `uv run jev_gate.py`) called by the orchestrator | Orchestrator LLM | Script (code) | Small (one bash call + JSON result) | Routing steps in `process.md` |
| **MCP server** (community) | Orchestrator LLM | Orchestrator LLM | Medium (tool schema + state in the call) | Ad hoc questions, exploration |
| **External orchestrator** (Python program owns the graph) | Code | Code | None | Full "code owns control flow" design |
| **TypeSafe agent skill** (official) | n/a | n/a | n/a | Teaches the coding agent to **write** Jev code. It does not make decisions |

### 6.1 Official TypeSafe skill

Install in Claude Code:

```bash
claude plugin marketplace add typesafe-ai/skills
claude plugin install typesafe@typesafe-ai
```

Install in other agents (for example Codex):

```bash
npx skills add typesafe-ai/skills --skill typesafe-ai
```

Use: the skill helps a coding agent design questions and write integration code. TypeSafe notes that agents are not good at writing questions. Keep questions and thresholds in one file and review them.

### 6.2 Python SDK

```bash
uv add typesafe-sdk
```

```python
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

client = TypeSafeClient(model="jev-1.13.0")  # Pin the version. Aliases move.
response = client.system_one(state={...}, questions={...})
answer = response.answers["lane"]
print(answer.choice, answer.confidence)
```

Notes:

- The client reads `TYPESAFE_API_KEY` from the environment.
- The SDK retries with backoff on rate limits.
- Python SDK 0.7.0 (2026-09-18) changed serialization from `msgspec` to Pydantic. This is a breaking change.

### 6.3 Community MCP servers (examples, not verified by me)

| Project | Notes |
|---|---|
| `lhviet/jev-bridge` | Zero-dependency MCP server. Local answer cache. Cost tracking. Tested in real Claude Code sessions |
| `rashedInt32/jev-mcp` | classify / score / check / batched ask. Ships as a Claude Code plugin |
| `codaaiteam/jev-mcp` | classify / score / check + gate for risky tool calls |
| `abhishekswe/agent-fastpath` | Ship gates, risk checks, file triage that keeps files out of context |

All community projects are 1 to 9 days old at the research date. Examine the code before you use it. Keep the API key in the environment, not in the repo.

---

## 7. Community patterns relevant to Graph Engineering

| Pattern | Project | What Jev decides | Key lesson |
|---|---|---|---|
| "Done" claim gate | `valentynkit/jev-belay` (Stop hook) | Does the closing message claim "done" without a passing check? | Code checks the facts first (regex on transcript). Jev is called only in 17.7% of stops. AUROC 0.976 with facts vs 0.777 on wording alone |
| Evidence ledger | `qkal/Canny` (Claude Code + Codex hooks) | Judgments only (does a message claim done, does a diff break a rule) | "Facts go to code. Judgments go to Jev. Only facts can block." |
| Supervisor above workers | `thruwire/foreman` (Codex/OpenCode workers) | implementation_complete, tests_sufficient, worker_stuck, needs_human, agents_md_drift | A second loop watches the worker. It steers, stops, or asks for verification |
| Capability router | `BillionsBobby/JevRouter` | Which model, subagent, skill, MCP tool or CLI handles the next step | Jev owns probabilities. Code owns availability, permissions, risk, confirmation |
| Escalation to strong model | `aaronshaf/opencode-jev-orchestrator` | Is this turn hard, easy, or unsure? | Cheap parent model stays. Strong model runs only in a child for hard turns |
| Model + effort routing | Switchboard, jev-router, Jevonian | Model and reasoning effort per task | Keep the choice stable in a conversation to keep the prompt cache |
| Skill routing | `shimo4228/jev-skill-router` | Which skill fits the prompt (or none) | Start in shadow mode: log only, do not act |
| Commit check | `valentynkit/jev-commit` | Does the commit message match the staged diff? | Block only on facts (credential found) |
| Rule compliance | `doeixd/jev-pref`, `lakeday-org/perch` | Does a code change follow project preferences? | Feed findings back to the coding agent |
| Tool-call gate | `eugeniughelbur/jev-engineering` | Is a shell command dangerous? | Hard rules first. Jev for the long tail |
| Context filter | `GhalebDweikat/winnow`, `tamaratran/fast-jev-compaction` | Is this tool result relevant enough to enter context? | Saves LLM context. Omitted content cannot be proven unnecessary |

Rollout pattern seen in several projects (BotNexus issue #4314, jev-skill-router, jev-engineering):

1. **Shadow mode**: Jev decides, code logs the decision, nothing changes.
2. **Advisory mode**: the orchestrator sees the decision and can follow it.
3. **Enforcing mode**: code acts on the decision. Only for decisions with measured accuracy.

---

## 8. Evidence on decision quality

| Source | Result | Meaning for this setup |
|---|---|---|
| TypeSafe workflow evals (vendor) | Claims 193.6x faster, 444.6x cheaper than LLMs on their workflows | Vendor numbers. TypeSafe says these are "on the higher end" of real gains |
| Independent calibration study (Nautilus, 240 questions) | Accuracy 92.2%, Brier 0.048, ECE 0.041 | Good calibration on normal questions |
| "Jev Does Not Play Dice" | On inputs with known random probabilities, Choice put 82.9% on one die face. A stated 30% risk became 5.3% | Calibration is weaker when the true answer is itself uncertain |
| jev-decision-benchmarks: BFCL V4 | 87.5% correct action, 86.7% correct abstention (better than several frontier LLMs) | Good at "should I act?" when the options are clear |
| jev-decision-benchmarks: When2Call | Selected "tool call" in 76% of cases where "cannot answer" was correct | Jev tends to pick an action. Design an explicit "none / escalate" option and gate it |
| jev-engineering injection test (300 calls) | Blunt injection: 0/30 dangerous passed, 10% safe blocked. "Owner approved this" framing: 3/30 passed | Repo content (issues, comments) can steer Jev. Do not let Jev alone approve risky actions |
| jev-belay (100 labeled stops) | AUROC 0.976 when code supplies facts | Quality comes from good state built by code, not from the model alone |

General conclusion: Jev gives a calibrated **second opinion on narrow questions**. It cannot judge "is this implementation correct?" as one question. Decompose such judgments into atomic checks, and let tests supply the facts.

---

## 9. Assessment against the four goals

This section is my assessment. It is not a decision.

| Goal | Expected effect | Condition for success | Risk |
|---|---|---|---|
| (1) Speed | Positive, but indirect. A Jev call is fast (< 0.5 s). The real gain is fewer LLM steps and fewer human stops | Jev must replace an LLM step or a human wait, not only add a check | Extra gates add latency and failure points if they do not skip work |
| (2) Tokens / cost | Dollar cost: safe (approx. $0.04 per project). Claude/Codex usage: possible reduction | Code (hooks, scripts) builds the state. Jev decisions skip or downsize LLM work | If the orchestrator LLM builds state for Jev, usage can increase |
| (3) Decision quality | Positive for narrow, checkable decisions (routing, gates, AC checks) | Atomic questions, small state, facts from code, thresholds tuned on own data | Literal reading, bias to act, injection from repo text, large diffs |
| (4) Human feedback | Strong fit. Confidence-gated routing decides when to ask the human | Clear three-band policy per decision type | Thresholds that are too strict create "permission prompts with extra steps" |

---

## 10. Recommended rules if we integrate Jev

These are recommendations from the research. We decide in the brainstorming.

1. Use Jev only on the edges of the graph (routing, gates, checks). Do not model Jev as an agent role.
2. Let code build the state. Prefer hooks and scripts over MCP calls for recurring decisions.
3. Ask atomic questions. Ask many questions in one call. Combine answers in code.
4. Keep all questions and thresholds in one reviewed file per repo (for example `_docs/jev/questions.py`).
5. Include an explicit "none / escalate" option in every Choice.
6. Use three confidence bands per decision: act, ask, escalate.
7. Only facts (tests, exit codes, git state) can block. Jev can route, warn, or escalate.
8. Pin the model version (`jev-1.13.0`). Re-tune thresholds when the version changes.
9. Start every new decision in shadow mode. Log state, questions, answers, and outcome.
10. Define the failure behavior. If the Jev API is down, fall back to the default path (fail open) for routing, and to the human for approvals.
11. Keep the API key in the environment (`TYPESAFE_API_KEY`). Never commit it.
12. Measure: Claude/Codex usage per task, wall time per task, human interventions per task, QA FAIL rate. Compare with and without Jev.

---

## 11. Open questions for verification (spike candidates)

1. How accurate is Jev on **our** decisions (for example lane routing: frontend vs backend vs infra) with our issue texts?
2. How large is a typical groomed issue in tokens? Does it fit the 32k state limit with margin?
3. Can a Claude Code hook build the state for a QA pre-check without LLM help (test output + acceptance criteria)?
4. How does the Codex CLI hook model compare to Claude Code hooks for the same gates?
5. What is the real reduction in Claude/Codex usage for 5 to 10 tasks, with and without Jev routing?

---

## 12. Sources

Official:

- TypeSafe documentation index: https://docs.typesafe.ai/llms.txt
- Introduction: https://docs.typesafe.ai/introduction
- Jev with coding agents: https://docs.typesafe.ai/introduction/coding-agents.md
- Quick start: https://docs.typesafe.ai/introduction/quickstart.md
- How to build with TypeSafe: https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md
- Confidence: https://docs.typesafe.ai/confidence.md
- Intent routing: https://docs.typesafe.ai/patterns/intent-routing.md
- Jev 1.13 jaggedness: https://docs.typesafe.ai/model-jaggedness/jev-1.13.md
- Models, limits, pricing: https://docs.typesafe.ai/models.md
- Agent skill: https://docs.typesafe.ai/agent-skill.md
- Skill source: https://github.com/typesafe-ai/skills
- Launch post: https://typesafe.ai/blog/introducing-system-one-models-and-jev

Community and third party:

- Curated list: https://github.com/cobanov/awesome-jev
- jev-belay: https://github.com/valentynkit/jev-belay
- Canny: https://github.com/qkal/Canny
- Foreman: https://github.com/thruwire/foreman
- JevRouter: https://github.com/BillionsBobby/JevRouter
- opencode-jev-orchestrator: https://github.com/aaronshaf/opencode-jev-orchestrator
- jev-engineering: https://github.com/eugeniughelbur/jev-engineering
- jev-decision-benchmarks: https://github.com/baibizhe/jev-decision-benchmarks
- jev-bridge (MCP): https://github.com/lhviet/jev-bridge
- BotNexus evaluation issue: https://github.com/sytone/botnexus/issues/4314
- LangChain: https://www.langchain.com/blog/building-a-harness-with-jev
- MarkTechPost: https://www.marktechpost.com/2026/09/19/typesafe-ai-releases-jev/
- Firecrawl: https://www.firecrawl.dev/blog/what-is-jev
- Flavio Copes: https://flaviocopes.com/jev/

Workflow reference:

- AI-Native Development: Specifications, Loop and Graph Engineering: https://aishippingblog.com/p/ai-native-development-specifications
