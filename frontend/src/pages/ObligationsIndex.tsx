import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ScrollText, ChevronRight } from 'lucide-react';
import { api } from '../api';

export default function ObligationsIndex() {
  const navigate = useNavigate();
  const [assessments, setAssessments] = useState<any[]>([]);

  useEffect(() => {
    api.getAssessments().then(setAssessments).catch(console.error);
  }, []);

  return (
    <div style={{ padding: '2rem 3rem' }}>
      <div className="page-header">
        <h1>Obligations Explorer</h1>
        <p>Select an assessment to view its mapped obligations.</p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '1.5rem' }}>
        {assessments.length === 0 ? (
          <div className="card" style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
            <ScrollText size={32} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
            <p>No assessments found. Create an assessment first to explore its obligations.</p>
          </div>
        ) : (
          assessments.map(a => (
            <div
              key={a.id}
              className="card"
              style={{ padding: '1.25rem 1.5rem', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              onClick={() => navigate(`/assessments/${a.id}/obligations`)}
            >
              <div>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--color-text-navy)', marginBottom: '0.25rem' }}>
                  {a.product_name}
                </h3>
                <p style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', maxWidth: '600px', lineHeight: 1.4 }}>
                  {a.description?.slice(0, 150)}{a.description?.length > 150 ? '...' : ''}
                </p>
              </div>
              <ChevronRight size={20} style={{ color: 'var(--color-text-muted)', flexShrink: 0 }} />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
