"""資料轉換：CSV／TSV、JSON、XML、SQLite、XLSX、YAML、TOML。

表格型來源（CSV／TSV／XLSX／SQLite）第一列視為欄位名稱；結構型來源
（JSON／XML／YAML／TOML）則盡量保留原本的巢狀結構。
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import yaml

from ..core.errors import ConversionError, InvalidInputError
from ..core.textio import read_text, write_text
from .base import ConvertContext, Converter

try:  # Python 3.11+ 內建；較舊版本由 tomli 提供
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 僅舊版 Python
    import tomli as tomllib  # type: ignore[no-redef]

TABULAR_EXTENSIONS = frozenset({"csv", "tsv", "xlsx", "xlsm", "ods"})
STRUCTURED_EXTENSIONS = frozenset({"json", "yaml", "yml", "toml"})
CSV_DELIMITERS = {"csv": ",", "tsv": "\t"}

_ODS_TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
_ODS_OFFICE_NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
_ODS_TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"

#: ODS 的重複儲存格上限，避免尾端大量空儲存格拖垮解析
_ODS_MAX_REPEAT = 1000


# --------------------------------------------------------------------------- 讀取


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _dedupe_header(header: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for index, name in enumerate(header):
        label = name.strip() or f"欄位{index + 1}"
        if label in seen:
            seen[label] += 1
            label = f"{label}_{seen[label]}"
        else:
            seen[label] = 0
        result.append(label)
    return result


def table_from_rows(rows: list[list[Any]]) -> tuple[list[str], list[list[Any]]]:
    """把原始列資料整理成 ``(欄位, 資料列)``。"""
    cleaned = [row for row in rows if any(_cell_text(cell).strip() for cell in row)]
    if not cleaned:
        return [], []
    width = max(len(row) for row in cleaned)
    padded = [list(row) + [None] * (width - len(row)) for row in cleaned]
    header = _dedupe_header([_cell_text(cell) for cell in padded[0]])
    return header, padded[1:]


def _read_csv(path: Path, extension: str) -> tuple[list[str], list[list[Any]]]:
    try:
        text = read_text(path)
    except OSError as exc:
        raise ConversionError(f"無法讀取「{path.name}」：{exc}", detail=str(exc)) from exc
    reader = csv.reader(io.StringIO(text), delimiter=CSV_DELIMITERS[extension])
    return table_from_rows([list(row) for row in reader])


def _read_xlsx(path: Path, sheet: str | None) -> tuple[list[str], list[list[Any]]]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - 依賴缺失
        raise ConversionError("缺少 openpyxl，無法讀取 Excel 檔案。") from exc

    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # openpyxl 的例外種類很多
        raise ConversionError(f"無法讀取「{path.name}」：{exc}", detail=str(exc)) from exc

    try:
        if sheet:
            if sheet not in workbook.sheetnames:
                names = "、".join(workbook.sheetnames) or "（無）"
                raise InvalidInputError(f"「{path.name}」沒有工作表「{sheet}」。可用的工作表：{names}")
            worksheet = workbook[sheet]
        else:
            worksheet = workbook.active
        if worksheet is None:
            raise ConversionError(f"「{path.name}」沒有任何工作表。")
        rows = [list(row) for row in worksheet.iter_rows(values_only=True)]
    finally:
        workbook.close()
    return table_from_rows(rows)


def _read_ods(path: Path, sheet: str | None) -> tuple[list[str], list[list[Any]]]:
    """讀取 OpenDocument 試算表（.ods）。

    ODS 本質是 ZIP + content.xml；這裡直接解析 XML，不依賴 LibreOffice，
    讓「資料 → CSV/JSON」在沒有安裝引擎的機器上也能用。
    """
    try:
        with zipfile.ZipFile(path) as archive:
            content = archive.read("content.xml")
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise ConversionError(f"「{path.name}」不是有效的 ODS 檔案。", detail=str(exc)) from exc

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ConversionError(f"「{path.name}」的 content.xml 無法解析：{exc}") from exc

    tables = root.iter(f"{{{_ODS_TABLE_NS}}}table")
    worksheet = None
    for table in tables:
        if sheet is None or table.get(f"{{{_ODS_TABLE_NS}}}name") == sheet:
            worksheet = table
            break
    if worksheet is None:
        names = [t.get(f"{{{_ODS_TABLE_NS}}}name") or "?" for t in root.iter(f"{{{_ODS_TABLE_NS}}}table")]
        raise InvalidInputError(
            f"「{path.name}」沒有工作表「{sheet}」。可用的工作表：{'、'.join(names) or '（無）'}"
        )

    rows: list[list[Any]] = []
    for row in worksheet.iter(f"{{{_ODS_TABLE_NS}}}table-row"):
        row_repeat = min(int(row.get(f"{{{_ODS_TABLE_NS}}}number-rows-repeated") or 1), _ODS_MAX_REPEAT)
        cells: list[Any] = []
        for cell in row:
            if not cell.tag.endswith("}table-cell") and not cell.tag.endswith("}covered-table-cell"):
                continue
            repeat = min(int(cell.get(f"{{{_ODS_TABLE_NS}}}number-columns-repeated") or 1), _ODS_MAX_REPEAT)
            value = _ods_cell_value(cell)
            if repeat > 0:
                cells.extend([value] * repeat)
        rows.extend([list(cells)] * row_repeat)
    return table_from_rows(rows)


def _ods_cell_value(cell: ET.Element) -> Any:
    value_type = cell.get(f"{{{_ODS_OFFICE_NS}}}value-type")
    if value_type in ("float", "percentage", "currency"):
        raw = cell.get(f"{{{_ODS_OFFICE_NS}}}value")
        try:
            return float(raw) if raw is not None else _ods_text(cell)
        except ValueError:
            return _ods_text(cell)
    if value_type == "boolean":
        return "TRUE" if cell.get(f"{{{_ODS_OFFICE_NS}}}boolean-value") == "true" else "FALSE"
    if value_type == "date":
        return cell.get(f"{{{_ODS_OFFICE_NS}}}date-value") or _ods_text(cell)
    if value_type == "time":
        return cell.get(f"{{{_ODS_OFFICE_NS}}}time-value") or _ods_text(cell)
    return _ods_text(cell)


def _ods_text(cell: ET.Element) -> str:
    parts = ["".join(node.itertext()) for node in cell.iter(f"{{{_ODS_TEXT_NS}}}p")]
    text = "\n".join(part for part in parts if part)
    return text if text else "".join(cell.itertext())


def _read_structured(path: Path, extension: str) -> Any:
    try:
        text = read_text(path)
    except OSError as exc:
        raise ConversionError(f"無法讀取「{path.name}」：{exc}", detail=str(exc)) from exc

    try:
        if extension == "json":
            return json.loads(text)
        if extension in ("yaml", "yml"):
            return yaml.safe_load(text)
        if extension == "toml":
            return tomllib.loads(text)
    except (ValueError, yaml.YAMLError, tomllib.TOMLDecodeError) as exc:
        raise ConversionError(f"「{path.name}」格式不正確：{exc}", detail=str(exc)) from exc
    raise ConversionError(f"不支援的資料格式：{extension}")  # pragma: no cover


def _read_xml(path: Path) -> Any:
    """讀取 XML：根元素的每個子元素是一筆記錄（屬性＋子元素）。"""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise ConversionError(f"「{path.name}」不是有效的 XML：{exc}", detail=str(exc)) from exc

    children = list(root)
    if not children:
        return _xml_record(root)
    return [_xml_record(child) for child in children]


def _xml_record(element: ET.Element) -> Any:
    """把一個 XML 元素轉成 dict（或純文字）。保留屬性與子元素；重複子標籤會變成陣列。"""
    record: dict[str, Any] = dict(element.attrib)
    children = list(element)
    if children:
        seen: dict[str, Any] = {}
        for child in children:
            value = _xml_value(child)
            if child.tag in seen:
                existing = seen[child.tag]
                if not isinstance(existing, list):
                    seen[child.tag] = [existing]
                seen[child.tag].append(value)
            else:
                seen[child.tag] = value
        record.update(seen)
    if not record:
        return (element.text or "").strip()
    return record


def _xml_value(element: ET.Element) -> Any:
    if list(element) or element.attrib:
        return _xml_record(element)
    return (element.text or "").strip()


def _read_sqlite(path: Path, sheet: str | None) -> tuple[list[str], list[list[Any]]]:
    """讀取 SQLite 資料庫：以唯讀模式開啟，取出指定資料表。"""
    import sqlite3

    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise ConversionError(f"無法開啟 SQLite 檔案「{path.name}」：{exc}", detail=str(exc)) from exc

    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        if not tables:
            raise ConversionError(f"「{path.name}」中沒有任何資料表。")
        table = sheet or tables[0]
        if sheet and sheet not in tables:
            raise InvalidInputError(
                f"「{path.name}」沒有資料表「{sheet}」。可用的資料表：{'、'.join(tables)}"
            )
        safe_table = table.replace('"', '""')
        try:
            cursor = connection.execute(f'SELECT * FROM "{safe_table}"')
        except sqlite3.Error as exc:
            raise ConversionError(f"讀取資料表失敗：{exc}", detail=str(exc)) from exc
        header = [column[0] for column in cursor.description]
        rows = [list(row) for row in cursor.fetchall()]
        return header, rows
    finally:
        connection.close()


def load_source(path: Path, sheet: str | None = None) -> tuple[str, Any]:
    """回傳 ``("table", (欄位, 列))`` 或 ``("value", 物件)``。"""
    extension = path.suffix.lstrip(".").lower()
    if extension in TABULAR_EXTENSIONS:
        if extension in CSV_DELIMITERS:
            header, rows = _read_csv(path, extension)
        elif extension == "ods":
            header, rows = _read_ods(path, sheet)
        else:
            header, rows = _read_xlsx(path, sheet)
        return "table", (header, rows)
    if extension in STRUCTURED_EXTENSIONS:
        return "value", _read_structured(path, extension)
    if extension == "xml":
        return "value", _read_xml(path)
    if extension in ("db", "sqlite", "sqlite3"):
        header, rows = _read_sqlite(path, sheet)
        return "table", (header, rows)
    raise ConversionError(f"不支援的資料來源：{path.name}")


# --------------------------------------------------------------------------- 轉換


def _records(header: list[str], rows: list[list[Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        record: dict[str, Any] = {}
        for index, name in enumerate(header):
            value = row[index] if index < len(row) else None
            record[name] = "" if value is None else value
        records.append(record)
    return records


def to_table(kind: str, payload: Any) -> tuple[list[str], list[list[Any]]]:
    """把任何來源整理成可寫入 CSV／XLSX 的表格。"""
    if kind == "table":
        return payload

    data = payload
    if isinstance(data, list):
        if not data:
            return [], []
        if all(isinstance(item, dict) for item in data):
            header: list[str] = []
            for item in data:
                for key in item:
                    if str(key) not in header:
                        header.append(str(key))
            rows = [[_cell_text(item.get(key)) for key in header] for item in data]
            return header, rows
        if all(isinstance(item, (list, tuple)) for item in data):
            return table_from_rows([list(item) for item in data])
        return ["值"], [[_cell_text(item)] for item in data]

    if isinstance(data, dict):
        return ["鍵", "值"], [[str(key), _cell_text(value)] for key, value in data.items()]

    return ["值"], [[_cell_text(data)]]


def _to_json(kind: str, payload: Any) -> str:
    data = _records(*payload) if kind == "table" else payload
    return json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n"


def _to_csv(kind: str, payload: Any) -> str:
    header, rows = to_table(kind, payload)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    if header:
        writer.writerow(header)
    for row in rows:
        writer.writerow([_cell_text(cell) for cell in row])
    return buffer.getvalue()


def _to_xlsx(dest: Path, kind: str, payload: Any, sheet: str | None) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError as exc:  # pragma: no cover - 依賴缺失
        raise ConversionError("缺少 openpyxl，無法產生 Excel 檔案。") from exc

    header, rows = to_table(kind, payload)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = (sheet or "資料")[:31] or "資料"

    if header:
        worksheet.append(header)
        for cell in worksheet[1]:
            cell.font = Font(bold=True)
        worksheet.freeze_panes = "A2"
    for row in rows:
        worksheet.append([_excel_value(cell) for cell in row])

    for index, name in enumerate(header, start=1):
        width = min(48, max(10, len(str(name)) + 4))
        worksheet.column_dimensions[worksheet.cell(row=1, column=index).column_letter].width = width

    try:
        workbook.save(dest)
    except OSError as exc:
        raise ConversionError(f"無法寫入 Excel 檔案：{exc}", detail=str(exc)) from exc
    finally:
        workbook.close()


def _excel_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _to_yaml(kind: str, payload: Any) -> str:
    data = _records(*payload) if kind == "table" else payload
    try:
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000)
    except yaml.YAMLError as exc:
        raise ConversionError(f"無法產生 YAML：{exc}", detail=str(exc)) from exc


def _toml_safe(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, dict):
        return {str(key): _toml_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_toml_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _to_toml(kind: str, payload: Any) -> str:
    import tomli_w

    data = _records(*payload) if kind == "table" else payload
    if isinstance(data, list):
        data = {"records": data}
    if not isinstance(data, dict):
        data = {"value": data}
    try:
        return tomli_w.dumps(_toml_safe(data))
    except (TypeError, ValueError) as exc:
        raise ConversionError(
            "無法產生 TOML：資料中含 TOML 不支援的結構（例如空值或混合陣列）。",
            detail=str(exc),
        ) from exc


def _xml_tag(key: Any) -> str:
    """把任意欄位名稱整理成安全的 XML 標籤。"""
    tag = re.sub(r"[^\w.-]", "_", str(key), flags=re.UNICODE)
    if not tag:
        return "field"
    if not (tag[0].isalpha() or tag[0] == "_"):
        tag = f"_{tag}"
    return tag


def _fill_xml(element: ET.Element, value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _append_xml(element, key, item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _append_xml(element, "item", item)
    else:
        element.text = _cell_text(value)


def _append_xml(parent: ET.Element, key: Any, value: Any) -> None:
    # 陣列使用重複標籤，讓 XML → JSON → XML 能保留相同的資料形狀。
    if isinstance(value, (list, tuple)):
        if not value:
            ET.SubElement(parent, _xml_tag(key))
        for item in value:
            _append_xml(parent, key, item)
        return
    child = ET.SubElement(parent, _xml_tag(key))
    _fill_xml(child, value)


def _to_xml(kind: str, payload: Any) -> bytes:
    data = _records(*payload) if kind == "table" else payload
    if isinstance(data, list):
        root = ET.Element("records")
        for item in data:
            child = ET.SubElement(root, "record")
            _fill_xml(child, item)
    else:
        root = ET.Element("root")
        _fill_xml(root, data)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    buffer = io.BytesIO()
    tree.write(buffer, encoding="utf-8", xml_declaration=True)
    return buffer.getvalue() + b"\n"


class DataConverter(Converter):
    name = "data"

    def convert(self, ctx: ConvertContext) -> list[Path]:
        self.ensure_source_exists(ctx)
        self.ensure_kind(ctx, {"data", "sheet"})

        source = ctx.source
        token = ctx.token
        sheet = str(ctx.option("sheet", "") or "").strip() or None

        ctx.report(0.1, "讀取資料")
        kind, payload = load_source(source, sheet)

        dest = ctx.resolve_output(source, ctx.job.target.extension)
        ctx.track(dest)
        ctx.report(0.6, "寫入檔案")

        if token == "data-json":
            write_text(dest, _to_json(kind, payload))
        elif token == "data-csv":
            write_text(dest, _to_csv(kind, payload), bom=True)
        elif token == "data-yaml":
            write_text(dest, _to_yaml(kind, payload))
        elif token == "data-toml":
            write_text(dest, _to_toml(kind, payload))
        elif token == "data-xlsx":
            _to_xlsx(dest, kind, payload, sheet)
        elif token == "data-xml":
            try:
                dest.write_bytes(_to_xml(kind, payload))
            except OSError as exc:
                raise ConversionError(f"無法寫入 XML：{exc}", detail=str(exc)) from exc
        else:
            raise ConversionError(f"不支援的資料目標：{token}")

        ctx.report(1.0, "完成")
        if not dest.exists() or dest.stat().st_size == 0:
            dest.unlink(missing_ok=True)
            raise ConversionError("資料轉換失敗，沒有產生有效檔案。")
        return [dest]


__all__ = ["DataConverter", "load_source", "table_from_rows", "to_table"]
