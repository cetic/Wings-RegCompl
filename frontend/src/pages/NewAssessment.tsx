import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Loader2, Upload, X } from 'lucide-react';
import { api } from '../api';
import type { Regulation } from '../api';
import './NewAssessment.css';

export default function NewAssessment() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', regulation: 'CRA' });
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const [regulations, setRegulations] = useState<Regulation[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.getRegulations().then(setRegulations).catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name || (!form.description && !selectedFile)) {
      setError(`Please provide a ${form.regulation === 'Part-IS' ? 'organisation' : 'product'} name and either a description or a file.`);
      return;
    }
    
    setError('');
    setLoading(true);
    try {
      const res = await api.createAssessment(form.name, form.description, selectedFile || undefined, form.regulation);
      navigate(`/assessments/${res.id}/info`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const clearFile = () => {
    setSelectedFile(null);
  };

  return (
    <div className="new-assessment">
      <div className="page-header">
        <h1>New Product</h1>
        <p>Create a new {form.regulation === 'Part-IS' ? 'organisation' : 'product'} and run its first compliance assessment.</p>
      </div>

      <div className="card form-card">
        {error && <div className="error-alert">{error}</div>}
        
        <form onSubmit={handleSubmit} className="assessment-form">
          <div className="form-group">
            <label>Regulation</label>
            <select
              value={form.regulation}
              onChange={(e) => setForm({ ...form, regulation: e.target.value })}
              disabled={loading}
              className="text-input"
            >
              {regulations.length > 0 ? regulations.map(r => (
                <option key={r.id} value={r.id}>{r.name} ({r.short})</option>
              )) : (
                <>
                  <option value="CRA">Cyber Resilience Act (CRA)</option>
                  <option value="Part-IS">Part-IS — Information Security (Part-IS)</option>
                </>
              )}
            </select>
          </div>

          <div className="form-group">
            <label>{form.regulation === 'Part-IS' ? 'Organisation Name' : 'Product / System Name'}</label>
            <input 
              type="text" 
              placeholder={form.regulation === 'Part-IS' ? 'e.g. Eurocontrol MUAC' : 'e.g. SmartWear Cardio Monitor'}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              disabled={loading}
              className="text-input"
            />
          </div>
          
          <div className="form-group">
            <label>Technical Description & Architecture</label>
            <textarea 
              placeholder="Describe the functionality, network interfaces, target users, and security features to help the AI map applicable obligations..."
              rows={8}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              disabled={loading}
              className="text-input"
            />
            <div className="upload-row">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp"
                onChange={handleFileSelect}
                disabled={loading}
                style={{ display: 'none' }}
              />
              <button
                type="button"
                className="btn btn-outline btn-sm upload-btn"
                onClick={() => fileInputRef.current?.click()}
                disabled={loading}
              >
                <Upload size={14} /> {selectedFile ? 'Change file' : 'Upload specification file'}
              </button>
              <span className="upload-hint">
                {selectedFile ? '' : 'PDF, DOCX, TXT, MD, or image — or type a description above'}
              </span>
            </div>
            {selectedFile && (
              <div className="upload-info">
                📄 {selectedFile.name}
                <button type="button" className="btn-link" onClick={clearFile} style={{ marginLeft: 8 }}>
                  <X size={14} /> Remove
                </button>
              </div>
            )}
          </div>

          <div className="form-actions">
            <button 
              type="button" 
              className="btn btn-outline" 
              onClick={() => navigate('/')}
              disabled={loading}
            >
              Cancel
            </button>
            <button 
              type="submit" 
              className="btn btn-primary submit-btn"
              disabled={loading}
            >
              {loading ? (
                <>
                  <Loader2 className="spinner" size={18} />
                  {selectedFile ? 'Summarising & Classifying...' : 'Analyzing Graph...'}
                </>
              ) : (
                <>
                  Generate Assessment
                  <ArrowRight size={18} />
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
