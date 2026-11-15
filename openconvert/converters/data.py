"""資料轉換：CSV／TSV、JSON、XLSX、YAML、TOML。

表格型來源（CSV／TSV／XLSX）第一列視為欄位名稱；結構型來源
（JSON／YAML／TOML）則盡量保留原本的巢狀結構。
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from ..core.errors import ConversionError, InvalidInputError
from ..core.paths import resolve_output
from ..core.textio import read_text, write_text
from .base import ConvertContext, Converter

try:  # Python 3.11+ 內建；較舊版本由 tomli 提供
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 僅舊版 Python
    import tomli as tomllib  # type: ignore[no-redef]

TABULAR_EXTENSIONS = frozenset({"csv", "tsv", "xlsx", "xlsm"})
STRUCTURED_EXTENSIONS = frozenset({"json", "yaml", "yml", "toml"})
CSV_DELIMITERS = {"csv": ",", "tsv": "\t"}


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


def load_source(path: Path, sheet: str | None = None) -> tuple[str, Any]:
    """回傳 ``("table", (欄位, 列))`` 或 ``("value", 物件)``。"""
    extension = path.suffix.lstrip(".").lower()
    if extension in TABULAR_EXTENSIONS:
        if extension in CSV_DELIMITERS:
            header, rows = _read_csv(path, extension)
        else:
            header, rows = _read_xlsx(path, sheet)
        return "table", (header, rows)
    if extension in STRUCTURED_EXTENSIONS:
        return "value", _read_structured(path, extension)
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

        dest = resolve_output(source, ctx.output_dir, ctx.job.target.extension, overwrite=ctx.overwrite)
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
        else:
            raise ConversionError(f"不支援的資料目標：{token}")

        ctx.report(1.0, "完成")
        if not dest.exists() or dest.stat().st_size == 0:
            dest.unlink(missing_ok=True)
            raise ConversionError("資料轉換失敗，沒有產生有效檔案。")
        return [dest]


__all__ = ["DataConverter", "load_source", "table_from_rows", "to_table"]
