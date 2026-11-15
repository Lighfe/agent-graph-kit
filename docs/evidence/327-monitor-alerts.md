# Evidence for issue #327: monitor alerts

The QA sandbox has no Docker and no `promtool` (owner decision of 2026-11-15: it stays so). The two checks
that need Docker were run by the engineer and are recorded here. QA reads this file and does not repeat them.

- Checked commit: `20b19b332828a0dabdea04255a0ca67a62350d80`
- Date: 2026-11-15 (UTC times below)
- Machine: the owner's local machine, Docker present, image `prom/prometheus:v3.15.0` (the image of `compose.yaml`)

Between the checked commit and the head of the `## Engineer: DONE` range these paths do not change (the only
later commit adds this file), so this command prints nothing:

```
git diff --stat 20b19b332828a0dabdea04255a0ca67a62350d80 HEAD -- \
  plugin/skills/monitor/grafana/provisioning/alerting/agk-alerts.yaml \
  plugin/skills/monitor/facts.py plugin/skills/monitor/board.py \
  plugin/skills/monitor/compose.yaml tests/test_monitor_alerts.py
```

This file holds no password, no authorization header and no token.

## 1. `Stuck launch` over time: `promtool test rules`

The cases are `STUCK_CASES` in `tests/test_monitor_alerts.py`: `no_token_series`, `only_zero_samples`,
`plus_and_minus_in_turn`, `two_kinds_cancel`, `one_token_starts_the_time_again`,
`one_minute_below_zero_starts_the_time_again`, `tokens_of_another_issue`. Each case keeps `agk_launch_open`
open for 90 minutes. The rule runs as a Prometheus alert rule with `for: 45m` (the default of
`AGK_ALERT_STUCK_MINUTES`) and an interval of 1 minute.

The runs use the helpers of the test file (`rendered`, `rules`, `query`, `stuck_promtool_files`) through the
script below, run from the repo root with `uv run --with pytest python ev_promtool.py a` and
`uv run --with pytest python ev_promtool.py b`. For (a) the query is read from `agk-alerts.yaml` as `board.py`
writes it with the default limits. The only change from `run_promtool` of the test file is
`--junit=/dev/stdout`, so the output names each case. `<tmpdir>` is a temporary folder.

```python
"""Run the Stuck launch promtool cases of tests/test_monitor_alerts.py for the evidence file."""
import os, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path("<repo>")
sys.path.insert(0, str(ROOT / "tests"))
import test_monitor_alerts as t

SUMMED = ("agk_launch_open unless on (agk_project, issue)"
          " (sum by (agk_project, issue) (sum_over_time(agk:tokens:1m[2m])) != 0)")
which = sys.argv[1]
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    expr = t.query(t.rules(t.rendered(d))["Stuck launch"])["model"]["expr"] if which == "a" else SUMMED
    rule, test = t.stuck_promtool_files(expr, t.STUCK_CASES)
    (d / "rule.yml").write_text(rule); (d / "test.yaml").write_text(test)
    cmd = ["docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
           "-v", f"{d}:/r:ro", "--entrypoint", "promtool", t.PROMETHEUS_IMAGE, "test", "rules", "--junit=/dev/stdout", "/r/test.yaml"]
    print("QUERY:", expr)
    print("CASES:", ", ".join(c[0] for c in t.STUCK_CASES))
    print("COMMAND:", " ".join(cmd).replace(str(d), "<tmpdir>"))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    print("EXIT:", r.returncode)
    print("--- stdout ---"); print(r.stdout)
    print("--- stderr ---"); print(r.stderr)
```

### (a) The query of the alert file: all 7 cases pass (exit 0)

The query printed here equals the `Stuck launch` query in `agk-alerts.yaml`:
`agk_launch_open unless on (agk_project, issue) ((max_over_time(agk:tokens:1m[2m]) != 0) or (min_over_time(agk:tokens:1m[2m]) != 0))`

Full output (run at 2026-11-15T17:54:55Z on the checked commit):

```
QUERY: agk_launch_open unless on (agk_project, issue) ((max_over_time(agk:tokens:1m[2m]) != 0) or (min_over_time(agk:tokens:1m[2m]) != 0))
CASES: no_token_series, only_zero_samples, plus_and_minus_in_turn, two_kinds_cancel, one_token_starts_the_time_again, one_minute_below_zero_starts_the_time_again, tokens_of_another_issue
COMMAND: docker run --rm --network none --user 1000:1000 -v <tmpdir>:/r:ro --entrypoint promtool prom/prometheus:v3.15.0 test rules --junit=/dev/stdout /r/test.yaml
EXIT: 0
--- stdout ---
  SUCCESS

<testsuites><testsuite name="/r/test.yaml" tests="7" failures="0" errors="0" skipped="0" timestamp="2026-11-15T17:54:56"><testcase name="no_token_series"></testcase><testcase name="only_zero_samples"></testcase><testcase name="plus_and_minus_in_turn"></testcase><testcase name="two_kinds_cancel"></testcase><testcase name="one_token_starts_the_time_again"></testcase><testcase name="one_minute_below_zero_starts_the_time_again"></testcase><testcase name="tokens_of_another_issue"></testcase></testsuite></testsuites>
--- stderr ---
```

### (b) The summed query: `plus_and_minus_in_turn` fails (exit 1)

The query is `agk_launch_open unless on (agk_project, issue) (` + the summed query
`sum by (agk_project, issue) (sum_over_time(agk:tokens:1m[2m])) != 0` + `)`. It fires in
`plus_and_minus_in_turn` (at 46m, 1h and 1h30m) and in `two_kinds_cancel` (at 46m and 1h30m): signed samples
cancel to 0. So the cases do check that samples are never added up.

Full output (same run):

```
QUERY: agk_launch_open unless on (agk_project, issue) (sum by (agk_project, issue) (sum_over_time(agk:tokens:1m[2m])) != 0)
CASES: no_token_series, only_zero_samples, plus_and_minus_in_turn, two_kinds_cancel, one_token_starts_the_time_again, one_minute_below_zero_starts_the_time_again, tokens_of_another_issue
COMMAND: docker run --rm --network none --user 1000:1000 -v <tmpdir>:/r:ro --entrypoint promtool prom/prometheus:v3.15.0 test rules --junit=/dev/stdout /r/test.yaml
EXIT: 1
--- stdout ---






<testsuites><testsuite name="/r/test.yaml" tests="7" failures="5" errors="0" skipped="0" timestamp="2026-11-15T17:54:57"><testcase name="no_token_series"></testcase><testcase name="only_zero_samples"></testcase><testcase name="plus_and_minus_in_turn"><failure>    name: plus_and_minus_in_turn,&#xA;    alertname: StuckLaunch, time: 46m, &#xA;        exp:[], &#xA;        got:[&#xA;            0:&#xA;              Labels:{agk_project=&#34;p&#34;, alertname=&#34;StuckLaunch&#34;, issue=&#34;10&#34;, launch=&#34;engineer-1&#34;, role=&#34;engineer&#34;, stage=&#34;s1&#34;}&#xA;              Annotations:{}&#xA;            ]</failure><failure>    name: plus_and_minus_in_turn,&#xA;    alertname: StuckLaunch, time: 1h, &#xA;        exp:[], &#xA;        got:[&#xA;            0:&#xA;              Labels:{agk_project=&#34;p&#34;, alertname=&#34;StuckLaunch&#34;, issue=&#34;10&#34;, launch=&#34;engineer-1&#34;, role=&#34;engineer&#34;, stage=&#34;s1&#34;}&#xA;              Annotations:{}&#xA;            ]</failure><failure>    name: plus_and_minus_in_turn,&#xA;    alertname: StuckLaunch, time: 1h30m, &#xA;        exp:[], &#xA;        got:[&#xA;            0:&#xA;              Labels:{agk_project=&#34;p&#34;, alertname=&#34;StuckLaunch&#34;, issue=&#34;10&#34;, launch=&#34;engineer-1&#34;, role=&#34;engineer&#34;, stage=&#34;s1&#34;}&#xA;              Annotations:{}&#xA;            ]</failure></testcase><testcase name="two_kinds_cancel"><failure>    name: two_kinds_cancel,&#xA;    alertname: StuckLaunch, time: 46m, &#xA;        exp:[], &#xA;        got:[&#xA;            0:&#xA;              Labels:{agk_project=&#34;p&#34;, alertname=&#34;StuckLaunch&#34;, issue=&#34;10&#34;, launch=&#34;engineer-1&#34;, role=&#34;engineer&#34;, stage=&#34;s1&#34;}&#xA;              Annotations:{}&#xA;            ]</failure><failure>    name: two_kinds_cancel,&#xA;    alertname: StuckLaunch, time: 1h30m, &#xA;        exp:[], &#xA;        got:[&#xA;            0:&#xA;              Labels:{agk_project=&#34;p&#34;, alertname=&#34;StuckLaunch&#34;, issue=&#34;10&#34;, launch=&#34;engineer-1&#34;, role=&#34;engineer&#34;, stage=&#34;s1&#34;}&#xA;              Annotations:{}&#xA;            ]</failure></testcase><testcase name="one_token_starts_the_time_again"></testcase><testcase name="one_minute_below_zero_starts_the_time_again"></testcase><testcase name="tokens_of_another_issue"></testcase></testsuite></testsuites>
--- stderr ---
  FAILED:
    name: plus_and_minus_in_turn,
    alertname: StuckLaunch, time: 46m, 
        exp:[], 
        got:[
            0:
              Labels:{agk_project="p", alertname="StuckLaunch", issue="10", launch="engineer-1", role="engineer", stage="s1"}
              Annotations:{}
            ]
    name: plus_and_minus_in_turn,
    alertname: StuckLaunch, time: 1h, 
        exp:[], 
        got:[
            0:
              Labels:{agk_project="p", alertname="StuckLaunch", issue="10", launch="engineer-1", role="engineer", stage="s1"}
              Annotations:{}
            ]
    name: plus_and_minus_in_turn,
    alertname: StuckLaunch, time: 1h30m, 
        exp:[], 
        got:[
            0:
              Labels:{agk_project="p", alertname="StuckLaunch", issue="10", launch="engineer-1", role="engineer", stage="s1"}
              Annotations:{}
            ]
    name: two_kinds_cancel,
    alertname: StuckLaunch, time: 46m, 
        exp:[], 
        got:[
            0:
              Labels:{agk_project="p", alertname="StuckLaunch", issue="10", launch="engineer-1", role="engineer", stage="s1"}
              Annotations:{}
            ]
    name: two_kinds_cancel,
    alertname: StuckLaunch, time: 1h30m, 
        exp:[], 
        got:[
            0:
              Labels:{agk_project="p", alertname="StuckLaunch", issue="10", launch="engineer-1", role="engineer", stage="s1"}
              Annotations:{}
            ]
```

## 2. Live check against Grafana

Steps on the checked commit:

1. `uv run --script plugin/skills/monitor/board.py up`: exit 0 at 2026-11-15T17:55:13Z. Prometheus was
   recreated and facts.py restarted. Grafana kept running, because the written alert file and its
   `AGK_ALERTS_VERSION` did not change. Default limits: `AGK_ALERT_ISSUE_TOKENS=23000000`,
   `AGK_ALERT_STUCK_MINUTES=45`.
2. After a wait of about 100 seconds, a script read the admin password from the password file
   (`<state dir>/grafana-admin`), called the two Grafana APIs on `127.0.0.1:3000` and the Prometheus API on
   `127.0.0.1:9090`, and printed only the fields below. The password was never printed.

Output of the script:

```
UTC: 2026-11-15T17:56:58Z

## GET /api/v1/provisioning/alert-rules
- title: Runaway issue
  folder: agk
  ruleGroup: agk-runaway
  for: 0s
  noDataState: OK
  provenance: file
  expr: sum by (agk_project, issue) (sum_over_time(agk:tokens:1m{issue!=""}[365d])) > 23000000
- title: Stuck launch
  folder: agk
  ruleGroup: agk-stuck
  for: 45m
  noDataState: OK
  provenance: file
  expr: agk_launch_open unless on (agk_project, issue) ((max_over_time(agk:tokens:1m[2m]) != 0) or (min_over_time(agk:tokens:1m[2m]) != 0))

## GET /api/prometheus/grafana/api/v1/rules
- Runaway issue | file agk | group agk-runaway | state inactive | health ok | lastEvaluation 2026-11-15T17:53:20Z
    instance: state Normal (NoData) | agk_project None | issue None | launch None | activeAt 2026-11-15T16:48:20Z
- Stuck launch | file agk | group agk-stuck | state inactive | health ok | lastEvaluation 2026-11-15T17:56:10Z
    instance: state Normal (NoData) | agk_project Lighfe/agent-graph-kit | issue 327 | launch pm-2 | activeAt 2026-11-15T17:54:10Z
    instance: state Normal (NoData) | agk_project Lighfe/agent-graph-kit | issue 329 | launch qa-2 | activeAt 2026-11-15T17:54:10Z

## Prometheus: agk_launch_open
   {'agk_project': 'Lighfe/agent-graph-kit', 'issue': '327', 'launch': 'engineer-5', 'role': 'engineer', 'stage': '332'} 1

## Prometheus: measurement query
query: sort_desc(sum by (agk_project, stage, issue) (sum_over_time(agk:tokens:1m{stage="308",issue!=""}[365d])))
   {'agk_project': 'Lighfe/agent-graph-kit', 'issue': '315', 'stage': '308'} 11329034
   {'agk_project': 'Lighfe/agent-graph-kit', 'issue': '324', 'stage': '308'} 311019
```

Reading of the output:

- The alert-rules API lists both rules, folder `agk`. Each `expr` equals the rule's query in `agk-alerts.yaml`
  with the default limit put in: `${AGK_ALERT_ISSUE_TOKENS}` became `23000000`, and the `Stuck launch` query
  has no variable. `for` is `0s` and `45m` (`${AGK_ALERT_STUCK_MINUTES}m` with 45). `noDataState` is `OK` for
  both.
- `Runaway issue`: state `inactive`, its only instance is `Normal (NoData)`: **not firing**. The largest issue
  (315) has 11329034 tokens; the limit is 23000000.
- `Stuck launch`: state `inactive`, **no instance is firing**. The two instances `pm-2` (issue 327) and `qa-2`
  (issue 329) are `Normal (NoData)`; both launches have newer owner comments on their issues (their results and
  later receipts). The only open launch in `agk_launch_open` is this one (`engineer-5` on issue 327). It uses
  tokens, so the query of the rule does not return it.
- Measurement query of the default limit: top result issue 315 with 11329034 tokens. Twice is 22658068,
  rounded to the nearest million 23000000, the default.
