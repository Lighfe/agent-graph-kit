import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
LANE = (ROOT / "docs/lovable-frontend-lane.md").read_text()
V2 = LANE.split("## Set-up")[1].split("\n## ")[0]


def test_steps_in_order():
    keys = ["Create the Lovable project", "workspace to GitHub", "Connect the project",
            "public", "git submodule add -b main", "@playwright/test",
            "git submodule update --remote frontend", "Lovable project: <project id>",
            "Install the `lovable` plugin"]
    pos = [V2.index(k) for k in keys]
    assert pos == sorted(pos)


def test_credit_checkin_and_synthetic_id():
    pauses = LANE.split("## How Lovable pauses")[1].split("\n## ")[0]
    assert "## Engineer: BLOCKED" in pauses and "before a frontend issue gets the label `ready`" in pauses
    assert "Lovable project: 00000000-0000-4000-8000-000000000000" in V2


def test_steps_written_once():
    assert LANE.count("git submodule add -b main") == 1
    assert "git submodule add -b main" not in README


def test_project_knowledge_step():
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


def test_readme_links_the_lane_file():
    assert README.count("](docs/lovable-frontend-lane.md)") >= 2
    step9 = [l for l in README.splitlines() if l.startswith("9. ")][0]
    assert "Lovable frontend lane" in step9 and "docs/lovable-frontend-lane.md" in step9
    assert "## Lovable frontend lane" not in README
    assert "Frontend lane (optional)" not in README


def test_lane_file_headings_and_no_version_words():
    for h in ["## Set-up", "## How Lovable pauses", "## QA pre-step", "## Accepted risk"]:
        assert h in LANE.splitlines()
    assert not re.search(r"\bv[12]\b", LANE, re.I)
