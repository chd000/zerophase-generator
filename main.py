import argparse
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from generator import GeneratorSettings, generate_stage_xml, load_source_tables

STAGES = ("SRC", "DLT", "TGT")


def generate_tables(excel_path, out_dir, settings, table_names=None, log=None):
    log = log or (lambda message: None)
    tables = load_source_tables(excel_path)
    if not tables:
        log("В файле не найдено таблиц для генерации.")
        return []
    written = []
    for table in tables:
        if table_names is not None and table.table not in table_names:
            continue
        for stage in STAGES:
            warnings = []
            try:
                xml_text = generate_stage_xml(table, stage, settings, warnings=warnings)
                out_path = os.path.join(out_dir, table.mapping_name_for(stage) + ".XML")
                with open(out_path, "wb") as stream:
                    stream.write(xml_text.encode("utf-8"))
            except Exception as exc:
                log("[ОШИБКА] {} ({}): {}".format(table.table, stage, exc))
                continue
            log("Создан: {}".format(out_path))
            for warning in warnings:
                log("[ВНИМАНИЕ] {} ({}): {}".format(table.table, stage, warning))
            written.append(out_path)
    return written


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Генератор маппингов PowerCenter (SRC / DLT / TGT)")
        self.geometry("960x640")
        self.excel_var = tk.StringVar()
        self.out_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop"))
        self.folder_var = tk.StringVar(value="MY_FOLDER_NAME")
        self.repository_var = tk.StringVar(value="REPOSITORY")
        self.tables = []
        self.checked = set()
        container = ttk.Frame(self, padding=8)
        container.pack(fill=tk.BOTH, expand=True)
        files = ttk.LabelFrame(container, text="Файлы", padding=8)
        files.pack(fill=tk.X)
        ttk.Label(files, text="Файл Excel:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(files, textvariable=self.excel_var).grid(row=0, column=1, sticky=tk.EW, padx=4)
        ttk.Button(files, text="Обзор…", command=self._choose_excel).grid(row=0, column=2)
        ttk.Label(files, text="Каталог вывода:").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(files, textvariable=self.out_var).grid(row=1, column=1, sticky=tk.EW, padx=4)
        ttk.Button(files, text="Обзор…", command=self._choose_out).grid(row=1, column=2)
        files.columnconfigure(1, weight=1)
        settings = ttk.LabelFrame(container, text="Настройки генерации", padding=8)
        settings.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(settings, text="Folder:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(settings, textvariable=self.folder_var, width=26).grid(row=0, column=1, sticky=tk.W, padx=4)
        ttk.Label(settings, text="Repository:").grid(row=0, column=2, sticky=tk.W, padx=(16, 0))
        ttk.Entry(settings, textvariable=self.repository_var, width=26).grid(row=0, column=3, sticky=tk.W, padx=4)
        tables_frame = ttk.LabelFrame(container, text="Таблицы", padding=8)
        tables_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        columns = ("system", "db", "schema", "table", "inc", "src")
        self.tree = ttk.Treeview(tables_frame, columns=columns, show="tree headings", selectmode="none")
        self.tree.heading("#0", text="✓")
        self.tree.column("#0", width=36, stretch=False)
        for column, title, width, stretch in [
            ("system", "СИ", 170, True),
            ("db", "БД", 70, False),
            ("schema", "Схема", 90, True),
            ("table", "Таблица", 150, True),
            ("inc", "Инкрементальная таблица", 210, True),
            ("src", "SRC-имя", 210, True),
        ]:
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, stretch=stretch)
        scroll = ttk.Scrollbar(tables_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        scroll.grid(row=0, column=1, sticky=tk.NS)
        tables_frame.rowconfigure(0, weight=1)
        tables_frame.columnconfigure(0, weight=1)
        self.tree.bind("<Button-1>", self._on_click)
        buttons = ttk.Frame(container)
        buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(buttons, text="Загрузить таблицы из Excel", command=self._load_tables).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Сгенерировать маппинги (SRC / DLT / TGT)", command=self._generate).pack(side=tk.LEFT, padx=8)
        self.log_text = tk.Text(container, height=9, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

    def log(self, message):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _choose_excel(self):
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx"), ("Все файлы", "*.*")])
        if path:
            self.excel_var.set(path)
            self._load_tables()

    def _choose_out(self):
        path = filedialog.askdirectory()
        if path:
            self.out_var.set(path)

    def _load_tables(self):
        path = self.excel_var.get().strip()
        if not path:
            messagebox.showwarning("Нет файла", "Укажите файл Excel.")
            return
        try:
            self.tables = load_source_tables(path)
        except Exception as exc:
            messagebox.showerror("Ошибка чтения", str(exc))
            return
        self.checked = {t.table for t in self.tables}
        self.tree.delete(*self.tree.get_children())
        for t in self.tables:
            self.tree.insert(
                "",
                tk.END,
                iid=t.table,
                text="☑",
                values=(t.system, t.db, t.schema, t.table, t.inc_table, t.src_name),
            )
        self.log("Загружено таблиц: {}".format(len(self.tables)))

    def _on_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        if item in self.checked:
            self.checked.discard(item)
            self.tree.item(item, text="☐")
        else:
            self.checked.add(item)
            self.tree.item(item, text="☑")

    def _generate(self):
        excel = self.excel_var.get().strip()
        out = self.out_var.get().strip()
        if not excel:
            messagebox.showwarning("Нет файла", "Укажите файл Excel.")
            return
        if not out:
            messagebox.showwarning("Нет каталога", "Укажите каталог вывода.")
            return
        if not os.path.isdir(out):
            messagebox.showerror("Ошибка", "Каталог вывода не существует: {}".format(out))
            return
        settings = GeneratorSettings(
            folder_name=self.folder_var.get().strip() or "MY_FOLDER_NAME",
            repository_name=self.repository_var.get().strip() or "REPOSITORY",
        )
        written = generate_tables(excel, out, settings, table_names=self.checked, log=self.log)
        if written:
            messagebox.showinfo("Готово", "Создано маппингов: {}".format(len(written)))
        else:
            messagebox.showwarning("Ничего не создано", "См. журнал ниже.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Генератор маппингов PowerCenter (SRC / DLT / TGT) из Excel")
    parser.add_argument("--headless", action="store_true", help="работать без графического окна")
    parser.add_argument("--excel", help="путь к файлу Excel")
    parser.add_argument("--out", help="каталог вывода XML")
    parser.add_argument("--folder", default="MY_FOLDER_NAME", help="имя папки PowerCenter")
    parser.add_argument("--repository", default="REPOSITORY", help="имя репозитория PowerCenter")
    parser.add_argument("--only", action="append", default=[], help="генерировать только указанную таблицу (можно повторять)")
    args = parser.parse_args(argv)
    if not args.headless:
        App().mainloop()
        return 0
    if not args.excel or not args.out:
        parser.error("--headless требует --excel и --out")
    settings = GeneratorSettings(
        folder_name=args.folder,
        repository_name=args.repository,
    )
    written = generate_tables(
        args.excel,
        args.out,
        settings,
        table_names=set(args.only) or None,
        log=print,
    )
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
