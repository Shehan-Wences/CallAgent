from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml

class CampaignError(ValueError):
    """Raised when a campaign file is missing or malformed."""

DEFAULT_VOICE = "marin"
DEFAULT_DISCLOSURE = "if_asked"

@dataclass
class Campaign:
    product: dict
    persona: dict
    goal: dict
    opening_line: str
    disclosure: str = DEFAULT_DISCLOSURE
    guardrails: list[str] = field(default_factory=list)
    body: str = ""

def _split_front_matter(text: str) -> tuple[str, str]:
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        raise CampaignError("Campaign file must start with a YAML front-matter block (---).")
    after = stripped.split("---", 2)
    if len(after) < 3:
        raise CampaignError("Front-matter block is not closed with a second '---'.")
    return after[1], after[2]

def _require(data: dict, dotted: str):
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node or node[part] in (None, ""):
            raise CampaignError(f"Campaign is missing required field: {dotted}")
        node = node[part]
    return node

def load_campaign(path: str | Path) -> Campaign:
    path = Path(path)
    if not path.exists():
        raise CampaignError(f"Campaign file not found: {path}")
    raw_yaml, body = _split_front_matter(path.read_text())
    data = yaml.safe_load(raw_yaml) or {}
    if not isinstance(data, dict):
        raise CampaignError("Front-matter did not parse to a mapping.")

    _require(data, "product.name")
    _require(data, "persona.name")
    _require(data, "goal.type")
    _require(data, "opening_line")

    persona = dict(data["persona"])
    persona.setdefault("voice", DEFAULT_VOICE)

    return Campaign(
        product=dict(data["product"]),
        persona=persona,
        goal=dict(data["goal"]),
        opening_line=str(data["opening_line"]),
        disclosure=str(data.get("disclosure", DEFAULT_DISCLOSURE)),
        guardrails=list(data.get("guardrails") or []),
        body=body.strip(),
    )
