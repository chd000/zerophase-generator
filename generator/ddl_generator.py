from typing import Dict, Optional

from .models import SourceTable
from .settings import GeneratorSettings
from .xml_generator import _build_fields

_DDL_TAIL = [
    "   ) SEGMENT CREATION IMMEDIATE ",
    "  PCTFREE 10 PCTUSED 40 INITRANS 1 MAXTRANS 255 ",
    " NOCOMPRESS NOLOGGING",
    "  STORAGE(INITIAL 163840 NEXT 1048576 MINEXTENTS 1 MAXEXTENTS 2147483645",
    "  PCTINCREASE 0 FREELISTS 1 FREELIST GROUPS 1",
    "  BUFFER_POOL DEFAULT FLASH_CACHE DEFAULT CELL_FLASH_CACHE DEFAULT)",
    '  TABLESPACE "{tablespace}" ;',
]


def _sql_type(spec) -> str:
    datatype = spec["datatype"]
    if datatype == "varchar2":
        return "VARCHAR2({})".format(spec["prec"])
    if datatype == "char":
        return "CHAR({})".format(spec["prec"])
    if datatype in ("number", "number(p,s)"):
        if spec.get("explicit"):
            return "NUMBER ({}, {})".format(spec["prec"], spec["scale"])
        return "NUMBER"
    if datatype == "date":
        return "DATE"
    return "TIMESTAMP ({})".format(spec["scale"])


def generate_table_ddl(
    table: SourceTable,
    table_name: str,
    settings: Optional[GeneratorSettings] = None,
) -> str:
    settings = settings or GeneratorSettings()
    fields = _build_fields(table)
    lines = ['CREATE TABLE "{}"."{}" '.format(settings.owner, table_name)]
    for index, spec in enumerate(fields):
        prefix = "   (    " if index == 0 else "    "
        suffix = ", " if index < len(fields) - 1 else ""
        lines.append('{}"{}" {}{}'.format(prefix, spec["name"], _sql_type(spec), suffix))
    for tail in _DDL_TAIL:
        lines.append(tail.format(tablespace=settings.ddl_tablespace))
    return "\r\n".join(lines) + "\r\n"


def _ddl_file_name(table: SourceTable) -> str:
    base = table.src_name
    if base.upper().endswith("_SRC"):
        base = base[:-4]
    return base + ".sql"


def generate_ddl_for_table(
    table: SourceTable,
    settings: Optional[GeneratorSettings] = None,
) -> Dict[str, str]:
    settings = settings or GeneratorSettings()
    statements = [
        generate_table_ddl(table, table.src_name, settings),
        generate_table_ddl(table, table.dlt_name, settings),
        generate_table_ddl(table, table.tgt_name, settings),
    ]
    combined = "\r\n\r\n".join(text.rstrip("\r\n") for text in statements) + "\r\n"
    return {_ddl_file_name(table): combined}
