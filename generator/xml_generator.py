import datetime
import json
import re
import uuid
from dataclasses import dataclass
from typing import List, Optional

from .models import SourceTable

_TYPE_RE = re.compile(
    r"^([A-Za-z0-9_ ]+?)\s*(?:\(\s*(\d+)\s*(?:,\s*(\d+))?\s*(?:char|byte)?\s*\))?$",
    re.IGNORECASE,
)

_LOGICAL_TYPE_ALIASES = {
    "timestamp-micros": "timestamp",
    "timestamp-millis": "timestamp",
    "local-timestamp-micros": "timestamp",
    "local-timestamp-millis": "timestamp",
    "decimal": "number",
    "numeric": "number",
}

_TYPE_SUBSTITUTIONS = {
    "string": ("varchar2", 1000, 0),
    "long": ("number", None, None),
}

FIELD_LENGTH = {"varchar2": 0, "number": 24, "date": 19, "timestamp": 19}

TECH_FIELD_SPECS = [
    ("DWH$CHANGE_DATE", "date", None, None),
    ("DWH$CHANGE_TYPE", "varchar2", 25, 0),
    ("ODS$OP_SEQ", "number", None, None),
    ("ODS$OP_CSN", "number", None, None),
    ("ODS$COMMIT_TS", "timestamp", None, None),
    ("ODS$PROCESSED_DT", "date", None, None),
    ("ODS$OP_TYPE", "varchar2", 50, 0),
]

GATHER_STATS_SQL = (
    "begin dbms_stats.gather_table_stats (ownname=>'{owner}',tabname=>'{tabname}'{cascade_sep}TRUE, "
    "granularity=>'AUTO', estimate_percent=>5, method_opt=>'FOR ALL COLUMNS SIZE 1')\\;"
)

TGT_SOURCE_FILTER = "DWH$CHANGE_TYPE IN ('I', 'U', 'D')"


def _strip_quotes(text: str) -> str:
    text = text.strip()
    while len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def _json_type_info(text: str):
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict):
        value = data.get("logicalType") or data.get("type")
        if isinstance(value, str):
            precision = data.get("precision")
            scale = data.get("scale")
            return (
                value,
                precision if isinstance(precision, int) else None,
                scale if isinstance(scale, int) else None,
            )
        return None, None, None
    match = re.search(r'"logicalType"\s*:\s*"([^"]+)"', text)
    if match:
        value = match.group(1)
    else:
        match = re.search(r'"type"\s*:\s*"([^"]+)"', text)
        value = match.group(1) if match else None
    if not value:
        return None, None, None
    precision_match = re.search(r'"precision"\s*:\s*(\d+)', text)
    scale_match = re.search(r'"scale"\s*:\s*(\d+)', text)
    return (
        value,
        int(precision_match.group(1)) if precision_match else None,
        int(scale_match.group(1)) if scale_match else None,
    )


def parse_data_type(raw):
    text = _strip_quotes(str(raw or ""))
    json_precision = None
    json_scale = None
    if text.startswith("{"):
        logical, json_precision, json_scale = _json_type_info(text)
        if not logical:
            raise ValueError("Не удалось разобрать тип данных: {!r}".format(raw))
        logical = logical.strip()
        text = _LOGICAL_TYPE_ALIASES.get(logical.lower(), logical)
    key = text.strip().lower()
    if key in _TYPE_SUBSTITUTIONS:
        base, precision, scale = _TYPE_SUBSTITUTIONS[key]
    else:
        match = _TYPE_RE.match(text.strip())
        if not match:
            raise ValueError("Не удалось разобрать тип данных: {!r}".format(raw))
        base = re.sub(r"\s+", " ", match.group(1)).lower()
        precision = int(match.group(2)) if match.group(2) else None
        scale = int(match.group(3)) if match.group(3) else None
    if json_precision is not None:
        precision = json_precision
    if json_scale is not None:
        scale = json_scale
    return base, precision, scale


def _field_spec(datatype, precision, scale):
    if datatype == "varchar2":
        size = precision if precision is not None else 1000
        return {"datatype": "varchar2", "phys": size, "prec": size, "scale": 0}
    if datatype == "number":
        prec = precision if precision is not None else 15
        return {
            "datatype": "number",
            "phys": prec,
            "prec": prec,
            "scale": scale if scale is not None else 0,
            "explicit": precision is not None,
        }
    if datatype == "date":
        return {"datatype": "date", "phys": 19, "prec": 19, "scale": 0}
    if datatype in ("timestamp", "datetime"):
        return {"datatype": "timestamp", "phys": 26, "prec": 26, "scale": 6}
    raise ValueError("Неподдерживаемый тип данных: {!r}".format(datatype))


def _escape_attr(value) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("\\", "&#x5c;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
        .replace("\r", "&#xD;")
        .replace("\n", "&#xA;")
    )


def _attr_list(pairs) -> str:
    return " ".join('{} ="{}"'.format(name, _escape_attr(value)) for name, value in pairs)


def _attr_plain(pairs) -> str:
    return " ".join('{}="{}"'.format(name, _escape_attr(value)) for name, value in pairs)


@dataclass
class GeneratorSettings:
    folder_name: str = "MY_FOLDER_NAME"
    folder_owner: str = "Administrator"
    dbdname: str = "OFSDEV"
    owner: str = "STAGE"
    repository_name: str = "REPOSITORY"
    repository_version: str = "189"
    repository_version_full: str = "189.98"
    codepage: str = "UTF-8"
    repository_database_type: str = "PostgreSQL"
    definition_database_type: str = "Oracle"
    folder_uuid: Optional[str] = None
    creation_date: Optional[str] = None


def _build_fields(table: SourceTable) -> List[dict]:
    fields = []
    for name, datatype, precision, scale in TECH_FIELD_SPECS:
        spec = _field_spec(datatype, precision, scale)
        spec["name"] = name
        spec["description"] = ""
        fields.append(spec)
    for attribute in table.attributes:
        base, precision, scale = parse_data_type(attribute.data_type)
        spec = _field_spec(base, precision, scale)
        spec["name"] = attribute.name
        spec["description"] = ""
        fields.append(spec)
    offset = 0
    physical_offset = 0
    for number, spec in enumerate(fields, 1):
        spec["field_number"] = number
        spec["length"] = FIELD_LENGTH[spec["datatype"]]
        spec["offset"] = offset
        spec["physical_offset"] = physical_offset
        offset += spec["length"]
        physical_offset += spec["phys"]
    return fields


def _transform_type(spec):
    if spec["datatype"] == "varchar2":
        return "string", spec["prec"], 0
    if spec["datatype"] == "number":
        if spec.get("explicit"):
            return "decimal", spec["prec"], spec["scale"]
        return "double", 15, 0
    return "date/time", 29, 9


def _pk_columns(table: SourceTable, warnings: List[str]) -> List[str]:
    marked = [a.name for a in table.attributes if a.pk]
    named = [n for n in marked if n.upper().startswith("PK_")]
    rest = [n for n in marked if not n.upper().startswith("PK_")]
    columns = named + rest
    if not columns:
        warnings.append("Не найдены PK-атрибуты — PARTITION BY в Sql Query пропущен")
    return columns


def _sql_query(table: SourceTable, warnings: List[str]) -> str:
    business = [a.name for a in table.attributes]
    outer = [
        "DWH$CHANGE_DATE",
        "DWH$CHANGE_TYPE",
        "ODS$OP_SEQ",
        "ODS$OP_CSN",
        "ODS$COMMIT_TS",
        "ODS$PROCESSED_DT",
        "ODS$OP_TYPE",
    ] + business
    inner = ["ODS$OP_SEQ", "ODS$OP_CSN", "ODS$COMMIT_TS", "ODS$PROCESSED_DT", "ODS$OP_TYPE"] + business
    partition = _pk_columns(table, warnings)
    lines = ["SELECT " + ",\r\n       ".join(outer)]
    lines.append("  FROM (SELECT ROW_NUMBER ()")
    lines.append("               OVER (")
    if partition:
        lines.append("                  PARTITION BY " + ", ".join(partition))
    lines.append("                  ORDER BY")
    lines.append("                     ODS$COMMIT_TS DESC, ODS$OP_CSN DESC, ODS$OP_SEQ DESC)")
    lines.append("                  AS RN,")
    lines.append("               SYSDATE AS DWH$CHANGE_DATE,")
    lines.append("               'U' AS DWH$CHANGE_TYPE,")
    lines.append("               " + ",\r\n               ".join(inner))
    lines.append("          FROM {}.{}".format(table.schema, table.table))
    lines.append("         WHERE     ODS$PROCESSED_DT >=")
    lines.append("                      TO_DATE ('$$FROM_PRC_DTTM', 'DD.MM.YYYY HH24:MI:SS')")
    lines.append("               AND ODS$PROCESSED_DT <=")
    lines.append("                      TO_DATE ('$$TO_PRC_DTTM', 'DD.MM.YYYY HH24:MI:SS'))")
    lines.append(" WHERE RN = 1")
    return "\r\n".join(lines)


def _sql_query_dlt(table: SourceTable, settings: GeneratorSettings, warnings: List[str]) -> str:
    business = [a.name for a in table.attributes]
    pk = _pk_columns(table, warnings)
    if not pk:
        raise ValueError("Для DLT-маппинга необходимы PK-атрибуты")
    columns = [
        "ODS$OP_SEQ",
        "ODS$OP_CSN",
        "ODS$COMMIT_TS",
        "ODS$PROCESSED_DT",
        "ODS$OP_TYPE",
    ] + business
    lines = [
        "SELECT DISTINCT",
        "       N.DWH$CHANGE_DATE,",
        "       CASE",
        "          WHEN N.ODS$OP_TYPE = 'DELETE' THEN 'D'",
        "          WHEN N.ODS$COMMIT_TS < O.ODS$COMMIT_TS THEN 'S'",
        "          WHEN N.ODS$COMMIT_TS >= O.ODS$COMMIT_TS THEN 'U'",
        "          WHEN O.{} IS NULL THEN 'I'".format(pk[0]),
        "       END",
        "          AS DWH$CHANGE_TYPE,",
        "       " + ",\r\n       ".join("N." + name for name in columns),
        "  FROM {}.{} N".format(settings.owner, table.src_name),
        "       LEFT JOIN {}.{} O".format(settings.owner, table.tgt_name),
        "          ON ({})".format(" AND ".join("N.{0} = O.{0}".format(name) for name in pk)),
    ]
    return "\r\n".join(lines)


def _gather_stats(owner: str, tabname: str, cascade_sep: str) -> str:
    return GATHER_STATS_SQL.format(owner=owner, tabname=tabname, cascade_sep=cascade_sep)


def _target_instance_pre_sql(table: SourceTable, settings: GeneratorSettings) -> str:
    pk = _pk_columns(table, [])
    if not pk:
        raise ValueError("Для TGT-маппинга необходимы PK-атрибуты")
    keys = pk[0]
    delete_sql = (
        "DELETE {owner}.{target} WHERE ({keys}) IN (SELECT {keys} FROM {owner}.{dlt} "
        "WHERE DWH$CHANGE_TYPE IN ('I','U','D'))\\; COMMIT\\; end\\;"
    ).format(owner=settings.owner, target=table.tgt_name, dlt=table.dlt_name, keys=keys)
    return (
        _gather_stats(settings.owner, table.dlt_name, ",cascade=>")
        + " \r\n"
        + delete_sql
    )


def generate_stage_xml(
    table: SourceTable,
    stage: str = "SRC",
    settings: Optional[GeneratorSettings] = None,
    warnings: Optional[List[str]] = None,
) -> str:
    if stage not in ("SRC", "DLT", "TGT"):
        raise ValueError("Неизвестный этап: {!r}".format(stage))
    settings = settings or GeneratorSettings()
    warnings = warnings if warnings is not None else []
    fields = _build_fields(table)
    if stage == "SRC":
        source_name = table.src_name
        target_name = table.src_name
        src_instance_name = source_name + "1"
        mapping_version = "3"
        sq_version = "2"
        sql_query = _sql_query(table, warnings)
        source_filter = ""
        sq_pre_sql = ""
        target_pre_sql = None
    elif stage == "DLT":
        source_name = table.src_name
        target_name = table.dlt_name
        src_instance_name = source_name
        mapping_version = "4"
        sq_version = "3"
        sql_query = _sql_query_dlt(table, settings, warnings)
        source_filter = ""
        sq_pre_sql = _gather_stats(settings.owner, source_name, ", cascade=>") + " end\\;"
        target_pre_sql = None
    else:
        source_name = table.dlt_name
        target_name = table.tgt_name
        src_instance_name = source_name
        mapping_version = "4"
        sq_version = "3"
        sql_query = ""
        source_filter = TGT_SOURCE_FILTER
        sq_pre_sql = ""
        target_pre_sql = _target_instance_pre_sql(table, settings)
    sq_name = "SQ_" + source_name
    mapping_name = "MAP_" + target_name
    creation_date = settings.creation_date or datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    folder_uuid = settings.folder_uuid or str(uuid.uuid4())
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append("<!-- Informatica proprietary -->")
    lines.append('<!DOCTYPE POWERMART SYSTEM "powrmart.dtd">')
    lines.append(
        '<POWERMART CREATION_DATE="{}" REPOSITORY_VERSION="{}">'.format(
            _escape_attr(creation_date), _escape_attr(settings.repository_version_full)
        )
    )
    lines.append(
        "<REPOSITORY {}>".format(
            _attr_plain(
                [
                    ("NAME", settings.repository_name),
                    ("VERSION", settings.repository_version),
                    ("CODEPAGE", settings.codepage),
                    ("DATABASETYPE", settings.repository_database_type),
                ]
            )
        )
    )
    lines.append(
        "<FOLDER {}>".format(
            _attr_plain(
                [
                    ("NAME", settings.folder_name),
                    ("GROUP", ""),
                    ("OWNER", settings.folder_owner),
                    ("SHARED", "NOTSHARED"),
                    ("DESCRIPTION", ""),
                    ("PERMISSIONS", "rwx---r--"),
                    ("UUID", folder_uuid),
                ]
            )
        )
    )
    lines.append(
        "    <SOURCE {}>".format(
            _attr_list(
                [
                    ("BUSINESSNAME", ""),
                    ("DATABASETYPE", settings.definition_database_type),
                    ("DBDNAME", settings.dbdname),
                    ("DESCRIPTION", ""),
                    ("NAME", source_name),
                    ("OBJECTVERSION", "1"),
                    ("OWNERNAME", settings.owner),
                    ("VERSIONNUMBER", "3"),
                ]
            )
        )
    )
    for spec in fields:
        lines.append(
            "        <SOURCEFIELD {}/>".format(
                _attr_list(
                    [
                        ("BUSINESSNAME", ""),
                        ("DATATYPE", spec["datatype"]),
                        ("DESCRIPTION", spec["description"]),
                        ("FIELDNUMBER", str(spec["field_number"])),
                        ("FIELDPROPERTY", "0"),
                        ("FIELDTYPE", "ELEMITEM"),
                        ("HIDDEN", "NO"),
                        ("KEYTYPE", "NOT A KEY"),
                        ("LENGTH", str(spec["length"])),
                        ("LEVEL", "0"),
                        ("NAME", spec["name"]),
                        ("NULLABLE", "NULL"),
                        ("OCCURS", "0"),
                        ("OFFSET", str(spec["offset"])),
                        ("PHYSICALLENGTH", str(spec["phys"])),
                        ("PHYSICALOFFSET", str(spec["physical_offset"])),
                        ("PICTURETEXT", ""),
                        ("PRECISION", str(spec["prec"])),
                        ("SCALE", str(spec["scale"])),
                        ("USAGE_FLAGS", ""),
                    ]
                )
            )
        )
    lines.append("    </SOURCE>")
    lines.append(
        "    <TARGET {}>".format(
            _attr_list(
                [
                    ("BUSINESSNAME", ""),
                    ("CONSTRAINT", ""),
                    ("DATABASETYPE", settings.definition_database_type),
                    ("DESCRIPTION", ""),
                    ("NAME", target_name),
                    ("OBJECTVERSION", "1"),
                    ("TABLEOPTIONS", ""),
                    ("VERSIONNUMBER", "3"),
                ]
            )
        )
    )
    for spec in fields:
        lines.append(
            "        <TARGETFIELD {}/>".format(
                _attr_list(
                    [
                        ("BUSINESSNAME", ""),
                        ("DATATYPE", spec["datatype"]),
                        ("DESCRIPTION", spec["description"]),
                        ("FIELDNUMBER", str(spec["field_number"])),
                        ("KEYTYPE", "NOT A KEY"),
                        ("NAME", spec["name"]),
                        ("NULLABLE", "NULL"),
                        ("PICTURETEXT", ""),
                        ("PRECISION", str(spec["prec"])),
                        ("SCALE", str(spec["scale"])),
                    ]
                )
            )
        )
    lines.append("    </TARGET>")
    lines.append(
        "    <MAPPING {}>".format(
            _attr_list(
                [
                    ("DESCRIPTION", ""),
                    ("ISVALID", "YES"),
                    ("NAME", mapping_name),
                    ("OBJECTVERSION", "1"),
                    ("VERSIONNUMBER", mapping_version),
                ]
            )
        )
    )
    lines.append(
        "        <TRANSFORMATION {}>".format(
            _attr_list(
                [
                    ("DESCRIPTION", ""),
                    ("NAME", sq_name),
                    ("OBJECTVERSION", "1"),
                    ("REUSABLE", "NO"),
                    ("TYPE", "Source Qualifier"),
                    ("VERSIONNUMBER", sq_version),
                ]
            )
        )
    )
    for spec in fields:
        datatype, precision, scale = _transform_type(spec)
        lines.append(
            "            <TRANSFORMFIELD {}/>".format(
                _attr_list(
                    [
                        ("DATATYPE", datatype),
                        ("DEFAULTVALUE", ""),
                        ("DESCRIPTION", ""),
                        ("NAME", spec["name"]),
                        ("PICTURETEXT", ""),
                        ("PORTTYPE", "INPUT/OUTPUT"),
                        ("PRECISION", str(precision)),
                        ("SCALE", str(scale)),
                    ]
                )
            )
        )
    for name, value in [
        ("Sql Query", sql_query),
        ("User Defined Join", ""),
        ("Source Filter", source_filter),
        ("Number Of Sorted Ports", "0"),
        ("Tracing Level", "Normal"),
        ("Select Distinct", "NO"),
        ("Is Partitionable", "NO"),
        ("Pre SQL", sq_pre_sql),
        ("Post SQL", ""),
        ("Output is deterministic", "NO"),
        ("Output is repeatable", "Never"),
    ]:
        lines.append(
            "            <TABLEATTRIBUTE {}/>".format(
                _attr_list([("NAME", name), ("VALUE", value)])
            )
        )
    lines.append(
        "            <METADATAEXTENSION {}/>".format(
            _attr_list(
                [
                    ("DATATYPE", "STRING"),
                    ("DESCRIPTION", ""),
                    ("DOMAINNAME", "User Defined Metadata Domain"),
                    ("ISCLIENTEDITABLE", "YES"),
                    ("ISCLIENTVISIBLE", "YES"),
                    ("ISREUSABLE", "YES"),
                    ("ISSHAREREAD", "NO"),
                    ("ISSHAREWRITE", "NO"),
                    ("MAXLENGTH", "256"),
                    ("NAME", "Extension"),
                    ("VALUE", ""),
                    ("VENDORNAME", "INFORMATICA"),
                ]
            )
        )
    )
    lines.append("        </TRANSFORMATION>")
    target_instance_pairs = [
        ("DESCRIPTION", ""),
        ("NAME", target_name),
        ("TRANSFORMATION_NAME", target_name),
        ("TRANSFORMATION_TYPE", "Target Definition"),
        ("TYPE", "TARGET"),
    ]
    if target_pre_sql is None:
        lines.append("        <INSTANCE {}/>".format(_attr_list(target_instance_pairs)))
    else:
        lines.append("        <INSTANCE {}>".format(_attr_list(target_instance_pairs)))
        lines.append(
            "            <TABLEATTRIBUTE {}/>".format(
                _attr_list([("NAME", "Pre SQL"), ("VALUE", target_pre_sql)])
            )
        )
        lines.append("        </INSTANCE>")
    lines.append(
        "        <INSTANCE {}>".format(
            _attr_list(
                [
                    ("DESCRIPTION", ""),
                    ("NAME", sq_name),
                    ("REUSABLE", "NO"),
                    ("TRANSFORMATION_NAME", sq_name),
                    ("TRANSFORMATION_TYPE", "Source Qualifier"),
                    ("TYPE", "TRANSFORMATION"),
                ]
            )
        )
    )
    lines.append('            <ASSOCIATED_SOURCE_INSTANCE NAME ="{}"/>'.format(_escape_attr(src_instance_name)))
    lines.append("        </INSTANCE>")
    lines.append(
        "        <INSTANCE {}/>".format(
            _attr_list(
                [
                    ("DBDNAME", settings.dbdname),
                    ("DESCRIPTION", ""),
                    ("NAME", src_instance_name),
                    ("TRANSFORMATION_NAME", source_name),
                    ("TRANSFORMATION_TYPE", "Source Definition"),
                    ("TYPE", "SOURCE"),
                ]
            )
        )
    )
    for from_instance, from_type, to_instance, to_type in [
        (sq_name, "Source Qualifier", target_name, "Target Definition"),
        (src_instance_name, "Source Definition", sq_name, "Source Qualifier"),
    ]:
        for spec in fields:
            lines.append(
                "        <CONNECTOR {}/>".format(
                    _attr_list(
                        [
                            ("FROMFIELD", spec["name"]),
                            ("FROMINSTANCE", from_instance),
                            ("FROMINSTANCETYPE", from_type),
                            ("TOFIELD", spec["name"]),
                            ("TOINSTANCE", to_instance),
                            ("TOINSTANCETYPE", to_type),
                        ]
                    )
                )
            )
    lines.append(
        "        <TARGETLOADORDER {}/>".format(
            _attr_list([("ORDER", "1"), ("TARGETINSTANCE", target_name)])
        )
    )
    for variable in ("$$FROM_PRC_DTTM", "$$TO_PRC_DTTM"):
        lines.append(
            "        <MAPPINGVARIABLE {}/>".format(
                _attr_list(
                    [
                        ("DATATYPE", "string"),
                        ("DEFAULTVALUE", ""),
                        ("DESCRIPTION", ""),
                        ("ISEXPRESSIONVARIABLE", "NO"),
                        ("ISPARAM", "YES"),
                        ("NAME", variable),
                        ("PRECISION", "19"),
                        ("SCALE", "0"),
                        ("USERDEFINED", "YES"),
                    ]
                )
            )
        )
    lines.append("        <ERPINFO/>")
    lines.append("    </MAPPING>")
    lines.append("</FOLDER>")
    lines.append("</REPOSITORY>")
    lines.append("</POWERMART>")
    return "\r\n".join(lines)


def generate_src_xml(
    table: SourceTable,
    settings: Optional[GeneratorSettings] = None,
    warnings: Optional[List[str]] = None,
) -> str:
    return generate_stage_xml(table, "SRC", settings, warnings)


def generate_dlt_xml(
    table: SourceTable,
    settings: Optional[GeneratorSettings] = None,
    warnings: Optional[List[str]] = None,
) -> str:
    return generate_stage_xml(table, "DLT", settings, warnings)


def generate_tgt_xml(
    table: SourceTable,
    settings: Optional[GeneratorSettings] = None,
    warnings: Optional[List[str]] = None,
) -> str:
    return generate_stage_xml(table, "TGT", settings, warnings)
