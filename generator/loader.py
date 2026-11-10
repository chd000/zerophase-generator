import re
from typing import List, Tuple

from .excel_reader import read_sheets
from .models import SourceAttribute, SourceTable

SHEET_TABLES = "Таблицы источника"
SHEET_ATTRIBUTES = "Атрибуты источника"

_WS_RE = re.compile(r"\s+")
_STAGE_SUFFIX_RE = re.compile(r"(?:^|[^A-ZА-ЯЁ])(SRC|DLT|TGT)$", re.IGNORECASE)
_HEADER_SCAN = 5

_TABLE_TITLES = (
    "СИ",
    "БД",
    "Схема",
    "Таблица источника",
    "Описание таблиц источников",
    "Описание таблиц источника",
    "Описание таблицы",
    "Инкрементальная таблица",
    "Таргетная таблица",
    "Workflow IPC",
    "Комментарий",
    "Комментарии",
)

_ATTRIBUTE_TITLES = (
    "Схема",
    "Таблица источника",
    "Атрибут источника",
    "Наименование атрибута",
    "Тип данных",
    "Описание атрибута",
    "PK",
)


def _stage_suffix(title: str) -> str:
    match = _STAGE_SUFFIX_RE.search(str(title).strip())
    return match.group(1).upper() if match else ""


def _row_titles(row: dict) -> set:
    return {str(value).strip() for value in row.values()}


def _header_columns(rows, header_indices) -> dict:
    headers = {}
    for index in header_indices:
        for column, value in rows[index].items():
            title = str(value).strip()
            if title and title not in headers:
                headers[title] = column
    return headers


def _split_header(rows, titles, allow_stage: bool = False) -> Tuple[dict, int]:
    titles = set(titles)
    first = None
    known = set()
    for index in range(min(_HEADER_SCAN, len(rows))):
        row_titles = _row_titles(rows[index])
        found = row_titles & titles
        if found or (allow_stage and any(_stage_suffix(title) for title in row_titles)):
            first = index
            known = found
            break
    if first is None:
        return {}, 0
    last = first
    if first + 1 < len(rows):
        extra = _row_titles(rows[first + 1]) & (titles - known)
        if extra:
            last = first + 1
    return _header_columns(rows, range(last + 1)), last + 1


def _column_for(headers: dict, titles, suffix: str = "") -> str:
    for title, column in headers.items():
        if title in titles or (suffix and _stage_suffix(title) == suffix):
            return column
    return ""


def _cell(cells: dict, column: str) -> str:
    if not column:
        return ""
    return str(cells.get(column, "") or "").strip()


def _identifier(cells: dict, column: str) -> str:
    return _WS_RE.sub("", _cell(cells, column))


def _unquoted(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()
    return text


def _text(cells: dict, column: str) -> str:
    return _WS_RE.sub(" ", _cell(cells, column)).strip()


def _table_columns(headers: dict) -> dict:
    return {
        "system": _column_for(headers, ("СИ",)),
        "db": _column_for(headers, ("БД",)),
        "schema": _column_for(headers, ("Схема",)),
        "table": _column_for(headers, ("Таблица источника",)),
        "description": _column_for(
            headers,
            ("Описание таблиц источников", "Описание таблиц источника", "Описание таблицы"),
        ),
        "inc_table": _column_for(headers, ("Инкрементальная таблица",), suffix="SRC"),
        "tgt_table": _column_for(headers, ("Таргетная таблица",), suffix="TGT"),
        "workflow": _column_for(headers, ("Workflow IPC",)),
        "comment": _column_for(headers, ("Комментарий", "Комментарии")),
    }


def _attribute_columns(headers: dict) -> dict:
    return {
        "schema": _column_for(headers, ("Схема",)),
        "table": _column_for(headers, ("Таблица источника",)),
        "name": _column_for(headers, ("Атрибут источника", "Наименование атрибута")),
        "data_type": _column_for(headers, ("Тип данных",)),
        "avro_type": _column_for(headers, ("Тип AVRO",)),
        "description": _column_for(headers, ("Описание атрибута",)),
        "pk": _column_for(headers, ("PK",)),
    }


def load_source_tables(xlsx_path: str) -> List[SourceTable]:
    sheets = read_sheets(xlsx_path, [SHEET_TABLES, SHEET_ATTRIBUTES])
    table_rows = sheets[SHEET_TABLES]
    attribute_rows = sheets[SHEET_ATTRIBUTES]
    table_headers, table_start = _split_header(table_rows, _TABLE_TITLES, allow_stage=True)
    table_cols = _table_columns(table_headers)
    tables = []
    for cells in table_rows[table_start:]:
        table = SourceTable(
            system=_text(cells, table_cols["system"]),
            db=_identifier(cells, table_cols["db"]),
            schema=_identifier(cells, table_cols["schema"]),
            table=_identifier(cells, table_cols["table"]),
            description=_text(cells, table_cols["description"]),
            inc_table=_identifier(cells, table_cols["inc_table"]),
            tgt_table=_identifier(cells, table_cols["tgt_table"]),
            workflow=_text(cells, table_cols["workflow"]),
            comment=_text(cells, table_cols["comment"]),
        )
        if table.table or table.inc_table:
            tables.append(table)
    attribute_headers, attribute_start = _split_header(attribute_rows, _ATTRIBUTE_TITLES)
    attribute_cols = _attribute_columns(attribute_headers)
    by_key = {(t.schema.upper(), t.table.upper()): t for t in tables}
    for cells in attribute_rows[attribute_start:]:
        name = _unquoted(_identifier(cells, attribute_cols["name"]))
        if not name:
            continue
        key = (
            _identifier(cells, attribute_cols["schema"]).upper(),
            _identifier(cells, attribute_cols["table"]).upper(),
        )
        table = by_key.get(key)
        if table is None:
            continue
        table.attributes.append(
            SourceAttribute(
                name=name,
                data_type=_text(cells, attribute_cols["data_type"])
                or _text(cells, attribute_cols["avro_type"]),
                description=_text(cells, attribute_cols["description"]),
                pk=_cell(cells, attribute_cols["pk"]).upper() == "Y",
            )
        )
    return tables
