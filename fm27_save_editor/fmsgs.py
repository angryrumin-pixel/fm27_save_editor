# -*- coding: utf-8 -*-
"""
Чтение и запись файлов сохранений Football Manager (.fmag/.fmgs).

Формат (известная структура FM Save Game):
  - заголовок из 16 байт:
        * 4 байта  : сигнатура "FMSG" (little-endian)
        * 4 байта  : смещение таблицы смещений (offset table)
        * 4 байта  : размер таблицы смещений
        * 4 байта  : количество элементов данных (data elements)
  - далее идут элементы данных (как правило, сжатые zlib блоки — текстовые
    данные сохранения в формате, близком к XML/BNF)
  - в конце файла — таблица смещений: массив uint32 (little-endian),
    по одному значению на каждый элемент.

Этот модуль умеет:
  * разбирать файл на элементы;
  * декомппрессировать zlib-элементы в текст;
  * заменять/модифицировать текстовое содержимое элементов;
  * собирать файл обратно корректным (с пересчётом таблицы смещений).
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

MAGIC = b"FMSG"
HEADER_SIZE = 16


@dataclass
class FmsgElement:
    """Один элемент данных внутри файла сохранения."""

    raw: bytes = b""
    text: str | None = None  # декодированный текст (если это zlib-текст)
    compressed: bool = False
    is_text: bool = False

    def decoded(self) -> str:
        if self.text is not None:
            return self.text
        return self.raw.decode("utf-8", errors="replace")


@dataclass
class FmsgFile:
    elements: list[FmsgElement] = field(default_factory=list)
    version_bytes: bytes = b"\x00\x00\x00\x00"

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls, path: str | Path) -> "FmsgFile":
        data = Path(path).read_bytes()
        return cls.loads(data)

    @classmethod
    def loads(cls, data: bytes) -> "FmsgFile":
        if len(data) < HEADER_SIZE:
            raise ValueError("Файл слишком мал — это не FM save?")

        magic = data[0:4]
        off_table, off_size, n_elems = struct.unpack("<III", data[4:16])

        obj = cls()

        if magic != MAGIC or not cls._table_looks_valid(data, off_table, off_size, n_elems):
            # Неизвестный/повреждённый формат — сохраняем как один сырой блок.
            obj.elements = [FmsgElement(raw=data)]
            return obj

        offsets = struct.unpack(
            f"<{n_elems}I", data[off_table:off_table + n_elems * 4]
        )
        bounds = sorted(set(offsets)) + [len(data)]

        for i in range(n_elems):
            start, end = offsets[i], _next_bound(bounds, offsets[i])
            raw = data[start:end]
            elem = FmsgElement(raw=raw)
            try:
                dec = zlib.decompress(raw)
                elem.compressed = True
                # Похоже ли на текст?
                sample = dec[:2048]
                printable = sum(1 for b in sample if 32 <= b < 127 or b in (9, 10, 13))
                if sample and printable / len(sample) > 0.85:
                    elem.is_text = True
                    elem.text = dec.decode("utf-8", errors="replace")
            except zlib.error:
                pass
            obj.elements.append(elem)

        return obj

    @staticmethod
    def _table_looks_valid(data: bytes, off_table: int, off_size: int, n_elems: int) -> bool:
        if n_elems == 0 or n_elems > 10_000:
            return False
        if off_table + n_elems * 4 > len(data):
            return False
        if off_table < HEADER_SIZE:
            return False
        try:
            offsets = struct.unpack(f"<{n_elems}I", data[off_table:off_table + n_elems * 4])
        except struct.error:
            return False
        first = min(offsets)
        return first >= HEADER_SIZE and max(offsets) < len(data)

    # ------------------------------------------------------------------ save
    def dumps(self) -> bytes:
        """Собирает файл обратно: заголовок + элементы + таблица смещений.

        Смещения в таблице — абсолютные (от начала файла), как в оригинале.
        Таблица смещений размещается ПОСЛЕ всех элементов данных.
        """
        n = len(self.elements)
        table_size = n * 4
        body_start = HEADER_SIZE

        # сначала кодируем тела элементов, чтобы знать размеры
        blobs = []
        for elem in self.elements:
            if elem.text is not None and elem.is_text:
                payload = elem.text.encode("utf-8")
                blob = zlib.compress(payload, 9) if elem.compressed else payload
            else:
                blob = elem.raw
            blobs.append(blob)

        total_body = sum(len(b) for b in blobs)
        off_table = body_start + total_body

        out = bytearray()
        out += MAGIC
        out += struct.pack("<III", off_table, table_size, n)
        assert len(out) == HEADER_SIZE

        offsets = []
        cursor = body_start
        for blob in blobs:
            offsets.append(cursor)
            out += blob
            cursor += len(blob)

        out += struct.pack(f"<{n}I", *offsets)
        return bytes(out)

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.dumps())

    # ---------------------------------------------------------------- helpers
    def text_elements(self) -> list[tuple[int, FmsgElement]]:
        return [(i, e) for i, e in enumerate(self.elements) if e.is_text]

    def find_text(self, needle: str) -> list[int]:
        """Возвращает индексы текстовых элементов, содержащих подстроку."""
        return [i for i, e in self.text_elements() if needle in (e.text or "")]


def _next_bound(sorted_bounds: list[int], value: int) -> int:
    for b in sorted_bounds:
        if b > value:
            return b
    return sorted_bounds[-1]
