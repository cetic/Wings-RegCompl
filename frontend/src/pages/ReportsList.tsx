import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, ArrowRight } from 'lucide-react';
import { api } from '../api';

export default function ReportsList() {
  const navigate = useNavigate();
  const [assessments, setAssessments] = useState<any[]>([]);

  useEffect(() => {
    api.getAssessments()
      .then(a => setAssessments(a.filter((item: any) => item.progress_percent === 100)))
      .catch(console.error);
  }, []);

  return (
    <div style={{ padding: '2rem 3rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '2rem' }}>
        <div style={{ background: '#0e793c', padding: '0.75rem', borderRadius: 'var(--radius-lg)' }}>
          <FileText size={32} color="white" />
        </div>
        <div>
          <h1 style={{ fontSize: '2rem', color: 'var(--color-text-navy)', marginBottom: '0.25rem' }}>Compliance Reports</h1>
          <p style={{ color: 'var(--color-text-muted)' }}>Official readiness logs and cryptographic ledger verifications for completed assessments.</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '2rem' }}>
         {assessments.length === 0 ? (
           <div className="card" style={{ padding: '3rem', gridColumn: '1 / -1', textAlign: 'center', color: 'var(--color-text-muted)' }}>
              No completed assessment reports available yet. Complete an assessment to 100% to generate its ledger report.
           </div>
         ) : (
           assessments.map(a => (
             <div key={a.id} className="card" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column' }}>
               <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
                 <span style={{ fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.1em', color: 'var(--color-success)' }}>COMPLIANCE CERTIFIED</span>
                 <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Neo4j Vault</span>
               </div>
               <h3 style={{ fontSize: '1.25rem', color: 'var(--color-text-navy)', marginBottom: '0.5rem' }}>{a.product_name}</h3>
               <p style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginBottom: '2rem', flex: 1 }}>{a.description?.substring(0, 100)}...</p>
               <button 
                 className="btn btn-navy-light" 
                 style={{ width: '100%', justifyContent: 'space-between' }}
                 onClick={() => navigate(`/products/${a.id}/results`)}
               >
                 View Ledger Report <ArrowRight size={18} />
               </button>
             </div>
           ))
         )}
      </div>
    </div>
  );
}
