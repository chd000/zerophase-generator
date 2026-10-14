import datetime
import uuid
from typing import Iterable, List, Optional

from .master_workflow_template import WORKFLOW_TEMPLATE
from .models import SourceTable
from .settings import GeneratorSettings


def _escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\"", "&quot;").replace("'", "&apos;")
            .replace("\r", "&#xD;").replace("\n", "&#xA;"))


def generate_master_workflow_xml(
    tables: Iterable[SourceTable],
    settings: Optional[GeneratorSettings] = None,
    warnings: Optional[List[str]] = None,
) -> str:
    settings = settings or GeneratorSettings()
    tables = list(tables)
    if not tables:
        raise ValueError("Список таблиц для управляющего потока пуст.")
    names = [(table.schema.strip() + "_" + table.table.strip()).upper() for table in tables]
    if any(not name.strip("_") for name in names):
        raise ValueError("У таблиц не заполнено имя для управляющего потока.")
    schema = tables[0].schema.strip().upper()
    workflow_name = settings.master_workflow_name or "wf_load_prm_ODS_" + schema
    workflow_log_name = settings.master_workflow_log_name or (workflow_name + ".log")
    session_log_name = settings.master_session_log_name or ("s_DWH_LOAD_STATUS_ODS_" + schema + ".log")
    table_list = "(&#xD;&#xA;" + ",&#xD;&#xA;".join("&apos;" + _escape(name) + "&apos;" for name in names) + ")"
    values = {
        "@@CREATION_DATE@@": settings.creation_date or datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S"),
        "@@FOLDER_NAME@@": settings.folder_name,
        "@@FOLDER_OWNER@@": settings.folder_owner,
        "@@FOLDER_UUID@@": settings.folder_uuid or str(uuid.uuid4()),
        "@@DBDNAME@@": settings.dbdname,
        "@@OWNER@@": settings.owner,
        "@@WF_NAME@@": workflow_name,
        "@@WF_LOG@@": workflow_log_name,
        "@@SESS_LOG@@": session_log_name,
        "@@CONN@@": settings.master_connection,
        "@@SVC@@": settings.integration_service,
        "@@DOMAIN@@": settings.domain_name,
        "@@PMCMD_USER@@": settings.pmcmd_user,
        "@@PMCMD_PASSWORD@@": settings.pmcmd_password,
        "@@TABLES@@": table_list,
    }
    text = WORKFLOW_TEMPLATE
    for token, value in values.items():
        text = text.replace(token, value.replace("\r\n", "\n"))
    if "@@" in text:
        raise ValueError("В шаблоне управляющего потока остался незаполненный токен: {}".format(
            text[text.index("@@"):text.index("@@") + 20]))
    return text.replace("\n", "\r\n")
