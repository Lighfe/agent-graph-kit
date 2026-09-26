# Spike S3: Lovable MCP

How can the frontend engineer (#9) drive Lovable through MCP, detect that a change has finished, and pin the exact commit of that change? This file answers Q1–Q4 of issue #3 with evidence. Spec: `docs/specs/2026-09-25-agent-graph-kit-v1.md`, section 9 and the S3 row in section 13.

- Date of the experiments: 2026-09-26, 13:53–13:58 UTC
- Lovable project: `d3807291-da7f-4024-a86e-05dec34c5b06` (throwaway, name `paint-math-throwaway-lov`, granted by the owner on #3)
- GitHub repo: `https://github.com/Lighfe/paint-math-throwaway-lov` (throwaway, private)
- Base SHA of `main` before the first message: `4f68d71c3fb16767c40dcf888359d86a81c00ccd` ("Add project README", author Lovable). Same value from `git ls-remote` (13:53:16Z and 13:54:16.917Z) and from `get_project.latest_commit_sha`
- MCP server: the Claude Code plugin `lovable` (server `lovable`), 40 tools. The session was a Claude Code subagent (the software-engineer launch for #3), not a `frontend-engineer` launch
- Messages sent: 2, each "change one text, change nothing else". `cost_credits` 0.2 per message
- Redaction: the workspace id, the account id, the account e-mail (also in `Co-authored-by`), the screenshot URLs and all local paths are removed. `$SCRATCH` is the scratch directory of the experiments (outside this repo). Commit SHAs, the project id, message ids and edit ids stay

## How the experiments ran

- The throwaway repo was cloned into `$SCRATCH/repo` over HTTPS with the owner's local git credentials. Nothing was pushed to it.
- `$SCRATCH/poll.sh` ran in the background from 13:54:16Z to 13:58:00Z. Every 5 s it ran `git ls-remote https://github.com/Lighfe/paint-math-throwaway-lov refs/heads/main` and logged each change of `main` with a UTC timestamp (ms). Each loop takes the 5 s sleep plus the `ls-remote` time, so the time a commit appeared is known to about 6 s.
- Local timestamps: `date -u +%FT%T.%3NZ` in a Bash call right before and right after an MCP call. Lovable timestamps: `created_at` fields (seconds) and git author dates.
- Change 1 was sent with `wait=false` and polled with `get_message`. Change 2 was sent with the default `wait=true`. So both modes of `send_message` were tried.

## Questions and answers

| # | Answer | Confirmed by |
|---|---|---|
| Q1 | **Tool, field, value:** `send_message` with `wait=true` (the default) blocks until the agent has finished and returns top-level `status: "completed"` with `edit_id` and `commit_sha`. With `wait=false` it returns at once with `status: "accepted"` and a `message_id` (`umsg_…`); then poll `get_message(project_id, message_id, thread_id)` and read the **nested** `response.status`: `"completed"` (with `completion_reason: "finished"`) means done. The top-level `status` of `get_message` stays `"running"` even after the agent finished, so it must not be used. **Other values:** top-level `get_message.status` `queued`, `accepted`, `running` (never terminal; `queue_pause_reason: "hitl_tool"` means queued behind a paused turn); `response` absent = still working; `response.status` `stopped` and `error` = terminal failure; `awaiting_input` = the agent paused for a human decision (tool approval or a credit/spend-limit prompt) and will not go on by itself, only the user can answer it in the Lovable editor, and a new `send_message` does not answer it but supersedes it; `send_message` returns `status: "in_progress"` when its `timeout_seconds` (default and max 600) runs out, then poll `get_message`. `get_project.project.agentFinished` (true/false) is a second, coarser signal. **Time per change:** change 1: sent 13:54:19.445Z (message `created_at` 13:54:24Z), still working at 13:54:27.758Z, `completed` at the next poll 13:54:55.168Z; the edit record is from 13:54:40Z, so the agent finished between 16 s and 36 s after the send. Change 2: sent 13:55:26.935Z (`created_at` 13:55:32Z), `send_message` returned `completed` before 13:56:00.011Z: at most 33 s, including the tool-call overhead | `completed`, `accepted`, `running`, absent `response`, `completion_reason: "finished"`, `agentFinished: true`: experiment. `queued`, `stopped`, `error`, `awaiting_input`, `in_progress`, `hitl_tool`: tool schema only (the descriptions of `send_message` and `get_message`); provoking them needs a spend limit, a failing change or a change longer than a timeout, which is not "few and small" messages |
| Q2 | **When the commit reaches GitHub:** in both changes the commit was on GitHub before or at the moment "finished" was seen. Change 1: `main` moved to `9f85a53` at 13:54:46.610Z (edit `created_at` 13:54:40Z), "finished" was seen at 13:54:55.168Z. Change 2: `main` moved to `9326256` at 13:55:51.267Z (edit `created_at` 13:55:43Z); the first `ls-remote` after `send_message` returned (13:56:00Z) already showed it. So the measured delay after "finished" is 0 s; the push came about 3–8 s after the edit record. The poll resolution is about 6 s, and two samples are few, so the engineer still waits for the SHA on GitHub (see Consequences). **The link:** `send_message` (`wait=true`) and `get_message` (`response.edit_id`, `response.commit_sha`) return the edit id and the SHA of the commit on GitHub. `list_edits` returns the same pair (`id`, `commit_sha`) for every edit. The commit with that SHA carries the trailer `X-Lovable-Edit-ID: <edit_id>`. Both matched for both changes. **Commits per message:** two. First a commit "Changes" (no trailer, author `gpt-engineer-app[bot]`), whose parent is the previous AI edit commit, not necessarily the tip of `main`. Then a merge commit with the edit summary as subject and the trailer; its first parent is the old tip of `main`, its second parent is the "Changes" commit. Only the merge commit is the edit's `commit_sha`. **Commits without the id:** yes, the "Changes" commits, and "Add project README" (author Lovable, from project creation; `list_edits` lists it as `type: "developer_update"` with its own edit id but no trailer in git). **What to pin:** the `commit_sha` of the last message of the launch (the merge commit). Its first-parent chain contains all earlier merge commits (`9f85a53` is the first parent of `9326256`). Never pin a "Changes" commit: `dc37a98` is based on `4313be0` and does not contain the README change `4f68d71` that `main` had. The link is reliable (MCP field = SHA on GitHub = trailer), so no fallback is needed; the rest risk is that the pinned merge also contains commits that others pushed to `main` in between (two-way sync) | Experiment (2 changes, SHAs and trailers in the evidence); the order of the two commits per message was also seen in the older first message of the project (`75f03af`, `4313be0`) |
| Q3 | **No.** None of the 40 Lovable MCP tools creates or changes a GitHub connection, takes a repo or a git provider as argument, or returns the connection state (`get_project` has no repo field). `add_connector` only returns a dashboard link and says "Connectors must always be added through the dashboard — the MCP cannot add them programmatically"; its connectors are Lovable integrations (Stripe, Supabase, …), not Git sync. **Manual steps for the owner** (Lovable docs): 1. Workspace admin connects the workspace to GitHub once (installs the Lovable GitHub app; it asks for Contents write, Metadata read, Pull requests write, Workflows write, Administration write). 2. In the project: Project settings → Git → GitHub → **Connect** next to the workspace connection. Lovable creates a new repo and starts two-way sync of the default branch. 3. Copy the repo URL. Limits from the docs: one repo per project; deleting the repo breaks sync; after a disconnect, Lovable makes a new repo on reconnect. **Private:** yes. The docs say "Repositories created by Lovable are private by default, on every plan"; the throwaway repo is private (`gh repo view`: `"isPrivate":true`). **Access:** anonymous HTTPS gets `404` (web) and `401` (`info/refs`). `git ls-remote` and a submodule fetch need a GitHub credential with read access to that repo on the machine that runs them (here the owner's HTTPS credentials worked, exit 0). Alternatively the owner makes the repo public in GitHub (allowed after creation, per the docs) | Tool list and schemas (all 40 read); `list_connectors` was not called (the permission system denied the call), so the connector catalog of the workspace is not checked; manual steps and "private by default" from the Lovable docs only (https://docs.lovable.dev/integrations/github, read 2026-09-26), no project was connected in this spike because the throwaway was already connected; privacy and access by experiment |
| Q4 | See the tool table in the evidence. **Needed** in `tools:` of `.claude/agents/frontend-engineer.md`: `mcp__plugin_lovable_lovable__send_message`, `mcp__plugin_lovable_lovable__get_message`, `mcp__plugin_lovable_lovable__list_messages`, `mcp__plugin_lovable_lovable__list_edits`, `mcp__plugin_lovable_lovable__get_diff`, `mcp__plugin_lovable_lovable__get_project`. All others: not needed. The prefix `mcp__plugin_lovable_lovable__` comes from installing Lovable as the Claude Code **plugin** `lovable`; a server added another way (for example `claude mcp add lovable …`) has other names (`mcp__lovable__…`) | Names by experiment: every name is exactly as this Claude Code subagent session shows it, and all six needed tools were called with these names (see the evidence). Not checked: a launch of a subagent whose `tools:` list names these tools (the agent file is #9). In this session the Lovable tools were **deferred** and had to be loaded with `ToolSearch` before the first call; whether a `tools:` allowlist without `ToolSearch` still reaches them is not checked |

## Evidence

### Tool list (Q3, Q4)

All 40 tools of the plugin, with the role they could play and the Q4 verdict. Names are exactly as Claude Code shows them.

| Tool (`mcp__plugin_lovable_lovable__…`) | What it does (schema) | Q4 |
|---|---|---|
| `send_message` | send a chat message; `wait` (default true), `timeout_seconds` (≤600), `plan_mode`, `files` | needed: sends the goal, criteria and follow-ups |
| `get_message` | status and content of a message; `message_id`, `thread_id` | needed: detects "finished" after `wait=false` or a timeout, returns `edit_id` and `commit_sha` |
| `list_messages` | recent messages, newest first | needed: finds the message id again if a `send_message` result is lost |
| `list_edits` | edit history: `id`, `type`, `commit_sha`, `commit_message`, `status`, `created_at` | needed: maps edit ids to SHAs, cross-check before pinning |
| `get_diff` | unified diff of a message (`message_id`) or a commit (`sha`) | needed: reads what one message changed before deciding on a follow-up |
| `get_project` | project details, `latest_commit_sha`, `project.agentFinished` | needed: second "finished" signal and the tip Lovable knows |
| `list_files` | files at a ref | not needed: after the fetch, `git ls-tree` in the submodule shows the same |
| `read_file` | one file at a ref | not needed: after the fetch, `git show <sha>:<path>` shows the same |
| `render_project_widget` | UI widget for chat clients | not needed: no UI in a Claude Code subagent |
| `get_file_upload_url` | presigned upload URL for images | not needed: v1 sends text only (and the presigned URL is a secret to keep out of comments) |
| `create_project` | creates a project | not needed: the engineer never creates projects (owner step) |
| `initiate_project` | deprecated alias of `create_project` | not needed: same reason |
| `remix_project` | forks a project | not needed: creates projects |
| `deploy_project` | publishes to lovable.app | not needed: deploy is not part of the lane |
| `set_project_visibility` | editor access of a project | not needed: owner setting |
| `move_projects_to_folder`, `set_folder_visibility` | workspace folders | not needed: owner setting |
| `get_project_knowledge` | project instructions | not needed: the engineer sends all it needs in the message |
| `set_project_knowledge` | replaces project instructions | not needed: changes Lovable's behavior for all later messages, owner setting |
| `get_workspace_knowledge`, `set_workspace_knowledge` | workspace instructions | not needed: workspace scope, owner setting |
| `list_workspace_skills`, `get_workspace_skill`, `create_workspace_skill`, `update_workspace_skill`, `delete_workspace_skill` | workspace skills | not needed: workspace scope, owner setting |
| `enable_database`, `get_database_status`, `query_database` | Lovable Cloud database | not needed: the demo has no backend; `query_database` can change production data |
| `list_connectors`, `list_custom_connectors`, `add_connector` | Lovable integrations; `add_connector` only returns a dashboard link | not needed: owner setting, and none of them is Git sync |
| `get_me`, `list_workspaces`, `get_workspace` | account and workspaces | not needed: the project id is known; the output has ids to keep out of comments |
| `list_projects`, `list_template_projects`, `list_design_systems` | workspace listings | not needed: the project id is known |
| `get_project_analytics`, `get_project_analytics_trend` | visitor analytics | not needed |

Tools that create projects: `create_project`, `initiate_project`, `remix_project`. Send messages: `send_message`. Read message status: `get_message`, `list_messages`, `get_project` (`agentFinished`). List edits: `list_edits`. Read diffs: `get_diff`. Connect GitHub: none.

### Project state before the first message (Q3)

`get_project(project_id="d3807291-da7f-4024-a86e-05dec34c5b06")`, 13:53Z, relevant fields:

```json
{"creation_status":"completed","is_published":false,"last_edited_at":"2026-09-26T12:21:13.766Z",
 "latest_commit_sha":"4f68d71c3fb16767c40dcf888359d86a81c00ccd","name":"paint-math-throwaway-lov",
 "visibility":"workspace_edit","project":{"status":"ready","error":null,"agentFinished":true}}
```

No field names the GitHub repo or the connection. The connection is shown by the git history instead: `latest_commit_sha` equals `main` on GitHub.

```text
$ git ls-remote https://github.com/Lighfe/paint-math-throwaway-lov      # 2026-09-26T13:53:16Z
4f68d71c3fb16767c40dcf888359d86a81c00ccd	HEAD
4f68d71c3fb16767c40dcf888359d86a81c00ccd	refs/heads/main
exit=0
$ gh repo view Lighfe/paint-math-throwaway-lov --json visibility,isPrivate,defaultBranchRef,createdAt
{"createdAt":"2026-09-26T12:21:09Z","defaultBranchRef":{"name":"main"},"isPrivate":true,"visibility":"PRIVATE"}
$ curl -s -o /dev/null -w '%{http_code}' https://github.com/Lighfe/paint-math-throwaway-lov
404
$ curl -s -o /dev/null -w '%{http_code}' 'https://github.com/Lighfe/paint-math-throwaway-lov.git/info/refs?service=git-upload-pack'
401
```

`list_edits(project_id=…)` before the first message:

```json
{"data":[
 {"id":"edt-50a47980-ac39-4b0e-a935-c46db9d56c1f","type":"ai_update","commit_sha":"4313be0432c3b8cdd125e0c4e41fceda587a4cbc","commit_message":"Added counter landing page","status":"completed","created_at":"2026-09-26T12:20:26Z"},
 {"id":"edt-ae2ad096-6e53-4674-82a6-fabd448a9a9e","type":"developer_update","commit_sha":"4f68d71c3fb16767c40dcf888359d86a81c00ccd","commit_message":"Add project README","status":"completed","created_at":"2026-09-26T12:21:13Z"}],
 "pagination":{"next_cursor":null,"has_more":false}}
```

`list_messages(project_id=…)` returned the one earlier user message (`status: "accepted"`) and its assistant answer (`status: "completed"`, `edit_id: "edt-50a47980-…"`). The assistant `content` is the full agent transcript with `<lov-tool-use>` blocks (long; not needed by the engineer).

### Change 1: `wait=false` and polling (Q1, Q2)

```text
13:54:19.445Z  (local, before the call) poller: main=4f68d71 since 13:54:16.917Z
send_message(project_id="d3807291-…", message="Change the browser tab title of the home page to \"S3 Spike One\". Change nothing else.", wait=false)
  -> {"message_id":"umsg_01m3ezxrsgf2rap8j977tepb8y","thread_id":"main","status":"accepted","preview_url":"…"}
13:54:27.758Z  (local, after the call)
get_message(project_id="d3807291-…", message_id="umsg_01m3ezxrsgf2rap8j977tepb8y", thread_id="main")
  -> {"status":"running","message_id":"main:user#00000000000009#usr:AJ5D4XT2","role":"user","content":"Change the browser tab title …","created_at":"2026-09-26T13:54:24Z","preview_url":"…"}
     (no "response" field: the agent is still working)
13:54:46.610Z  poller: main=9f85a537927d30f0e397a0a0b7cb8b646982d9a6
13:54:55.168Z  (local, before the call)
get_message(same arguments)
  -> {"status":"running", "message_id":"main:user#00000000000009#usr:AJ5D4XT2", "created_at":"2026-09-26T13:54:24Z",
      "response":{"message_id":"main:agent#00000000000128#don:CXJTWGLN","status":"completed","completion_reason":"finished",
                  "edit_id":"edt-62de6133-3046-471f-b8b3-5e0a508b5dd1",
                  "commit_sha":"9f85a537927d30f0e397a0a0b7cb8b646982d9a6",
                  "summary":"The AI changed the browser tab title from \"Count Up — A Tiny Counter\" to \"S3 Spike One\" …","cost_credits":0.2, "content":"…"}}
get_project(project_id="d3807291-…")
  -> "last_edited_at":"2026-09-26T13:54:40.989Z","latest_commit_sha":"9f85a537927d30f0e397a0a0b7cb8b646982d9a6", "project":{"agentFinished":true,…}
```

Note: `get_message` echoes an internal id (`main:user#…`), not the `umsg_…` id that was passed in. Polling works with the `umsg_…` id and `thread_id`.

`list_edits` after change 1 (new entry):

```json
{"id":"edt-62de6133-3046-471f-b8b3-5e0a508b5dd1","type":"ai_update","commit_sha":"9f85a537927d30f0e397a0a0b7cb8b646982d9a6","commit_message":"Updated home page tab title","status":"completed","created_at":"2026-09-26T13:54:40Z"}
```

`get_diff(project_id="d3807291-…", message_id="umsg_01m3ezxrsgf2rap8j977tepb8y")` returned structured hunks for `src/routes/index.tsx`: two `remove`/`add` pairs, `title` and `og:title` from `"Count Up — A Tiny Counter"` to `"S3 Spike One"`. The same as `git diff 4f68d71 9f85a53` below.

Git, after `git fetch` in `$SCRATCH/repo` (e-mail redacted):

```text
$ git log --format='%H %P%n%an | %ad%n%B' --date=iso-strict 4f68d71..origin/main
9f85a537927d30f0e397a0a0b7cb8b646982d9a6 4f68d71c3fb16767c40dcf888359d86a81c00ccd dc37a98f213cd3ecbaa6ad2d92d363fb566a6b72
gpt-engineer-app[bot] | 2026-09-26T13:54:40+00:00
Updated home page tab title

X-Lovable-Edit-ID: edt-62de6133-3046-471f-b8b3-5e0a508b5dd1
Co-authored-by: Lighfe <REDACTED>

dc37a98f213cd3ecbaa6ad2d92d363fb566a6b72 4313be0432c3b8cdd125e0c4e41fceda587a4cbc
gpt-engineer-app[bot] | 2026-09-26T13:54:34+00:00
Changes

Co-authored-by: Lighfe <REDACTED>

$ git diff --stat dc37a98^ dc37a98        # the "Changes" commit holds the change …
 src/routes/index.tsx | 4 ++--
$ git diff --stat dc37a98 9f85a53         # … but lacks the README commit that main had
 README.md | 17 ++++++-----------
$ git diff 4f68d71 9f85a53                # the merge vs old main: only the requested change
-      { title: "Count Up — A Tiny Counter" },
+      { title: "S3 Spike One" },
-      { property: "og:title", content: "Count Up — A Tiny Counter" },
+      { property: "og:title", content: "S3 Spike One" },
```

### Change 2: `wait=true` (Q1, Q2)

```text
13:55:26.935Z  (local, before the call) git ls-remote … refs/heads/main -> 9f85a537927d30f0e397a0a0b7cb8b646982d9a6
send_message(project_id="d3807291-…", message="Change the visible heading text \"Count Up\" on the home page to \"S3 Spike Two\". Change nothing else.")
13:55:51.267Z  poller: main=93262569438a3a3deaf937af42f4752d6b1f74cb     (during the blocking call)
  -> {"status":"completed","message_id":"umsg_01m3ezztzsfhgta8yzjy4nhg19","thread_id":"main",
      "edit_id":"edt-521ff7d9-fba4-41ab-af1b-15c065bd0b33","commit_sha":"93262569438a3a3deaf937af42f4752d6b1f74cb",
      "summary":"The AI changed the visible heading text from \"Count Up\" to \"S3 Spike Two\" …","cost_credits":0.2,"content":"…","preview_url":"…"}
13:56:00.011Z  (local, after the call) git ls-remote … refs/heads/main -> 93262569438a3a3deaf937af42f4752d6b1f74cb
get_message(project_id="d3807291-…", message_id="umsg_01m3ezztzsfhgta8yzjy4nhg19", thread_id="main")
  -> {"status":"running","message_id":"main:user#00000000000014#usr:W47AJWYD","created_at":"2026-09-26T13:55:32Z",
      "response":{"status":"completed","completion_reason":"finished","edit_id":"edt-521ff7d9-fba4-41ab-af1b-15c065bd0b33","commit_sha":"93262569438a3a3deaf937af42f4752d6b1f74cb",…}}
list_edits(project_id="d3807291-…", limit=2)
  -> {"id":"edt-521ff7d9-fba4-41ab-af1b-15c065bd0b33","type":"ai_update","commit_sha":"93262569438a3a3deaf937af42f4752d6b1f74cb","commit_message":"Chg'd home heading to \"S3 Spike Two","status":"completed","created_at":"2026-09-26T13:55:43Z"}
     (plus the change-1 edit; the page is in ascending order and has a next_cursor)
```

The `top-level status` of `get_message` is still `"running"` minutes after the agent finished; only `response.status` is terminal. The `commit_message` in `list_edits` is a shortened summary with an unbalanced quote, so text matching is not a safe link; the edit id is.

```text
$ git log --format='%H %P%n%an | %ad%n%B' --date=iso-strict 9f85a53..origin/main
93262569438a3a3deaf937af42f4752d6b1f74cb 9f85a537927d30f0e397a0a0b7cb8b646982d9a6 8bd0027800ef35b4648d1734afe02246e600d0d9
gpt-engineer-app[bot] | 2026-09-26T13:55:42+00:00
Chg'd home heading to "S3 Spike Two

X-Lovable-Edit-ID: edt-521ff7d9-fba4-41ab-af1b-15c065bd0b33
Co-authored-by: Lighfe <REDACTED>

8bd0027800ef35b4648d1734afe02246e600d0d9 9f85a537927d30f0e397a0a0b7cb8b646982d9a6
gpt-engineer-app[bot] | 2026-09-26T13:55:36+00:00
Changes

Co-authored-by: Lighfe <REDACTED>

$ git log -1 --format=%B 9326256 | grep -c '^X-Lovable-Edit-ID: edt-521ff7d9-fba4-41ab-af1b-15c065bd0b33$'
1
$ git merge-base --is-ancestor 9f85a53 9326256 && echo yes
yes
$ git rev-parse 9326256^1
9f85a537927d30f0e397a0a0b7cb8b646982d9a6
```

### Poller log and timing summary (Q1, Q2)

```text
2026-09-26T13:54:16.917Z rc=0 main=4f68d71c3fb16767c40dcf888359d86a81c00ccd
2026-09-26T13:54:46.610Z rc=0 main=9f85a537927d30f0e397a0a0b7cb8b646982d9a6
2026-09-26T13:55:51.267Z rc=0 main=93262569438a3a3deaf937af42f4752d6b1f74cb
2026-09-26T13:58:00.635Z poller end
```

| | Change 1 (`wait=false`) | Change 2 (`wait=true`) |
|---|---|---|
| Send (local, before the call) | 13:54:19.445Z | 13:55:26.935Z |
| Message `created_at` | 13:54:24Z | 13:55:32Z |
| "Changes" commit (author date) | 13:54:34Z | 13:55:36Z |
| Edit `created_at` / merge commit date | 13:54:40Z / 13:54:40Z | 13:55:43Z / 13:55:42Z |
| Commit first seen on GitHub (poller) | 13:54:46.610Z | 13:55:51.267Z |
| "Finished" seen | 13:54:55.168Z (`get_message`, `response.status: completed`); previous poll at 13:54:27.758Z had no `response` | `send_message` returned `completed`, before 13:56:00.011Z |
| Send → finished | between 16 s (edit record) and 36 s (poll) | at most 33 s |
| Finished → commit on GitHub | 0 s: already there when "finished" was seen | 0 s: already there when the call returned |
| Edit record → commit on GitHub | at most 6.6 s | at most 8.3 s |

Commit graph of the throwaway repo after the spike:

```text
*   9326256 Chg'd home heading to "S3 Spike Two        <- edit edt-521ff7d9-…  (pin this for a launch that ends here)
|\
| * 8bd0027 Changes
|/
*   9f85a53 Updated home page tab title                  <- edit edt-62de6133-…
|\
| * dc37a98 Changes                                      (parent 4313be0, not 4f68d71)
* | 4f68d71 Add project README                           <- developer_update edt-ae2ad096-…, no trailer
|/
*   4313be0 Added counter landing page                   <- edit edt-50a47980-…
|\
| * 75f03af Changes
|/
* 07342b2 template: tanstack_start_ts_current-78c8e5169cf8
```

### Not tested

- A message that makes no code change (for example a question, or `plan_mode=true`). Expected: no `edit_id` and no `commit_sha` in the result, so nothing to pin.
- `awaiting_input`, `stopped`, `error` and the `send_message` timeout (`in_progress`). Their meaning comes from the schema text only.
- A commit pushed to the Lovable repo from outside Lovable (two-way sync). The docs say Lovable pulls it in; the next Lovable merge would then contain it.

## Consequences for the plan

Method for the engineer, from Q1 and Q2 (for #9, step 3 and step 5 of "Lane `frontend`"):

1. Send with `send_message` (`wait=true`, `timeout_seconds=600`). Keep `message_id` and `thread_id`.
2. If the result is `in_progress`, poll `get_message(project_id, message_id, thread_id)` until `response.status` is terminal. Read `response.status`, never the top-level `status`.
3. `completed`: take `edit_id` and `commit_sha`. `awaiting_input`: only a human can answer in the Lovable editor, so post `## Engineer: BLOCKED` with the reason. `stopped` or `error`: send a follow-up message within the budget, otherwise `## Engineer: BLOCKED`.
4. Wait until the commit is on GitHub: `git -C frontend fetch origin` until `git -C frontend merge-base --is-ancestor <commit_sha> origin/<branch>` succeeds (it was already true when "finished" was seen in both changes; use a short timeout, for example 5 minutes, then `## Engineer: BLOCKED`).
5. Check the link: `git -C frontend log -1 --format=%B <commit_sha>` contains `X-Lovable-Edit-ID: <edit_id>`.
6. Pin `<commit_sha>` of the **last** message of the launch (the merge commit), never a "Changes" commit and never the branch tip without steps 4–5. Check `git -C frontend diff <old pointer> <commit_sha> --stat` for changes that Lovable did not make in this launch (two-way sync).

### #9 (Frontend lane)

- Holds: spec 9.2 steps 1–7, the 60-minute budget, "nothing edits `frontend/` locally", and pinning an exact commit. Detection and pinning work through MCP as the spec assumes.
- Change needed: fill the placeholders with the method above, including the `awaiting_input` → BLOCKED rule and "read `response.status`, not `status`". `tools:` gets `Read, Grep, Glob, Bash` and the six tools from Q4 (`mcp__plugin_lovable_lovable__send_message`, `…__get_message`, `…__list_messages`, `…__list_edits`, `…__get_diff`, `…__get_project`). When #9 launches the agent the first time, check that these tools are reachable from the `tools:` list; in this spike session they were deferred and needed `ToolSearch`, so `ToolSearch` may have to be in `tools:` too.
- Owner decision needed: no.

### #11 (paint-math set-up)

- Holds: owner step 2 ("Create the Lovable project and connect it to GitHub") stays a manual owner step; MCP cannot do it (Q3). The manual steps are in the Q3 answer.
- Change needed: the Lovable repo is private by default, so the machine that runs the loop (engineer fetch, Codex QA with `--submodule=diff`) needs git read access to it, or the owner makes it public. Also the submodule should track the branch Lovable syncs (the default branch, `main` here).
- Owner decision needed: yes: keep the Lovable repo private (and give the loop machine read access), or make it public. If `paint-math` is public and `frontend/` stays private, readers of `paint-math` cannot open the frontend.

### #10 (README set-up section)

- Change needed: the prerequisite "Lovable MCP plugin (frontend lane only)" names the Claude Code plugin `lovable`, because the tool names in `frontend-engineer.md` (`mcp__plugin_lovable_lovable__…`) depend on it. The set-up names the manual GitHub connection (Q3) and the access to the private Lovable repo.
- Owner decision needed: no.

### #6 (Codex QA launcher)

- Holds, if Codex QA runs in the same clone in which the engineer fetched the submodule commits: then `git diff --submodule=diff <base>..<head>` needs no network. A fresh clone would need read access to the private Lovable repo, which the S2 localhost-only sandbox does not have.
- Owner decision needed: no.
