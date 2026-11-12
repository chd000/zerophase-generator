import re
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Set, Tuple

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_DRAWING = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


_COL_RE = re.compile(r"([A-Z]+)")

_INDEXED_COLORS = (
    "00000000", "00FFFFFF", "00FF0000", "0000FF00", "000000FF", "00FFFF00",
    "00FF00FF", "0000FFFF", "00000000", "00FFFFFF", "00FF0000", "0000FF00",
    "000000FF", "00FFFF00", "00FF00FF", "0000FFFF", "00800000", "00008000",
    "00000080", "00808000", "00800080", "00008080", "00C0C0C0", "00808080",
    "009999FF", "00993366", "00FFFFCC", "00CCFFFF", "00660066", "00FF8080",
    "000066CC", "00CCCCFF", "00000080", "00FF00FF", "00FFFF00", "0000FFFF",
    "00800080", "00800000", "00008080", "000000FF", "0000CCFF", "00CCFFFF",
    "00CCFFCC", "00FFFF99", "0099CCFF", "00FF99CC", "00CC99FF", "00FFCC99",
    "003366FF", "0033CCCC", "0099CC00", "00FFFF00", "00FFCC00", "00FF9900",
    "00FF6600", "00666699", "00969696", "00003366", "00339966", "00003300",
    "00333333", "00993300", "00993366", "00333399",
)

_THEME_ORDER = (
    "lt1", "dk1", "lt2", "dk2",
    "accent1", "accent2", "accent3", "accent4", "accent5", "accent6",
    "hlink", "folHlink",
)


def _column_of(cell_ref: str) -> str:
    match = _COL_RE.match((cell_ref or "").upper())
    return match.group(1) if match else ""


def _sheet_targets(archive) -> dict:
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
    with zipfile.ZipFile(xlsx_path) as archive:
        return list(_sheet_targets(archive))


def _hex6(value: str) -> str:
    value = (value or "").strip().lstrip("#").upper()
    return value[-6:] if len(value) >= 6 else ""


def _apply_tint(hex6: str, tint: float) -> str:
    red, green, blue = (int(hex6[index:index + 2], 16) / 255.0 for index in (0, 2, 4))
    peak, low = max(red, green, blue), min(red, green, blue)
    lightness = (peak + low) / 2.0
    if peak == low:
        hue = saturation = 0.0
    else:
        delta = peak - low
        saturation = delta / (2.0 - peak - low) if lightness > 0.5 else delta / (peak + low)
        if peak == red:
            hue = (green - blue) / delta % 6.0
        elif peak == green:
            hue = (blue - red) / delta + 2.0
        else:
            hue = (red - green) / delta + 4.0
        hue *= 60.0
    if tint > 0:
        lightness = lightness * (1.0 - tint) + tint
    else:
        lightness = lightness * (1.0 + tint)
    chroma = (1.0 - abs(2.0 * lightness - 1.0)) * saturation
    part = chroma * (1.0 - abs(hue / 60.0 % 2.0 - 1.0))
    shift = lightness - chroma / 2.0
    sector = int(hue // 60.0) % 6
    channels = [
        (chroma, part, 0.0), (part, chroma, 0.0), (0.0, chroma, part),
        (0.0, part, chroma), (part, 0.0, chroma), (chroma, 0.0, part),
    ][sector]
    return "{:02X}{:02X}{:02X}".format(
        *(min(255, max(0, round((value + shift) * 255.0))) for value in channels))


def _theme_colors(archive) -> List[str]:
    try:
        data = archive.read("xl/theme/theme1.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    scheme = root.find(".//" + NS_DRAWING + "clrScheme")
    if scheme is None:
        return []
    colors = {}
    for slot in scheme:
        name = slot.tag.split("}")[-1]
        srgb = slot.find(NS_DRAWING + "srgbClr")
        if srgb is not None:
            colors[name] = srgb.get("val") or ""
            continue
        system = slot.find(NS_DRAWING + "sysClr")
        if system is not None:
            colors[name] = system.get("lastClr") or ""
    return [colors.get(name, "") for name in _THEME_ORDER]


def _color_hex6(node, theme_colors: List[str]) -> str:
    if node is None:
        return ""
    rgb = node.get("rgb")
    if rgb:
        return _hex6(rgb)
    indexed = node.get("indexed")
    if indexed is not None:
        try:
            return _INDEXED_COLORS[int(indexed)][-6:]
        except (ValueError, IndexError):
            return ""
    theme = node.get("theme")
    if theme is not None and theme_colors:
        try:
            base = _hex6(theme_colors[int(theme)])
        except (ValueError, IndexError):
            return ""
        tint_text = node.get("tint")
        tint = 0.0
        if tint_text:
            try:
                tint = float(tint_text)
            except ValueError:
                tint = 0.0
        return _apply_tint(base, tint) if base else ""
    return ""


def _is_red(hex6: str) -> bool:
    if len(hex6) != 6:
        return False
    try:
        red, green, blue = (int(hex6[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return False
    return red >= 0x80 and red - green >= 0x30 and red - blue >= 0x30


def _red_cell_styles(archive) -> Set[int]:
    try:
        data = archive.read("xl/styles.xml")
    except KeyError:
        return set()
    root = ET.fromstring(data)
    theme_colors = _theme_colors(archive)
    red_fills = []
    fills_node = root.find(NS_MAIN + "fills")
    if fills_node is not None:
        for fill in fills_node.findall(NS_MAIN + "fill"):
            pattern = fill.find(NS_MAIN + "patternFill")
            visible = bool(
                pattern is not None and pattern.get("patternType") == "solid"
            )
            red_fills.append(visible and _is_red(
                _color_hex6(pattern.find(NS_MAIN + "fgColor"), theme_colors)))
    red_styles = set()
    xfs_node = root.find(NS_MAIN + "cellXfs")
    if xfs_node is not None:
        for index, xf in enumerate(xfs_node.findall(NS_MAIN + "xf")):
            if xf.get("applyFill") == "0":
                continue
            try:
                fill_id = int(xf.get("fillId", "0"))
            except ValueError:
                continue
            if 0 <= fill_id < len(red_fills) and red_fills[fill_id]:
                red_styles.add(index)
    return red_styles


def _style_index(text: str) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return -1


def _parse_sheet(data: bytes, shared: List[str], red_styles: Set[int]) -> Tuple[List[dict], List[bool]]:
    root = ET.fromstring(data)
    rows, red_rows = [], []
    for row in root.iter(NS_MAIN + "row"):
        row_style = row.get("s")
        row_red = row_style is not None and _style_index(row_style) in red_styles
        cells, filled, marked = {}, 0, 0
        for cell in row.iter(NS_MAIN + "c"):
            column = _column_of(cell.get("r"))
            is_red = _style_index(cell.get("s")) in red_styles
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
                filled += 1
                marked += 1 if is_red else 0
        rows.append(cells)
        red_rows.append(row_red or (filled > 0 and marked * 2 >= filled))
    return rows, red_rows


def read_sheets(xlsx_path: str, wanted: List[str]) -> dict:
    with zipfile.ZipFile(xlsx_path) as archive:
        sheet_map = _sheet_targets(archive)
        for name in wanted:
            if name not in sheet_map:
                raise KeyError(
                    "Лист {!r} не найден. Доступные листы: {}".format(name, ", ".join(sheet_map))
                )
        shared = _shared_strings(archive)
        red_styles = _red_cell_styles(archive)
        return {
            name: _parse_sheet(archive.read(sheet_map[name]), shared, red_styles)
            for name in wanted
        }


def read_sheet(xlsx_path: str, sheet_name: str) -> List[dict]:
    return read_sheets(xlsx_path, [sheet_name])[sheet_name][0]
