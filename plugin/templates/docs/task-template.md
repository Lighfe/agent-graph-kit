Lane: default
<!-- default, or frontend (only in a repo with a Lovable submodule in frontend/) -->
Source: <URL>
<!-- optional, only for follow-ups: the URL of the issue, comment or review the follow-up came from -->
Permissions: none
<!-- list each permission beyond the defaults that the engineer or QA needs (for example GitHub writes other than issue comments: create, link, reorder or close issues; writes to other external systems; settings changes), separated by `;`. Each entry ends with ` - set` once the owner has set it. `none` when there is none -->

## Goal

One or two sentences on what should be true when this is done.

## Acceptance criteria

- [ ] A statement you can check by looking at the result
- [ ] One line per case, including the awkward ones

## Out of scope

- Something that does not belong in this task, moved to #TASK-NUMBER

## Constraints

- Files this should stay inside
- Libraries to use
- Guidelines to follow

# Stage issue

A stage issue has the label `stage` and never the label `ready`. It never goes through PM, engineer and QA. Its work is its sub-issues: each sub-issue is a task in the form above. A stage issue has no `Lane:` line. The default exit check is "Every sub-issue is closed and the purpose is met."

```
## Purpose

One or two sentences on what the stage is for.

## Background

Context that every sub-issue needs: the plan, the spec, decisions taken.

## Exit check

Every sub-issue is closed and the purpose is met.
```
