# QA and CI/CD in agent graphs

Research on two questions from the v1 design session:

1. What does a QA role do in a multi-agent graph, if the engineer already writes and runs the tests?
2. Is CI/CD part of the agent graph, or is it handled separately?

- Research date: 2026-09-25
- Sources: web search and the Zoomcamp article summaries in `docs/references/summaries/`. Vendor sources are marked. They sell testing agents and are not neutral.
- Status: research input. The owner's decisions are in the v1 spec.

---

## 1. The QA role

### Findings

- **Zoomcamp (Articles 1 and 5).** QA checks against the criteria, runs the full test suite, and reports PASS or FAIL. The reason for a separate agent is a fresh context without implementation bias. The role is thin: a second pair of eyes.
- **Testing-agent vendors (DevAssure, TestSprite, Autonoma; vendor sources).** Tests written by the coding agent come from the same understanding of the task. They check that the code does what the author believes it should do. A separate checker should run the real result against real scenarios (app, CLI, browser), not re-read or re-run the author's tests.
- **First Mate (reported by developer-tech).** The checker designs the test cases and reviews the code. A different model implements and runs the tests.
- **AgentForge (research paper).** Separate Tester role with execution in a sandbox. Execution feedback and role separation each improve results.

### Three kinds of check

| Check | Question | Evidence |
|---|---|---|
| Reviewer | Is the code good (quality, risk)? | Reading the diff |
| QA | Does the result do what each criterion says? | Running the behavior of each criterion |
| CI | Does it work outside the local machine? | Tests in a clean environment |

### Conclusions

- If QA only re-runs the engineer's tests, QA adds almost nothing. The engineer already ran them in the same checkout.
- The value of QA is independent execution: exercise each criterion, and judge if a test really covers the criterion or only mirrors the implementation.
- "Works on my machine" is a CI problem. QA runs in the same checkout and cannot find it.
- Independent test design by the checker (First Mate pattern) is a stronger option. Use it only if QA often finds missing tests.

## 2. CI/CD and the agent graph

### Findings

- **Common pattern (DeployHQ, Zoomcamp Article 3).** The pipeline stays deterministic. An agent opens a PR. CI runs the tests. A human reviews and merges. Deployment is gated on passing tests. Production needs a manual approval.
- **Zoomcamp Article 4.** Automatic deploy to dev, manual promotion to prod. The "AI on-call engineer" is a separate observe/respond loop: an alert starts a headless agent that finds the cause and commits a fix. It is not a node in the issue graph.
- **Agent-operated CI/CD (Alex Lavaee).** A CI failure or an alert triggers an agent that diagnoses and opens a fix. Specialized agents have scoped permissions. High-risk actions (production deploy) need human approval.
- **GitHub Agentic Workflows.** Agents run inside GitHub Actions. This is the opposite direction (the agent lives in CI). It does not fit a kit where the Claude main session is the orchestrator.

### Conclusions

- Agents touch CI/CD at two points: the CI result as a fact at a gate (merge or close), and a CI failure or alert as input that starts a fix.
- Setting up CI/CD and deploying are one-time or occasional procedures. A skill fits better than a team role (Zoomcamp Article 5 uses a `release` skill as an example). Roles are for steps that repeat on each issue.

---

## Sources

- DevAssure: https://www.devassure.io/blog/why-coding-agents-cant-test/ (vendor)
- developer-tech: https://www.developer-tech.com/news/ai-coding-agents-test-own-code/
- TestSprite: https://www.testsprite.com/blog/do-ai-coding-agents-need-a-separate-testing-agent (vendor)
- Autonoma: https://getautonoma.com/blog/ai-coding-agent (vendor)
- AgentForge: https://arxiv.org/html/2604.13120v1
- DeployHQ: https://www.deployhq.com/blog/ai-agents-cicd-pipelines-github-issue-to-production-deploy
- Alex Lavaee: https://alexlavaee.me/blog/agent-operated-cicd-pipelines/
- InfoQ on GitHub Agentic Workflows: https://www.infoq.com/news/2026/02/github-agentic-workflows/
- Zoomcamp Articles 1, 3, 4, 5: see `docs/references/summaries/`
