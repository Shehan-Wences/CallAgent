from __future__ import annotations
import json
from pathlib import Path

class BookingStore:
    """Append-only JSON list of booking/outcome records."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                records = json.loads(self.path.read_text())
                if not isinstance(records, list):
                    records = []
            except json.JSONDecodeError:
                records = []
        else:
            records = []
        records.append(record)
        self.path.write_text(json.dumps(records, indent=2))
