import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Save, ArrowRight, Paperclip, AlertCircle, CheckCircle2, ScrollText } from 'lucide-react';
import { api } from '../api';
import type { Question, Answer } from '../api';
import './AssessmentQuiz.css';

export default function AssessmentQuiz() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [_initialPage, setInitialPage] = useState<number | null>(null);
  const [regulation, setRegulation] = useState<string>('CRA');
  
  const [currentPage, setCurrentPage] = useState(1);
  const qsPerPage = 10;

  const questionByVerificationId = questions.reduce<Record<string, Question>>((acc, q) => {
    acc[q.verification_id] = q;
    return acc;
  }, {});

  useEffect(() => {
    if (!id) return;
    
    Promise.all([
      api.getQuestions(id),
      api.getAnswers(id),
      api.getAssessment(id)
    ])
    .then(([qData, aData, assessment]) => {
      setQuestions(qData);
      setRegulation(assessment.regulation || 'CRA');
      
      const aMap: Record<string, Answer> = {};
      aData.forEach(ans => {
        aMap[ans.verification_id] = ans;
      });
      setAnswers(aMap);
      const savedPage = assessment.quiz_page || 1;
      const maxPage = Math.max(1, Math.ceil(qData.length / qsPerPage));
      const validPage = Math.min(savedPage, maxPage);
      setCurrentPage(validPage);
      setInitialPage(validPage);
      setLoading(false);
    })
    .catch(console.error);
  }, [id]);

  const handleAnswerSelect = (vId: string, status: string) => {
    const q = questionByVerificationId[vId];
    setAnswers(prev => ({
      ...prev,
      [vId]: {
        ...(prev[vId] || { evidence: '', notes: '' }),
        verification_id: vId,
        verification_text: q?.verification_text || prev[vId]?.verification_text || '',
        associated_obligations: q?.associated_obligations || prev[vId]?.associated_obligations || [],
        status
      }
    }));
  };

  const handleSave = async (redirect: boolean) => {
    if (!id) return;
    setSaving(true);
    try {
      const updateData = Object.values(answers).map((ans) => {
        const q = questionByVerificationId[ans.verification_id];
        return {
          ...ans,
          verification_text: q?.verification_text || ans.verification_text || '',
          associated_obligations: q?.associated_obligations || ans.associated_obligations || [],
        };
      });
      await api.saveAnswers(id, updateData);
      // Save quiz page separately – don't let failure block the redirect
      api.updateAssessment(id, { quiz_page: currentPage }).catch(() => {});
      if (redirect) {
        navigate(`/products/${id}/results`);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="loading-state">Loading specific Assessment Quiz from Knowledge Graph...</div>;
  }

  const completedCount = Object.values(answers).filter(a => a.status).length;
  const totalCount = questions.length;
  const progressPercent = totalCount === 0 ? 0 : Math.round((completedCount / totalCount) * 100);

  const totalPages = Math.max(1, Math.ceil(totalCount / qsPerPage));
  const currentQuestions = questions.slice((currentPage - 1) * qsPerPage, currentPage * qsPerPage);
  
  const pageCompletedCount = currentQuestions.filter(q => answers[q.verification_id]?.status).length;
  const remainingOnPage = Math.max(0, currentQuestions.length - pageCompletedCount);

  return (
    <div className="assessment-quiz">
      <div className="breadcrumbs">
        <span>Assessments</span>
        <span className="separator">›</span>
        <span className="current">{regulation === 'Part-IS' ? 'Part-IS Verification' : 'EU CRA Verification'}</span>
      </div>

      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <p>Verify technical controls across institutional environments to ensure compliance with the {regulation === 'Part-IS' ? 'Part-IS (EU 2023/203)' : 'Cyber Resilience Act'} frameworks.</p>
        </div>
        <button className="btn btn-outline" onClick={() => navigate(`/products/${id}/obligations`)} style={{ whiteSpace: 'nowrap' }}>
          <ScrollText size={16} /> View Obligations
        </button>
      </div>

      <div className="card progress-panel">
        <div className="progress-left">
          <h4>ASSESSMENT COMPLETION</h4>
          <div className="progress-bar-container">
            <div className="progress-bar-bg"></div>
            <div className="progress-bar-fill blue" style={{ width: `${progressPercent}%` }}></div>
          </div>
          <div className="progress-stats">
            <span>{completedCount} of {totalCount} Questions Completed</span>
            <span className="percent-text">{progressPercent}% Overall Progress</span>
          </div>
        </div>
        <div className="progress-right">
          <span className="remaining-number">{remainingOnPage.toString().padStart(2, '0')}</span>
          <span className="remaining-label">REMAINING ON PAGE</span>
          <CheckCircle2 className="completion-icon" size={24} />
        </div>
      </div>

      <div className="questions-list">
        {currentQuestions.map((q) => {
          const ans = answers[q.verification_id];
          const isYes = ans?.status === 'Verified';
          const isNo = ans?.status === 'Not Compliant';
          
          let cardClass = 'question-card';
          if (isYes) cardClass += ' verified';
          else if (isNo) cardClass += ' failed';

          return (
            <div key={q.verification_id} className={`card ${cardClass}`}>
              <div className="q-content">
                <h3>{q.verification_type}: {q.verification_text}</h3>
                <p>Mapped to {q.associated_obligations.length} obligation(s).</p>
                {isNo && (
                  <div className="alert-box">
                    <AlertCircle size={16} />
                    <span>Requires immediate documentation or remediation.</span>
                  </div>
                )}
              </div>
              <div className="q-actions">
                <div className="pill-toggle">
                  <button 
                    className={`toggle-btn ${isYes ? 'active-yes' : ''}`}
                    onClick={() => handleAnswerSelect(q.verification_id, 'Verified')}
                  >
                    {isYes && <CheckCircle2 size={16} />} Yes
                  </button>
                  <button 
                    className={`toggle-btn ${isNo ? 'active-no' : ''}`}
                    onClick={() => handleAnswerSelect(q.verification_id, 'Not Compliant')}
                  >
                    {isNo && <AlertCircle size={16} />} No
                  </button>
                </div>
                
                <div style={{ position: 'relative', overflow: 'hidden' }}>
                  <input 
                    type="file" 
                    title="Upload evidence file"
                    style={{ position: 'absolute', opacity: 0, right: 0, top: 0, minWidth: '100%', minHeight: '100%', cursor: 'pointer' }}
                    onChange={async (e) => {
                      if (e.target.files && e.target.files[0]) {
                        const file = e.target.files[0];
                        
                        // Set it optimistically or show loading state if preferred
                        setAnswers(prev => ({
                          ...prev,
                          [q.verification_id]: {
                            ...(prev[q.verification_id] || { status: '', notes: '' }),
                            verification_id: q.verification_id,
                            evidence: 'Uploading...'
                          }
                        }));

                        try {
                          await api.uploadEvidence(file);
                          const qMeta = questionByVerificationId[q.verification_id];
                          setAnswers(prev => ({
                            ...prev,
                            [q.verification_id]: {
                              ...(prev[q.verification_id] || { status: '', notes: '' }),
                              verification_id: q.verification_id,
                              verification_text: qMeta?.verification_text || prev[q.verification_id]?.verification_text || '',
                              associated_obligations: qMeta?.associated_obligations || prev[q.verification_id]?.associated_obligations || [],
                              evidence: file.name
                            }
                          }));
                        } catch (err) {
                          console.error("Upload failed", err);
                          const qMeta = questionByVerificationId[q.verification_id];
                          setAnswers(prev => ({
                            ...prev,
                            [q.verification_id]: {
                              ...(prev[q.verification_id] || { status: '', notes: '' }),
                              verification_id: q.verification_id,
                              verification_text: qMeta?.verification_text || prev[q.verification_id]?.verification_text || '',
                              associated_obligations: qMeta?.associated_obligations || prev[q.verification_id]?.associated_obligations || [],
                              evidence: 'Upload Failed'
                            }
                          }));
                        }
                      }
                    }}
                  />
                  <button className="btn btn-outline evidence-btn" style={{ pointerEvents: 'none' }}>
                    <Paperclip size={16} />
                    {ans?.evidence ? (
                      <span style={{ maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {ans.evidence}
                      </span>
                    ) : 'Attach Evidence'}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {totalPages > 1 && (
        <div className="pagination-controls">
          <button 
            className="btn btn-outline" 
            disabled={currentPage === 1} 
            onClick={() => {
              setCurrentPage(p => p - 1);
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
          >
            Previous
          </button>
          <span className="page-indicator">Page {currentPage} of {totalPages}</span>
          <button 
            className="btn btn-outline" 
            disabled={currentPage === totalPages} 
            onClick={() => {
              setCurrentPage(p => p + 1);
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
          >
            Next
          </button>
        </div>
      )}

      <div className="sticky-footer">
        <div className="footer-progress">
          <span className="f-label">ASSESSMENT PROGRESS</span>
          <div className="f-bar">
             <div className="f-fill" style={{ width: `${progressPercent}%` }}></div>
          </div>
          <span className="f-percent">{progressPercent}% Complete</span>
        </div>
        <div className="footer-actions">
          <button className="btn btn-secondary" onClick={() => handleSave(false)} disabled={saving}>
            <Save size={18} />
            {saving ? 'Saving...' : 'Save Progress'}
          </button>
          <button className="btn btn-primary" onClick={() => handleSave(true)} disabled={saving}>
            View Ledger Results
            <ArrowRight size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}
