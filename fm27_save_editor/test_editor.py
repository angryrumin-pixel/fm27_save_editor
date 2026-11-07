# -*- coding: utf-8 -*-
"""Тесты round-trip и правил для fm27_save_editor."""

from __future__ import annotations

import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fmsgs import FmsgFile  # noqa: E402
from rules import apply_edit  # noqa: E402


def make_sample_fmsg() -> bytes:
    """Собираем синтетический FMSG-файл из двух текстовых zlib-блоков."""
    t1 = (
        '<save>\n'
        '  <club id="42">\n'
        '    name = "Manchester United"\n'
        '    cash = 25000000\n'
        '    transfer-budget = 15000000\n'
        '    wage-budget = 8000000\n'
        '    domestic-reputation = 4500\n'
        '    international-reputation = 6000\n'
        '  </club>\n'
        '</save>\n'
    )
    t2 = (
        '<player id="777">\n'
        '  full-name = "Wayne Rooney"\n'
        '  condition = 62\n'
        '  energy = 71\n'
        '  pac = 78\n'
        '  tech = 84\n'
        '</player>\n'
    )
    blobs = [zlib.compress(t.encode("utf-8"), 9) for t in (t1, t2)]
    import struct
    header_size = 16
    total = sum(len(b) for b in blobs)
    off_table = header_size + total
    out = bytearray(b"FMSG")
    out += struct.pack("<III", off_table, len(blobs) * 4, len(blobs))
    cursor = header_size
    offsets = []
    for b in blobs:
        offsets.append(cursor)
        out += b
        cursor += len(b)
    out += struct.pack(f"<{len(offsets)}I", *offsets)
    return bytes(out)


def test_roundtrip(tmpdir: Path):
    data = make_sample_fmsg()
    p = tmpdir / "sample.fmag"
    p.write_bytes(data)

    f = FmsgFile.load(p)
    assert len(f.elements) == 2, f"ожидалось 2 блока, получено {len(f.elements)}"
    texts = f.text_elements()
    assert len(texts) == 2, "оба блока должны быть текстовыми"
    assert "Manchester United" in f.elements[0].text
    assert "Wayne Rooney" in f.elements[1].text

    # неизменённый round-trip должен читаться снова
    repacked = f.dumps()
    f2 = FmsgFile.loads(repacked)
    assert len(f2.elements) == 2
    assert f2.elements[0].text == f.elements[0].text
    assert f2.elements[1].text == f.elements[1].text
    print("OK roundtrip")


def test_edits():
    data = make_sample_fmsg()
    f = FmsgFile.loads(data)

    # cash
    total = 0
    for _, el in f.text_elements():
        new_text, res = apply_edit(el.text or "", "cash", value=100_000_000)
        if res.changed:
            el.text = new_text
            total += res.count
    assert total >= 2, f"ожидались замены cash/transfer-budget, есть {total}"
    assert "cash = 100000000" in f.elements[0].text
    assert "transfer-budget = 100000000" in f.elements[0].text

    # name
    for _, el in f.text_elements():
        new_text, res = apply_edit(el.text or "", "name",
                                   old="Manchester United", new="Man Utd FC")
        if res.changed:
            el.text = new_text
    assert '"Man Utd FC"' in f.elements[0].text
    assert '"Manchester United"' not in f.elements[0].text

    # attribute pac -> 20
    for _, el in f.text_elements():
        new_text, res = apply_edit(el.text or "", "attribute", shortname="pac", value=20)
        if res.changed:
            el.text = new_text
    assert "pac = 20" in f.elements[1].text

    # condition clamp
    for _, el in f.text_elements():
        new_text, res = apply_edit(el.text or "", "condition", value=999)
        if res.changed:
            el.text = new_text
    assert "condition = 100" in f.elements[1].text

    # сохранение и повторное чтение изменённого файла
    repacked = f.dumps()
    f3 = FmsgFile.loads(repacked)
    assert '"Man Utd FC"' in f3.elements[0].text
    assert "pac = 20" in f3.elements[1].text
    print("OK edits")


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        test_roundtrip(Path(td))
    test_edits()
    print("ALL TESTS PASSED")
