# Spike: sub-issue order and blocker paging with `gh`

Issue: #95. Date: 2026-10-01. Repo: `Lighfe/agent-graph-kit`.

Question: does `gh` return the sub-issues of an issue in the order GitHub keeps, and can it change that order? How do blocker lists behave with paging, and with a blocker in a repo the `gh` login cannot see?

Short answer:

- **Order read: yes.** `gh issue view <n> --json subIssues`, `gh issue view <n>` (plain) and `gh api .../sub_issues` all return the sub-issues in the same order. That order is the add order at first and follows every reorder. Closing a sub-issue does not move it.
- **Reorder: yes, with `gh api` only.** `PATCH .../sub_issues/priority` with `before_id` or `after_id` moves a sub-issue to a given position. `gh issue edit` has no reorder flag.
- **Paging: needed.** The REST list endpoints return one page (default 30, max 100). Without `--paginate`, a list longer than one page is cut off with no warning in the body.
- **Blocker in a repo the login cannot see: not observed, not documented.** Do not assume a blocker list is complete.
- **Blocker lists have no stable order.** The REST form and the `--json blockedBy` form returned the same three blockers in two different orders, neither by number nor by add order.

## Tool version

```
$ gh --version
gh version 2.98.0 (2026-08-20)
https://github.com/cli/cli/releases/tag/v2.98.0
```

## Test issues

All created for this spike, title starting with "Spike test:", label `later`. Body of each: "Test issue for the spike in #95. It will be closed as not planned."

```
$ gh issue create --title "Spike test: parent" --label later --body "..."
https://github.com/Lighfe/agent-graph-kit/issues/109
$ gh issue create --title "Spike test: sub A" --label later --body "..."
https://github.com/Lighfe/agent-graph-kit/issues/110
$ gh issue create --title "Spike test: sub B" --label later --body "..."
https://github.com/Lighfe/agent-graph-kit/issues/111
$ gh issue create --title "Spike test: sub C" --label later --body "..."
https://github.com/Lighfe/agent-graph-kit/issues/112
$ gh issue create --title "Spike test: blocked issue" --label later --body "..."
https://github.com/Lighfe/agent-graph-kit/issues/113
```

Roles: #109 is the parent; #110, #111, #112 are its sub-issues; #113 is blocked by #110, #111 and #112. No real issue was linked.

REST ids (needed for the reorder call): #110 = `5668939484`, #111 = `5668939762`, #112 = `5668940188`.

## Case 1: sub-issue order read

### Read right after adding

Sub-issues added one at a time, in the order A, B, C:

```
$ gh issue edit 109 --add-sub-issue 110
https://github.com/Lighfe/agent-graph-kit/issues/109
$ gh issue edit 109 --add-sub-issue 111
https://github.com/Lighfe/agent-graph-kit/issues/109
$ gh issue edit 109 --add-sub-issue 112
https://github.com/Lighfe/agent-graph-kit/issues/109
```

The read, one `gh` call with number and state of each sub-issue:

```
$ gh issue view 109 --json subIssues
{"subIssues":{"nodes":[
  {"id":"I_kwDOUphNq88AAAABUeUm3A","number":110,"state":"OPEN","title":"Spike test: sub A","url":"https://github.com/Lighfe/agent-graph-kit/issues/110"},
  {"id":"I_kwDOUphNq88AAAABUeUn8g","number":111,"state":"OPEN","title":"Spike test: sub B","url":"https://github.com/Lighfe/agent-graph-kit/issues/111"},
  {"id":"I_kwDOUphNq88AAAABUeUpnA","number":112,"state":"OPEN","title":"Spike test: sub C","url":"https://github.com/Lighfe/agent-graph-kit/issues/112"}
],"totalCount":3}}
```

(line breaks added)

The REST form gives the same order:

```
$ gh api repos/Lighfe/agent-graph-kit/issues/109/sub_issues --jq '.[] | {number, state, title, id}'
{"id":5668939484,"number":110,"state":"open","title":"Spike test: sub A"}
{"id":5668939762,"number":111,"state":"open","title":"Spike test: sub B"}
{"id":5668940188,"number":112,"state":"open","title":"Spike test: sub C"}
```

Here add order and number order are the same (110, 111, 112), so this read alone does not tell them apart. The reorder below does.

### Read after a reorder

After moving C before A (call in Case 2):

```
$ gh issue view 109 --json subIssues --jq '.subIssues.nodes[] | {number, state}'
{"number":112,"state":"OPEN"}
{"number":110,"state":"OPEN"}
{"number":111,"state":"OPEN"}
$ gh api repos/Lighfe/agent-graph-kit/issues/109/sub_issues --jq '.[] | {number, state}'
{"number":112,"state":"open"}
{"number":110,"state":"open"}
{"number":111,"state":"open"}
```

After moving A after B (second call in Case 2):

```
$ gh issue view 109 --json subIssues --jq '[.subIssues.nodes[] | .number]'
[112,111,110]
$ gh api repos/Lighfe/agent-graph-kit/issues/109/sub_issues --jq '[.[] | .number]'
[112,111,110]
```

So the read follows the stored position, not the issue number.

After closing the middle sub-issue #111 (with the REST PATCH call, see Clean-up), the order stays the same, the state changes:

```
$ gh issue view 109 --json subIssues --jq '.subIssues.nodes[] | {number, state}'
{"number":112,"state":"OPEN"}
{"number":111,"state":"CLOSED"}
{"number":110,"state":"OPEN"}
$ gh api repos/Lighfe/agent-graph-kit/issues/109/sub_issues --jq '[.[] | {number, state}]'
[{"number":112,"state":"open"},{"number":111,"state":"closed"},{"number":110,"state":"open"}]
```

The plain `gh issue view` gives the same order in its `sub-issues:` row:

```
$ gh issue view 109
title:	Spike test: parent
state:	OPEN
...
sub-issues:	Lighfe/agent-graph-kit#112, Lighfe/agent-graph-kit#111, Lighfe/agent-graph-kit#110
sub-issues-completed:	1/3
...
```

### Compared with the GitHub page: page not observed

I could not view the rendered GitHub page in a browser. I fetched the public HTML of https://github.com/Lighfe/agent-graph-kit/issues/109 with `curl`: it holds only the timeline events "added sub-issue" (in add order A, B, C) and `subIssuesSummary`, not the sub-issue list itself, which the page loads later with JavaScript. So the order on the page is **not observed**.

What GitHub documents about the order, from the REST docs for sub-issues (https://docs.github.com/en/rest/issues/sub-issues#reprioritize-sub-issue):

> You can use the REST API to reprioritize a sub-issue to a different position in the parent list.

and for the body parameters of that call:

> `after_id` (integer): The id of the sub-issue to be prioritized after (either positional argument after OR before should be specified).
>
> `before_id` (integer): The id of the sub-issue to be prioritized before (either positional argument after OR before should be specified).

So GitHub keeps one ordered "parent list" per parent, and the order is a priority. The user docs (https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues and https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/browsing-sub-issues) do not say in words that the page shows this list in this order; that link between the API order and the page is an inference, not a quote.

## Case 2: sub-issue reorder

`gh issue edit --help` lists `--add-sub-issue`, `--remove-sub-issue`, `--parent` and `--remove-parent`, but no flag for the position. The REST call works:

Move C (#112) before A (#110):

```
$ gh api -X PATCH repos/Lighfe/agent-graph-kit/issues/109/sub_issues/priority -F sub_issue_id=5668940188 -F before_id=5668939484 --jq '{number, title, sub_issues_summary}'
{"number":109,"sub_issues_summary":{"completed":0,"percent_completed":0,"total":3},"title":"Spike test: parent"}
```

Order read after it: `112, 110, 111` (output in Case 1).

Move A (#110) after B (#111):

```
$ gh api -X PATCH repos/Lighfe/agent-graph-kit/issues/109/sub_issues/priority -F sub_issue_id=5668939484 -F after_id=5668939762 --jq '{number, title}'
{"number":109,"title":"Spike test: parent"}
```

Order read after it: `112, 111, 110` (output in Case 1).

Notes:

- The call takes the REST `id` (integer, the `id` field of the REST issue object), not the issue number and not the GraphQL node id.
- The response is the parent issue, not the new order. Read the order again to check it.

## Case 3: paging of blockers

Add three blockers to #113:

```
$ gh issue edit 113 --add-blocked-by 110,111,112
https://github.com/Lighfe/agent-graph-kit/issues/113
```

`per_page=2` with 3 blockers, without `--paginate`: **2 entries**.

```
$ gh api "repos/Lighfe/agent-graph-kit/issues/113/dependencies/blocked_by?per_page=2" --jq '[.[] | {number, state}]'
[{"number":111,"state":"open"},{"number":110,"state":"open"}]
$ gh api "repos/Lighfe/agent-graph-kit/issues/113/dependencies/blocked_by?per_page=2" --jq 'length'
2
```

The body gives no hint that more exist. Only the `Link` header does:

```
$ gh api -i "repos/Lighfe/agent-graph-kit/issues/113/dependencies/blocked_by?per_page=2" | grep -i '^link:'
Link: <https://api.github.com/repositories/1385713067/issues/113/dependencies/blocked_by?per_page=2&page=2>; rel="next", <https://api.github.com/repositories/1385713067/issues/113/dependencies/blocked_by?per_page=2&page=2>; rel="last"
```

Same call with `--paginate`: **3 entries**.

```
$ gh api --paginate "repos/Lighfe/agent-graph-kit/issues/113/dependencies/blocked_by?per_page=2" --jq '.[] | {number, state}'
{"number":111,"state":"open"}
{"number":110,"state":"open"}
{"number":112,"state":"open"}
$ gh api --paginate "repos/Lighfe/agent-graph-kit/issues/113/dependencies/blocked_by?per_page=2" --jq '.[] | .number' | wc -l
3
```

Trap: with `--paginate`, `--jq` runs once per page. A count must be done per item (as above) or after `--slurp`:

```
$ gh api --paginate "repos/Lighfe/agent-graph-kit/issues/113/dependencies/blocked_by?per_page=2" --jq 'length'
2
1
$ gh api --paginate --slurp "repos/Lighfe/agent-graph-kit/issues/113/dependencies/blocked_by?per_page=2" | jq 'add | length'
3
```

Default page size, no `per_page`, no `--paginate`: 3 entries (all fit in one page of 30).

```
$ gh api repos/Lighfe/agent-graph-kit/issues/113/dependencies/blocked_by --jq 'length'
3
```

The sub-issue list pages the same way:

```
$ gh api "repos/Lighfe/agent-graph-kit/issues/109/sub_issues?per_page=2" --jq '[.[]|.number]'
[112,111]
$ gh api --paginate "repos/Lighfe/agent-graph-kit/issues/109/sub_issues?per_page=2" --jq '.[]|.number'
112
111
110
```

The order across pages is the same as the order in one page.

Documented page size, from https://docs.github.com/en/rest/issues/issue-dependencies#list-dependencies-an-issue-is-blocked-by (the same text is on https://docs.github.com/en/rest/issues/sub-issues#list-sub-issues):

> `per_page` (integer): The number of results per page (max 100). For more information, see "Using pagination in the REST API."
> Default: `30`

Documented limits that make paging matter:

- Blockers, from the changelog https://github.blog/changelog/2025-08-21-dependencies-on-issues/: "You can link up to 50 issues for each relationship type." 50 is more than the default page of 30.
- Sub-issues, from https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues: "You can add up to 100 sub-issues per parent issue and create up to eight levels of nested sub-issues." 100 is more than the default page of 30.

### Blocker order

The two read forms returned the same three blockers in different orders:

```
$ gh api repos/Lighfe/agent-graph-kit/issues/113/dependencies/blocked_by --jq '[.[] | .number]'
[111,110,112]
$ gh issue view 113 --json blockedBy --jq '{totalCount: .blockedBy.totalCount, nodes: [.blockedBy.nodes[] | .number]}'
{"nodes":[112,110,111],"totalCount":3}
```

Neither is the number order nor the order given in `--add-blocked-by 110,111,112`. Blocker lists are sets: no rule may depend on their order.

## Case 4: a blocker in a repo the login cannot see

**Result: not observed, not documented.**

**Not observed.** The constraints of #95 allow issues and links only in this repo, which is public, so no blocker in a repo the login cannot see was made. Observing one would need a test issue in a private repo, a cross-repo link and a read with a login that lacks access to that repo; that is outside this spike.

**Not documented.** The pages checked; none of them says whether a blocker the reader cannot see is left out, returned in part, or counted:

- https://docs.github.com/en/rest/issues/issue-dependencies (REST, issue dependencies): the status codes of the list call are "200 - OK", "301 - Moved permanently", "404 - Resource not found", "410 - Gone". Nothing on hidden blockers.
- https://docs.github.com/en/rest/issues/sub-issues (REST, sub-issues): the only access sentence is "The sub-issue must belong to the same repository owner as the parent issue" (body parameter `sub_issue_id` of "Add sub-issue").
- https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies (user docs): nothing on access to the blocking issue.
- https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues (user docs): nothing on access to the linked issue.
- https://github.blog/changelog/2025-08-21-dependencies-on-issues/ (changelog): nothing on cross-repo access.
- https://github.com/orgs/community/discussions/165749 (feedback discussion for issue dependencies): nothing on hidden blockers.

The GraphQL schema descriptions, read with an introspection query:

```
$ gh api graphql -f query='{ issue: __type(name: "Issue") { fields { name description } } summary: __type(name: "IssueDependenciesSummary") { fields { name description } } }' --jq '{blockedBy: [.data.issue.fields[] | select(.name == "blockedBy") | .description], totalBlockedBy: [.data.summary.fields[] | select(.name == "totalBlockedBy") | .description]}'
{"blockedBy":["A list of issues that are blocking this issue."],"totalBlockedBy":["Total count of issues this issue is blocked by (open and closed)"]}
```

So `Issue.blockedBy` is "A list of issues that are blocking this issue." and `IssueDependenciesSummary.totalBlockedBy` is "Total count of issues this issue is blocked by (open and closed)". Neither says whether issues the reader cannot see are left out of the list or counted in the total.

What is known from the earlier spike `docs/research/spike-github-issue-dependencies.md` (#80): a blocker in another repo the login **can** see is returned with `repository.full_name`, number and state. Whether a hidden blocker is left out, returned in part, or counted in `totalCount` stays open. A reader must therefore not treat "no blocker returned" as proof that no blocker exists when cross-repo links to private repos are possible.

## Clean-up

Remove the links, then set each test issue to closed with the REST PATCH call (not with the CLI's issue-close command):

```
$ gh issue edit 113 --remove-blocked-by 110,111,112
https://github.com/Lighfe/agent-graph-kit/issues/113
$ gh issue edit 109 --remove-sub-issue 110,111,112
https://github.com/Lighfe/agent-graph-kit/issues/109
$ gh api -X PATCH repos/Lighfe/agent-graph-kit/issues/111 -f state=closed -f state_reason=not_planned --jq '{number, state, state_reason}'
{"number":111,"state":"closed","state_reason":"not_planned"}
$ gh api -X PATCH repos/Lighfe/agent-graph-kit/issues/109 -f state=closed -f state_reason=not_planned --jq '{number, state, state_reason}'
{"number":109,"state":"closed","state_reason":"not_planned"}
$ gh api -X PATCH repos/Lighfe/agent-graph-kit/issues/110 -f state=closed -f state_reason=not_planned --jq '{number, state, state_reason}'
{"number":110,"state":"closed","state_reason":"not_planned"}
$ gh api -X PATCH repos/Lighfe/agent-graph-kit/issues/112 -f state=closed -f state_reason=not_planned --jq '{number, state, state_reason}'
{"number":112,"state":"closed","state_reason":"not_planned"}
$ gh api -X PATCH repos/Lighfe/agent-graph-kit/issues/113 -f state=closed -f state_reason=not_planned --jq '{number, state, state_reason}'
{"number":113,"state":"closed","state_reason":"not_planned"}
```

(#111 was closed earlier, before the links were removed, for the order test in Case 1.)

Final read:

```
$ gh issue list --state all --search "Spike test: in:title"
109	CLOSED	Spike test: parent	later	2026-10-01T20:50:55Z
113	CLOSED	Spike test: blocked issue	later	2026-10-01T20:50:58Z
112	CLOSED	Spike test: sub C	later	2026-10-01T20:50:57Z
110	CLOSED	Spike test: sub A	later	2026-10-01T20:50:56Z
111	CLOSED	Spike test: sub B	later	2026-10-01T20:50:37Z
$ gh api repos/Lighfe/agent-graph-kit/issues/109/dependencies/blocked_by
[]
$ gh api repos/Lighfe/agent-graph-kit/issues/109/sub_issues
[]
$ gh api repos/Lighfe/agent-graph-kit/issues/110/dependencies/blocked_by
[]
$ gh api repos/Lighfe/agent-graph-kit/issues/110/sub_issues
[]
$ gh api repos/Lighfe/agent-graph-kit/issues/111/dependencies/blocked_by
[]
$ gh api repos/Lighfe/agent-graph-kit/issues/111/sub_issues
[]
$ gh api repos/Lighfe/agent-graph-kit/issues/112/dependencies/blocked_by
[]
$ gh api repos/Lighfe/agent-graph-kit/issues/112/sub_issues
[]
$ gh api repos/Lighfe/agent-graph-kit/issues/113/dependencies/blocked_by
[]
$ gh api repos/Lighfe/agent-graph-kit/issues/113/sub_issues
[]
```

All five test issues are closed, each with the label `later`, and none has a blocker or a sub-issue. No issue was deleted.

## Consequences

**#64 (Native "blocked by" links replace `Waiting on:` and `waiting`)**

- Read form: `gh api --paginate repos/<owner>/<repo>/issues/<n>/dependencies/blocked_by --jq '.[] | {repo: .repository.full_name, number, state}'`. It gives repo, number and state per blocker in one call.
- Always use `--paginate`: up to 50 blockers are allowed, a page holds 30 by default. Count per item or after `--slurp`, never with `--jq 'length'` on a paginated call.
- Order rule: none. Blockers are a set; their order differs between read forms. A check asks only "is any blocker open".
- Hidden blockers (Case 4, not observed, not documented): #64 and #97 must not assume the blocker list is complete. An empty or all-closed blocker list is not proof that no open blocker exists when cross-repo links to private repos are possible.

**#97 (The close check allows a finished stage issue)**

- Read form: `gh api --paginate repos/<owner>/<repo>/issues/<n>/sub_issues --jq '.[] | {number, state}'`, and the stage issue is finished only when that list is not empty and every entry is `closed`. Use `--paginate`: up to 100 sub-issues per parent, a page holds 30 by default.
- `gh issue view <n> --json subIssues` returns the same list and order with `totalCount`; if a hook uses it, it should check that the number of nodes equals `totalCount`. This spike did not test more than 3 sub-issues on that form.
- Order rule: none. The close check does not depend on order.
- Hidden blockers: the same unknown applies (see the line under #64). If #97 reads blockers, it must not treat the list as complete.

**#96 (Stage issues and parked follow-ups in the process)**

- Order rule for the pick order: inside a stage, native "blocked by" links first, then the position in the sub-issue list as `gh` returns it. The spec's fallback to the issue number is not needed: `gh` reads the list order, and that order follows the stored position (add order, then every reorder), not the number.
- A closed sub-issue keeps its position, so the next pick is the first open, unblocked entry of the list.
- To set or change the order, use `gh api -X PATCH repos/<owner>/<repo>/issues/<parent>/sub_issues/priority -F sub_issue_id=<REST id> -F before_id=<REST id>` (or `after_id`). `gh issue edit` cannot do it. New sub-issues go to the end of the list.
- The order on the GitHub page was not observed; the REST docs call the list a priority order ("reprioritize a sub-issue to a different position in the parent list").
