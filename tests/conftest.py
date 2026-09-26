import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".claude" / "hooks"), str(ROOT / "scripts"), str(ROOT / "tests")]
