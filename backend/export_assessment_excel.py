#!/usr/bin/env python3
"""
RegComply: Export assessment as an Excel file with:
  - Current assessor answers + empty rows for incomplete assessments
  - Excel formulas to calculate compliance scores
  - Cell references for easy local completion by assessors
  - Downloadable file suitable for offline work

The Excel structure:
  Sheet 1 "Assessment":
    - Header: product name, version, regulation, assessment date
    - Table with columns:
      * Obligation ID
      * Article Reference
      * Requirement Text (truncated)
      * Status (compliant | non-compliant | partial | not-assessed)
      * Evidence (text)
      * Notes
      * Score (formula: 1 if compliant, 0.5 if partial, 0 if non-compliant/not-assessed)

  Sheet 2 "Summary":
    - Total obligations
    - Compliant count
    - Non-compliant count
    - Partial count
    - Not-assessed count
    - Overall compliance % (formula)
    - Compliance status (formula: based on % threshold)
"""

import io
from datetime import datetime
from typing import Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import (
    Font,
    PatternFill,
    Border,
    Side,
    Alignment,
    Protection,
)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy.orm import Session

from models import Assessment, VerificationAnswer

# Excel styling constants
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
SUBHEADER_FILL = PatternFill(
    start_color="D9E1F2", end_color="D9E1F2", fill_type="solid"
)
SUBHEADER_FONT = Font(bold=True, size=10)
SUMMARY_FILL = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
SUMMARY_FONT = Font(bold=True)
BORDER_THIN = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
CENTER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT_ALIGN = Alignment(horizontal="left", vertical="top", wrap_text=True)

# Status -> compliance score mapping
STATUS_SCORES = {
    "compliant": 1.0,
    "partial": 0.5,
    "non-compliant": 0.0,
    "not-assessed": 0.0,
    "": 0.0,  # blank = not assessed
}

# Valid statuses for dropdown
VALID_STATUSES = ["compliant", "partial", "non-compliant", "not-assessed"]


def normalize_status(raw_status: str) -> str:
    """Map legacy quiz statuses to the Excel dropdown vocabulary."""
    value = (raw_status or "").strip().lower()
    if not value:
        return ""

    mappings = {
        "verified": "compliant",
        "yes": "compliant",
        "pass": "compliant",
        "ok": "compliant",
        "not compliant": "non-compliant",
        "non compliant": "non-compliant",
        "failed": "non-compliant",
        "fail": "non-compliant",
        "no": "non-compliant",
        "n/a": "not-assessed",
        "na": "not-assessed",
        "not assessed": "not-assessed",
        "unknown": "not-assessed",
    }

    if value in VALID_STATUSES:
        return value
    return mappings.get(value, "not-assessed")


def _extract_article_ref(requirement_id: str) -> str:
    """Best-effort article extraction from requirement ID stored in DB."""
    if not requirement_id:
        return "General"
    parts = requirement_id.split("_")
    return parts[0] if parts else "General"


def build_quiz_rows_from_db(assessment: Assessment) -> List[Dict[str, str]]:
    """
    Build Excel rows using only relational DB data.

    Sources:
      - assessment.obligation_ids
      - assessment.justifications (requirement text)
      - assessment.answers (current assessor quiz answers)

    No Neo4j dependency.
    """
    obligation_ids = assessment.obligation_ids or []
    justifications = assessment.justifications or {}
    answers = assessment.answers or []

    by_verification_id: Dict[str, VerificationAnswer] = {
        a.verification_id: a for a in answers if a.verification_id
    }

    rows: List[Dict[str, str]] = []
    seen_verification_ids = set()

    # Primary initialization from requirement list in DB
    for requirement_id in obligation_ids:
        answer = by_verification_id.get(requirement_id)
        rows.append(
            {
                "requirement_id": requirement_id,
                "article_ref": _extract_article_ref(requirement_id),
                "requirement_text": (justifications.get(requirement_id) or "").strip()
                or "Requirement selected for this assessment.",
                "verification_id": requirement_id,
                "verification_text": (answer.verification_text if answer else "") or "",
                "status": (answer.status if answer else "") or "",
                "evidence": (answer.evidence if answer else "") or "",
                "notes": (answer.notes if answer else "") or "",
            }
        )
        seen_verification_ids.add(requirement_id)

    # Include saved quiz answers with explicit requirement mapping metadata.
    for answer in answers:
        vid = (answer.verification_id or "").strip()
        if not vid:
            continue

        mapped_any = False
        associated = answer.associated_obligations or []
        for assoc in associated:
            requirement_id = (assoc.get("obligation_id") or "").strip()
            article_ref = (assoc.get("article") or "").strip() or "General"
            requirement_text = (assoc.get("obligation_text") or "").strip()

            if not requirement_id:
                requirement_id = ""

            rows.append(
                {
                    "requirement_id": requirement_id,
                    "article_ref": article_ref,
                    "requirement_text": requirement_text
                    or (answer.verification_text or "")
                    or "Requirement selected for this assessment.",
                    "verification_id": vid,
                    "verification_text": answer.verification_text or "",
                    "status": answer.status or "",
                    "evidence": answer.evidence or "",
                    "notes": answer.notes or "",
                }
            )
            mapped_any = True
            if requirement_id:
                seen_verification_ids.add(requirement_id)

        if mapped_any:
            continue

        # Fallback for legacy rows that predate metadata persistence.
        if vid in seen_verification_ids:
            continue
        rows.append(
            {
                "requirement_id": vid if vid in obligation_ids else "",
                "article_ref": _extract_article_ref(
                    vid if vid in obligation_ids else ""
                ),
                "requirement_text": (answer.verification_text or "").strip()
                or (justifications.get(vid) or "").strip()
                or f"Verification action: {vid}",
                "verification_id": vid,
                "verification_text": answer.verification_text or "",
                "status": answer.status or "",
                "evidence": answer.evidence or "",
                "notes": answer.notes or "",
            }
        )

    return rows


def create_assessment_excel(
    db: Session,
    assessment: Assessment,
    include_answers: bool = True,
) -> io.BytesIO:
    """
    Generate an Excel workbook for the assessment.

    Args:
        db: database session
        assessment: Assessment object
        include_answers: if True, populate with current answers; else leave blank for fresh input

    Returns:
        BytesIO buffer containing the Excel file (ready to send as response)
    """
    wb = Workbook()
    ws_main = wb.active
    ws_main.title = "Assessment"
    ws_summary = wb.create_sheet("Summary")

    # ────────────────────────────────────────────────────────────────────────
    # ASSESSMENT SHEET
    # ────────────────────────────────────────────────────────────────────────

    # Header block
    ws_main["A1"] = "RegComply - Compliance Assessment Export"
    ws_main["A1"].font = Font(bold=True, size=14, color="FFFFFF")
    ws_main["A1"].fill = HEADER_FILL
    ws_main.merge_cells("A1:F1")
    ws_main["A1"].alignment = CENTER_ALIGN
    ws_main.row_dimensions[1].height = 25

    # Metadata
    row = 3
    ws_main[f"A{row}"] = "Product:"
    ws_main[f"B{row}"] = assessment.product_name
    ws_main[f"A{row}"].font = Font(bold=True)

    row += 1
    ws_main[f"A{row}"] = "Version:"
    ws_main[f"B{row}"] = (
        assessment.product_version.version_number if assessment.product_version else ""
    )
    ws_main[f"A{row}"].font = Font(bold=True)

    row += 1
    ws_main[f"A{row}"] = "Regulation:"
    ws_main[f"B{row}"] = assessment.regulation
    ws_main[f"A{row}"].font = Font(bold=True)

    row += 1
    ws_main[f"A{row}"] = "Assessment Date:"
    ws_main[f"B{row}"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    ws_main[f"A{row}"].font = Font(bold=True)

    row += 1
    ws_main[f"A{row}"] = "Product Class:"
    ws_main[f"B{row}"] = assessment.product_class
    ws_main[f"A{row}"].font = Font(bold=True)

    # Instructions
    row += 2
    ws_main[f"A{row}"] = (
        "Instructions: Complete the 'Status' column for each obligation. "
        "Valid values: compliant, partial, non-compliant, not-assessed. "
        "The 'Score' column will calculate automatically."
    )
    ws_main[f"A{row}"].font = Font(italic=True, size=9)
    ws_main.merge_cells(f"A{row}:F{row}")
    ws_main[f"A{row}"].alignment = LEFT_ALIGN

    # Table header
    row += 2
    header_row = row
    headers = [
        "Requirement ID",
        "Article Ref",
        "Requirement / Verification Action",
        "Status",
        "Evidence",
        "Notes",
        "Score",
    ]
    for col, header in enumerate(headers, start=1):
        cell = ws_main.cell(row=header_row, column=col, value=header)
        cell.fill = SUBHEADER_FILL
        cell.font = SUBHEADER_FONT
        cell.border = BORDER_THIN
        cell.alignment = CENTER_ALIGN
    ws_main.row_dimensions[header_row].height = 20

    # Build quiz rows from DB only (no Neo4j)
    quiz_rows = build_quiz_rows_from_db(assessment)

    # Data rows
    first_data_row = header_row + 1
    data_row = first_data_row
    for row_data in quiz_rows:
        # Requirement ID
        ws_main.cell(row=data_row, column=1, value=row_data["requirement_id"])

        # Article Ref
        ws_main.cell(row=data_row, column=2, value=row_data["article_ref"])

        # Requirement / verification text (full text with wrapping)
        ws_main.cell(row=data_row, column=3, value=row_data["requirement_text"])

        # Status (with data validation dropdown)
        status_cell = ws_main.cell(row=data_row, column=4)
        if include_answers:
            status_cell.value = normalize_status(row_data["status"])
        else:
            status_cell.value = ""

        # Evidence
        evidence_cell = ws_main.cell(row=data_row, column=5)
        if include_answers:
            evidence_cell.value = row_data["evidence"]
        else:
            evidence_cell.value = ""

        # Notes
        notes_cell = ws_main.cell(row=data_row, column=6)
        if include_answers:
            notes_cell.value = row_data["notes"]
        else:
            notes_cell.value = ""

        # Score (formula: VLOOKUP or nested IF)
        score_cell = ws_main.cell(row=data_row, column=7)
        score_cell.value = (
            f'=IF(D{data_row}="compliant",1,IF(D{data_row}="partial",0.5,0))'
        )
        score_cell.number_format = "0.0"

        # Apply formatting
        for col in range(1, 8):
            cell = ws_main.cell(row=data_row, column=col)
            cell.border = BORDER_THIN
            cell.alignment = Alignment(
                horizontal="left", vertical="top", wrap_text=True
            )  # All columns wrap
            if col in (1, 2):  # Obligation ID, Article Ref - center align
                cell.alignment = Alignment(
                    horizontal="center", vertical="center", wrap_text=True
                )
            elif col == 7:  # Score - center align
                cell.alignment = Alignment(horizontal="center", vertical="center")

        data_row += 1

    # Column widths
    ws_main.column_dimensions["A"].width = 18
    ws_main.column_dimensions["B"].width = 14
    ws_main.column_dimensions["C"].width = (
        50  # requirement text - wider for full display
    )
    ws_main.column_dimensions["D"].width = 16
    ws_main.column_dimensions["E"].width = 28
    ws_main.column_dimensions["F"].width = 28
    ws_main.column_dimensions["G"].width = 12

    # Set row heights to accommodate wrapped text
    for row_num in range(10, data_row):
        ws_main.row_dimensions[row_num].height = None  # Auto-fit height

    # Add dropdown validation to Status column (D)
    dv = DataValidation(
        type="list", formula1=f'"{",".join(VALID_STATUSES)}"', allow_blank=True
    )
    dv.error = "Please select from: compliant, partial, non-compliant, not-assessed"
    dv.errorTitle = "Invalid Status"
    dv.prompt = "Select a status"
    dv.promptTitle = "Status"
    ws_main.add_data_validation(dv)
    if data_row > first_data_row:
        dv.add(f"D{first_data_row}:D{data_row - 1}")

    # ────────────────────────────────────────────────────────────────────────
    # SUMMARY SHEET
    # ────────────────────────────────────────────────────────────────────────

    ws_summary["A1"] = "Compliance Summary"
    ws_summary["A1"].font = Font(bold=True, size=14, color="FFFFFF")
    ws_summary["A1"].fill = HEADER_FILL
    ws_summary.merge_cells("A1:B1")
    ws_summary["A1"].alignment = CENTER_ALIGN
    ws_summary.row_dimensions[1].height = 25

    row = 3
    # Total obligations
    ws_summary[f"A{row}"] = "Total Obligations:"
    ws_summary[f"B{row}"] = f"=COUNTA(Assessment!A{first_data_row}:A{data_row - 1})"
    ws_summary[f"A{row}"].font = Font(bold=True)

    row += 1
    ws_summary[f"A{row}"] = "Compliant Count:"
    ws_summary[f"B{row}"] = (
        f'=COUNTIF(Assessment!D{first_data_row}:D{data_row - 1},"compliant")'
    )
    ws_summary[f"A{row}"].font = Font(bold=True)

    row += 1
    ws_summary[f"A{row}"] = "Partial Count:"
    ws_summary[f"B{row}"] = (
        f'=COUNTIF(Assessment!D{first_data_row}:D{data_row - 1},"partial")'
    )
    ws_summary[f"A{row}"].font = Font(bold=True)

    row += 1
    ws_summary[f"A{row}"] = "Non-Compliant Count:"
    ws_summary[f"B{row}"] = (
        f'=COUNTIF(Assessment!D{first_data_row}:D{data_row - 1},"non-compliant")'
    )
    ws_summary[f"A{row}"].font = Font(bold=True)

    row += 1
    ws_summary[f"A{row}"] = "Not-Assessed Count:"
    ws_summary[f"B{row}"] = (
        f"=COUNTA(Assessment!D{first_data_row}:D{data_row - 1})-B{row - 4}-B{row - 3}-B{row - 2}"
    )
    ws_summary[f"A{row}"].font = Font(bold=True)

    row += 2
    # Overall compliance score
    ws_summary[f"A{row}"] = "Overall Compliance Score (%):"
    ws_summary[f"B{row}"] = (
        f"=IF(B3=0,0,ROUND(SUM(Assessment!G{first_data_row}:G{data_row - 1})/B3*100,1))"
    )
    ws_summary[f"B{row}"].number_format = "0.0"
    ws_summary[f"A{row}"].font = Font(bold=True)
    ws_summary[f"B{row}"].font = Font(bold=True, size=12, color="FFFFFF")
    ws_summary[f"B{row}"].fill = SUMMARY_FILL

    row += 1
    # Compliance status (>90% = compliant, >50% = partial, <=50% = non-compliant)
    ws_summary[f"A{row}"] = "Compliance Status:"
    ws_summary[f"B{row}"] = (
        f'=IF(B{row - 1}>=90,"COMPLIANT",IF(B{row - 1}>=50,"PARTIAL","NON-COMPLIANT"))'
    )
    ws_summary[f"A{row}"].font = Font(bold=True, size=12)
    ws_summary[f"B{row}"].font = Font(bold=True, size=12, color="FFFFFF")
    ws_summary[f"B{row}"].fill = SUMMARY_FILL
    ws_summary[f"B{row}"].alignment = CENTER_ALIGN

    # Column widths
    ws_summary.column_dimensions["A"].width = 30
    ws_summary.column_dimensions["B"].width = 20

    # Apply formatting to summary cells
    for r in range(3, row + 1):
        for col in ["A", "B"]:
            ws_summary[f"{col}{r}"].border = BORDER_THIN
            if col == "B":
                ws_summary[f"{col}{r}"].alignment = CENTER_ALIGN

    # ────────────────────────────────────────────────────────────────────────
    # Write to buffer
    # ────────────────────────────────────────────────────────────────────────

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def export_filename(assessment: Assessment) -> str:
    """Generate a sensible export filename."""
    date_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return (
        f"{assessment.product_name}_{assessment.regulation}_"
        f"v{assessment.product_version.version_number if assessment.product_version else '?'}"
        f"_{date_str}.xlsx"
    )
