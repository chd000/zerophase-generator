import datetime
import uuid
from typing import List, Optional

from .models import SourceTable
from .settings import GeneratorSettings
from .xml_generator import generate_stage_xml
from .workflow_template import WORKFLOW_TEMPLATE


def _section(stage_text: str, tag: str) -> str:
    lines = stage_text.split("\r\n")
    start = next(i for i, line in enumerate(lines) if line.startswith("    <" + tag + " "))
    end = lines.index("    </" + tag + ">", start)
    return "\r\n".join(lines[start:end + 1])


def _process_id(settings: GeneratorSettings, table: SourceTable, stage: str):
    key = (table.table.strip().upper(), stage)
    if settings.wk_process_id_map:
        value = settings.wk_process_id_map.get(key)
        if value:
            return value
    if stage == "SRC":
        return settings.wk_process_id_src
    if stage == "DLT":
        return settings.wk_process_id_dlt
    return settings.wk_process_id_tgt


def generate_workflow_xml(
    table: SourceTable,
    settings: Optional[GeneratorSettings] = None,
    warnings: Optional[List[str]] = None,
) -> str:
    settings = settings or GeneratorSettings()
    stage_texts = {}
    for stage in ("TGT", "DLT", "SRC"):
        stage_warnings: List[str] = []
        stage_texts[stage] = generate_stage_xml(table, stage, settings, warnings=stage_warnings)
    stem_body = (table.schema.strip() + "_" + table.table.strip()).upper()
    stem = "ODS_" + stem_body
    workflow_name = settings.workflow_name or "wf_" + stem
    workflow_log_name = settings.workflow_log_name or ("wf_" + stem)
    values = {
        "@@SRC_DEF_DLT@@": _section(stage_texts["TGT"], "SOURCE"),
        "@@TGT_DEF_TGT@@": _section(stage_texts["TGT"], "TARGET"),
        "@@MAPPING_TGT@@": _section(stage_texts["TGT"], "MAPPING"),
        "@@SRC_DEF_SRC@@": _section(stage_texts["DLT"], "SOURCE"),
        "@@TGT_DEF_DLT@@": _section(stage_texts["DLT"], "TARGET"),
        "@@MAPPING_DLT@@": _section(stage_texts["DLT"], "MAPPING"),
        "@@TGT_DEF_SRC@@": _section(stage_texts["SRC"], "TARGET"),
        "@@MAPPING_SRC@@": _section(stage_texts["SRC"], "MAPPING"),
        "@@STEM@@": stem_body,
        "@@WF_NAME@@": workflow_name,
        "@@WF_LOG@@": workflow_log_name,
        "@@AUDIT@@": settings.audit_log_prefix,
        "@@CONN_STAGE@@": settings.stage_connection,
        "@@CONN_SRC@@": settings.source_connection,
        "@@SVC@@": settings.integration_service,
        "@@DOMAIN@@": settings.domain_name,
        "@@OWNER@@": settings.owner,
        "@@PID_TGT@@": str(_process_id(settings, table, "TGT")),
        "@@PID_DLT@@": str(_process_id(settings, table, "DLT")),
        "@@PID_SRC@@": str(_process_id(settings, table, "SRC")),
        "@@CREATION_DATE@@": settings.creation_date or datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S"),
        "@@FOLDER_NAME@@": settings.folder_name,
        "@@FOLDER_OWNER@@": settings.folder_owner,
        "@@FOLDER_UUID@@": settings.folder_uuid or str(uuid.uuid4()),
    }
    text = WORKFLOW_TEMPLATE
    for token, value in values.items():
        text = text.replace(token, value.replace("\r\n", "\n"))
    if "@@" in text:
        raise ValueError("В шаблоне потока остался незаполненный токен: {}".format(
            text[text.index("@@"):text.index("@@") + 20]))
    return text.replace("\n", "\r\n")
