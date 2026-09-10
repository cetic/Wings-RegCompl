"""Export a CRA assessment JSON to a formatted Excel compliance workbook.

This module provides the ``export_assessment_to_excel`` tool which reads an
assessment JSON (produced by ``product_obligations``) and writes a
professionally-formatted *.xlsx* workbook with two core sheets:
  - **Obligations**: every legal obligation with an auto-computed compliance status
  - **Verification Actions**: every verification action linked to an obligation
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
    numbers,
)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

logger = logging.getLogger(__name__)

# ── Colours & styles ──────────────────────────────────────────────────
_NAVY = "1F3864"
_WHITE = "FFFFFF"
_LIGHT_BLUE = "D6E4F0"
_LIGHT_GREY = "F2F2F2"
_GREEN = "C6EFCE"
_RED = "FFC7CE"
_YELLOW = "FFEB9C"
_ORANGE = "FCE4D6"

_HEADER_FONT = Font(name="Calibri", bold=True, size=11, color=_WHITE)
_HEADER_FILL = PatternFill(start_color=_NAVY, end_color=_NAVY, fill_type="solid")
_HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)

_BODY_FONT = Font(name="Calibri", size=10)
_BODY_ALIGN = Alignment(vertical="top", wrap_text=True)
_CENTER_ALIGN = Alignment(horizontal="center", vertical="top", wrap_text=True)

_THIN_BORDER = Border(
    left=Side(style="thin", color="B0B0B0"),
    right=Side(style="thin", color="B0B0B0"),
    top=Side(style="thin", color="B0B0B0"),
    bottom=Side(style="thin", color="B0B0B0"),
)

_STRIPE_FILL = PatternFill(
    start_color=_LIGHT_GREY, end_color=_LIGHT_GREY, fill_type="solid"
)


# ── Summary sheet ─────────────────────────────────────────────────────
def _write_summary_sheet(wb: Workbook, data: dict[str, Any]) -> None:
    """Create a Cover / Summary sheet."""
    ws: Worksheet = wb.active  # type: ignore[assignment]
    ws.title = "Summary"
    ws.sheet_properties.tabColor = _NAVY

    product = data.get("product", {})
    stats = data.get("statistics", {})
    conformity = data.get("conformity_assessment", {})

    # Title
    ws.merge_cells("A1:F1")
    title_cell = ws["A1"]
    title_cell.value = "EU Cyber Resilience Act — Compliance Assessment"
    title_cell.font = Font(name="Calibri", bold=True, size=16, color=_NAVY)
    title_cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 35

    # Subtitle
    ws.merge_cells("A2:F2")
    sub_cell = ws["A2"]
    sub_cell.value = "Regulation (EU) 2024/2847"
    sub_cell.font = Font(name="Calibri", size=12, color="666666")
    ws.row_dimensions[2].height = 22

    row = 4
    info_items: list[tuple[str, str]] = [
        ("Product Description", product.get("description", "")),
        ("CRA Classification", product.get("classification", "")),
        (
            "Annex III Categories",
            ", ".join(product.get("matched_annex_iii_categories", [])),
        ),
        ("Actor Role", product.get("actor_role", "")),
        ("Classification Confidence", product.get("confidence", "")),
        ("Classification Reasoning", product.get("reasoning", "")),
        ("Conformity Assessment Route", conformity.get("route", "")),
        ("", ""),  # spacer
        ("Total Obligations", str(stats.get("total_obligations", ""))),
        (
            "Obligations with Verifications",
            str(stats.get("obligations_with_actions", "")),
        ),
        (
            "Obligations with Evidence Suggestions",
            str(stats.get("obligations_with_evidence", "")),
        ),
        (
            "Obligations with Deadlines",
            str(stats.get("obligations_with_deadlines", "")),
        ),
        ("Articles Covered", str(stats.get("articles_covered", ""))),
    ]

    label_font = Font(name="Calibri", bold=True, size=11, color=_NAVY)
    value_font = Font(name="Calibri", size=11)
    value_align = Alignment(vertical="top", wrap_text=True)

    for label, value in info_items:
        if not label:
            row += 1
            continue
        cell_l = ws.cell(row=row, column=1, value=label)
        cell_l.font = label_font
        cell_l.alignment = Alignment(vertical="top")
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
        cell_v = ws.cell(row=row, column=2, value=value)
        cell_v.font = value_font
        cell_v.alignment = value_align
        ws.row_dimensions[row].height = max(20, min(80, 15 * (1 + len(value) // 90)))
        row += 1

    # Legend
    row += 2
    ws.cell(row=row, column=1, value="Status Legend").font = Font(
        name="Calibri", bold=True, size=12, color=_NAVY
    )
    row += 1
    legend = [
        ("Compliant", "All verification actions verified", _GREEN),
        ("Not Compliant", "Obligation not met — action required", _RED),
        ("Partially Compliant", "Some verifications verified", _YELLOW),
        ("Not Applicable", "Obligation does not apply to this product", _ORANGE),
    ]
    for status_val, desc, colour in legend:
        cell_s = ws.cell(row=row, column=1, value=status_val)
        cell_s.font = Font(name="Calibri", bold=True, size=10)
        cell_s.fill = PatternFill(
            start_color=colour, end_color=colour, fill_type="solid"
        )
        ws.cell(row=row, column=2, value=desc).font = Font(name="Calibri", size=10)
        row += 1

    # Instructions
    row += 2
    ws.cell(row=row, column=1, value="How to Use").font = Font(
        name="Calibri", bold=True, size=12, color=_NAVY
    )
    row += 1
    instructions = [
        "1. Go to the 'Verification Actions' sheet",
        "2. For each verification, set Status to 'Verified' or 'Not Verified'",
        "3. The 'Obligations' sheet Status column auto-updates based on verification statuses",
        "4. When ALL verifications for an obligation are 'Verified', the obligation becomes 'Compliant'",
        "5. Override the auto-status in the Obligations sheet if needed (e.g. 'Not Applicable')",
        "6. Use the Evidence column to reference your documentation",
        "7. Filter by Article or Status to focus on specific areas",
    ]
    for instr in instructions:
        ws.cell(row=row, column=1, value=instr).font = Font(name="Calibri", size=10)
        row += 1

    ws.column_dimensions["A"].width = 32
    for col_idx in range(2, 7):
        ws.column_dimensions[get_column_letter(col_idx)].width = 25


# ── Obligations sheet ─────────────────────────────────────────────────
def _write_obligations_sheet(
    wb: Workbook,
    checklist: list[dict],
    verif_start_row: int,
    verif_end_row: int,
) -> None:
    """Create the Obligations sheet with auto-compliance formulas.

    The Status column uses COUNTIFS formulas referencing the Verification
    Actions sheet: if ALL verifications for an obligation are 'Verified',
    the status becomes 'Compliant'. If some are verified, 'Partially Compliant'.
    If none are verified, 'Not Compliant'. If there are no verifications, it
    defaults to '' (blank) for manual entry.
    """
    ws: Worksheet = wb.create_sheet("Obligations")
    ws.sheet_properties.tabColor = "4472C4"
    ws.freeze_panes = "E2"

    headers = [
        "#",
        "Obligation ID",
        "Article",
        "Article Title",
        "Paragraph",
        "Obligation",
        "Trigger",
        "Deadline",
        "Status",
        "Evidence",
        "Notes",
    ]
    widths = [5, 20, 12, 22, 22, 70, 25, 25, 20, 40, 35]

    # Headers
    for col_idx, (header, width) in enumerate(zip(headers, widths), start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _HEADER_ALIGN
        cell.border = _THIN_BORDER
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.row_dimensions[1].height = 30

    # The "Associated Obligations" column letter in the Verifications sheet (col B)
    # and the "Status" column letter in the Verifications sheet (col E)
    verif_obl_col = "B"  # Associated Obligations in Verification Actions sheet
    verif_status_col = "E"  # Status in Verification Actions sheet

    status_col_idx = headers.index("Status") + 1  # 1-indexed

    for row_idx, item in enumerate(checklist, start=2):
        is_odd = row_idx % 2 == 1
        obl_id = item.get("id", "")

        data_map = {
            "#": item.get("#", ""),
            "Obligation ID": obl_id,
            "Article": item.get("article", ""),
            "Article Title": item.get("article_title", ""),
            "Paragraph": item.get("paragraph", ""),
            "Obligation": item.get("obligation", ""),
            "Trigger": item.get("trigger", ""),
            "Deadline": item.get("deadline", ""),
            "Status": "",  # formula will be set below
            "Evidence": item.get("evidence", ""),
            "Notes": item.get("notes", ""),
        }

        for col_idx, header in enumerate(headers, start=1):
            value = data_map.get(header, "")
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = _BODY_FONT
            cell.alignment = (
                _CENTER_ALIGN if header in ("#", "Obligation ID", "Article", "Status")
                else _BODY_ALIGN
            )
            cell.border = _THIN_BORDER
            if is_odd:
                cell.fill = _STRIPE_FILL

        # ── Auto-compliance formula in Status column ──
        # Uses COUNTIFS on the Verification Actions sheet to compute status
        status_cell = ws.cell(row=row_idx, column=status_col_idx)
        va_range_obl = f"'Verification Actions'!{verif_obl_col}{verif_start_row}:{verif_obl_col}{verif_end_row}"
        va_range_status = f"'Verification Actions'!{verif_status_col}{verif_start_row}:{verif_status_col}{verif_end_row}"
        #   total = COUNTIF(obl_range, "* " & obl_id & " *")
        #   verified = COUNTIFS(obl_range, "* " & obl_id & " *", status_range, "Verified")
        #   IF total=0, "" (no verifications, fill manually)
        #   ELSE IF verified=total, "Compliant"
        #   ELSE IF verified>0, "Partially Compliant"
        #   ELSE "Not Compliant"
        formula = (
            f'=IF(COUNTIF({va_range_obl},"* "&B{row_idx}&" *")=0,"",'
            f'IF(COUNTIFS({va_range_obl},"* "&B{row_idx}&" *",{va_range_status},"Verified")'
            f'=COUNTIF({va_range_obl},"* "&B{row_idx}&" *"),"Compliant",'
            f'IF(COUNTIFS({va_range_obl},"* "&B{row_idx}&" *",{va_range_status},"Verified")>0,'
            f'"Partially Compliant","Not Compliant")))'
        )
        status_cell.value = formula
        status_cell.font = _BODY_FONT
        status_cell.alignment = _CENTER_ALIGN
        status_cell.border = _THIN_BORDER

    # Status dropdown override (user can manually override the formula)
    dv = DataValidation(
        type="list",
        formula1='"Compliant,Not Compliant,Partially Compliant,Not Applicable"',
        allow_blank=True,
    )
    dv.error = "Select: Compliant, Not Compliant, Partially Compliant, or Not Applicable"
    dv.errorTitle = "Invalid Status"
    dv.prompt = "Auto-computed from verifications. Override if needed."
    dv.promptTitle = "Obligation Status"
    # Note: we do NOT add the validation to avoid overriding the formula
    # Users can still type/paste a manual override

    # Auto-filter
    last_row = len(checklist) + 1
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last_row}"

    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = "1:1"


# ── Verification Actions sheet ────────────────────────────────────────
def _write_verifications_sheet(wb: Workbook, verif_rows: list[dict]) -> int:
    """Create the Verification Actions sheet.

    Returns the last data row number (for formula references).
    """
    ws: Worksheet = wb.create_sheet("Verification Actions")
    ws.sheet_properties.tabColor = "548235"
    ws.freeze_panes = "D2"

    headers = [
        "#",
        "Associated Obligations",
        "Verification Type",
        "Verification Description",
        "Status",
        "Required Evidence",
        "Evidence Provided",
        "Notes",
    ]
    widths = [5, 40, 16, 55, 16, 40, 40, 30]

    _VERIF_FILL = PatternFill(start_color="548235", end_color="548235", fill_type="solid")

    for col_idx, (header, width) in enumerate(zip(headers, widths), start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _VERIF_FILL
        cell.alignment = _HEADER_ALIGN
        cell.border = _THIN_BORDER
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.row_dimensions[1].height = 30

    for row_idx, vrow in enumerate(verif_rows, start=2):
        is_odd = row_idx % 2 == 1
        data_vals = [
            vrow.get("#", ""),
            vrow.get("associated_obligations", ""),
            vrow.get("type", ""),
            vrow.get("description", ""),
            "",  # Status — user fills this
            vrow.get("evidence", ""),
            "",  # Evidence Provided — user fills
            "",  # Notes — user fills
        ]
        for col_idx, value in enumerate(data_vals, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = _BODY_FONT
            cell.alignment = (
                _CENTER_ALIGN
                if headers[col_idx - 1] in ("#", "Verification Type", "Status")
                else _BODY_ALIGN
            )
            cell.border = _THIN_BORDER
            if is_odd:
                cell.fill = _STRIPE_FILL

    # Status dropdown on the Status column (col E = 5)
    status_col_letter = "E"
    last_row = max(len(verif_rows) + 1, 2)
    dv = DataValidation(
        type="list",
        formula1='"Verified,Not Verified,In Progress,Blocked,Not Applicable"',
        allow_blank=True,
    )
    dv.error = "Select: Verified, Not Verified, In Progress, Blocked, or Not Applicable"
    dv.errorTitle = "Invalid Status"
    dv.prompt = "Set verification status"
    dv.promptTitle = "Verification Status"
    dv.add(f"{status_col_letter}2:{status_col_letter}{last_row}")
    ws.add_data_validation(dv)

    # Auto-filter
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last_row}"

    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.print_title_rows = "1:1"

    return last_row


# ── Public tool function ──────────────────────────────────────────────


def export_assessment_to_excel(json_file: str) -> dict:
    """Convert a CRA assessment JSON file to a formatted Excel compliance workbook.

    Reads the JSON file produced by ``product_obligations`` and writes a *.xlsx*
    workbook with:
    - **Summary**: product info, classification, statistics and usage instructions
    - **Obligations**: all obligations with auto-computed compliance status
    - **Verification Actions**: every verification action with type, status dropdown, and evidence

    When all Verification Actions for an obligation are marked 'Verified',
    the obligation's Status auto-updates to 'Compliant'.

    Args:
        json_file: Path to a CRA assessment JSON file (e.g.
            ``outputs/CRA_assessment_smart_thermostat_20260226_180652.json``).
            Accepts an absolute path or a path relative to the outputs/ folder.

    Returns:
        dict with "status", "excel_file" (path), and "summary" message.
    """
    # ── Resolve the file path ─────────────────────────────────────────
    path = Path(json_file)
    if not path.exists():
        # Try relative to outputs/
        alt = Path("outputs") / path.name
        if alt.exists():
            path = alt
        else:
            return {
                "status": "error",
                "message": f"File not found: {json_file}. Provide the path to a CRA assessment JSON file.",
            }

    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"status": "error", "message": f"Failed to read JSON: {exc}"}

    checklist: list[dict] = data.get("checklist", [])
    if not checklist:
        return {
            "status": "error",
            "message": "No obligations found in the JSON file.",
        }

    # ── Fetch VerificationActions from Neo4j ──────────────────────────
    verif_rows: list[dict] = []
    try:
        from .neo4j_tools import _get_driver
        _driver = _get_driver()
        obl_ids = [c["id"] for c in checklist]
        with _driver.session() as _session:
            _res = _session.run(
                "MATCH (o:Obligation)-[:HAS_VERIFICATION]->(v:VerificationAction) "
                "WHERE o.id IN $ids "
                "RETURN v.id AS vid, v.type AS type, v.description AS description, v.evidence AS evidence, "
                "collect(o.id) AS obligation_ids "
                "ORDER BY type, vid",
                ids=obl_ids,
            )
            v_num = 0
            for row in _res:
                v_num += 1
                # Format with spaces so Excel wildcard "* "&B2&" *" matches accurately
                assoc = " " + " ".join(row["obligation_ids"]) + " "
                verif_rows.append({
                    "#": v_num,
                    "associated_obligations": assoc,
                    "type": (row["type"] or "").capitalize(),
                    "description": row["description"] or "",
                    "evidence": row["evidence"] or "",
                })
        _driver.close()
    except Exception as e:
        logger.warning("Could not fetch VerificationActions from Neo4j: %s", e)

    # ── Build workbook ────────────────────────────────────────────────
    wb = Workbook()

    # Write the Verification Actions sheet FIRST so we know the row range
    # (the Obligations sheet formulas reference it)
    verif_last_row = _write_verifications_sheet(wb, verif_rows)
    verif_start_row = 2  # data starts at row 2

    _write_summary_sheet(wb, data)
    _write_obligations_sheet(wb, checklist, verif_start_row, verif_last_row)

    # Reorder sheets: Summary first, then Obligations, then Verification Actions
    wb.move_sheet("Summary", offset=-2)
    wb.move_sheet("Obligations", offset=-1)

    # ── Save ──────────────────────────────────────────────────────────
    xlsx_name = path.stem + ".xlsx"
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    xlsx_path = output_dir / xlsx_name

    wb.save(str(xlsx_path))
    logger.info("Excel workbook written to %s", xlsx_path)

    # ── Summary ───────────────────────────────────────────────────────
    product = data.get("product", {})
    obligations_with_verifs = sum(
        len(v["associated_obligations"].strip().split(" ")) for v in verif_rows
    )

    summary = (
        f"Excel compliance workbook saved to **{xlsx_path}**\n\n"
        f"Product: {product.get('description', 'N/A')[:80]}…\n"
        f"Classification: {product.get('classification', 'N/A')}\n"
        f"Actor: {product.get('actor_role', 'N/A')}\n\n"
        f"Sheets created:\n"
        f"  • **Summary** — product info, classification & instructions\n"
        f"  • **Obligations** — {len(checklist)} obligations with auto-computed compliance status\n"
        f"  • **Verification Actions** — {len(verif_rows)} verification actions across "
        f"{obligations_with_verifs} obligations\n\n"
        f"ℹ️ Mark each Verification Action as 'Verified' in the Verification Actions sheet.\n"
        f"When ALL verifications for an obligation are 'Verified', its status auto-updates to 'Compliant'."
    )

    return {
        "status": "ok",
        "excel_file": str(xlsx_path),
        "verification_count": len(verif_rows),
        "summary": summary,
    }
