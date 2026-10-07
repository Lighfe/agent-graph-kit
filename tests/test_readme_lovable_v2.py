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
