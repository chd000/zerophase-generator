import re
from typing import List

from .excel_reader import read_sheet
from .models import SourceAttribute, SourceTable

SHEET_TABLES = "Таблицы источника"
SHEET_ATTRIBUTES = "Атрибуты источника"

_WS_RE = re.compile(r"\s+")


def _header_columns(rows, header_indices) -> dict:
    headers = {}
    for index in header_indices:
        for column, value in rows[index].items():
            title = str(value).strip()
            if title and title not in headers:
                headers[title] = column
    return headers


def _cell(cells: dict, headers: dict, title: str) -> str:
    column = headers.get(title)
    if column is None:
        return ""
    return str(cells.get(column, "") or "").strip()


def _identifier(cells: dict, headers: dict, title: str) -> str:
    return _WS_RE.sub("", _cell(cells, headers, title))


def _text(cells: dict, headers: dict, title: str) -> str:
    return _WS_RE.sub(" ", _cell(cells, headers, title)).strip()


def load_source_tables(xlsx_path: str) -> List[SourceTable]:
    table_rows = read_sheet(xlsx_path, SHEET_TABLES)
    attribute_rows = read_sheet(xlsx_path, SHEET_ATTRIBUTES)
    table_headers = _header_columns(table_rows, [0])
    tables = []
    for cells in table_rows[1:]:
        table = SourceTable(
            system=_text(cells, table_headers, "СИ"),
            db=_identifier(cells, table_headers, "БД"),
            schema=_identifier(cells, table_headers, "Схема"),
            table=_identifier(cells, table_headers, "Таблица источника"),
            description=_text(cells, table_headers, "Описание таблиц источников"),
            inc_table=_identifier(cells, table_headers, "Инкрементальная таблица"),
            tgt_table=_identifier(cells, table_headers, "Таргетная таблица"),
            workflow=_text(cells, table_headers, "Workflow IPC"),
            comment=_text(cells, table_headers, "Комментарий"),
        )
        if table.table or table.inc_table:
            tables.append(table)
    attribute_headers = _header_columns(attribute_rows, [0, 1])
    by_key = {(t.schema.upper(), t.table.upper()): t for t in tables}
    for cells in attribute_rows[2:]:
        name = _identifier(cells, attribute_headers, "Атрибут источника")
        if not name:
            continue
        key = (
            _identifier(cells, attribute_headers, "Схема").upper(),
            _identifier(cells, attribute_headers, "Таблица источника").upper(),
        )
        table = by_key.get(key)
        if table is None:
            continue
        table.attributes.append(
            SourceAttribute(
                name=name,
                data_type=_text(cells, attribute_headers, "Тип данных"),
                description=_text(cells, attribute_headers, "Описание атрибута"),
                pk=_cell(cells, attribute_headers, "PK").upper() == "Y",
            )
        )
    return tables
