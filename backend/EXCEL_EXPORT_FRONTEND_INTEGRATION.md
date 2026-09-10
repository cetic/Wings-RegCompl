#!/usr/bin/env bash
# FRONTEND INTEGRATION - Excel Export Button

# ============================================================================
# REACT / TYPESCRIPT INTEGRATION EXAMPLE
# ============================================================================
# 
# Add this component/function to your assessment detail page or report view.
# The button will download the Excel file when clicked.
#

# --- Example 1: Inline Export Button (React) ---

# Inside your assessment detail component:
# 
# const [isExporting, setIsExporting] = useState(false);
#
# const handleExportExcel = async (assessmentId: string, includeAnswers: boolean = true) => {
#   setIsExporting(true);
#   try {
#     const params = new URLSearchParams({
#       include_answers: String(includeAnswers),
#     });
#     const response = await fetch(
#       `/api/assessments/${assessmentId}/export-excel?${params}`,
#       {
#         method: 'GET',
#         headers: {
#           'Authorization': `Bearer ${token}`, // if using bearer auth
#         },
#       }
#     );
#
#     if (!response.ok) {
#       throw new Error(`Export failed: ${response.statusText}`);
#     }
#
#     // Get filename from Content-Disposition header
#     const disposition = response.headers.get('content-disposition');
#     const filename = disposition?.split('filename="')[1]?.split('"')[0] || 'assessment.xlsx';
#
#     // Create blob and download
#     const blob = await response.blob();
#     const url = window.URL.createObjectURL(blob);
#     const a = document.createElement('a');
#     a.href = url;
#     a.download = filename;
#     document.body.appendChild(a);
#     a.click();
#     window.URL.revokeObjectURL(url);
#     document.body.removeChild(a);
#   } catch (error) {
#     console.error('Export failed:', error);
#     // Show error toast/notification
#   } finally {
#     setIsExporting(false);
#   }
# };
#
# // Button in JSX:
# <button
#   onClick={() => handleExportExcel(assessment.id, true)}
#   disabled={isExporting}
#   className="btn btn-secondary"
# >
#   {isExporting ? 'Exporting...' : '📥 Export as Excel (with answers)'}
# </button>
# 
# <button
#   onClick={() => handleExportExcel(assessment.id, false)}
#   disabled={isExporting}
#   className="btn btn-secondary"
# >
#   {isExporting ? 'Exporting...' : '📄 Export as Excel (blank template)'}
# </button>


# --- Example 2: Custom Hook (React) ---

# // useExportAssessment.ts
# import { useCallback, useState } from 'react';
#
# interface ExportOptions {
#   assessmentId: string;
#   includeAnswers?: boolean;
# }
#
# export const useExportAssessment = () => {
#   const [isLoading, setIsLoading] = useState(false);
#   const [error, setError] = useState<string | null>(null);
#
#   const exportAsExcel = useCallback(async (options: ExportOptions) => {
#     const { assessmentId, includeAnswers = true } = options;
#     setIsLoading(true);
#     setError(null);
#
#     try {
#       const params = new URLSearchParams({
#         include_answers: String(includeAnswers),
#       });
#       const response = await fetch(
#         `/api/assessments/${assessmentId}/export-excel?${params}`,
#         { method: 'GET' }
#       );
#
#       if (!response.ok) {
#         throw new Error(`HTTP ${response.status}`);
#       }
#
#       const blob = await response.blob();
#       const filename = 
#         response.headers
#           .get('content-disposition')
#           ?.split('filename="')[1]
#           ?.split('"')[0] || 'assessment.xlsx';
#
#       const url = window.URL.createObjectURL(blob);
#       const link = document.createElement('a');
#       link.href = url;
#       link.download = filename;
#       link.click();
#       window.URL.revokeObjectURL(url);
#     } catch (err) {
#       setError(err instanceof Error ? err.message : 'Export failed');
#       throw err;
#     } finally {
#       setIsLoading(false);
#     }
#   }, []);
#
#   return { exportAsExcel, isLoading, error };
# };
#
# // Usage in component:
# const { exportAsExcel, isLoading } = useExportAssessment();
# 
# <button onClick={() => exportAsExcel({ assessmentId, includeAnswers: true })}>
#   Export Excel
# </button>


# --- Example 3: Dropdown Menu for Export Options ---

# <div className="export-menu">
#   <button className="btn-menu">📤 Export</button>
#   <ul className="dropdown">
#     <li>
#       <button onClick={() => exportAsExcel({ assessmentId, includeAnswers: true })}>
#         📊 Excel (with current answers)
#       </button>
#     </li>
#     <li>
#       <button onClick={() => exportAsExcel({ assessmentId, includeAnswers: false })}>
#         📄 Excel (blank template)
#       </button>
#     </li>
#     <li>
#       <a href={`/api/assessments/${assessmentId}/compliance-report/pdf`}>
#         📋 PDF Report
#       </a>
#     </li>
#   </ul>
# </div>


# ============================================================================
# PLACEMENT RECOMMENDATIONS
# ============================================================================
#
# 1. NEAR THE REPORT (primary location)
#    - After the compliance report is displayed
#    - Next to PDF export button (if exists)
#    - In a toolbar or action menu
#
# 2. IN A SIDEBAR
#    - "Quick Actions" section
#    - Next to "View Report", "Lock Assessment", "Download PDF"
#
# 3. IN A MODAL/DIALOG
#    - When user clicks "Export" or "Share"
#    - Offer multiple formats: Excel, PDF, JSON
#
# 4. AS A FLOATING BUTTON
#    - Fixed position button (e.g., bottom-right)
#    - Triggers dropdown menu with export options


# ============================================================================
# API RESPONSE HANDLING
# ============================================================================
#
# Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
# Content-Disposition: attachment; filename="{ProductName}_{Regulation}_v{Version}_{Timestamp}.xlsx"
#
# The response is a binary blob (the Excel file). 
# Always save to disk via download, not display in iframe.


# ============================================================================
# ERROR HANDLING
# ============================================================================
#
# 404 Not Found - Assessment doesn't exist or user doesn't have access
# 401 Unauthorized - User not authenticated
# 500 Server Error - Excel generation failed (check backend logs)
#
# Example error handling:
# 
# try {
#   await exportAsExcel({ assessmentId });
#   showNotification('Excel exported successfully', 'success');
# } catch (error) {
#   if (error.status === 404) {
#     showNotification('Assessment not found', 'error');
#   } else if (error.status === 401) {
#     redirectToLogin();
#   } else {
#     showNotification('Export failed: ' + error.message, 'error');
#   }
# }


# ============================================================================
# UI/UX BEST PRACTICES
# ============================================================================
#
# 1. Show loading state while exporting
#    - Disable button during export
#    - Show spinner or progress bar
#    - Display "Exporting..." text
#
# 2. Provide feedback
#    - Toast notification: "Excel exported successfully"
#    - Log download progress if file is large
#
# 3. Clear instructions
#    - Tooltip: "Download as Excel spreadsheet"
#    - Subtitle: "Complete offline, share with team"
#    - Help text: "Formulas auto-calculate compliance score"
#
# 4. Multiple export options
#    - "With current answers" (faster to review)
#    - "Blank template" (for fresh assessments)
#    - Similar to existing PDF export button
#
# 5. Accessibility
#    - Keyboard-navigable buttons
#    - ARIA labels: aria-label="Export assessment as Excel"
#    - Proper button semantics (not divs)


# ============================================================================
# NEXT STEPS - FUTURE ENHANCEMENTS
# ============================================================================
#
# 1. IMPORT COMPLETED EXCEL
#    - POST /api/assessments/{id}/import-excel (upload file)
#    - Parse Excel and update VerificationAnswers
#    - Validate status values
#    - Return updated assessment with merged answers
#
# 2. BATCH EXPORT
#    - Export multiple assessments as ZIP
#    - Each assessment in separate Excel file
#
# 3. CUSTOM TEMPLATES
#    - Allow users to customize Excel structure
#    - Add custom columns/fields
#    - Save template for reuse
#
# 4. REAL-TIME SYNC
#    - Sync Excel changes back to database
#    - Push notifications when assessor shares the file
#    - Audit trail of offline edits
#
# 5. COMPLIANCE TRACKING
#    - Export compliance history (versions over time)
#    - Compare assessments across products
#    - Generate executive summary
