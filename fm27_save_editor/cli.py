# -*- coding: utf-8 -*-
"""
CLI-версия редактора (без GUI) — удобно для скриптов и проверки формата.

Примеры:
    python cli.py info save.fmag
    python cli.py search save.fmag "cash"
    python cli.py edit save.fmag cash 100000000
    python cli.py edit save.fmag name --old "Manchester United" --new "Man Utd"
    python cli.py edit save.fmag attribute --shortname pac --value 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fmsgs import FmsgFile  # noqa: E402
from rules import apply_edit  # noqa: E402


def cmd_info(args) -> int:
    f = FmsgFile.load(args.file)
    print(f"Файл: {args.file}")
    print(f"Блоков всего: {len(f.elements)}")
    texts = f.text_elements()
    print(f"Текстовых блоков: {len(texts)}")
    for i, el in texts:
        preview = (el.text or "").strip().replace("\n", " ")[:80]
        print(f"  [{i}] {len(el.raw):>9} бт (текст {len(el.text or ''):>9} симв): {preview}")
    return 0


def cmd_search(args) -> int:
    f = FmsgFile.load(args.file)
    needle = args.needle if args.case else args.needle.lower()
    found = False
    for i, el in f.text_elements():
        hay = el.text if args.case else (el.text or "").lower()
        if needle in (hay or ""):
            found = True
            pos = (hay or "").find(needle)
            snippet = (el.text or "")[max(0, pos - 60):pos + 60].replace("\n", " ")
            print(f"[{i}] …{snippet}…")
    if not found:
        print("Совпадений нет.")
    return 0


def cmd_edit(args) -> int:
    f = FmsgFile.load(args.file)
    kwargs: dict = {}
    if args.kind == "name":
        if not args.old or not args.new:
            print("Для name нужны --old и --new", file=sys.stderr)
            return 2
        kwargs = {"old": args.old, "new": args.new}
    elif args.kind == "attribute":
        if not args.shortname or args.value is None:
            print("Для attribute нужны --shortname и --value", file=sys.stderr)
            return 2
        kwargs = {"shortname": args.shortname, "value": args.value}
    else:
        if args.value is None:
            print(f"Для {args.kind} нужно --value", file=sys.stderr)
            return 2
        kwargs = {"value": args.value}

    total = 0
    details: list[str] = []
    for idx, elem in f.text_elements():
        new_text, res = apply_edit(elem.text or "", args.kind, **kwargs)
        if res.changed:
            elem.text = new_text
            total += res.count
            details.extend(res.details)

    if total == 0:
        print("Ничего не найдено — файл не изменён.")
        return 1

    out = Path(args.output) if args.output else Path(args.file)
    if out == Path(args.file) and not args.no_backup:
        bak = out.with_suffix(out.suffix + ".bak")
        if not bak.exists():
            bak.write_bytes(Path(args.file).read_bytes())
            print(f"Резервная копия: {bak}")
    f.save(out)
    print(f"Замен выполнено: {total}. Сохранено: {out}")
    for d in sorted(set(details)):
        print(f"  • {d}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fm27-cli", description="CLI-редактор сохранений FM 27")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("info", help="Показать структуру файла сохранения")
    pi.add_argument("file")
    pi.set_defaults(func=cmd_info)

    ps = sub.add_parser("search", help="Поиск подстроки в текстовых блоках")
    ps.add_argument("file")
    ps.add_argument("needle")
    ps.add_argument("--case", action="store_true", help="Учитывать регистр")
    ps.set_defaults(func=cmd_search)

    pe = sub.add_parser("edit", help="Применить правку")
    pe.add_argument("file")
    pe.add_argument("kind", choices=["cash", "wage_budget", "reputation",
                                     "condition", "energy", "name", "attribute"])
    pe.add_argument("value", type=int, nargs="?", default=None)
    pe.add_argument("--old", default=None, help="Старое имя (для kind=name)")
    pe.add_argument("--new", default=None, help="Новое имя (для kind=name)")
    pe.add_argument("--shortname", default=None, help="Shortname атрибута (для kind=attribute)")
    pe.add_argument("-o", "--output", default=None, help="Куда сохранить (по умолчанию — поверх)")
    pe.add_argument("--no-backup", action="store_true", help="Не создавать .bak")
    pe.set_defaults(func=cmd_edit)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
