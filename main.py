import argparse
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from generator import (GeneratorSettings, generate_ddl_for_table, generate_master_workflow_xml,
                       generate_stage_xml, generate_workflow_xml, load_source_tables)

STAGES = ("SRC", "DLT", "TGT")


def parse_process_ids(values):
    parsed = {}
    for key, text in values.items():
        text = (text or "").strip()
        if text.isdigit():
            parsed[key] = int(text)
    return parsed


def generate_tables(excel_path, out_dir, settings, table_names=None, log=None,
                    generate_mappings=True, generate_ddl=True, generate_workflow=True,
                    generate_master=True):
    log = log or (lambda message: None)
    tables = load_source_tables(excel_path)
    if not tables:
        log("В файле не найдено таблиц для генерации.")
        return []
    written = []
    processed = []
    for table in tables:
        if table_names is not None and table.table not in table_names:
            continue
        processed.append(table)
        xml_dir = os.path.join(out_dir, table.schema or "UNKNOWN", "xml")
        ddl_dir = os.path.join(out_dir, table.schema or "UNKNOWN", "ddl")
        if generate_mappings or generate_workflow:
            os.makedirs(xml_dir, exist_ok=True)
        if generate_ddl:
            os.makedirs(ddl_dir, exist_ok=True)
        if generate_mappings:
            for stage in STAGES:
                warnings = []
                try:
                    xml_text = generate_stage_xml(table, stage, settings, warnings=warnings)
                    out_path = os.path.join(xml_dir, table.mapping_name_for(stage) + ".XML")
                    with open(out_path, "wb") as stream:
                        stream.write(xml_text.encode("utf-8"))
                except Exception as exc:
                    log("[ОШИБКА] {} ({}): {}".format(table.table, stage, exc))
                    continue
                log("Создан: {}".format(out_path))
                for warning in warnings:
                    log("[ВНИМАНИЕ] {} ({}): {}".format(table.table, stage, warning))
                written.append(out_path)
        if generate_ddl:
            for ddl_file_name, ddl_text in generate_ddl_for_table(table, settings).items():
                try:
                    ddl_path = os.path.join(ddl_dir, ddl_file_name)
                    with open(ddl_path, "wb") as stream:
                        stream.write(ddl_text.encode("utf-8"))
                except Exception as exc:
                    log("[ОШИБКА] {} (DDL {}): {}".format(table.table, ddl_file_name, exc))
                    continue
                log("Создан: {}".format(ddl_path))
                written.append(ddl_path)
        if generate_workflow:
            warnings = []
            try:
                os.makedirs(xml_dir, exist_ok=True)
                wf_text = generate_workflow_xml(table, settings, warnings=warnings)
                wf_name = settings.workflow_name or "wf_ODS_{}_{}".format(table.schema, table.table)
                wf_path = os.path.join(xml_dir, wf_name + ".XML")
                with open(wf_path, "wb") as stream:
                    stream.write(wf_text.encode("utf-8"))
            except Exception as exc:
                log("[ОШИБКА] {} (WORKFLOW): {}".format(table.table, exc))
                continue
            log("Создан: {}".format(wf_path))
            written.append(wf_path)
    if generate_master and generate_workflow and processed:
        schema_order = []
        by_schema = {}
        for table in processed:
            key = table.schema.strip().upper()
            if key not in by_schema:
                by_schema[key] = []
                schema_order.append(key)
            by_schema[key].append(table)
        for schema in schema_order:
            schema_tables = by_schema[schema]
            warnings = []
            try:
                xml_dir = os.path.join(out_dir, schema_tables[0].schema or "UNKNOWN", "xml")
                os.makedirs(xml_dir, exist_ok=True)
                wf_text = generate_master_workflow_xml(schema_tables, settings, warnings=warnings)
                wf_name = settings.master_workflow_name or "wf_load_prm_ODS_" + schema
                wf_path = os.path.join(xml_dir, wf_name + ".XML")
                with open(wf_path, "wb") as stream:
                    stream.write(wf_text.encode("utf-8"))
            except Exception as exc:
                log("[ОШИБКА] (управляющий поток {}): {}".format(schema, exc))
                continue
            log("Создан: {}".format(wf_path))
            for warning in warnings:
                log("[ВНИМАНИЕ] (управляющий поток {}): {}".format(schema, warning))
            written.append(wf_path)
    return written


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Генератор потоков PowerCenter")
        self.geometry("960x640")
        self.excel_var = tk.StringVar()
        self.out_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop"))
        self.tables = []
        self.checked = set()
        self.process_ids = {}
        self.mappings_var = tk.BooleanVar(value=True)
        self.ddl_var = tk.BooleanVar(value=True)
        self.workflow_var = tk.BooleanVar(value=True)
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
        ttk.Checkbutton(buttons, text="Маппинги (XML)", variable=self.mappings_var).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(buttons, text="DDL-скрипты", variable=self.ddl_var).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(buttons, text="Поток (workflow)", variable=self.workflow_var).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Сгенерировать", command=self._generate).pack(side=tk.LEFT, padx=8)
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
        known = {t.table.strip().upper() for t in self.tables}
        self.process_ids = {k: v for k, v in self.process_ids.items() if k[0] in known}
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
        self._ask_process_ids()

    def _ask_process_ids(self):
        dialog = tk.Toplevel(self)
        dialog.title("Process ID ворклетов")
        dialog.transient(self)
        dialog.grab_set()
        wrapper = ttk.Frame(dialog, padding=8)
        wrapper.pack(fill=tk.BOTH, expand=True)
        defaults = GeneratorSettings()
        ttk.Label(wrapper, text=(
            "Таблиц: {}. Для каждой таблицы задайте $$wk_PROCESS_ID её ворклетов (SRC, DLT, TGT).\n"
            "Поля предзаполнены значениями по умолчанию (заглушка) — измените при необходимости."
        ).format(len(self.tables))).grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=(0, 6))
        canvas = tk.Canvas(wrapper, highlightthickness=0)
        vsb = ttk.Scrollbar(wrapper, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=1, column=0, sticky=tk.NSEW)
        vsb.grid(row=1, column=1, sticky=tk.NS)
        wrapper.rowconfigure(1, weight=1)
        wrapper.columnconfigure(0, weight=1)
        for col, title in enumerate(("Таблица (схема)", "SRC", "DLT", "TGT")):
            ttk.Label(inner, text=title).grid(row=0, column=col, sticky=tk.W, padx=4, pady=(0, 4))
        fields = {}
        for row, table in enumerate(self.tables, start=1):
            ttk.Label(inner, text="{} ({})".format(table.table, table.schema)).grid(
                row=row, column=0, sticky=tk.W, padx=4, pady=1)
            for col, stage in enumerate(STAGES, start=1):
                key = (table.table.strip().upper(), stage)
                if key in self.process_ids:
                    initial = str(self.process_ids[key])
                else:
                    initial = str(getattr(defaults, "wk_process_id_" + stage.lower()))
                var = tk.StringVar(value=initial)
                ttk.Entry(inner, textvariable=var, width=14).grid(row=row, column=col, padx=4, pady=1)
                fields[key] = var
        buttons = ttk.Frame(wrapper)
        buttons.grid(row=2, column=0, columnspan=2, sticky=tk.E, pady=(8, 0))

        def on_ok():
            self.process_ids = parse_process_ids({key: var.get() for key, var in fields.items()})
            self.log("Process ID ворклетов: указано значений: {} (остальные — по умолчанию).".format(
                len(self.process_ids)))
            dialog.destroy()

        ttk.Button(buttons, text="OK", command=on_ok).pack(side=tk.RIGHT)
        dialog.geometry("520x420")
        dialog.wait_window()

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
            wk_process_id_map=self.process_ids or None,
        )
        if not self.mappings_var.get() and not self.ddl_var.get() and not self.workflow_var.get():
            messagebox.showwarning("Ничего не выбрано", "Отметьте хотя бы один тип генерации.")
            return
        written = generate_tables(
            excel,
            out,
            settings,
            table_names=self.checked,
            log=self.log,
            generate_mappings=self.mappings_var.get(),
            generate_ddl=self.ddl_var.get(),
            generate_workflow=self.workflow_var.get(),
            generate_master=self.workflow_var.get(),
        )
        if written:
            messagebox.showinfo("Готово", "Создано файлов: {}".format(len(written)))
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
    parser.add_argument("--no-mappings", action="store_true", help="не генерировать маппинги (XML)")
    parser.add_argument("--no-ddl", action="store_true", help="не генерировать DDL-скрипты")
    parser.add_argument("--no-workflow", action="store_true", help="не генерировать поток (workflow)")
    parser.add_argument("--no-master", action="store_true", help="не генерировать управляющий поток")
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
        generate_mappings=not args.no_mappings,
        generate_ddl=not args.no_ddl,
        generate_workflow=not args.no_workflow,
        generate_master=not args.no_master,
    )
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
