import { useState, useRef, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Loader2, Upload, X, Info } from 'lucide-react';
import { api, type Regulation, type ProductDetail } from '../api';
import './NewAssessment.css';

export default function NewAssessmentForProduct() {
  const { productId } = useParams<{ productId: string }>();
  const navigate = useNavigate();
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [regulations, setRegulations] = useState<Regulation[]>([]);
  const [regulation, setRegulation] = useState('CRA');
  const [description, setDescription] = useState('');
  const [originalDescription, setOriginalDescription] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.getRegulations().then(setRegulations).catch(() => {});
  }, []);

  useEffect(() => {
    if (!productId) return;
    api.getProduct(productId).then(p => {
      setProduct(p);
      const latest = p.versions[p.versions.length - 1];
      const desc = latest?.description || '';
      setDescription(desc);
      setOriginalDescription(desc);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [productId]);

  const latest = product?.versions[product.versions.length - 1];
  const descriptionChanged = description.trim() !== originalDescription.trim();
  const willCreateNewVersion = descriptionChanged || !!selectedFile || (latest?.has_locked_assessment ?? false);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!productId) return;
    if (!description.trim() && !selectedFile) {
      setError('Please provide a description or upload a file.');
      return;
    }
    setError('');
    setSubmitting(true);
    try {
      const res = await api.createAssessmentForProduct(
        productId,
        regulation,
        description,
        selectedFile || undefined,
      );
      navigate(`/assessments/${res.id}/info`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  if (loading) return <div className="home-loading">Loading product…</div>;
  if (!product) return <div className="home-loading">Product not found.</div>;

  return (
    <div className="new-assessment">
      <div className="page-header">
        <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/products/${productId}`)}>
          <ArrowLeft size={16} /> Back to product
        </button>
        <h1>New assessment for <em>{product.name}</em></h1>
        <p>
          The latest version (V{latest?.version_number}) is used as a starting point.
          If you change the description or upload a different file, a new product version
          will be created automatically.
        </p>
      </div>

      <div className="card form-card">
        {error && <div className="error-alert">{error}</div>}

        <form onSubmit={handleSubmit} className="assessment-form">
          <div className="form-group">
            <label>Regulation</label>
            <select
              value={regulation}
              onChange={(e) => setRegulation(e.target.value)}
              disabled={submitting}
              className="text-input"
            >
              {regulations.length > 0 ? regulations.map(r => (
                <option key={r.id} value={r.id}>{r.name} ({r.short})</option>
              )) : (
                <>
                  <option value="CRA">Cyber Resilience Act (CRA)</option>
                  <option value="Part-IS">Part-IS — Information Security</option>
                </>
              )}
            </select>
          </div>

          <div className="form-group">
            <label>Product Name (locked)</label>
            <input
              type="text"
              value={product.name}
              disabled
              className="text-input"
              style={{ background: '#f7f7f9', cursor: 'not-allowed' }}
            />
            <span className="upload-hint">
              The product name is fixed. To rename, edit the product directly.
            </span>
          </div>

          <div className="form-group">
            <label>Description {descriptionChanged && <span style={{ color: '#c66', fontSize: '0.8rem' }}>(modified)</span>}</label>
            <textarea
              rows={8}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={submitting}
              className="text-input"
            />
            <div className="upload-row">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp"
                onChange={handleFileSelect}
                disabled={submitting}
                style={{ display: 'none' }}
              />
              <button
                type="button"
                className="btn btn-outline btn-sm upload-btn"
                onClick={() => fileInputRef.current?.click()}
                disabled={submitting}
              >
                <Upload size={14} /> {selectedFile ? 'Change file' : 'Upload new technical file'}
              </button>
              {latest?.technical_file_name && !selectedFile && (
                <span className="upload-hint">Current: {latest.technical_file_name}</span>
              )}
            </div>
            {selectedFile && (
              <div className="upload-info">
                📄 {selectedFile.name}
                <button type="button" className="btn-link" onClick={() => setSelectedFile(null)} style={{ marginLeft: 8 }}>
                  <X size={14} /> Remove
                </button>
              </div>
            )}
          </div>

          <div className="pdp-info-banner">
            <Info size={14} />
            {willCreateNewVersion
              ? <>This will create <strong>version V{(latest?.version_number ?? 0) + 1}</strong> of the product.</>
              : <>This assessment will be linked to the existing <strong>V{latest?.version_number}</strong> (no changes).</>}
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn btn-outline"
              onClick={() => navigate(`/products/${productId}`)}
              disabled={submitting}
            >
              Cancel
            </button>
            <button type="submit" className="btn btn-primary submit-btn" disabled={submitting}>
              {submitting ? (
                <><Loader2 className="spinner" size={18} /> Creating…</>
              ) : (
                <>Create Assessment <ArrowRight size={18} /></>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
