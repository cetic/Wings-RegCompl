import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Package, ScrollText, ClipboardCheck, BarChart3 } from 'lucide-react';
import { api } from '../api';
import ProductInfo from './ProductInfo';
import ObligationsList from './ObligationsList';
import AssessmentQuiz from './AssessmentQuiz';
import AssessmentResults from './AssessmentResults';
import FloatingCommentButton from '../components/FloatingCommentButton';
import './ProductDashboard.css';

const ALL_TABS = [
  { key: 'info', label: 'Assessment Info', icon: Package },
  { key: 'obligations', label: 'Obligations', icon: ScrollText },
  { key: 'quiz', label: 'Verification Quiz', icon: ClipboardCheck },
  { key: 'results', label: 'Compliance Results', icon: BarChart3 },
] as const;

type TabKey = typeof ALL_TABS[number]['key'];

export default function ProductDashboard() {
  const { id, tab } = useParams<{ id: string; tab?: string }>();
  const navigate = useNavigate();
  const [locked, setLocked] = useState<boolean | null>(null);
  const [productId, setProductId] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api.getAssessment(id).then(p => {
      setLocked(p.locked === true);
      setProductId(p.product_id);
    }).catch(() => setLocked(false));
  }, [id]);

  const tabs = locked
    ? ALL_TABS
    : ALL_TABS.filter(t => t.key === 'info');

  const initialTab = tabs.find(t => t.key === tab)?.key || 'info';
  const [activeTab, setActiveTab] = useState<TabKey>(initialTab);

  // Reset to info tab if navigating to a tab that's not visible (unlocked product)
  useEffect(() => {
    if (locked === false && activeTab !== 'info') {
      setActiveTab('info');
      navigate(`/assessments/${id}/info`, { replace: true });
    }
  }, [locked]);

  // Sync activeTab with URL tab param (and when locked state resolves)
  useEffect(() => {
    const validTab = tabs.find(t => t.key === tab)?.key;
    if (validTab && validTab !== activeTab) {
      setActiveTab(validTab);
    }
  }, [tab, locked]);

  const switchTab = (key: TabKey) => {
    setActiveTab(key);
    navigate(`/assessments/${id}/${key}`, { replace: true });
  };

  if (locked === null) return null; // loading

  return (
    <div className="product-dashboard">
      <div className="pd-topbar">
        <button
          className="btn btn-ghost"
          onClick={() => productId ? navigate(`/products/${productId}`) : navigate('/')}
        >
          <ArrowLeft size={18} /> Back to product
        </button>
        <div className="pd-tabs">
          {tabs.map(t => (
            <button
              key={t.key}
              className={`pd-tab ${activeTab === t.key ? 'active' : ''}`}
              onClick={() => switchTab(t.key)}
            >
              <t.icon size={16} />
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="pd-content">
        {activeTab === 'info' && <ProductInfo onLocked={() => { setLocked(true); switchTab('obligations'); }} />}
        {activeTab === 'obligations' && <ObligationsList />}
        {activeTab === 'quiz' && <AssessmentQuiz />}
        {activeTab === 'results' && <AssessmentResults />}
      </div>

      {productId && (
        <FloatingCommentButton
          productId={productId}
          contextLabel={id ? `assessment ${id.slice(0, 8)}…` : undefined}
        />
      )}
    </div>
  );
}
