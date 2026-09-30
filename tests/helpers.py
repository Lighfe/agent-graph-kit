from issue_state import Facts, Issue

HEAD = "a" * 40
OLD = "b" * 40


def launch(role, n=1, agent=None, call=None):
    agent = agent or {"pm": "pm", "engineer": "software-engineer", "qa": "qa-codex"}[role]
    text = f"## Launch: {role} (attempt {n})\nAgent: {agent}"
    return f"{text}\nCall: {call}" if call else text


def cont(role, n, agent, call=None):
    text = f"## Launch: {role} (continued, round {n})\nAgent: {agent}"
    return f"{text}\nCall: {call}" if call else text


def not_started(role, n, call, continued=False, reason="Classifier unavailable"):
    kind = f"continued, round {n}" if continued else f"attempt {n}"
    return f"## Launch not started: {role} ({kind})\nCall: {call}\nReason: {reason}"


def issue(*comments, labels=("ready",), body="Lane: default\n", open=True):
    return Issue(number=7, open=open, labels=frozenset(labels), body=body, comments=tuple(comments))


def facts(iss, head=HEAD, clean=True, blocker_open=None):
    return Facts(issue=iss, head=head, clean=clean, blocker_open=blocker_open)
