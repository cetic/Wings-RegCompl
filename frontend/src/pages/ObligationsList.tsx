import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Search, Filter, ChevronDown, ChevronRight, Clock, AlertTriangle, Edit3, Save, X, Trash2, Plus, Info } from 'lucide-react';
import { api } from '../api';
import type { Obligation, Verification } from '../api';
import './ObligationsList.css';

interface GroupedObligations {
  article_id: string;
  article_title: string | null;
  obligations: Obligation[];
}

export default function ObligationsList() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [obligations, setObligations] = useState<Obligation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [expandedArticles, setExpandedArticles] = useState<Set<string>>(new Set());
  const [filterDeadline, setFilterDeadline] = useState(false);
  const [regulation, setRegulation] = useState<string>('CRA');

  // Per-obligation expand/collapse for verifications
  const [expandedObligations, setExpandedObligations] = useState<Set<string>>(new Set());
  const [verificationsCache, setVerificationsCache] = useState<Record<string, Verification[]>>({});
  const [loadingVerifs, setLoadingVerifs] = useState<Set<string>>(new Set());

  // Editing state
  const [editingObligation, setEditingObligation] = useState<string | null>(null);
  const [editOblData, setEditOblData] = useState<{ action: string; trigger: string; deadline: string }>({ action: '', trigger: '', deadline: '' });
  const [editingVerif, setEditingVerif] = useState<string | null>(null);
  const [editVerifData, setEditVerifData] = useState<{ type: string; description: string; evidence: string }>({ type: '', description: '', evidence: '' });
  const [addingVerifFor, setAddingVerifFor] = useState<string | null>(null);
  const [newVerifData, setNewVerifData] = useState<{ type: string; description: string; evidence: string }>({ type: 'review', description: '', evidence: '' });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!id) return;
    api.getAssessment(id).then(a => setRegulation(a.regulation || 'CRA')).catch(() => {});
    api.getObligations(id)
      .then(data => {
        setObligations(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
  }, [id]);

  const loadVerifications = useCallback(async (oblId: string) => {
    if (verificationsCache[oblId]) return;
    setLoadingVerifs(prev => new Set(prev).add(oblId));
    try {
      const verifs = await api.getVerifications(oblId);
      setVerificationsCache(prev => ({ ...prev, [oblId]: verifs }));
    } catch {
      setVerificationsCache(prev => ({ ...prev, [oblId]: [] }));
    } finally {
      setLoadingVerifs(prev => { const n = new Set(prev); n.delete(oblId); return n; });
    }
  }, [verificationsCache]);

  const toggleObligation = (oblId: string) => {
    setExpandedObligations(prev => {
      const next = new Set(prev);
      if (next.has(oblId)) {
        next.delete(oblId);
      } else {
        next.add(oblId);
        loadVerifications(oblId);
      }
      return next;
    });
  };

  // Obligation editing
  const startEditObl = (obl: Obligation) => {
    setEditingObligation(obl.id);
    setEditOblData({ action: obl.action || '', trigger: obl.trigger || '', deadline: obl.deadline || '' });
  };

  const saveObl = async (oblId: string) => {
    setSaving(true);
    try {
      await api.updateObligation(oblId, editOblData);
      setObligations(prev => prev.map(o => o.id === oblId ? { ...o, ...editOblData } : o));
      setEditingObligation(null);
    } catch (e) {
      alert('Failed to save obligation');
    } finally {
      setSaving(false);
    }
  };

  // Verification editing
  const startEditVerif = (v: Verification) => {
    setEditingVerif(v.id);
    setEditVerifData({ type: v.type || '', description: v.description || '', evidence: v.evidence || '' });
  };

  const saveVerif = async (verifId: string, oblId: string) => {
    setSaving(true);
    try {
      await api.updateVerification(verifId, editVerifData);
      setVerificationsCache(prev => ({
        ...prev,
        [oblId]: (prev[oblId] || []).map(v => v.id === verifId ? { ...v, ...editVerifData } : v)
      }));
      setEditingVerif(null);
    } catch {
      alert('Failed to save verification');
    } finally {
      setSaving(false);
    }
  };

  const deleteVerif = async (verifId: string, oblId: string) => {
    if (!confirm('Delete this verification action?')) return;
    try {
      await api.deleteVerification(verifId);
      setVerificationsCache(prev => ({
        ...prev,
        [oblId]: (prev[oblId] || []).filter(v => v.id !== verifId)
      }));
    } catch {
      alert('Failed to delete verification');
    }
  };

  const deleteObl = async (oblId: string) => {
    if (!confirm('Delete this obligation and all its verifications?')) return;
    try {
      await api.deleteObligation(id!, oblId);
      setObligations(prev => prev.filter(o => o.id !== oblId));
      setExpandedObligations(prev => { const n = new Set(prev); n.delete(oblId); return n; });
      setVerificationsCache(prev => { const n = { ...prev }; delete n[oblId]; return n; });
    } catch {
      alert('Failed to delete obligation');
    }
  };

  const addVerif = async (oblId: string) => {
    if (!newVerifData.description.trim()) return;
    setSaving(true);
    try {
      const created = await api.createVerification(oblId, newVerifData);
      setVerificationsCache(prev => ({
        ...prev,
        [oblId]: [...(prev[oblId] || []), created]
      }));
      setAddingVerifFor(null);
      setNewVerifData({ type: 'review', description: '', evidence: '' });
    } catch {
      alert('Failed to create verification');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="loading-state">Loading obligations from knowledge graph...</div>;
  }

  if (error) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-danger)' }}>
        <AlertTriangle size={32} style={{ marginBottom: '1rem' }} />
        <p>{error}</p>
      </div>
    );
  }

  // Filter obligations
  let filtered = obligations;
  if (search) {
    const q = search.toLowerCase();
    filtered = filtered.filter(o =>
      (o.action?.toLowerCase().includes(q)) ||
      (o.id?.toLowerCase().includes(q)) ||
      (o.article_id?.toLowerCase().includes(q)) ||
      (o.paragraph_ref?.toLowerCase().includes(q))
    );
  }
  if (filterDeadline) {
    filtered = filtered.filter(o => o.deadline);
  }

  // Group by article
  const grouped: GroupedObligations[] = [];
  const articleMap = new Map<string, GroupedObligations>();
  for (const obl of filtered) {
    const key = obl.article_id || 'Unknown';
    if (!articleMap.has(key)) {
      const group: GroupedObligations = { article_id: key, article_title: obl.article_title, obligations: [] };
      articleMap.set(key, group);
      grouped.push(group);
    }
    articleMap.get(key)!.obligations.push(obl);
  }

  const toggleArticle = (articleId: string) => {
    setExpandedArticles(prev => {
      const next = new Set(prev);
      if (next.has(articleId)) next.delete(articleId);
      else next.add(articleId);
      return next;
    });
  };

  const expandAll = () => setExpandedArticles(new Set(grouped.map(g => g.article_id)));
  const collapseAll = () => setExpandedArticles(new Set());

  return (
    <div className="obligations-page">
      <div className="breadcrumbs">
        <span style={{ cursor: 'pointer' }} onClick={() => navigate('/')}>Assessments</span>
        <span className="separator">&rsaquo;</span>
        <span style={{ cursor: 'pointer' }} onClick={() => navigate(`/products/${id}/quiz`)}>Verification Quiz</span>
        <span className="separator">&rsaquo;</span>
        <span className="current">Obligations</span>
      </div>

      <div className="page-header obligations-header">
        <div>
          <h1>{regulation} Obligations</h1>
          <p>{obligations.length} obligations mapped to this assessment.</p>
        </div>
        <button className="btn btn-outline" onClick={() => navigate(`/products/${id}/quiz`)}>
          <ArrowLeft size={16} /> Back to Quiz
        </button>
      </div>

      {/* Toolbar */}
      <div className="obligations-toolbar">
        <div className="search-box">
          <Search size={16} className="search-icon" />
          <input
            type="text"
            placeholder="Search obligations..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <button
          className={`btn btn-outline filter-toggle ${filterDeadline ? 'active' : ''}`}
          onClick={() => setFilterDeadline(!filterDeadline)}
        >
          <Clock size={16} /> With Deadlines
        </button>
        <button className="btn btn-outline" onClick={expandAll}>Expand All</button>
        <button className="btn btn-outline" onClick={collapseAll}>Collapse All</button>
      </div>

      {/* Stats bar */}
      <div className="obligations-stats">
        <div className="stat-chip">
          <span className="stat-number">{grouped.length}</span>
          <span className="stat-label">Articles</span>
        </div>
        <div className="stat-chip">
          <span className="stat-number">{filtered.length}</span>
          <span className="stat-label">Obligations</span>
        </div>
        <div className="stat-chip">
          <span className="stat-number">{filtered.filter(o => o.deadline).length}</span>
          <span className="stat-label">With Deadlines</span>
        </div>
        <div className="stat-chip">
          <span className="stat-number">{filtered.filter(o => o.trigger).length}</span>
          <span className="stat-label">With Triggers</span>
        </div>
      </div>

      {/* Grouped obligations */}
      <div className="obligations-groups">
        {grouped.length === 0 ? (
          <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
            No obligations match your search.
          </div>
        ) : (
          grouped.map(group => {
            const isExpanded = expandedArticles.has(group.article_id);
            return (
              <div key={group.article_id} className="card obligation-group">
                <div className="group-header" onClick={() => toggleArticle(group.article_id)}>
                  <div className="group-left">
                    {isExpanded ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
                    <span className="group-article-id">{group.article_id}</span>
                    {group.article_title && (
                      <span className="group-article-title">&mdash; {group.article_title}</span>
                    )}
                  </div>
                  <span className="group-count">{group.obligations.length} obligation{group.obligations.length !== 1 ? 's' : ''}</span>
                </div>

                {isExpanded && (
                  <div className="group-body">
                    {group.obligations.map(obl => {
                      const isOblExpanded = expandedObligations.has(obl.id);
                      const verifs = verificationsCache[obl.id];
                      const isLoadingVerifs = loadingVerifs.has(obl.id);
                      const isEditing = editingObligation === obl.id;

                      return (
                        <div key={obl.id} className={`obligation-item ${isOblExpanded ? 'expanded' : ''}`}>
                          <div className="obligation-row">
                            <button
                              className="obl-expand-btn"
                              onClick={() => toggleObligation(obl.id)}
                              title="Toggle verifications"
                            >
                              {isOblExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                            </button>

                            <div className="obl-id-col">
                              <code className="obl-id">{obl.id}</code>
                              {obl.paragraph_ref && <span className="obl-para">{obl.paragraph_ref}</span>}
                            </div>

                            {isEditing ? (
                              <div className="obl-edit-col">
                                <label className="edit-label">Action</label>
                                <textarea
                                  className="edit-textarea"
                                  value={editOblData.action}
                                  onChange={e => setEditOblData(d => ({ ...d, action: e.target.value }))}
                                  rows={3}
                                />
                                <div className="edit-row">
                                  <div>
                                    <label className="edit-label">Trigger</label>
                                    <input className="edit-input" value={editOblData.trigger} onChange={e => setEditOblData(d => ({ ...d, trigger: e.target.value }))} />
                                  </div>
                                  <div>
                                    <label className="edit-label">Deadline</label>
                                    <input className="edit-input" value={editOblData.deadline} onChange={e => setEditOblData(d => ({ ...d, deadline: e.target.value }))} />
                                  </div>
                                </div>
                                <div className="edit-actions">
                                  <button className="btn btn-sm btn-primary" onClick={() => saveObl(obl.id)} disabled={saving}>
                                    <Save size={14} /> Save
                                  </button>
                                  <button className="btn btn-sm btn-outline" onClick={() => setEditingObligation(null)}>
                                    <X size={14} /> Cancel
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <div className="obl-action-col">
                                <p className="obl-action">{obl.action || 'No action text available'}</p>
                                <div className="obl-tags">
                                  {obl.trigger && (
                                    <span className="tag tag-trigger">
                                      <Filter size={12} /> {obl.trigger}
                                    </span>
                                  )}
                                  {obl.deadline && (
                                    <span className="tag tag-deadline">
                                      <Clock size={12} /> {obl.deadline}
                                    </span>
                                  )}
                                  {obl.justification && (
                                    <span className="tag tag-justification">
                                      <Info size={12} /> {obl.justification}
                                    </span>
                                  )}
                                </div>
                              </div>
                            )}

                            {!isEditing && (
                              <div className="obl-row-actions">
                                <button className="btn-icon" onClick={() => startEditObl(obl)} title="Edit obligation">
                                  <Edit3 size={15} />
                                </button>
                                <button className="btn-icon btn-icon-danger" onClick={() => deleteObl(obl.id)} title="Delete obligation">
                                  <Trash2 size={15} />
                                </button>
                              </div>
                            )}
                          </div>

                          {/* Verifications panel */}
                          {isOblExpanded && (
                            <div className="verifications-panel">
                              <div className="verif-header">
                                <span className="verif-title">Verification Actions</span>
                                <button
                                  className="btn btn-sm btn-outline"
                                  onClick={() => { setAddingVerifFor(obl.id); setNewVerifData({ type: 'review', description: '', evidence: '' }); }}
                                >
                                  <Plus size={14} /> Add
                                </button>
                              </div>

                              {isLoadingVerifs ? (
                                <div className="verif-loading">Loading verifications...</div>
                              ) : !verifs || verifs.length === 0 ? (
                                <div className="verif-empty">No verification actions yet.</div>
                              ) : (
                                <div className="verif-list">
                                  {verifs.map(v => {
                                    const isEditingV = editingVerif === v.id;
                                    return (
                                      <div key={v.id} className="verif-row">
                                        {isEditingV ? (
                                          <div className="verif-edit-form">
                                            <div className="edit-row">
                                              <div>
                                                <label className="edit-label">Type</label>
                                                <select className="edit-input" value={editVerifData.type} onChange={e => setEditVerifData(d => ({ ...d, type: e.target.value }))}>
                                                  <option value="review">Review</option>
                                                  <option value="test">Test</option>
                                                  <option value="inspection">Inspection</option>
                                                  <option value="analysis">Analysis</option>
                                                  <option value="documentation">Documentation</option>
                                                </select>
                                              </div>
                                              <div style={{ flex: 1 }}>
                                                <label className="edit-label">Evidence</label>
                                                <input className="edit-input" value={editVerifData.evidence} onChange={e => setEditVerifData(d => ({ ...d, evidence: e.target.value }))} />
                                              </div>
                                            </div>
                                            <label className="edit-label">Description</label>
                                            <textarea className="edit-textarea" value={editVerifData.description} onChange={e => setEditVerifData(d => ({ ...d, description: e.target.value }))} rows={2} />
                                            <div className="edit-actions">
                                              <button className="btn btn-sm btn-primary" onClick={() => saveVerif(v.id, obl.id)} disabled={saving}>
                                                <Save size={14} /> Save
                                              </button>
                                              <button className="btn btn-sm btn-outline" onClick={() => setEditingVerif(null)}>
                                                <X size={14} /> Cancel
                                              </button>
                                            </div>
                                          </div>
                                        ) : (
                                          <>
                                            <div className="verif-content">
                                              <span className="verif-type-badge">{v.type || 'review'}</span>
                                              <span className="verif-desc">{v.description || '—'}</span>
                                              {v.evidence && <span className="verif-evidence">Evidence: {v.evidence}</span>}
                                            </div>
                                            <div className="verif-actions">
                                              <button className="btn-icon" onClick={() => startEditVerif(v)} title="Edit"><Edit3 size={14} /></button>
                                              <button className="btn-icon btn-icon-danger" onClick={() => deleteVerif(v.id, obl.id)} title="Delete"><Trash2 size={14} /></button>
                                            </div>
                                          </>
                                        )}
                                      </div>
                                    );
                                  })}
                                </div>
                              )}

                              {/* Add verification form */}
                              {addingVerifFor === obl.id && (
                                <div className="verif-add-form">
                                  <div className="edit-row">
                                    <div>
                                      <label className="edit-label">Type</label>
                                      <select className="edit-input" value={newVerifData.type} onChange={e => setNewVerifData(d => ({ ...d, type: e.target.value }))}>
                                        <option value="review">Review</option>
                                        <option value="test">Test</option>
                                        <option value="inspection">Inspection</option>
                                        <option value="analysis">Analysis</option>
                                        <option value="documentation">Documentation</option>
                                      </select>
                                    </div>
                                    <div style={{ flex: 1 }}>
                                      <label className="edit-label">Evidence</label>
                                      <input className="edit-input" value={newVerifData.evidence} onChange={e => setNewVerifData(d => ({ ...d, evidence: e.target.value }))} placeholder="Expected evidence..." />
                                    </div>
                                  </div>
                                  <label className="edit-label">Description</label>
                                  <textarea className="edit-textarea" value={newVerifData.description} onChange={e => setNewVerifData(d => ({ ...d, description: e.target.value }))} rows={2} placeholder="Describe the verification action..." />
                                  <div className="edit-actions">
                                    <button className="btn btn-sm btn-primary" onClick={() => addVerif(obl.id)} disabled={saving || !newVerifData.description.trim()}>
                                      <Plus size={14} /> Create
                                    </button>
                                    <button className="btn btn-sm btn-outline" onClick={() => setAddingVerifFor(null)}>
                                      <X size={14} /> Cancel
                                    </button>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
