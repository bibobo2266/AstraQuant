from datetime import date

from astraquant.research.contact_registry import ContactRecord, append_contact_record


def test_contact_registry_append_preserves_existing_bytes(tmp_path):
    path = tmp_path / "CONTACT_REGISTRY.md"
    original = "# Contact Registry\n\n| 報告或結果識別 | 涵蓋期間 | 接觸日期 | 接觸情境 |\n|---|---|---|---|\n"
    path.write_text(original, encoding="utf-8")
    record = ContactRecord(
        result_id="report-a",
        covered_period="2016-01-04 ~ 2021-12-31",
        contact_date=date(2026, 9, 29),
        context="E1 effect report",
    )
    assert append_contact_record(path, record) is True
    after = path.read_text(encoding="utf-8")
    assert after.startswith(original)
    assert "report-a" in after
    assert append_contact_record(path, record) is False
    assert path.read_text(encoding="utf-8") == after
