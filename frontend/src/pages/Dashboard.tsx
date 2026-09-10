import { PlusCircle, Box, Layers, ClipboardList, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { api, type ProductSummary } from '../api';
import './Dashboard.css';

export default function Dashboard() {
  const navigate = useNavigate();
  const [products, setProducts] = useState<ProductSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listProducts()
      .then(data => { setProducts(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const handleDelete = (e: React.MouseEvent, p: ProductSummary) => {
    e.stopPropagation();
    const msg = p.assessments_count > 0
      ? `Delete "${p.name}"? This will permanently remove the product and all ${p.assessments_count} assessment(s).`
      : `Delete "${p.name}"?`;
    if (!window.confirm(msg)) return;
    api.deleteProduct(p.id)
      .then(() => setProducts(prev => prev.filter(x => x.id !== p.id)))
      .catch(console.error);
  };

  if (loading) return <div className="home-loading">Loading products…</div>;

  return (
    <div className="home-page">
      <div className="home-header">
        <div>
          <h1>Products</h1>
          <p className="home-subtitle">
            {products.length} product{products.length !== 1 ? 's' : ''} — manage versions and run compliance assessments
          </p>
        </div>
      </div>

      <div className="product-grid">
        {products.map(p => (
          <div key={p.id} className="card product-card" onClick={() => navigate(`/products/${p.id}`)}>
            {(p.role === 'owner' || p.role === 'admin' || !p.role) && (
              <button
                className="pc-delete"
                title="Delete product"
                onClick={(e) => handleDelete(e, p)}
              >
                <Trash2 size={15} />
              </button>
            )}
            <div className="pc-icon"><Box size={22} /></div>
            <div className="pc-body">
              <h3 className="pc-name">{p.name}</h3>
              <p className="pc-desc">
                {p.role === 'collaborator' ? (
                  <>Shared by <strong>{p.owner_username || 'owner'}</strong></>
                ) : (
                  <>Created {p.created_at ? new Date(p.created_at).toLocaleDateString() : '—'}</>
                )}
              </p>
              <div className="pc-footer">
                <span className="pc-status" style={{ color: 'var(--color-text-muted)' }}>
                  <Layers size={14} /> {p.versions_count} version{p.versions_count !== 1 ? 's' : ''}
                </span>
                <span className="pc-status" style={{ color: 'var(--color-primary-blue)' }}>
                  <ClipboardList size={14} /> {p.assessments_count} assessment{p.assessments_count !== 1 ? 's' : ''}
                </span>
              </div>
            </div>
          </div>
        ))}

        <div className="card product-card add-card" onClick={() => navigate('/products/new')}>
          <PlusCircle size={28} className="add-icon" />
          <span className="add-label">New Product</span>
        </div>
      </div>
    </div>
  );
}
