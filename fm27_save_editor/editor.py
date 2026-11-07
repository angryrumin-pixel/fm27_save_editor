# -*- coding: utf-8 -*-
r"""
FM 27 Save Editor — простой графический редактор сохранений Football Manager 27.

Запуск:
    python editor.py

Возможности:
  * Открытие файла сохранения (.fmag / .fmsg / .dat-контейнер с FMSG)
  * Автодетект пути сохранений FM (Documents\Sports Interactive\Football Manager 2027)
  * Список текстовых блоков сохранения с предпросмотром
  * Быстрые правки: касса, бюджет зарплат, репутация, форма, энергия
  * Переименование и произвольный атрибут игрока
  * Поиск по содержимому сохранения
  * Сохранение с обязательной резервной копией (.bak)
"""

from __future__ import annotations

import os
import shutil
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

if getattr(sys, "frozen", False):
    # PyInstaller: модули уже встроены в exe
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    BASE_DIR = Path(__file__).resolve().parent
    sys.path.insert(0, str(BASE_DIR))

from fmsgs import FmsgFile  # noqa: E402
from rules import EDIT_LABELS, apply_edit  # noqa: E402


# ---------------------------------------------------------------- дефолтные пути

def default_save_dir() -> Path | None:
    """Типовое расположение сохранений FM 27 на Windows/macOS/Linux."""
    home = Path.home()
    candidates = [
        home / "Documents" / "Sports Interactive" / "Football Manager 2027" / "games",
        home / "Documents" / "Sports Interactive" / "Football Manager 27" / "games",
        home / "Library" / "Application Support" / "Football Manager 2027" / "games",
        home / ".local" / "share" / "Sports Interactive" / "Football Manager 2027" / "games",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


SAVE_GLOB = ("*.fmag", "*.fmsg", "*.fmgs")


class EditorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("FM 27 Save Editor — простой редактор сохранений")
        self.geometry("980x640")
        self.minsize(860, 560)

        self.fmsg: FmsgFile | None = None
        self.current_path: Path | None = None
        self.dirty = False

        self._build_menu()
        self._build_ui()
        self._set_status('Готов. Откройте файл сохранения (Файл → Открыть, Ctrl+O).')

    # ------------------------------------------------------------------ menu
    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        fm = tk.Menu(menubar, tearoff=0)
        fm.add_command(label="Открыть…", accelerator="Ctrl+O", command=self.open_file)
        fm.add_command(label="Сохранить", accelerator="Ctrl+S", command=self.save_file)
        fm.add_command(label="Сохранить как…", command=self.save_file_as)
        fm.add_separator()
        fm.add_command(label="Выход", command=self.destroy)
        menubar.add_cascade(label="Файл", menu=fm)

        helpm = tk.Menu(menubar, tearoff=0)
        helpm.add_command(label="О программе", command=self.about)
        menubar.add_cascade(label="Справка", menu=helpm)
        self.config(menu=menubar)
        self.bind_all("<Control-o>", lambda e: self.open_file())
        self.bind_all("<Control-s>", lambda e: self.save_file())

    # -------------------------------------------------------------------- ui
    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        # --- верхняя панель: путь к файлу --------------------------------
        top = ttk.Frame(root)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Файл сохранения:").grid(row=0, column=0, padx=(0, 6))
        self.var_path = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_path, state="readonly").grid(
            row=0, column=1, sticky="ew")
        ttk.Button(top, text="Открыть…", command=self.open_file).grid(row=0, column=2, padx=(6, 0))

        # --- панель быстрых правок ---------------------------------------
        edit_box = ttk.LabelFrame(root, text="Быстрые правки", padding=8)
        edit_box.grid(row=1, column=0, sticky="ew", pady=8)

        self.var_kind = tk.StringVar(value=EDIT_LABELS["cash"])
        kinds = ["cash", "wage_budget", "reputation", "condition", "energy", "name", "attribute"]
        self._kind_keys = kinds
        # reverse map: label -> key
        self._label_to_key = {EDIT_LABELS[k]: k for k in kinds}
        combo = ttk.Combobox(edit_box, textvariable=self.var_kind,
                             values=[EDIT_LABELS[k] for k in kinds], state="readonly", width=28)
        combo.grid(row=0, column=0, padx=(0, 8))
        combo.bind("<<ComboboxSelected>>", lambda e: self._on_kind_change())

        # поле значения (для имени — старое имя)
        self.lbl_value = ttk.Label(edit_box, text="Значение:")
        self.lbl_value.grid(row=0, column=1, padx=(0, 4))
        self.var_value = tk.StringVar(value="100000000")
        self.ent_value = ttk.Entry(edit_box, textvariable=self.var_value, width=16)
        self.ent_value.grid(row=0, column=2, padx=(0, 8))

        # доп. поле (для имени/атрибута)
        self.lbl_extra = ttk.Label(edit_box, text="Старое имя:")
        self.var_extra = tk.StringVar()
        self.ent_extra = ttk.Entry(edit_box, textvariable=self.var_extra, width=22)

        ttk.Button(edit_box, text="Применить", command=self.apply_current_edit).grid(
            row=0, column=3, padx=(0, 6))
        ttk.Button(edit_box, text="Сохранить", command=self.save_file).grid(row=0, column=4)

        self._on_kind_change()

        # --- низ: список блоков + предпросмотр + поиск --------------------
        paned = ttk.PanedWindow(root, orient="horizontal")
        paned.grid(row=2, column=0, sticky="nsew")

        left = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=1)
        paned.add(right, weight=3)

        # слева — блоки сохранения
        ttk.Label(left, text="Блоки сохранения:").pack(anchor="w")
        self.lst = tk.Listbox(left, exportselection=False)
        self.lst.pack(fill="both", expand=True, pady=(2, 6))
        self.lst.bind("<<ListboxSelect>>", self._show_element)

        # справа — поиск + просмотр
        search_row = ttk.Frame(right)
        search_row.pack(fill="x")
        ttk.Label(search_row, text="Поиск:").pack(side="left", padx=(0, 4))
        self.var_search = tk.StringVar()
        ttk.Entry(search_row, textvariable=self.var_search).pack(
            side="left", fill="x", expand=True)
        ttk.Button(search_row, text="Найти", command=self.do_search).pack(side="left", padx=4)
        self.var_case = tk.BooleanVar(value=False)
        ttk.Checkbutton(search_row, text="Учитывать регистр", variable=self.var_case).pack(side="left")

        ttk.Label(right, text="Предпросмотр блока:").pack(anchor="w", pady=(8, 2))
        self.preview = scrolledtext.ScrolledText(right, wrap="word", height=10,
                                                 font=("Consolas", 9))
        self.preview.pack(fill="both", expand=True)

        # --- статусная строка ---------------------------------------------
        self.var_status = tk.StringVar()
        status = ttk.Label(root, textvariable=self.var_status, relief="sunken", anchor="w")
        status.grid(row=3, column=0, sticky="ew", pady=(8, 0))

    # --------------------------------------------------------------- helpers
    def _on_kind_change(self) -> None:
        kind = self._current_kind()
        # убираем доп. поле и восстанавливаем основное
        self.ent_extra.grid_forget()
        self.lbl_extra.grid_forget()
        self.ent_value.grid(row=0, column=2, padx=(0, 8))

        defaults = {
            "cash": "100000000",
            "wage_budget": "50000000",
            "reputation": "5000",
            "condition": "100",
            "energy": "100",
            "name": "",
            "attribute": "20",
        }
        labels = {
            "cash": "Сумма:",
            "wage_budget": "Сумма:",
            "reputation": "Репутация (1–25000):",
            "condition": "Форма (0–100):",
            "energy": "Энергия (0–100):",
            "name": "Старое имя:",
            "attribute": "Новое значение:",
        }
        self.lbl_value.config(text=labels.get(kind, "Значение:"))
        self.var_value.set(defaults.get(kind, ""))

        if kind == "name":
            self.lbl_extra.config(text="Новое имя:")
            self.lbl_extra.grid(row=1, column=1, padx=(0, 4), pady=(6, 0))
            self.ent_extra.grid(row=1, column=2, columnspan=2, sticky="ew", pady=(6, 0))
            self.var_extra.set("")
        elif kind == "attribute":
            self.lbl_extra.config(text="Shortname атрибута:")
            self.lbl_extra.grid(row=1, column=1, padx=(0, 4), pady=(6, 0))
            self.ent_extra.grid(row=1, column=2, columnspan=2, sticky="ew", pady=(6, 0))
            self.ent_extra.delete(0, "end")
            self.ent_extra.insert(0, "pac")

    def _current_kind(self) -> str:
        return self._label_to_key.get(self.var_kind.get(), "cash")

    def _set_status(self, msg: str) -> None:
        self.var_status.set(msg)

    def _refresh_list(self) -> None:
        self.lst.delete(0, "end")
        if not self.fmsg:
            return
        for i, el in enumerate(self.fmsg.elements):
            tag = "текст" if el.is_text else ("zlib" if el.compressed else "бинарный")
            self.lst.insert("end", f"[{i}] {tag}, {len(el.raw):,} байт".replace(",", " "))

    # ---------------------------------------------------------------- actions
    def open_file(self) -> None:
        initial = default_save_dir()
        path = filedialog.askopenfilename(
            title="Выберите файл сохранения FM 27",
            initialdir=str(initial) if initial else str(Path.home()),
            filetypes=[("Football Manager saves", " ".join(SAVE_GLOB)),
                       ("Все файлы", "*.*")],
        )
        if not path:
            return
        self.load_path(Path(path))

    def load_path(self, path: Path) -> bool:
        try:
            self.fmsg = FmsgFile.load(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка открытия",
                                 f"Не удалось прочитать файл:\n{path}\n\n{exc}")
            return False
        self.current_path = path
        self.var_path.set(str(path))
        self.dirty = False
        self._refresh_list()
        n_text = len(self.fmsg.text_elements())
        self._set_status(
            f"Открыто: {path.name} — блоков: {len(self.fmsg.elements)}, "
            f"текстовых: {n_text}. Не забудьте сделать резервную копию!"
        )
        if n_text == 0:
            messagebox.showwarning(
                "Внимание",
                "В файле не найдено текстовых (zlib) блоков.\n"
                "Возможно, это не save FM или формат изменился — "
                "правки будут недоступны, но просмотр работает.",
            )
        return True

    def apply_current_edit(self) -> None:
        if not self.fmsg:
            messagebox.showinfo("Нет файла", "Сначала откройте файл сохранения.")
            return
        kind = self._current_kind()

        kwargs: dict = {}
        if kind == "name":
            # первое поле — СТАРОЕ имя, второе (доп.) — НОВОЕ имя
            old = self.var_value.get().strip()
            new = self.var_extra.get().strip()
            if not old or not new:
                messagebox.showwarning("Переименование",
                                       "Укажите СТАРОЕ имя (первое поле) и НОВОЕ имя.")
                return
            kwargs = {"old": old, "new": new}
        elif kind == "attribute":
            shortname = self.var_extra.get().strip()
            try:
                value = int(self.var_value.get().strip())
            except ValueError:
                messagebox.showwarning("Атрибут", "Значение атрибута должно быть числом 1–200.")
                return
            kwargs = {"shortname": shortname, "value": value}
        else:
            try:
                kwargs = {"value": int(self.var_value.get().strip().replace(" ", "").replace("_", ""))}
            except ValueError:
                messagebox.showwarning("Значение", "Введите целое число.")
                return

        total_changed = 0
        details: list[str] = []
        for idx, elem in self.fmsg.text_elements():
            new_text, res = apply_edit(elem.text or "", kind, **kwargs)
            if res.changed:
                elem.text = new_text
                total_changed += res.count
                details.extend(res.details)

        if total_changed == 0:
            msg = "Ничего не найдено/не изменено."
            if details:
                msg += " " + "; ".join(details)
            self._set_status(msg)
            messagebox.showinfo("Результат",
                                "Правка применена, но нужные поля в сохранении не найдены.\n"
                                "Проверьте название поля/значение — формат FM может отличаться.")
            return

        self.dirty = True
        self._set_status(
            f"Изменено замен: {total_changed} ({'; '.join(sorted(set(details)))}). "
            f"Не забудьте сохранить файл (Ctrl+S)."
        )
        self._show_element(None)

    def _selected_preview_text_name(self) -> str:
        return ""

    def do_search(self) -> None:
        if not self.fmsg:
            self._set_status("Нет открытого файла.")
            return
        needle = self.var_search.get()
        if not needle:
            return
        if not self.var_case.get():
            needle_cmp = needle.lower()
            hits = [i for i, e in self.fmsg.text_elements()
                    if needle_cmp in (e.text or "").lower()]
        else:
            hits = self.fmsg.find_text(needle)
        if not hits:
            self._set_status(f"Совпадений нет: «{needle}»")
            return
        self._set_status(f"Найдено в блоках: {hits[:20]}{'…' if len(hits) > 20 else ''}")
        self.lst.selection_clear(0, "end")
        for h in hits[:50]:
            self.lst.selection_set(h)
        if hits:
            self.lst.see(hits[0])

    def _show_element(self, _event) -> None:
        sel = self.lst.curselection()
        if not sel or not self.fmsg:
            return
        i = sel[0]
        el = self.fmsg.elements[i]
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        text = el.text if el.is_text else el.decoded()
        MAX = 200_000
        self.preview.insert("1.0", text[:MAX])
        if len(text) > MAX:
            self.preview.insert("end", f"\n…(обрезано, всего {len(text):,} симв.)".replace(",", " "))
        self.preview.configure(state="normal")

    # ------------------------------------------------------------- saving
    def save_file(self) -> None:
        if not self.fmsg or not self.current_path:
            messagebox.showinfo("Сохранение", "Нечего сохранять — файл не открыт.")
            return
        self._write(self.current_path)

    def save_file_as(self) -> None:
        if not self.fmsg:
            messagebox.showinfo("Сохранение", "Файл не открыт.")
            return
        path = filedialog.asksaveasfilename(
            title="Сохранить как…",
            defaultextension=".fmag",
            filetypes=[("Football Manager save", "*.fmag"), ("Все файлы", "*.*")],
        )
        if path:
            self._write(Path(path))

    def _write(self, path: Path) -> None:
        # резервная копия исходного файла
        try:
            if path.exists():
                bak = path.with_suffix(path.suffix + ".bak")
                if not bak.exists():
                    shutil.copy2(path, bak)
            data = self.fmsg.dumps()  # type: ignore[union-attr]
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка записи", f"Не удалось сохранить:\n{exc}")
            return
        self.dirty = False
        self._set_status(f"Сохранено: {path.name} (резервная копия: {path.name}.bak)")

    # ------------------------------------------------------------- about
    def about(self) -> None:
        messagebox.showinfo(
            "О программе",
            "FM 27 Save Editor — простой редактор сохранений Football Manager 27.\n\n"
            "• Работает с FMSG-контейнером (.fmag/.fmsg/.fmgs)\n"
            "• Перед первым сохранением создаёт копию .bak\n"
            "• Правки: касса, бюджеты, репутация, форма/энергия,\n"
            "  переименование и числовые атрибуты игроков\n\n"
            "Используйте на свой страх и риск; сначала попробуйте на копии сохранения.",
        )


def main() -> None:
    app = EditorApp()
    # автоподхват файла из аргумента командной строки
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        app.load_path(Path(sys.argv[1]))
    app.mainloop()


if __name__ == "__main__":
    main()
