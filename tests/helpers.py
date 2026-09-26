from issue_state import Facts, Issue

HEAD = "a" * 40
OLD = "b" * 40


def launch(role, n=1, agent=None):
    agent = agent or {"pm": "pm", "engineer": "software-engineer", "qa": "qa-codex"}[role]
    return f"## Launch: {role} (attempt {n})\nAgent: {agent}"


def cont(role, n, agent):
    return f"## Launch: {role} (continued, round {n})\nAgent: {agent}"


def issue(*comments, labels=("ready",), body="Lane: default\n", open=True):
    return Issue(number=7, open=open, labels=frozenset(labels), body=body, comments=tuple(comments))


def facts(iss, head=HEAD, clean=True):
    return Facts(issue=iss, head=head, clean=clean)
