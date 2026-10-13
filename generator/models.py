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
        base = self.inc_table.strip() or "ODS_{}_{}".format(self.schema.strip(), self.table.strip())
        if base.upper().endswith("_INC"):
            base = base[:-4] + "_SRC"
        return base

    @property
    def mapping_name(self) -> str:
        return "MAP_" + self.src_name

    @property
    def dlt_name(self) -> str:
        src = self.src_name
        if src.upper().endswith("_SRC"):
            return src[:-4] + "_DLT"
        return src + "_DLT"

    @property
    def tgt_name(self) -> str:
        base = self.tgt_table.strip()
        if base:
            return base
        src = self.src_name
        if src.upper().endswith("_SRC"):
            return src[:-4] + "_TGT"
        return src + "_TGT"

    def stage_table_name(self, stage: str) -> str:
        if stage == "SRC":
            return self.src_name
        if stage == "DLT":
            return self.dlt_name
        return self.tgt_name

    def mapping_name_for(self, stage: str) -> str:
        return "MAP_" + self.stage_table_name(stage)
