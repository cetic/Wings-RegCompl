import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Database, Download, ExternalLink, Filter } from 'lucide-react';
import { api } from '../api';

export default function EvidenceVault() {
  const navigate = useNavigate();
  const [evidence, setEvidence] = useState<any[]>([]);
  const [selectedProduct, setSelectedProduct] = useState('all');

  useEffect(() => {
    api.getEvidence().then(setEvidence).catch(console.error);
  }, []);

  const products = Array.from(new Map(evidence.map(e => [e.assessment_id, e.assessment_name])).entries());
  const filtered = selectedProduct === 'all' ? evidence : evidence.filter(e => e.assessment_id === selectedProduct);

  const handleDownload = (e: any) => {
    const content = `Evidence Artifact: ${e.evidence}\nTarget: ${e.verification_text}\nAssessment: ${e.assessment_name}\nStatus: ${e.status}`;
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${e.evidence}_export.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ padding: '2rem 3rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '2rem' }}>
        <div style={{ background: 'var(--color-bg-navy)', padding: '0.75rem', borderRadius: 'var(--radius-lg)' }}>
          <Database size={32} color="white" />
        </div>
        <div>
          <h1 style={{ fontSize: '2rem', color: 'var(--color-text-navy)', marginBottom: '0.25rem' }}>Central Evidence Vault</h1>
          <p style={{ color: 'var(--color-text-muted)' }}>Secure, immutable repository of all compliance artifacts and verification attachments.</p>
        </div>
      </div>

      {/* Product filter */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
        <Filter size={16} style={{ color: 'var(--color-text-muted)' }} />
        <select
          value={selectedProduct}
          onChange={e => setSelectedProduct(e.target.value)}
          style={{
            padding: '0.5rem 0.75rem',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-border)',
            background: 'var(--color-bg-card)',
            fontSize: '0.88rem',
            color: 'var(--color-text-main)',
            fontFamily: 'inherit',
          }}
        >
          <option value="all">All Assessments ({evidence.length})</option>
          {products.map(([id, name]) => {
            const count = evidence.filter(e => e.assessment_id === id).length;
            return <option key={id} value={id}>{name} ({count})</option>;
          })}
        </select>
        {selectedProduct !== 'all' && (
          <span style={{ fontSize: '0.82rem', color: 'var(--color-text-muted)' }}>
            {filtered.length} artifact{filtered.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      <div className="card" style={{ padding: '1.5rem' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--color-border)', color: 'var(--color-text-navy)' }}>
              <th style={{ padding: '1rem' }}>Artifact Reference</th>
              <th style={{ padding: '1rem' }}>Verification Target</th>
              <th style={{ padding: '1rem' }}>Verification Status</th>
              <th style={{ padding: '1rem' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan={4} style={{ padding: '4rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No evidence artifacts found{selectedProduct !== 'all' ? ' for this assessment' : ''}.</td></tr>
            ) : (
              filtered.map((e, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid var(--color-border-light)' }}>
                  <td style={{ padding: '1rem' }}>
                    <div style={{ fontWeight: 600 }}>{e.evidence}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>from {e.assessment_name}</div>
                  </td>
                  <td style={{ padding: '1rem', color: 'var(--color-text-muted)', fontSize: '0.85rem', maxWidth: '300px' }}>
                    {e.verification_text}
                  </td>
                  <td style={{ padding: '1rem' }}>
                    <span className={`badge ${e.status === 'Verified' ? 'gold' : 'priority'}`} style={{ padding: '0.3rem 0.6rem', borderRadius: '1rem', fontSize: '0.75rem', fontWeight: 700, backgroundColor: e.status === 'Verified' ? '#bbf7d0' : '#fecaca', color: e.status === 'Verified' ? '#166534' : '#991b1b' }}>
                      {e.status.toUpperCase()}
                    </span>
                  </td>
                  <td style={{ padding: '1rem' }}>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                       <button className="btn btn-outline" style={{ padding: '0.4rem', color: 'var(--color-text-muted)' }} title="Download Evidence" onClick={() => handleDownload(e)}><Download size={16} /></button>
                       <button className="btn btn-outline" style={{ padding: '0.4rem', color: 'var(--color-text-muted)' }} title="View in Assessment" onClick={() => navigate(`/products/${e.assessment_id}/quiz`)}><ExternalLink size={16} /></button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
