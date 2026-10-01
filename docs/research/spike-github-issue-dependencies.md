# Spike: GitHub native issue dependencies

Issue: #80. Date: 2026-10-01. Repo: `Lighfe/agent-graph-kit`.

Question: can GitHub's native "blocked by" links hold what the loop needs to know about blockers, read with `gh`? That is: several blockers on one issue, a blocker in another repo, and the state of each blocker.

Short answer: yes. One `gh` call returns every blocker of an issue with its repo, number and state. Cross-repo and closed blockers are stored and read back correctly. `is:blocked` in search counts only open blockers, as far as this spike shows. The limits are listed at the end.

## Tool version

```
$ gh --version
gh version 2.98.0 (2026-08-20)
https://github.com/cli/cli/releases/tag/v2.98.0
```

## Read forms used

Two forms, both `gh` only:

- **A. `gh issue view <n> --json blockedBy`** (also `blocking`). Each node has the fields `id`, `number`, `state`, `title`, `url`. There is **no repo field**: the repo can be read only from `url`.
- **B. `gh api repos/<owner>/<repo>/issues/<n>/dependencies/blocked_by`** (REST endpoint for issue dependencies). Each item is a full issue object with `repository.full_name`, `number` and `state`. The report uses B with `--jq` wherever repo, number and state must all come from one call.

Write form: `gh issue edit <n> --add-blocked-by <number or URL>` and `--remove-blocked-by <number or URL>`.

## Case 1: several blockers

#85 "Proposal: sort the open backlog" already had two native "blocked by" links. One call, form B:

```
$ gh api repos/Lighfe/agent-graph-kit/issues/85/dependencies/blocked_by --jq '.[] | {repo: .repository.full_name, number, state}'
{"number":83,"repo":"Lighfe/agent-graph-kit","state":"open"}
{"number":84,"repo":"Lighfe/agent-graph-kit","state":"open"}
```

Same issue, form A (repo only in `url`):

```
$ gh issue view 85 --json blockedBy
{"blockedBy":{"nodes":[
  {"id":"I_kwDOUphNq88AAAABUWG06A","number":84,"state":"OPEN","title":"Proposal: how long each kind of agent-readable doc lives","url":"https://github.com/Lighfe/agent-graph-kit/issues/84"},
  {"id":"I_kwDOUphNq88AAAABUWGznA","number":83,"state":"OPEN","title":"Proposal: where the big picture of the work lives","url":"https://github.com/Lighfe/agent-graph-kit/issues/83"}
],"totalCount":2}}
```

(line breaks added)

`gh issue list` also takes `blockedBy`, so one call can give the blockers of every listed issue:

```
$ gh issue list --state open --label ready --json number,blockedBy --jq '.[] | {number, blockedBy: [.blockedBy.nodes[]?.number]}'
{"blockedBy":[84,83],"number":85}
{"blockedBy":[81],"number":84}
{"blockedBy":[80],"number":83}
{"blockedBy":[81],"number":82}
{"blockedBy":[],"number":81}
{"blockedBy":[],"number":80}
{"blockedBy":[],"number":73}
```

## Case 2: blocker in another repo

Start state of #80: no blockers (`{"blockedBy":{"nodes":[],"totalCount":0}}`). It blocks #83, and that link was not touched.

Add a link to `Lighfe/paint-math#12` (open):

```
$ gh issue edit 80 --add-blocked-by https://github.com/Lighfe/paint-math/issues/12
https://github.com/Lighfe/agent-graph-kit/issues/80
```

Read back, form B (one call gives repo, number, state):

```
$ gh api repos/Lighfe/agent-graph-kit/issues/80/dependencies/blocked_by --jq '.[] | {repo: .repository.full_name, number, state, id}'
{"id":5627948160,"number":12,"repo":"Lighfe/paint-math","state":"open"}
```

Form A shows it too, the repo only in `url`:

```
$ gh issue view 80 --json blockedBy
{"blockedBy":{"nodes":[{"id":"I_kwDOUwPNxs8AAAABT3OsgA","number":12,"state":"OPEN","title":"Adaptive step size, stiff solvers and higher-dimensional systems","url":"https://github.com/Lighfe/paint-math/issues/12"}],"totalCount":1}}
```

Remove, then the final read:

```
$ gh issue edit 80 --remove-blocked-by https://github.com/Lighfe/paint-math/issues/12
https://github.com/Lighfe/agent-graph-kit/issues/80
$ gh issue view 80 --json blockedBy
{"blockedBy":{"nodes":[],"totalCount":0}}
$ gh api repos/Lighfe/agent-graph-kit/issues/80/dependencies/blocked_by
[]
```

## Case 3: closed blocker

#78 is closed:

```
$ gh issue view 78 --json number,state,title
{"number":78,"state":"CLOSED","title":"Drop the Owner-marker content check from G9, keep the exact form"}
```

Add, read back, remove, final read:

```
$ gh issue edit 80 --add-blocked-by 78
https://github.com/Lighfe/agent-graph-kit/issues/80
$ gh issue view 80 --json blockedBy
{"blockedBy":{"nodes":[{"id":"I_kwDOUphNq88AAAABUOzulw","number":78,"state":"CLOSED","title":"Drop the Owner-marker content check from G9, keep the exact form","url":"https://github.com/Lighfe/agent-graph-kit/issues/78"}],"totalCount":1}}
$ gh api repos/Lighfe/agent-graph-kit/issues/80/dependencies/blocked_by --jq '.[] | {repo: .repository.full_name, number, state}'
{"number":78,"repo":"Lighfe/agent-graph-kit","state":"closed"}
$ gh issue edit 80 --remove-blocked-by 78
https://github.com/Lighfe/agent-graph-kit/issues/80
$ gh issue view 80 --json blockedBy
{"blockedBy":{"nodes":[],"totalCount":0}}
$ gh api repos/Lighfe/agent-graph-kit/issues/80/dependencies/blocked_by
[]
```

A closed blocker stays linked. Its state reads as closed (`CLOSED` in form A, `closed` in form B).

## Case 4: search

```
$ gh issue list --state open --search "is:blocked"
85	OPEN	Proposal: sort the open backlog	ready	2026-10-01T09:56:17Z
84	OPEN	Proposal: how long each kind of agent-readable doc lives	ready	2026-10-01T09:56:14Z
83	OPEN	Proposal: where the big picture of the work lives	ready	2026-10-01T09:56:11Z
82	OPEN	Fix status lines in the v1 plan and spec that are false today	ready	2026-10-01T09:56:08Z
```

These are exactly the open issues with at least one open blocker (#85 by #83 and #84, #84 by #81, #83 by #80, #82 by #81).

```
$ gh issue list --state open --search "-is:blocked"
86	OPEN	Guard: false denies by G8 and G9	later	...
81	OPEN	Experiment: Claude Code /doctor prompt-audit on this repo	ready	...
80	OPEN	Experiment: GitHub native issue dependencies for the loop	ready	...
79	OPEN	...	later	...
... (30 rows in total, down to #23)
```

The output stops at 30 rows, which is the default `--limit` of `gh issue list`. With a higher limit:

```
$ gh issue list --state open --search "-is:blocked" --limit 200 --json number --jq 'length, [.[].number]'
40
[86,81,80,79,77,76,75,74,73,66,65,64,63,61,54,53,47,46,45,44,32,31,30,29,28,27,26,25,24,23,22,21,20,19,18,17,16,15,14,13]
$ gh issue list --state open --limit 200 --json number --jq length
44
```

4 blocked + 40 not blocked = 44 open issues, so the two searches split the open issues with no overlap.

Extra check with the same temporary links as cases 2 and 3: does `is:blocked` count a closed blocker or a blocker in another repo? The search ran right after adding the link, up to 3 times:

```
== blocker 78 (closed, this repo)
try 1: is:blocked -> [85,84,83,82]
try 2: is:blocked -> [85,84,83,82]
try 3: is:blocked -> [85,84,83,82]
removed; final read {"blockedBy":{"nodes":[],"totalCount":0}}
== blocker https://github.com/Lighfe/paint-math/issues/12 (open, other repo)
try 1: is:blocked -> [85,84,83,82]
try 2: is:blocked -> [85,84,83,82,80]
removed; final read {"blockedBy":{"nodes":[],"totalCount":0}}
```

So an open blocker in another repo counts for `is:blocked`, after a short index delay. A closed blocker did not make #80 count as blocked. This fits "blocked means at least one open blocker", but three quick tries cannot rule out a slower index.

## End state

The temporary links are gone. #80 is back to its start state:

```
$ gh issue view 80 --json blockedBy,blocking --jq '{blockedBy: [.blockedBy.nodes[].number], blocking: [.blocking.nodes[].number]}'
{"blockedBy":[],"blocking":[83]}
```

No other link, label, body or comment was changed.

## Limits found

1. `gh issue view --json blockedBy` (form A) has no repo field. The repo is only in `url`, so a reader must parse the URL. Form B (`gh api .../dependencies/blocked_by`) has `repository.full_name`.
2. Form A gives `state` in upper case (`OPEN`, `CLOSED`), form B in lower case (`open`, `closed`). A reader that uses both must normalize the case.
3. `gh issue list` stops at 30 rows by default. A loop that uses `-is:blocked` (or any list) must pass a higher `--limit`, or it misses issues without any warning.
4. The search index lags behind writes: a new cross-repo link showed in `is:blocked` only on the second try. `gh issue view` and `gh api` showed the link right away.
5. `is:blocked` did not count a closed blocker in this spike. That is what the loop wants, but it was seen only in three quick tries.
6. The REST endpoint returns one page (default size). With many blockers on one issue, a reader would need `--paginate`. This spike had at most two blockers per issue, so it did not test paging.
7. No permission error came up. The `gh` login is the owner of both repos, so the spike did not test a cross-repo link to a repo the login cannot write to or cannot see.
