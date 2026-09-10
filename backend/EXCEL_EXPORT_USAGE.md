#!/usr/bin/env python3
"""
Excel Export Feature - Usage Guide

OVERVIEW
========
The Excel export feature allows assessors to download an assessment as an Excel file,
complete it locally, and/or share it with others. The file includes:
  - Assessment metadata (product name, version, regulation, date)
  - All obligations with current assessor answers
  - Formulas to calculate compliance scores automatically
  - Summary sheet with overall compliance percentage

API ENDPOINT
============
GET /api/assessments/{assessment_id}/export-excel

Query Parameters:
  - include_answers (boolean, default=true)
      If true, the Excel file is populated with current assessor answers
      If false, the file includes empty cells for fresh input

Response:
  - MIME type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
  - Filename: {ProductName}_{Regulation}_v{Version}_{Timestamp}.xlsx

USAGE EXAMPLES
==============

1. Export with current answers:
   GET /api/assessments/abc123/export-excel?include_answers=true

2. Export blank template for fresh input:
   GET /api/assessments/abc123/export-excel?include_answers=false

EXCEL FILE STRUCTURE
====================

Sheet 1: "Assessment"
  Columns:
    A - Obligation ID (e.g., "obl_1")
    B - Article Ref (e.g., "Art. 13(1)")
    C - Requirement (requirement text, truncated)
    D - Status (dropdown: compliant | partial | non-compliant | not-assessed)
    E - Evidence (free text field for supporting evidence)
    F - Notes (free text for assessor notes)
    G - Score (auto-calculated formula:
        - 1.0 if "compliant"
        - 0.5 if "partial"
        - 0.0 if "non-compliant" or "not-assessed")

  Header rows 1-8: metadata + instructions
  Data rows 9+: one row per obligation

Sheet 2: "Summary"
  Summary statistics with auto-calculated formulas:
    - Total Obligations (count of rows with data)
    - Compliant Count (COUNTIF for "compliant")
    - Partial Count (COUNTIF for "partial")
    - Non-Compliant Count (COUNTIF for "non-compliant")
    - Not-Assessed Count (derived from total)
    - Overall Compliance Score (%) = SUM(scores) / total * 100
    - Compliance Status (formula-driven):
        >= 90% → COMPLIANT
        >= 50% → PARTIAL
        < 50% → NON-COMPLIANT

WORKFLOW
========

1. DOWNLOAD (Assessor)
   - User navigates to an assessment in the UI
   - Clicks "Export as Excel" button
   - Browser downloads the .xlsx file

2. LOCAL COMPLETION (Assessor)
   - Open the file in Excel, Google Sheets, LibreOffice, etc.
   - For each obligation:
     * Select Status from dropdown (compliant | partial | non-compliant)
     * Fill in Evidence (requirements, test results, documentation)
     * Add Notes if needed
   - Score column auto-calculates
   - Summary sheet updates automatically

3. UPLOAD / IMPORT (Optional)
   - Assessor can email the completed Excel to a colleague
   - Colleague imports it back to the system (future feature)
   - Or copy/paste answers back into the web UI

4. COMPLIANCE SCORE
   - Automatically calculated on every row change
   - Overall % shown in Summary sheet
   - Compliance status (COMPLIANT/PARTIAL/NON-COMPLIANT) auto-determined

FEATURES
========

✓ Offline-capable: complete assessment without internet
✓ Shareable: email to colleagues, co-assessors
✓ Formula-driven: all calculations update in real-time
✓ Data validation: Status column has dropdown to prevent typos
✓ Professional formatting: color-coded headers, proper alignment
✓ Regulation-aware: includes product class, version, regulation code
✓ Two views: detailed obligations + summary statistics

TECHNICAL DETAILS
=================

Implementation: backend/export_assessment_excel.py
  - create_assessment_excel(db, assessment, include_answers)
    Returns: io.BytesIO buffer with the Excel workbook
  - export_filename(assessment)
    Returns: suggested filename based on product + date

API Integration: backend/main.py
  - Endpoint: GET /api/assessments/{assessment_id}/export-excel
  - Returns: StreamingResponse with xlsx MIME type

Dependencies:
  - openpyxl: Excel file creation and manipulation
  - FastAPI: HTTP response streaming

FORMULA REFERENCE
=================

Score formula per obligation:
  =IF(D{row}="compliant",1,IF(D{row}="partial",0.5,0))

Overall compliance score:
  =IF(B4=0,0,ROUND(SUM(Assessment!G10:G{max_row})/B4*100,1))

Compliance status:
  =IF(B{score_row}>=90,"COMPLIANT",IF(B{score_row}>=50,"PARTIAL","NON-COMPLIANT"))

All formulas use cell references, so compliance scores update automatically
when assessors change Status values.
