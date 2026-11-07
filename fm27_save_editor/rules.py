# -*- coding: utf-8 -*-
"""
Правила редактирования сохранений Football Manager 27.

Каждое правило — чистая функция: принимает текст элемента сохранения,
возвращает (новый_текст, EditResult). Если поле не найдено — ничего
не меняем (безопасный режим).

Поддерживаемые правки:
  * cash          — касса/трансферный бюджет клуба
  * wage_budget   — бюджет на зарплаты
  * reputation    — репутация клуба (1..25000)
  * condition     — форма игрока (0..100)
  * energy        — энергия игрока (0..100)
  * name          — переименование (клуб/игрок/менеджер)
  * attribute     — произвольный числовой атрибут по shortname (1..200)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class EditResult:
    changed: bool = False
    count: int = 0
    details: list[str] = field(default_factory=list)


def _replace_int_field(text: str, fld: str, value: int) -> tuple[str, int]:
    pattern = re.compile(rf"(\b{re.escape(fld)}\s*=\s*)(-?\d+)")
    return pattern.subn(lambda m: m.group(1) + str(int(value)), text)


def _fields_for(kind: str) -> list[str]:
    return {
        "cash": ["cash", "club-cash", "transfer-budget"],
        "wage_budget": ["wage-budget"],
        "reputation": ["domestic-reputation", "international-reputation"],
        "condition": ["condition"],
        "energy": ["energy"],
    }.get(kind, [])


# ------------------------------------------------------------------ правила

def edit_cash(text: str, amount: int) -> tuple[str, EditResult]:
    total = 0
    for fld in _fields_for("cash"):
        text, n = _replace_int_field(text, fld, amount)
        total += n
    res = EditResult(changed=total > 0, count=total)
    if total:
        res.details.append(f"Касса/бюджет → {amount:,}".replace(",", " "))
    return text, res


def edit_wage_budget(text: str, amount: int) -> tuple[str, EditResult]:
    text, n = _replace_int_field(text, "wage-budget", amount)
    res = EditResult(changed=n > 0, count=n)
    if n:
        res.details.append(f"Бюджет зарплат → {amount:,}".replace(",", " "))
    return text, res


def edit_reputation(text: str, value: int) -> tuple[str, EditResult]:
    value = max(1, min(25000, int(value)))
    total = 0
    for fld in _fields_for("reputation"):
        text, n = _replace_int_field(text, fld, value)
        total += n
    res = EditResult(changed=total > 0, count=total)
    if total:
        res.details.append(f"Репутация → {value}")
    return text, res


def edit_condition(text: str, value: int) -> tuple[str, EditResult]:
    value = max(0, min(100, int(value)))
    text, n = _replace_int_field(text, "condition", value)
    res = EditResult(changed=n > 0, count=n)
    if n:
        res.details.append(f"Форма игрока → {value}")
    return text, res


def edit_energy(text: str, value: int) -> tuple[str, EditResult]:
    value = max(0, min(100, int(value)))
    text, n = _replace_int_field(text, "energy", value)
    res = EditResult(changed=n > 0, count=n)
    if n:
        res.details.append(f"Энергия → {value}")
    return text, res


def edit_name(text: str, old: str, new: str) -> tuple[str, EditResult]:
    """Меняет строковое имя (точное совпадение в кавычках)."""
    if not old or not new:
        return text, EditResult(details=["Пустое имя — ничего не сделано"])
    escaped_new = new.replace("\\", "\\\\").replace('"', '\\"')
    # old передаётся «как есть» (без кавычек внутри) — простое экранирование для regex
    pattern = re.compile('"' + re.escape(old) + '"')
    new_text, n = pattern.subn(f'"{escaped_new}"', text)
    res = EditResult(changed=n > 0, count=n)
    if n:
        res.details.append(f'"{old}" → "{new}" ({n}x)')
    return new_text, res


def edit_attribute(text: str, shortname: str, value: int) -> tuple[str, EditResult]:
    """Меняет числовой атрибут вида `shortname = 15` (например, pac, tech)."""
    if not shortname or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", shortname):
        return text, EditResult(details=["Некорректное имя атрибута"])
    value = max(1, min(200, int(value)))
    text, n = _replace_int_field(text, shortname, value)
    res = EditResult(changed=n > 0, count=n)
    if n:
        res.details.append(f"Атрибут '{shortname}' → {value} ({n}x)")
    return text, res


# ------------------------------------------------------------------ диспетчер

INT_RULES = {
    "cash": edit_cash,
    "wage_budget": edit_wage_budget,
    "reputation": edit_reputation,
    "condition": edit_condition,
    "energy": edit_energy,
}

EDIT_LABELS = {
    "cash": "Касса / трансферный бюджет",
    "wage_budget": "Бюджет зарплат",
    "reputation": "Репутация клуба",
    "condition": "Форма игрока",
    "energy": "Энергия игрока",
    "name": "Переименование",
    "attribute": "Атрибут игрока",
}


def apply_edit(text: str, kind: str, **kwargs) -> tuple[str, EditResult]:
    """Единая точка входа: (текст, результат)."""
    if kind == "name":
        return edit_name(text, kwargs.get("old", ""), kwargs.get("new", ""))
    if kind == "attribute":
        return edit_attribute(text, kwargs.get("shortname", ""), kwargs.get("value", 1))
    rule = INT_RULES.get(kind)
    if rule is None:
        return text, EditResult(details=[f"Неизвестный тип правки: {kind}"])
    try:
        value = int(kwargs.get("value", 0))
    except (TypeError, ValueError):
        return text, EditResult(details=["Значение должно быть целым числом"])
    return rule(text, value)
