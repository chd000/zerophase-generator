import re
import zipfile
import xml.etree.ElementTree as ET
from typing import List

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _column_of(cell_ref: str) -> str:
    match = re.match(r"([A-Z]+)", (cell_ref or "").upper())
    return match.group(1) if match else ""


def _sheet_targets(xlsx_path: str) -> dict:
    with zipfile.ZipFile(xlsx_path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {rel.get("Id"): rel.get("Target") or "" for rel in relations}
    sheet_map = {}
    for sheet in workbook.iter(NS_MAIN + "sheet"):
        target = targets.get(sheet.get(NS_REL + "id"), "")
        if target.startswith("/"):
            target = target.lstrip("/")
        elif not target.startswith("xl/"):
            target = "xl/" + target
        sheet_map[sheet.get("name")] = target
    return sheet_map


def _shared_strings(archive) -> List[str]:
    try:
        data = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    return [
        "".join(node.text or "" for node in item.iter(NS_MAIN + "t"))
        for item in root.findall(NS_MAIN + "si")
    ]


def sheet_names(xlsx_path: str) -> List[str]:
    return list(_sheet_targets(xlsx_path))


def read_sheet(xlsx_path: str, sheet_name: str) -> List[dict]:
    sheet_map = _sheet_targets(xlsx_path)
    if sheet_name not in sheet_map:
        raise KeyError(
            "Лист {!r} не найден. Доступные листы: {}".format(sheet_name, ", ".join(sheet_map))
        )
    with zipfile.ZipFile(xlsx_path) as archive:
        shared = _shared_strings(archive)
        root = ET.fromstring(archive.read(sheet_map[sheet_name]))
    rows = []
    for row in root.iter(NS_MAIN + "row"):
        cells = {}
        for cell in row.iter(NS_MAIN + "c"):
            column = _column_of(cell.get("r"))
            kind = cell.get("t")
            value = None
            if kind == "s":
                node = cell.find(NS_MAIN + "v")
                if node is not None and node.text is not None:
                    value = shared[int(node.text)]
            elif kind == "inlineStr":
                node = cell.find(NS_MAIN + "is")
                if node is not None:
                    value = "".join(part.text or "" for part in node.iter(NS_MAIN + "t"))
            else:
                node = cell.find(NS_MAIN + "v")
                if node is not None and node.text is not None:
                    value = node.text
            if value is not None:
                cells[column] = value
        rows.append(cells)
    return rows
