from pathlib import Path

README = (Path(__file__).resolve().parent.parent / "README.md").read_text()
V2 = README.split("## Lovable frontend lane (optional, v2)")[1].split("\n## ")[0]


def test_v2_steps_in_order():
    keys = ["Create the Lovable project", "workspace to GitHub", "Connect the project",
            "public", "git submodule add -b main", "@playwright/test",
            "git submodule update --remote frontend", "Lovable project: <project id>",
            "Install the `lovable` plugin"]
    pos = [V2.index(k) for k in keys]
    assert pos == sorted(pos)


def test_v2_credit_checkin_and_synthetic_id():
    assert "## Engineer: BLOCKED" in V2 and "before a frontend issue gets the label `ready`" in V2
    assert "Lovable project: 00000000-0000-4000-8000-000000000000" in V2


def test_steps_written_once():
    assert README.count("git submodule add -b main") == 1


def test_v2_project_knowledge_step():
    keys = ["Lovable project: <project id>", "Set the Lovable project knowledge",
            "Install the `lovable` plugin"]
    pos = [V2.index(k) for k in keys]
    assert pos == sorted(pos)
    step = V2.split("Set the Lovable project knowledge")[1].split("Install the `lovable` plugin")[0]
    assert "has no tool to set project knowledge" in step
    for k in ["drawing library", "random-number library", "`@playwright/test` dev dependency",
              "only after the frontend-engineer has confirmed"]:
        assert k in step
    for bad in ["auto-approve", "implement right away", "no need to wait"]:
        assert bad not in step.lower()
