from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class ContactRecord:
    result_id: str
    covered_period: str
    contact_date: date
    context: str

    def __post_init__(self) -> None:
        for name, value in {
            "result_id": self.result_id,
            "covered_period": self.covered_period,
            "context": self.context,
        }.items():
            if not value.strip():
                raise ValueError(f"{name} is required")


def _cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def render_contact_row(record: ContactRecord) -> str:
    return (
        f"| {_cell(record.result_id)} | {_cell(record.covered_period)} | "
        f"{record.contact_date.isoformat()} | {_cell(record.context)} |"
    )


def append_contact_record(path: str | Path, record: ContactRecord) -> bool:
    """Append one contact row without rewriting or deleting existing rows."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    before = p.read_text(encoding="utf-8")
    row = render_contact_row(record)
    if row in before.splitlines():
        return False
    suffix = "" if before.endswith("\n") else "\n"
    after = before + suffix + row + "\n"
    if not after.startswith(before):
        raise RuntimeError("contact registry append-only invariant violated")
    p.write_text(after, encoding="utf-8")
    return True
