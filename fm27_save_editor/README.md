# FM 27 Save Editor

Простой редактор сохранений **Football Manager 27** на Python (tkinter GUI + CLI).

## Возможности

- Открытие файлов сохранения FM (контейнер `FMSG`: `.fmag` / `.fmsg` / `.fmgs`)
- Автодетект папки сохранений:
  - Windows: `Documents\Sports Interactive\Football Manager 2027\games`
  - macOS: `~/Library/Application Support/Football Manager 2027/games`
  - Linux: `~/.local/share/Sports Interactive/Football Manager 2027/games`
- Список блоков сохранения, предпросмотр текстовых (zlib) блоков
- Поиск по содержимому (с учётом/без учёта регистра)
- Быстрые правки:
  | Правка | Что меняет |
  |---|---|
  | Касса / трансферный бюджет | `cash`, `club-cash`, `transfer-budget` |
  | Бюджет зарплат | `wage-budget` |
  | Репутация клуба | `domestic-reputation`, `international-reputation` (1–25000) |
  | Форма игрока | `condition` (0–100) |
  | Энергия игрока | `energy` (0–100) |
  | Переименование | точное совпадение `"Старое имя"` → `"Новое имя"` |
  | Атрибут игрока | любой числовой shortname-атрибут (`pac`, `tech`, …), 1–200 |
- Безопасное сохранение: автоматическая резервная копия `.bak` + атомарная запись через `.tmp`

## Запуск

GUI:

```bash
python editor.py [путь_к_сохранению.fmag]
```

CLI (без графики):

```bash
python cli.py info   save.fmag                       # структура файла
python cli.py search save.fmag "cash"                # поиск подстроки
python cli.py edit   save.fmag cash 100000000        # касса → 100 млн
python cli.py edit   save.fmag reputation 20000
python cli.py edit   save.fmag name --old "Manchester United" --new "Man Utd FC"
python cli.py edit   save.fmag attribute --shortname pac --value 20
python cli.py edit   save.fmag condition 100 -o modified.fmag   # без правки оригинала
```

Тесты формата и правил:

```bash
python test_editor.py
```

## Структура проекта

```
fm27_save_editor/
├── editor.py        # tkinter GUI — главное окно
├── cli.py           # консольная версия (info / search / edit)
├── fmsgs.py         # парсер/сборщик контейнера FMSG (заголовок + zlib-блоки + таблица смещений)
├── rules.py         # правила правок (cash, reputation, name, атрибуты…)
└── test_editor.py   # тесты round-trip и правил
```

## Формат FMSG (кратко)

- 16 байт заголовка: сигнатура `FMSG`, смещение таблицы смещений, размер таблицы, число элементов
- далее — элементы данных (обычно zlib-сжатые текстовые блоки сохранения)
- в конце — таблица `uint32`-смещений (little-endian, абсолютные offsets)

Редактор переупаковывает изменённые текстовые блоки и пересчитывает таблицу смещений.

## Важно

- Сначала попробуйте на **копии** сохранения — правки атрибутов могут сломать карьеру.
- Если поле не найдено в тексте сохранения — правка безопасно пропускается (ничего не ломается).
- Имена полей (`cash = …`, `pac = …`) могут отличаться в реальных файлах FM; при необходимости
  добавьте свои пары «поле → значение» в `rules.py` или используйте поиск + просмотр блоков.
