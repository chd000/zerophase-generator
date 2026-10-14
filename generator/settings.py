from dataclasses import dataclass
from typing import Optional


@dataclass
class GeneratorSettings:
    folder_name: str = "MY_FOLDER_NAME"  # имя папки (FOLDER) в PowerCenter
    repository_name: str = "REPOSITORY"  # имя репозитория (NAME у REPOSITORY)

    master_connection: str = "IAS_to_GO_Stage"  # подключение к БД в сессиях управляющего потока
    stage_connection: str = "STAGE_CONNECT"  # подключение к стейджу (writer и reader DLT/TGT)
    source_connection: str = "SOURCE_CONNECT"  # подключение к БД источника (reader SRC)
    integration_service: str = "INTEGRATION_SERVICE"  # сервис интеграции (SERVERNAME потока)
    domain_name: str = "DOMAIN"  # домен PowerCenter
    pmcmd_user: str = "CABS_KIH"  # пользователь pmcmd при запуске рабочих потоков
    pmcmd_password: str = "CABS_KIH"  # пароль pmcmd

    folder_owner: str = "Administrator"  # владелец папки PowerCenter (OWNER у FOLDER)
    dbdname: str = "OFSDEV"  # подключение к БД в PowerCenter (DBDNAME у SOURCE/TARGET)
    owner: str = "STAGE"  # схема стейджинга: OWNERNAME и префикс в SQL/DDL (FROM STAGE.<таблица>)
    repository_version: str = "189"  # версия репозитория (VERSION у REPOSITORY)
    repository_version_full: str = "189.98"  # версия в заголовке POWERMART (REPOSITORY_VERSION)
    codepage: str = "UTF-8"  # кодировка репозитория (CODEPAGE)
    repository_database_type: str = "PostgreSQL"  # тип БД репозитория (DATABASETYPE у REPOSITORY)
    definition_database_type: str = "Oracle"  # тип БД определений (DATABASETYPE у SOURCE/TARGET)
    ddl_tablespace: str = "STAGE_DATA"  # TABLESPACE в DDL-скриптах
    audit_log_prefix: str = "ODS_CASTA"  # префикс лог-файлов сервисных сессий в worklet

    folder_uuid: Optional[str] = None  # UUID папки; None — новый для каждого XML-файла
    creation_date: Optional[str] = None  # дата в заголовке (MM/DD/YYYY HH:MI:SS); None — текущая
    workflow_name: Optional[str] = None  # имя потока; None — wf_ODS_<схема>_<таблица>
    workflow_log_name: Optional[str] = None  # базовое имя лога потока; None — как имя потока
    master_workflow_name: Optional[str] = None  # имя управляющего потока; None — wf_load_prm_ODS_<схема>
    master_workflow_log_name: Optional[str] = None  # лог управляющего потока; None — <имя потока>.log
    master_session_log_name: Optional[str] = None  # лог сессии статуса; None — s_DWH_LOAD_STATUS_ODS_<схема>.log
    wk_process_id_map: Optional[dict] = None  # PROCESS_ID ворклетов по таблицам: {("<ТАБЛИЦА>", "SRC"|"DLT"|"TGT"): id}; нет ключа — заглушки выше

    wk_process_id_src: int = 1000008927  # $$wk_PROCESS_ID в worklet SRC (DEFINE_VAR)
    wk_process_id_dlt: int = 1000008928  # $$wk_PROCESS_ID в worklet DLT (DEFINE_VAR)
    wk_process_id_tgt: int = 1000008929  # $$wk_PROCESS_ID в worklet TGT (DEFINE_VAR)