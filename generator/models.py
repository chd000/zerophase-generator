from dataclasses import dataclass, field
from typing import List


@dataclass
class SourceAttribute:
    name: str = ""
    data_type: str = ""
    description: str = ""
    pk: bool = False


@dataclass
class SourceTable:
    system: str = ""
    db: str = ""
    schema: str = ""
    table: str = ""
    description: str = ""
    inc_table: str = ""
    tgt_table: str = ""
    workflow: str = ""
    comment: str = ""
    attributes: List[SourceAttribute] = field(default_factory=list)

    @property
    def src_name(self) -> str:
        return self.base_name + "_SRC"

    @property
    def mapping_name(self) -> str:
        return "MAP_" + self.src_name

    @property
    def base_name(self) -> str:
        return "ODS_{}_{}".format(self.schema.strip(), self.table.strip()).upper()

    @property
    def dlt_name(self) -> str:
        return self.base_name + "_DLT"

    @property
    def tgt_name(self) -> str:
        return self.base_name + "_TGT"

    def stage_table_name(self, stage: str) -> str:
        if stage == "SRC":
            return self.src_name
        if stage == "DLT":
            return self.dlt_name
        return self.tgt_name

    def mapping_name_for(self, stage: str) -> str:
        return "MAP_" + self.stage_table_name(stage)
