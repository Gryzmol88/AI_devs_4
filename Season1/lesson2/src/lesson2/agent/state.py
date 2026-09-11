import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AgentState:
    trace_path: Path
    steps: list[dict[str, Any]] = field(default_factory=list)

    def log(self, payload: dict[str, Any]) -> None:
        self.steps.append(payload)
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

