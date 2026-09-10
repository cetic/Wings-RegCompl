import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { TrendingUp, ArrowLeft, AlertTriangle, ChevronDown, ChevronRight, Download, MessageSquare, Lightbulb, FileSpreadsheet } from 'lucide-react';
import { api } from '../api';
import './AssessmentResults.css';

interface ReportObligation {
  obligation_id: string;
  article: string | null;
  obligation_text: string | null;
  calculated_status: string;
  verifications: { verification_id: string; status: string }[];
}

interface Report {
  assessment_id: string;
  obligations: ReportObligation[];
  summary: {
    total_obligations: number;
    compliant: number;
    partially_compliant: number;
    not_compliant: number;
  };
  comment: string;
  recommendations: string[];
}

export default function AssessmentResults() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [report, setReport] = useState<Report | null>(null);
  const [assessment, setAssessment] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedArticles, setExpandedArticles] = useState<Set<string>>(new Set());
  const [downloading, setDownloading] = useState(false);
  const [downloadingExcel, setDownloadingExcel] = useState(false);

  useEffect(() => {
    if (!id) return;
    Promise.all([
      api.getReport(id),
      api.getAssessments()
    ]).then(([reportData, assessments]) => {
      setReport(reportData);
      const found = assessments.find((a: any) => a.id === id);
      setAssessment(found || null);
      setLoading(false);
    }).catch(err => {
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
    });
  }, [id]);

  if (loading) {
    return <div className="results-loading">Generating Institutional Compliance Report...</div>;
  }

  if (error || !report) {
    return (
      <div className="results-error">
        <AlertTriangle size={32} />
        <p>{error || 'Failed to load report'}</p>
        <button className="btn btn-outline" onClick={() => navigate(`/products/${id}/quiz`)}>
          <ArrowLeft size={16} /> Back to Quiz
        </button>
      </div>
    );
  }

  const { summary, obligations } = report;
  const finalScore = summary.total_obligations === 0
    ? 0
    : Math.round((summary.compliant / summary.total_obligations) * 100);

  const scoreLevel = finalScore >= 80 ? 'gold' : finalScore >= 50 ? 'silver' : 'needs-work';

  // Group obligations by article for category breakdown
  const categories: Record<string, { total: number; compliant: number; partial: number; obligations: ReportObligation[] }> = {};
  obligations.forEach(obl => {
    const cat = obl.article || 'General';
    if (!categories[cat]) categories[cat] = { total: 0, compliant: 0, partial: 0, obligations: [] };
    categories[cat].total += 1;
    categories[cat].obligations.push(obl);
    if (obl.calculated_status === 'Compliant') categories[cat].compliant += 1;
    if (obl.calculated_status === 'Partially Compliant') categories[cat].partial += 1;
  });

  const categoryList = Object.entries(categories)
    .map(([name, data]) => ({
      name,
      percent: data.total === 0 ? 0 : Math.round((data.compliant / data.total) * 100),
      total: data.total,
      compliant: data.compliant,
      partial: data.partial,
      obligations: data.obligations
    }))
    .sort((a, b) => b.total - a.total);

  const toggleArticle = (art: string) => {
    setExpandedArticles(prev => {
      const next = new Set(prev);
      if (next.has(art)) next.delete(art);
      else next.add(art);
      return next;
    });
  };

  const statusColor = (status: string) => {
    if (status === 'Compliant') return 'status-compliant';
    if (status === 'Partially Compliant') return 'status-partial';
    return 'status-noncompliant';
  };

  const handleDownloadPdf = async () => {
    if (!id) return;
    setDownloading(true);
    try {
      const { blob, filename } = await api.downloadAssessmentPdf(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDownloading(false);
    }
  };

  const handleDownloadExcel = async () => {
    if (!id) return;
    setDownloadingExcel(true);
    try {
      const { blob, filename } = await api.downloadAssessmentExcel(id, true);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDownloadingExcel(false);
    }
  };

  return (
    <div className="assessment-results">
      <div className="results-breadcrumbs">
        <span onClick={() => navigate('/')}>Assessments</span>
        <span className="sep">&rsaquo;</span>
        <span onClick={() => navigate(`/products/${id}/quiz`)}>{assessment?.product_name || 'Assessment'}</span>
        <span className="sep">&rsaquo;</span>
        <span className="current">Results Report</span>
      </div>

      <div className="results-page-header">
        <div>
          <h1>Assessment Results</h1>
          <p className="results-subtitle">
            A comprehensive analysis of institutional compliance across primary operational vectors based on the {assessment?.regulation === 'Part-IS' ? 'Part-IS (EU 2023/203)' : 'EU Cyber Resilience Act'}.
          </p>
        </div>
        <div className="results-header-actions">
          <button className="btn btn-outline" onClick={() => navigate(`/products/${id}/quiz`)}>
            <ArrowLeft size={16} /> Back to Quiz
          </button>
          <button
            className="btn btn-outline"
            onClick={handleDownloadExcel}
            disabled={downloadingExcel}
            title="Export quiz initialization and assessor answers with compliance formulas"
          >
            <FileSpreadsheet size={16} /> {downloadingExcel ? 'Exporting Excel...' : 'Export Excel'}
          </button>
          <button
            className="btn btn-primary"
            onClick={handleDownloadPdf}
            disabled={downloading}
          >
            <Download size={16} /> {downloading ? 'Generating PDF...' : 'Download PDF'}
          </button>
        </div>
      </div>

      {/* ── Score + Distribution Row ── */}
      <div className="results-grid top-row">
        <div className="card final-score-card">
          <div className="score-header">
            <span className="score-title">FINAL COMPLIANCE</span>
            {scoreLevel === 'gold' && <span className="score-badge gold">GOLD STANDARD</span>}
            {scoreLevel === 'silver' && <span className="score-badge silver">PASSING</span>}
            {scoreLevel === 'needs-work' && <span className="score-badge needs-work">NEEDS WORK</span>}
          </div>
          <div className="score-main">
            <span className="score-big">{finalScore}</span>
            <span className="score-symbol">%</span>
          </div>
          <div className="score-trend">
            <TrendingUp size={16} />
            <span className="trend-value">+{Math.max(0, finalScore - 50).toFixed(1)}%</span>
            <span className="trend-label">vs. baseline</span>
          </div>
          <div className="score-summary-row">
            <div className="summary-item">
              <span className="summary-val">{summary.compliant}</span>
              <span className="summary-lbl">Compliant</span>
            </div>
            <div className="summary-item">
              <span className="summary-val partial">{summary.partially_compliant}</span>
              <span className="summary-lbl">Partial</span>
            </div>
            <div className="summary-item">
              <span className="summary-val danger">{summary.not_compliant}</span>
              <span className="summary-lbl">Gaps</span>
            </div>
          </div>
        </div>

        <div className="card summary-chart-card">
          <div className="chart-header">
            <div>
              <h3>Compliance Distribution</h3>
              <p className="chart-subtitle">
                Status distribution across {summary.total_obligations} total obligations for {assessment?.product_name || 'this assessment'}.
              </p>
            </div>
          </div>
          <div className="distribution-bars">
            <div className="dist-bar-item">
              <div className="dist-bar-label">
                <span className="dist-dot compliant"></span>
                <span className="dist-name">Compliant</span>
                <span className="dist-count">{summary.compliant}</span>
              </div>
              <div className="dist-bar-track">
                <div
                  className="dist-bar-fill compliant"
                  style={{ width: `${summary.total_obligations ? (summary.compliant / summary.total_obligations) * 100 : 0}%` }}
                ></div>
              </div>
            </div>
            <div className="dist-bar-item">
              <div className="dist-bar-label">
                <span className="dist-dot partial"></span>
                <span className="dist-name">Partially Compliant</span>
                <span className="dist-count">{summary.partially_compliant}</span>
              </div>
              <div className="dist-bar-track">
                <div
                  className="dist-bar-fill partial"
                  style={{ width: `${summary.total_obligations ? (summary.partially_compliant / summary.total_obligations) * 100 : 0}%` }}
                ></div>
              </div>
            </div>
            <div className="dist-bar-item">
              <div className="dist-bar-label">
                <span className="dist-dot gap"></span>
                <span className="dist-name">Not Compliant</span>
                <span className="dist-count">{summary.not_compliant}</span>
              </div>
              <div className="dist-bar-track">
                <div
                  className="dist-bar-fill gap"
                  style={{ width: `${summary.total_obligations ? (summary.not_compliant / summary.total_obligations) * 100 : 0}%` }}
                ></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Comment & Recommendations Row ── */}
      {(report.comment || report.recommendations?.length > 0) && (
        <div className="results-grid commentary-row">
          {report.comment && (
            <div className="card commentary-card">
              <div className="commentary-header">
                <MessageSquare size={20} />
                <h3>Overall Assessment</h3>
              </div>
              <div className="commentary-body">
                {report.comment.split('\n\n').map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
              </div>
            </div>
          )}

          {report.recommendations?.length > 0 && (
            <div className="card recommendations-card">
              <div className="commentary-header">
                <Lightbulb size={20} />
                <h3>Recommendations</h3>
              </div>
              <ol className="recommendations-list">
                {report.recommendations.map((rec, i) => (
                  <li key={i}>{rec}</li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}

      {/* ── Detailed Obligation Ledger ── */}
      <div className="card obligation-ledger">
        <div className="ledger-header">
          <h3>Full Obligation Ledger</h3>
          <span className="ledger-count">{obligations.length} obligations across {categoryList.length} articles</span>
        </div>

        <div className="ledger-groups">
          {categoryList.map(cat => {
            const isExpanded = expandedArticles.has(cat.name);
            return (
              <div key={cat.name} className="ledger-group">
                <div className="ledger-group-header" onClick={() => toggleArticle(cat.name)}>
                  <div className="ledger-group-left">
                    {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                    <span className="ledger-article">Article {cat.name}</span>
                    <span className="ledger-group-score">{cat.percent}%</span>
                  </div>
                  <div className="ledger-group-right">
                    <span className="ledger-group-stat compliant">{cat.compliant} compliant</span>
                    {cat.partial > 0 && <span className="ledger-group-stat partial">{cat.partial} partial</span>}
                    {(cat.total - cat.compliant - cat.partial) > 0 && (
                      <span className="ledger-group-stat gap">{cat.total - cat.compliant - cat.partial} gaps</span>
                    )}
                  </div>
                </div>

                {isExpanded && (
                  <div className="ledger-group-body">
                    <div className="ledger-table-header">
                      <span className="lt-col-id">Obligation ID</span>
                      <span className="lt-col-text">Description</span>
                      <span className="lt-col-verifs">Verifications</span>
                      <span className="lt-col-status">Status</span>
                    </div>
                    {cat.obligations.map(obl => {
                      const verified = obl.verifications.filter(v => v.status === 'Verified').length;
                      return (
                        <div key={obl.obligation_id} className="ledger-row">
                          <span className="lt-col-id">
                            <code>{obl.obligation_id}</code>
                          </span>
                          <span className="lt-col-text">
                            {obl.obligation_text
                              ? (obl.obligation_text.length > 120
                                  ? obl.obligation_text.substring(0, 120) + '...'
                                  : obl.obligation_text)
                              : '—'}
                          </span>
                          <span className="lt-col-verifs">
                            <span className="verif-ratio">{verified}/{obl.verifications.length}</span>
                          </span>
                          <span className={`lt-col-status ${statusColor(obl.calculated_status)}`}>
                            {obl.calculated_status}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

    </div>
  );
}
