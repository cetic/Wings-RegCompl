import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, PlusCircle, Layers, ClipboardList, Lock,
  ChevronRight, Edit3, Save, X, Box, Trash2, FileText,
  Database, Download, BarChart3, CheckCircle2, AlertTriangle, Clock,
  MessageSquare, Send, RefreshCw, Brain, Users, UserPlus,
} from 'lucide-react';
import {
  api,
  type ProductDetail,
  type AssessmentResponse,
  type ProductVersion,
  type ProductEvidenceItem,
  type ProductComment,
  type ProductRule,
  type ProductShare,
} from '../api';
import './ProductDetailPage.css';

type Tab = 'versions' | 'evidence' | 'reports' | 'comments';

export default function ProductDetailPage() {
  const { productId } = useParams<{ productId: string }>();
  const navigate = useNavigate();
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [assessments, setAssessments] = useState<AssessmentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<Tab>('versions');
  const [shareOpen, setShareOpen] = useState(false);

  const role = product?.role ?? 'owner';
  const canManage = role === 'owner' || role === 'admin';

  const reload = async () => {
    if (!productId) return;
    try {
      const [p, ass] = await Promise.all([
        api.getProduct(productId),
        api.listProductAssessments(productId),
      ]);
      setProduct(p);
      setNameDraft(p.name);
      setAssessments(ass);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { reload(); }, [productId]);

  const handleRename = async () => {
    if (!productId || !nameDraft.trim() || nameDraft === product?.name) {
      setEditingName(false);
      return;
    }
    setSaving(true);
    setError('');
    try {
      await api.renameProduct(productId, nameDraft.trim());
      await reload();
      setEditingName(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteAssessment = async (a: AssessmentResponse) => {
    if (!window.confirm(`Delete this ${a.regulation} assessment (V${a.version_number})?`)) return;
    try {
      await api.deleteAssessment(a.id);
      setAssessments(prev => prev.filter(x => x.id !== a.id));
    } catch (e) {
      console.error(e);
    }
  };

  if (loading) return <div className="pdp-loading">Loading product…</div>;
  if (!product) return <div className="pdp-loading">Product not found.</div>;

  return (
    <div className="pdp-page">
      <div className="pdp-breadcrumbs">
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/')}>
          <ArrowLeft size={16} /> Products
        </button>
      </div>

      <div className="pdp-header card">
        <div className="pdp-header-left">
          <div className="pdp-icon"><Box size={28} /></div>
          <div className="pdp-title-block">
            {editingName ? (
              <div className="pdp-name-edit">
                <input
                  className="pdp-name-input"
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  disabled={saving}
                  autoFocus
                />
                <button className="btn btn-primary btn-sm" onClick={handleRename} disabled={saving}>
                  <Save size={14} /> Save
                </button>
                <button
                  className="btn btn-outline btn-sm"
                  onClick={() => { setEditingName(false); setNameDraft(product.name); setError(''); }}
                  disabled={saving}
                >
                  <X size={14} /> Cancel
                </button>
              </div>
            ) : (
              <>
                <h1 className="pdp-name">{product.name}</h1>
                {canManage && (
                  <button className="btn-link pdp-edit" onClick={() => setEditingName(true)}>
                    <Edit3 size={13} /> Rename
                  </button>
                )}
                {role === 'collaborator' && (
                  <span className="pdp-role-badge" title={`Shared by ${product.owner_username || 'owner'}`}>
                    Shared with you
                  </span>
                )}
              </>
            )}
            <p className="pdp-meta">
              <Layers size={14} /> {product.versions.length} version{product.versions.length !== 1 ? 's' : ''}
              <span className="pdp-meta-sep">·</span>
              <ClipboardList size={14} /> {assessments.length} assessment{assessments.length !== 1 ? 's' : ''}
              <span className="pdp-meta-sep">·</span>
              Created {product.created_at ? new Date(product.created_at).toLocaleDateString() : '—'}
            </p>
            {error && <div className="pdp-error">{error}</div>}
          </div>
        </div>
        <div className="pdp-header-actions">
          {canManage && (
            <button
              className="btn btn-outline"
              onClick={() => setShareOpen(true)}
              title="Manage collaborators"
            >
              <Users size={16} /> Share
            </button>
          )}
          <button
            className="btn btn-primary"
            onClick={() => navigate(`/products/${product.id}/assessments/new`)}
          >
            <PlusCircle size={16} /> New Assessment
          </button>
        </div>
      </div>

      {shareOpen && (
        <ShareModal
          productId={product.id}
          productName={product.name}
          ownerUsername={product.owner_username || ''}
          onClose={() => setShareOpen(false)}
        />
      )}

      <div className="pdp-tabs">
        <button
          className={`pdp-tab ${activeTab === 'versions' ? 'active' : ''}`}
          onClick={() => setActiveTab('versions')}
        >
          <Layers size={15} /> Versions & Assessments
        </button>
        <button
          className={`pdp-tab ${activeTab === 'evidence' ? 'active' : ''}`}
          onClick={() => setActiveTab('evidence')}
        >
          <Database size={15} /> Evidence
        </button>
        <button
          className={`pdp-tab ${activeTab === 'reports' ? 'active' : ''}`}
          onClick={() => setActiveTab('reports')}
        >
          <BarChart3 size={15} /> Reports
        </button>
        <button
          className={`pdp-tab ${activeTab === 'comments' ? 'active' : ''}`}
          onClick={() => setActiveTab('comments')}
        >
          <MessageSquare size={15} /> Comments
        </button>
      </div>

      {activeTab === 'versions' && (
        <VersionsTab
          product={product}
          assessments={assessments}
          onChanged={reload}
          onDeleteAssessment={handleDeleteAssessment}
          onOpenAssessment={(a) => navigate(`/assessments/${a.id}/info`)}
        />
      )}
      {activeTab === 'evidence' && <EvidenceTab productId={product.id} />}
      {activeTab === 'reports' && <ReportsTab assessments={assessments} />}
      {activeTab === 'comments' && <CommentsTab productId={product.id} />}
    </div>
  );
}

// ── Versions tab ────────────────────────────────────────────────────
function VersionsTab({
  product,
  assessments,
  onChanged,
  onDeleteAssessment,
  onOpenAssessment,
}: {
  product: ProductDetail;
  assessments: AssessmentResponse[];
  onChanged: () => void;
  onDeleteAssessment: (a: AssessmentResponse) => void;
  onOpenAssessment: (a: AssessmentResponse) => void;
}) {
  const assessmentsByVersion = useMemo(() => {
    const m = new Map<string, AssessmentResponse[]>();
    for (const a of assessments) {
      const list = m.get(a.product_version_id) || [];
      list.push(a);
      m.set(a.product_version_id, list);
    }
    return m;
  }, [assessments]);

  return (
    <div className="pdp-versions">
      {[...product.versions].reverse().map(v => (
        <VersionCard
          key={v.id}
          version={v}
          product={product}
          versionAssessments={assessmentsByVersion.get(v.id) || []}
          onChanged={onChanged}
          onDeleteAssessment={onDeleteAssessment}
          onOpenAssessment={onOpenAssessment}
        />
      ))}
    </div>
  );
}

function VersionCard({
  version,
  product,
  versionAssessments,
  onChanged,
  onDeleteAssessment,
  onOpenAssessment,
}: {
  version: ProductVersion;
  product: ProductDetail;
  versionAssessments: AssessmentResponse[];
  onChanged: () => void;
  onDeleteAssessment: (a: AssessmentResponse) => void;
  onOpenAssessment: (a: AssessmentResponse) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draftDesc, setDraftDesc] = useState(version.description);
  const [draftFeatures, setDraftFeatures] = useState(version.key_features.join('\n'));
  const [draftRoles, setDraftRoles] = useState(version.actor_roles.join(', '));
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const canEdit = !version.has_locked_assessment;
  const canDelete = !version.has_locked_assessment && product.versions.length > 1;

  const handleSave = async () => {
    setSaving(true);
    setErr('');
    try {
      await api.updateProductVersion(product.id, version.id, {
        description: draftDesc,
        key_features: draftFeatures.split('\n').map(s => s.trim()).filter(Boolean),
        actor_roles: draftRoles.split(',').map(s => s.trim()).filter(Boolean),
      });
      setEditing(false);
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Delete V${version.version_number} and all its assessments?`)) return;
    try {
      await api.deleteProductVersion(product.id, version.id);
      onChanged();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="card pdp-version">
      <div className="pdp-version-header">
        <div className="pdp-version-title">
          <span className="pdp-version-tag">V{version.version_number}</span>
          <span className="pdp-version-date">
            {version.created_at ? new Date(version.created_at).toLocaleString() : ''}
          </span>
          {version.has_locked_assessment && (
            <span className="pdp-version-lock"><Lock size={12} /> frozen</span>
          )}
        </div>
        <div className="pdp-version-actions">
          {version.technical_file_name && (
            <span className="pdp-version-file">
              <FileText size={13} /> {version.technical_file_name}
            </span>
          )}
          {!editing && canEdit && (
            <button className="btn btn-ghost btn-sm" onClick={() => setEditing(true)} title="Edit version">
              <Edit3 size={14} />
            </button>
          )}
          {canDelete && !editing && (
            <button
              className="btn btn-ghost btn-sm pdp-version-delete"
              onClick={handleDelete}
              title="Delete version"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {editing ? (
        <div className="pdp-version-edit">
          <label className="pdp-edit-label">Description</label>
          <textarea
            className="pdp-edit-textarea"
            rows={5}
            value={draftDesc}
            onChange={(e) => setDraftDesc(e.target.value)}
            disabled={saving}
          />
          <label className="pdp-edit-label">Key features (one per line)</label>
          <textarea
            className="pdp-edit-textarea"
            rows={3}
            value={draftFeatures}
            onChange={(e) => setDraftFeatures(e.target.value)}
            disabled={saving}
          />
          <label className="pdp-edit-label">Actor roles (comma-separated)</label>
          <input
            className="pdp-edit-input"
            value={draftRoles}
            onChange={(e) => setDraftRoles(e.target.value)}
            disabled={saving}
          />
          {err && <div className="pdp-error">{err}</div>}
          <div className="pdp-edit-actions">
            <button
              className="btn btn-outline btn-sm"
              onClick={() => {
                setEditing(false);
                setDraftDesc(version.description);
                setDraftFeatures(version.key_features.join('\n'));
                setDraftRoles(version.actor_roles.join(', '));
                setErr('');
              }}
              disabled={saving}
            >
              <X size={14} /> Cancel
            </button>
            <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
              <Save size={14} /> {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      ) : (
        <p className="pdp-version-desc">
          {version.description.length > 280
            ? version.description.slice(0, 280) + '…'
            : version.description}
        </p>
      )}

      {versionAssessments.length > 0 ? (
        <ul className="pdp-assessments-list">
          {versionAssessments.map(a => (
            <li key={a.id} className="pdp-assessment-row" onClick={() => onOpenAssessment(a)}>
              <div className="pdp-assessment-info">
                <span className={`pdp-reg-badge pdp-reg-${a.regulation === 'Part-IS' ? 'partis' : 'cra'}`}>
                  {a.regulation}
                </span>
                <span className="pdp-assessment-status">
                  {a.locked
                    ? <><Lock size={12} /> Locked · {a.obligation_ids.length} obligations</>
                    : 'Draft — not yet locked'}
                </span>
                {a.created_at && (
                  <span className="pdp-assessment-date">
                    {new Date(a.created_at).toLocaleDateString()}
                  </span>
                )}
              </div>
              <ProgressMini value={a.progress_percent ?? 0} />
              <div className="pdp-assessment-actions">
                <button
                  className="btn btn-ghost btn-sm pdp-assessment-delete"
                  title="Delete assessment"
                  onClick={(e) => { e.stopPropagation(); onDeleteAssessment(a); }}
                >
                  <Trash2 size={14} />
                </button>
                <ChevronRight size={16} />
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="pdp-no-assessments">No assessment on this version yet.</p>
      )}
    </div>
  );
}

function ProgressMini({ value }: { value: number }) {
  const color = value >= 100 ? 'var(--color-success, #16a34a)' : value > 0 ? '#ea580c' : 'var(--color-text-muted, #888)';
  const Icon = value >= 100 ? CheckCircle2 : value > 0 ? Clock : AlertTriangle;
  return (
    <div className="pdp-progress-mini" title={`${value}% complete`}>
      <div className="pdp-progress-bar">
        <div className="pdp-progress-fill" style={{ width: `${value}%`, background: color }} />
      </div>
      <span className="pdp-progress-label" style={{ color }}>
        <Icon size={12} /> {value}%
      </span>
    </div>
  );
}

// ── Evidence tab ────────────────────────────────────────────────────
function EvidenceTab({ productId }: { productId: string }) {
  const [items, setItems] = useState<ProductEvidenceItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getProductEvidence(productId)
      .then(setItems)
      .finally(() => setLoading(false));
  }, [productId]);

  if (loading) return <div className="pdp-tab-loading">Loading evidence…</div>;
  if (items.length === 0) {
    return (
      <div className="pdp-empty">
        <Database size={28} />
        <p>No evidence attached to this product's assessments yet.</p>
      </div>
    );
  }

  return (
    <div className="pdp-evidence-list">
      {items.map((e, i) => (
        <div key={`${e.assessment_id}-${e.verification_id}-${i}`} className="card pdp-evidence-card">
          <div className="pdp-evidence-head">
            <span className={`pdp-reg-badge pdp-reg-${e.regulation === 'Part-IS' ? 'partis' : 'cra'}`}>
              {e.regulation || '—'}
            </span>
            <span className="pdp-version-tag">V{e.version_number}</span>
            <span className={`pdp-evidence-status pdp-status-${(e.status || '').toLowerCase().replace(/\s+/g, '-')}`}>
              {e.status || 'Pending'}
            </span>
          </div>
          <p className="pdp-evidence-verif">{e.verification_text}</p>
          <p className="pdp-evidence-payload">{e.evidence}</p>
          {e.notes && <p className="pdp-evidence-notes">{e.notes}</p>}
        </div>
      ))}
    </div>
  );
}

// ── Reports tab ─────────────────────────────────────────────────────
function ReportsTab({ assessments }: { assessments: AssessmentResponse[] }) {
  const navigate = useNavigate();
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const triggerBlobDownload = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleDownloadPdf = async (assessmentId: string) => {
    setDownloadingId(`pdf:${assessmentId}`);
    try {
      const { blob, filename } = await api.downloadAssessmentPdf(assessmentId);
      triggerBlobDownload(blob, filename);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDownloadExcel = async (assessmentId: string) => {
    setDownloadingId(`excel:${assessmentId}`);
    try {
      const { blob, filename } = await api.downloadAssessmentExcel(assessmentId, true);
      triggerBlobDownload(blob, filename);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    } finally {
      setDownloadingId(null);
    }
  };

  if (assessments.length === 0) {
    return (
      <div className="pdp-empty">
        <BarChart3 size={28} />
        <p>No assessments yet — reports will appear here once you create one.</p>
      </div>
    );
  }
  return (
    <div className="pdp-reports-list">
      {assessments.map(a => (
        <div key={a.id} className="card pdp-report-card">
          <div className="pdp-report-head">
            <div>
              <span className={`pdp-reg-badge pdp-reg-${a.regulation === 'Part-IS' ? 'partis' : 'cra'}`}>
                {a.regulation}
              </span>
              <span className="pdp-version-tag" style={{ marginLeft: 6 }}>V{a.version_number}</span>
              {a.locked
                ? <span className="pdp-version-lock" style={{ marginLeft: 6 }}><Lock size={11} /> locked</span>
                : <span className="pdp-report-draft" style={{ marginLeft: 6 }}>draft</span>}
            </div>
            <span className="pdp-assessment-date">
              {a.created_at ? new Date(a.created_at).toLocaleDateString() : ''}
            </span>
          </div>
          <ProgressMini value={a.progress_percent ?? 0} />
          <div className="pdp-report-actions">
            <button
              className="btn btn-outline btn-sm"
              onClick={() => navigate(`/assessments/${a.id}/results`)}
              disabled={!a.locked}
            >
              <BarChart3 size={14} /> View report
            </button>
            <button
              className="btn btn-outline btn-sm"
              onClick={() => handleDownloadExcel(a.id)}
              disabled={downloadingId !== null}
            >
              <Download size={14} />
              {downloadingId === `excel:${a.id}` ? ' Exporting Excel...' : ' Export Excel'}
            </button>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => handleDownloadPdf(a.id)}
              disabled={!a.locked || downloadingId !== null}
            >
              <Download size={14} />
              {downloadingId === `pdf:${a.id}` ? ' Downloading PDF...' : ' Download PDF'}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Comments tab (raw notes + distilled reflection rules) ───────────
function CommentsTab({ productId }: { productId: string }) {
  const [comments, setComments] = useState<ProductComment[] | null>(null);
  const [rules, setRules] = useState<ProductRule[] | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [reflecting, setReflecting] = useState(false);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState('');

  const load = async () => {
    try {
      const [cs, rs] = await Promise.all([
        api.listProductComments(productId),
        api.listProductRules(productId),
      ]);
      setComments(cs);
      setRules(rs);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setComments([]);
      setRules([]);
    }
  };

  useEffect(() => { load(); }, [productId]);

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    setError('');
    setFlash('');
    try {
      const result = await api.createProductComment(productId, text);
      setRules(result.rules);
      await api.listProductComments(productId).then(setComments).catch(() => {});
      setDraft('');
      if (result.added.length === 0) {
        setFlash('Note saved — no new rule distilled (already covered or out of scope).');
      } else {
        setFlash(`Note saved — ${result.added.length} new rule${result.added.length === 1 ? '' : 's'} added to product memory.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (c: ProductComment) => {
    if (!window.confirm('Delete this note? The distilled rules it produced will be kept (delete them individually if needed).')) return;
    try {
      await api.deleteProductComment(productId, c.id);
      setComments((prev) => (prev || []).filter((x) => x.id !== c.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const removeRule = async (r: ProductRule) => {
    if (!window.confirm('Delete this rule from product memory? Future assessments will no longer apply it.')) return;
    try {
      await api.deleteProductRule(productId, r.id);
      setRules((prev) => (prev || []).filter((x) => x.id !== r.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const toggleRule = async (r: ProductRule) => {
    const next = (r.status || 'active') === 'active' ? 'archived' : 'active';
    try {
      const updated = await api.updateProductRule(productId, r.id, { status: next });
      setRules((prev) => (prev || []).map((x) => (x.id === r.id ? updated : x)));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const saveEdit = async (r: ProductRule) => {
    const text = editText.trim();
    if (!text) return;
    try {
      const updated = await api.updateProductRule(productId, r.id, { text });
      setRules((prev) => (prev || []).map((x) => (x.id === r.id ? updated : x)));
      setEditing(null);
      setEditText('');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const rereflect = async () => {
    if (reflecting) return;
    if (!window.confirm('Re-run reflection over ALL current notes? New rules may be added (existing rules are kept).')) return;
    setReflecting(true);
    setError('');
    setFlash('');
    try {
      const result = await api.reflectProduct(productId);
      setRules(result.rules);
      setFlash(`Reflection complete — ${result.added.length} new rule${result.added.length === 1 ? '' : 's'} added.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setReflecting(false);
    }
  };

  const activeRules = (rules || []).filter((r) => (r.status || 'active') === 'active');
  const archivedRules = (rules || []).filter((r) => (r.status || 'active') !== 'active');

  return (
    <div className="pdp-comments card">
      <div className="pdp-comments-header">
        <h2><MessageSquare size={18} /> Assessor notes &amp; product memory</h2>
        <p className="muted">
          Free-form notes you add below are distilled into <strong>rules</strong> —
          short imperative directives (EXCLUDE / PREFER / LIMIT / …) that
          become the product&apos;s permanent memory. Every future
          classification and obligation-selection call sees these rules, so
          they reliably steer the agent rather than drowning in narrative prose.
        </p>
      </div>

      {error && <div className="pdp-error">{error}</div>}
      {flash && <div className="pdp-flash">{flash}</div>}

      <div className="pdp-rules-section">
        <div className="pdp-rules-header">
          <h3><Brain size={16} /> Active rules ({activeRules.length})</h3>
          <button
            type="button"
            className="btn btn-sm"
            onClick={rereflect}
            disabled={reflecting || !comments || comments.length === 0}
            title="Re-run reflection over all current notes"
          >
            <RefreshCw size={14} className={reflecting ? 'spin' : ''} /> Re-reflect
          </button>
        </div>
        {rules === null && <div className="muted small">Loading…</div>}
        {rules && activeRules.length === 0 && (
          <div className="pdp-rule-empty muted small">
            No rules yet. Add a note below and the agent will distill it.
          </div>
        )}
        {activeRules.map((r) => (
          <div key={r.id} className="pdp-rule-item">
            <span className={`pdp-rule-cat cat-${r.category || 'scope'}`}>{r.category || 'scope'}</span>
            {editing === r.id ? (
              <>
                <input
                  className="pdp-rule-input"
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); saveEdit(r); }
                    if (e.key === 'Escape') { setEditing(null); setEditText(''); }
                  }}
                />
                <button className="btn-icon" onClick={() => saveEdit(r)} title="Save"><Save size={14} /></button>
                <button className="btn-icon" onClick={() => { setEditing(null); setEditText(''); }} title="Cancel"><X size={14} /></button>
              </>
            ) : (
              <>
                <span className="pdp-rule-text">{r.text}</span>
                <button className="btn-icon" onClick={() => { setEditing(r.id); setEditText(r.text); }} title="Edit"><Edit3 size={14} /></button>
                <button className="btn-icon" onClick={() => toggleRule(r)} title="Archive (stop applying)"><Clock size={14} /></button>
                <button className="btn-icon" onClick={() => removeRule(r)} title="Delete rule"><Trash2 size={14} /></button>
              </>
            )}
          </div>
        ))}
        {archivedRules.length > 0 && (
          <details className="pdp-rules-archived">
            <summary className="muted small">{archivedRules.length} archived rule{archivedRules.length === 1 ? '' : 's'}</summary>
            {archivedRules.map((r) => (
              <div key={r.id} className="pdp-rule-item pdp-rule-archived">
                <span className={`pdp-rule-cat cat-${r.category || 'scope'}`}>{r.category || 'scope'}</span>
                <span className="pdp-rule-text muted">{r.text}</span>
                <button className="btn-icon" onClick={() => toggleRule(r)} title="Re-activate"><CheckCircle2 size={14} /></button>
                <button className="btn-icon" onClick={() => removeRule(r)} title="Delete rule"><Trash2 size={14} /></button>
              </div>
            ))}
          </details>
        )}
      </div>

      <form className="pdp-comment-form" onSubmit={submit}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="e.g. This device only ships in the EEA, OTA updates are mandatory, FIPS 140-3 module in use…"
          rows={3}
          disabled={busy}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <div className="pdp-comment-form-actions">
          <span className="muted small">Cmd/Ctrl+Enter to post — your note will be reflected into rules.</span>
          <button
            type="submit"
            className="btn btn-primary btn-sm"
            disabled={busy || !draft.trim()}
          >
            <Send size={14} /> {busy ? 'Reflecting…' : 'Add note'}
          </button>
        </div>
      </form>

      <div className="pdp-comment-list">
        <h3 className="pdp-section-h3"><MessageSquare size={16} /> Notes history</h3>
        {comments === null && <div className="muted">Loading…</div>}
        {comments && comments.length === 0 && (
          <div className="pdp-comment-empty muted">No notes yet.</div>
        )}
        {comments && [...comments].reverse().map((c) => (
          <div key={c.id} className="pdp-comment-item">
            <div className="pdp-comment-meta">
              <strong>{c.author || 'anonymous'}</strong>
              <span className="muted small">
                {c.created_at ? new Date(c.created_at).toLocaleString() : ''}
              </span>
              <button
                className="btn-icon"
                onClick={() => remove(c)}
                title="Delete note"
              >
                <Trash2 size={14} />
              </button>
            </div>
            <div className="pdp-comment-text">{c.text}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Share modal ─────────────────────────────────────────────────────
function ShareModal({
  productId,
  productName,
  ownerUsername,
  onClose,
}: {
  productId: string;
  productName: string;
  ownerUsername: string;
  onClose: () => void;
}) {
  const [shares, setShares] = useState<ProductShare[]>([]);
  const [users, setUsers] = useState<{ username: string; full_name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const reload = async () => {
    try {
      setLoading(true);
      const [list, allUsers] = await Promise.all([
        api.listProductShares(productId),
        api.listShareableUsers(),
      ]);
      setShares(list);
      setUsers(allUsers);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { reload(); }, [productId]);

  // Filter out the owner and already-shared users
  const sharedSet = new Set(shares.map((s) => s.username));
  const candidates = users.filter(
    (u) => u.username !== ownerUsername && !sharedSet.has(u.username),
  );

  // Reset selection when the candidate list changes (e.g. after a grant)
  useEffect(() => {
    if (username && !candidates.find((c) => c.username === username)) {
      setUsername('');
    }
  }, [candidates, username]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const u = username.trim();
    if (!u) return;
    setSubmitting(true);
    setError('');
    try {
      await api.createProductShare(productId, u);
      setUsername('');
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleRevoke = async (u: string) => {
    if (!window.confirm(`Revoke access for "${u}"?`)) return;
    try {
      await api.deleteProductShare(productId, u);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  // Helper: resolve a username to its display label
  const displayFor = (u: string) => {
    const found = users.find((x) => x.username === u);
    return found && found.full_name ? `${found.full_name} (${u})` : u;
  };

  return (
    <div className="pdp-modal-backdrop" onClick={onClose}>
      <div className="pdp-modal" onClick={(e) => e.stopPropagation()}>
        <div className="pdp-modal-header">
          <div>
            <h2><Users size={18} /> Share “{productName}”</h2>
            <p className="pdp-modal-sub">
              Collaborators can edit versions, assessments, comments and rules.
              Only the owner can rename, delete, or manage sharing.
            </p>
          </div>
          <button className="btn-icon" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <form className="pdp-share-add" onSubmit={handleAdd}>
          <select
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={submitting || loading || candidates.length === 0}
          >
            <option value="">
              {loading
                ? 'Loading users…'
                : candidates.length === 0
                  ? 'No more users to add'
                  : 'Select a user…'}
            </option>
            {candidates.map((u) => (
              <option key={u.username} value={u.username}>
                {u.full_name ? `${u.full_name} (${u.username})` : u.username}
              </option>
            ))}
          </select>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting || !username}
          >
            <UserPlus size={15} /> Grant access
          </button>
        </form>

        {error && <div className="pdp-error">{error}</div>}

        <div className="pdp-share-list">
          <div className="pdp-share-row pdp-share-owner">
            <span className="pdp-share-user">{displayFor(ownerUsername) || '—'}</span>
            <span className="pdp-share-role">Owner</span>
            <span />
          </div>

          {loading ? (
            <div className="pdp-share-empty">Loading…</div>
          ) : shares.length === 0 ? (
            <div className="pdp-share-empty">No collaborators yet.</div>
          ) : (
            shares.map((s) => (
              <div key={s.username} className="pdp-share-row">
                <span className="pdp-share-user">{displayFor(s.username)}</span>
                <span className="pdp-share-role">Collaborator</span>
                <button
                  className="btn-icon"
                  title="Revoke access"
                  onClick={() => handleRevoke(s.username)}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
