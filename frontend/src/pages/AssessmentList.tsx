import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PlusCircle, Search, Trash2 } from 'lucide-react';
import { api } from '../api';

export default function AssessmentList() {
  const navigate = useNavigate();
  const [assessments, setAssessments] = useState<any[]>([]);

  useEffect(() => {
    api.getAssessments().then(setAssessments).catch(console.error);
  }, []);

  return (
    <div style={{ padding: '2rem 3rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2rem' }}>
        <div>
          <h1 style={{ fontSize: '2rem', color: 'var(--color-text-navy)', marginBottom: '0.5rem' }}>Active Assessments</h1>
          <p style={{ color: 'var(--color-text-muted)' }}>Manage ongoing compliance evaluations across your infrastructures.</p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/assessments/new')} style={{ height: 'fit-content' }}>
          <PlusCircle size={18} /> New Assessment
        </button>
      </div>

      <div className="card" style={{ padding: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', padding: '0 1rem' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={18} style={{ position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
            <input type="text" placeholder="Search assessments..." style={{ width: '100%', padding: '0.75rem 1rem 0.75rem 2.8rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)', backgroundColor: 'var(--color-bg-sidebar)' }} />
          </div>
        </div>

        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--color-border)', color: 'var(--color-text-navy)' }}>
              <th style={{ padding: '1rem' }}>Assessment Subject</th>
              <th style={{ padding: '1rem' }}>Framework</th>
              <th style={{ padding: '1rem' }}>Completion</th>
              <th style={{ padding: '1rem' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {assessments.length === 0 ? (
              <tr><td colSpan={4} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>No assessments currently active.</td></tr>
            ) : (
              assessments.map(a => (
                <tr key={a.id} style={{ borderBottom: '1px solid var(--color-border-light)' }}>
                  <td style={{ padding: '1rem', fontWeight: 600 }}>{a.product_name}</td>
                  <td style={{ padding: '1rem', color: 'var(--color-text-muted)' }}>
                    <span style={{
                      padding: '0.2rem 0.6rem',
                      borderRadius: '4px',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      background: a.regulation === 'Part-IS' ? '#e8f4fd' : '#f0f0ff',
                      color: a.regulation === 'Part-IS' ? '#0369a1' : '#4338ca',
                    }}>
                      {a.regulation === 'Part-IS' ? 'Part-IS' : 'CRA'}
                    </span>
                  </td>
                  <td style={{ padding: '1rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                      <div className="f-bar" style={{ width: '100px', height: '6px', background: 'var(--color-border-light)', borderRadius: '3px' }}>
                        <div style={{ width: `${a.progress_percent}%`, height: '100%', background: 'var(--color-primary-blue)', borderRadius: '3px' }}></div>
                      </div>
                      <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>{a.progress_percent}%</span>
                    </div>
                  </td>
                  <td style={{ padding: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <button className="btn btn-outline" style={{ padding: '0.4rem 1rem' }} onClick={() => navigate(`/products/${a.id}/info`)}>Open</button>
                    <button
                      className="btn btn-outline"
                      style={{ padding: '0.4rem 0.6rem', color: '#d14', borderColor: '#d14' }}
                      title="Delete assessment"
                      onClick={() => {
                        if (window.confirm(`Delete "${a.product_name}"? This cannot be undone.`)) {
                          api.deleteAssessment(a.id).then(() => {
                            setAssessments(prev => prev.filter(x => x.id !== a.id));
                          }).catch(console.error);
                        }
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
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
