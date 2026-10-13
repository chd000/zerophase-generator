from dataclasses import dataclass
from typing import Optional


@dataclass
class GeneratorSettings:
    folder_name: str = "MY_FOLDER_NAME"  # имя папки (FOLDER) в PowerCenter
    folder_owner: str = "Administrator"  # владелец папки PowerCenter (OWNER у FOLDER)
    dbdname: str = "OFSDEV"  # подключение к БД в PowerCenter (DBDNAME у SOURCE/TARGET)
    owner: str = "STAGE"  # схема стейджинга: OWNERNAME и префикс в SQL/DDL (FROM STAGE.<таблица>)
    repository_name: str = "REPOSITORY"  # имя репозитория (NAME у REPOSITORY)
    repository_version: str = "189"  # версия репозитория (VERSION у REPOSITORY)
    repository_version_full: str = "189.98"  # версия в заголовке POWERMART (REPOSITORY_VERSION)
    codepage: str = "UTF-8"  # кодировка репозитория (CODEPAGE)
    repository_database_type: str = "PostgreSQL"  # тип БД репозитория (DATABASETYPE у REPOSITORY)
    definition_database_type: str = "Oracle"  # тип БД определений (DATABASETYPE у SOURCE/TARGET)
    folder_uuid: Optional[str] = None  # UUID папки; None — новый для каждого XML-файла
    creation_date: Optional[str] = None  # дата в заголовке (MM/DD/YYYY HH:MI:SS); None — текущая
    ddl_tablespace: str = "STAGE_DATA"  # TABLESPACE в DDL-скриптах
