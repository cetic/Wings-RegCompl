import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, Edit3, X, Package, Shield, Tag, Users, CheckCircle2, ArrowRight, Lock, Loader2, RefreshCw } from 'lucide-react';
import { api } from '../api';
import type { AssessmentResponse } from '../api';
import './ProductInfo.css';

function makeSnapshot(product: AssessmentResponse): string {
  return JSON.stringify({
    product_name: product.product_name,
    description: product.description,
    key_features: product.key_features,
    actor_roles: product.actor_roles,
  });
}

export default function ProductInfo({ onLocked }: { onLocked?: () => void }) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [product, setProduct] = useState<AssessmentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [locking, setLocking] = useState(false);
  const [reclassifying, setReclassifying] = useState(false);
  const [draft, setDraft] = useState<Partial<AssessmentResponse>>({});
  const [classifiedSnapshot, setClassifiedSnapshot] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api.getAssessment(id).then(p => {
      setProduct(p);
      setDraft(p);
      setClassifiedSnapshot(makeSnapshot(p));
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [id]);

  const handleSave = async () => {
    if (!id || !draft || !product) return;
    setSaving(true);
    try {
      // Product name is fixed in assessment context — only edited via product management.
      // Description / key_features / actor_roles live on the product version.
      const versionChanged =
        draft.description !== product.description ||
        JSON.stringify(draft.key_features) !== JSON.stringify(product.key_features) ||
        JSON.stringify(draft.actor_roles) !== JSON.stringify(product.actor_roles);

      if (versionChanged) {
        await api.updateProductVersion(product.product_id, product.product_version_id, {
          description: draft.description,
          key_features: draft.key_features,
          actor_roles: draft.actor_roles,
        });
      }

      if (draft.product_class !== product.product_class) {
        await api.updateAssessment(id, { product_class: draft.product_class });
      }

      const updated = await api.getAssessment(id);
      setProduct(updated);
      setDraft(updated);
      setEditing(false);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleReclassify = async () => {
    if (!id) return;
    setReclassifying(true);
    try {
      const updated = await api.reclassifyAssessment(id);
      setProduct(updated);
      setDraft(updated);
      setClassifiedSnapshot(makeSnapshot(updated));
    } finally {
      setReclassifying(false);
    }
  };

  const handleContinue = async () => {
    if (!id) return;
    const confirmed = window.confirm(
      `Are you sure you want to continue?\n\nOnce you proceed, the ${product?.regulation === 'Part-IS' ? 'organisation' : 'product'} information will be locked and can no longer be edited.`
    );
    if (!confirmed) return;
    setLocking(true);
    try {
      const updated = await api.lockAssessment(id);
      setProduct(updated);
      onLocked?.();
    } catch {
      setLocking(false);
    }
  };

  const classLabel = (cls?: string) => {
    const map: Record<string, string> = {
      default: 'Default',
      class_i: 'Class I',
      class_ii: 'Class II',
      critical: 'Critical',
    };
    return map[cls || 'default'] || cls || 'Default';
  };

  const classBadgeClass = (cls?: string) => {
    const map: Record<string, string> = {
      default: 'badge-default',
      class_i: 'badge-class-i',
      class_ii: 'badge-class-ii',
      critical: 'badge-critical',
    };
    return map[cls || 'default'] || 'badge-default';
  };

  if (loading) return <div className="pi-loading">Loading assessment information...</div>;
  if (!product) return <div className="pi-loading">Assessment not found.</div>;

  const isLocked = product.locked === true;
  const needsReclassification = classifiedSnapshot !== null && makeSnapshot(product) !== classifiedSnapshot;
  const busy = locking || reclassifying;

  return (
    <div className="product-info-page">
      <div className="pi-breadcrumbs">
        <button className="btn-link" onClick={() => navigate('/')}>Products</button>
        <span className="sep">/</span>
        <button className="btn-link" onClick={() => navigate(`/products/${product.product_id}`)}>
          {product.product_name}
        </button>
        <span className="sep">/</span>
        <span>V{product.version_number} · {product.regulation}</span>
      </div>

      <div className="pi-header">
        <div className="pi-header-left">
          <button className="btn btn-ghost" onClick={() => navigate(-1)}>
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1>{product.product_name}</h1>
            <p className="pi-subtitle">{product.regulation === 'Part-IS' ? 'Organisation Information' : 'Product Information & CRA Classification'}</p>
          </div>
        </div>
        <div className="pi-header-actions">
          {isLocked ? (
            <span className="pi-locked-badge"><Lock size={14} /> Locked</span>
          ) : editing ? (
            <>
              <button className="btn btn-outline" onClick={() => { setEditing(false); setDraft(product); }} disabled={saving}>
                <X size={16} /> Cancel
              </button>
              <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
                <Save size={16} /> {saving ? 'Saving...' : 'Save'}
              </button>
            </>
          ) : (
            <button className="btn btn-outline" onClick={() => setEditing(true)} disabled={busy}>
              <Edit3 size={16} /> Edit
            </button>
          )}
        </div>
      </div>

      <div className="pi-grid">
        {/* Product Details Card */}
        <div className="card pi-card">
          <div className="pi-card-header">
            <Package size={20} />
            <h2>{product.regulation === 'Part-IS' ? 'Organisation Details' : 'Product Details'}</h2>
          </div>
          <div className="pi-field">
            <label>{product.regulation === 'Part-IS' ? 'Organisation Name' : 'Product Name'}</label>
            <p>
              {product.product_name}
              {editing && (
                <span style={{ marginLeft: 8, fontSize: '0.78rem', color: 'var(--color-text-muted)' }}>
                  (locked — rename via product management)
                </span>
              )}
            </p>
          </div>
          <div className="pi-field">
            <label>Description</label>
            {editing ? (
              <textarea
                className="pi-textarea"
                rows={5}
                value={draft.description || ''}
                onChange={e => setDraft({ ...draft, description: e.target.value })}
              />
            ) : (
              <p className="pi-description">{product.description}</p>
            )}
          </div>
          <div className="pi-field">
            <label>Regulation</label>
            <span className={`pi-badge ${product.regulation === 'Part-IS' ? 'pi-badge-blue' : 'pi-badge-purple'}`}>
              {product.regulation || 'CRA'}
            </span>
          </div>
          <div className="pi-field">
            <label>Obligations</label>
            <p className="pi-count">{product.obligation_ids.length} obligations mapped</p>
          </div>
        </div>

        {/* Classification Card — CRA only */}
        {product.regulation !== 'Part-IS' && (
        <div className="card pi-card">
          <div className="pi-card-header">
            <Shield size={20} />
            <h2>{product.regulation === 'Part-IS' ? 'Part-IS Classification' : 'CRA Classification'}</h2>
          </div>
          <div className="pi-field">
            <label>Product Class</label>
            {editing ? (
              <select
                className="pi-select"
                value={draft.product_class || 'default'}
                onChange={e => setDraft({ ...draft, product_class: e.target.value })}
              >
                <option value="default">Default</option>
                <option value="class_i">Class I (Important)</option>
                <option value="class_ii">Class II (Important)</option>
                <option value="critical">Critical</option>
              </select>
            ) : (
              <span className={`pi-badge ${classBadgeClass(product.product_class)}`}>
                {classLabel(product.product_class)}
              </span>
            )}
          </div>
          <div className="pi-field">
            <label>AI Confidence</label>
            <span className={`pi-confidence ${product.confidence || 'low'}`}>
              {(product.confidence || 'N/A').toUpperCase()}
            </span>
          </div>
          {product.reasoning && (
            <div className="pi-field">
              <label>Reasoning</label>
              <p className="pi-reasoning">{product.reasoning}</p>
            </div>
          )}
        </div>
        )}

        {/* Categories & Features Card — CRA only */}
        {product.regulation !== 'Part-IS' && (
        <div className="card pi-card">
          <div className="pi-card-header">
            <Tag size={20} />
            <h2>Matched Categories</h2>
          </div>
          {(product.matched_categories?.length ?? 0) > 0 ? (
            <ul className="pi-tag-list">
              {product.matched_categories!.map((cat, i) => (
                <li key={i} className="pi-tag">{cat}</li>
              ))}
            </ul>
          ) : (
            <p className="pi-empty">No specific Annex III category matched (default product).</p>
          )}
        </div>
        )}

        <div className="card pi-card">
          <div className="pi-card-header">
            <CheckCircle2 size={20} />
            <h2>Key Features</h2>
          </div>
          {editing ? (
            <textarea
              className="pi-textarea"
              rows={4}
              placeholder="One feature per line"
              value={(draft.key_features || []).join('\n')}
              onChange={e => setDraft({ ...draft, key_features: e.target.value.split('\n').filter(Boolean) })}
            />
          ) : (product.key_features?.length ?? 0) > 0 ? (
            <ul className="pi-feature-list">
              {product.key_features!.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          ) : (
            <p className="pi-empty">No key features identified.</p>
          )}
        </div>

        {/* Actor Roles Card — CRA only */}
        {product.regulation !== 'Part-IS' && (
        <div className="card pi-card">
          <div className="pi-card-header">
            <Users size={20} />
            <h2>Actor Roles</h2>
          </div>
          {editing ? (
            <div className="pi-checkbox-group">
              {['manufacturer', 'importer', 'distributor', 'open_source_steward'].map(role => (
                <label key={role} className="pi-checkbox-label">
                  <input
                    type="checkbox"
                    checked={(draft.actor_roles || []).includes(role)}
                    onChange={e => {
                      const roles = [...(draft.actor_roles || [])];
                      if (e.target.checked) roles.push(role);
                      else roles.splice(roles.indexOf(role), 1);
                      setDraft({ ...draft, actor_roles: roles });
                    }}
                  />
                  {role.replace(/_/g, ' ')}
                </label>
              ))}
            </div>
          ) : (
            <div className="pi-roles">
              {(product.actor_roles || ['manufacturer']).map(r => (
                <span key={r} className="pi-role-badge">{r.replace(/_/g, ' ')}</span>
              ))}
            </div>
          )}
        </div>
        )}

        {/* Conformity Route Card */}
        {product.conformity_route && (
          <div className="card pi-card pi-card-wide">
            <div className="pi-card-header">
              <Shield size={20} />
              <h2>Conformity Assessment Route</h2>
            </div>
            <p className="pi-conformity">{product.conformity_route}</p>
          </div>
        )}
      </div>

      {/* Bottom action bar — only when not locked and not editing */}
      {!isLocked && !editing && (
        <div className="pi-bottom-actions">
          {product.regulation !== 'Part-IS' && (
          <button
            className="btn btn-outline"
            onClick={handleReclassify}
            disabled={!needsReclassification || busy}
            title={needsReclassification ? 'Re-run AI classification with the updated product info' : 'No changes since last classification'}
          >
            {reclassifying ? (
              <><Loader2 size={16} className="spinner" /> Reclassifying...</>
            ) : (
              <><RefreshCw size={16} /> Reevaluate Product</>
            )}
          </button>
          )}
          <button className="btn btn-primary" onClick={handleContinue} disabled={busy}>
            {locking ? (
              <><Loader2 size={16} className="spinner" /> Generating obligations...</>
            ) : (
              <>Continue <ArrowRight size={16} /></>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
