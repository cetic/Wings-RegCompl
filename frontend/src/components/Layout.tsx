import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { PlusCircle, Box, Database, FileText, LogOut, Sparkles, KeyRound, X } from 'lucide-react';
import { useAuth } from './AuthContext';
import { api } from '../api';
import './Layout.css';

export default function Layout() {
  const navigate = useNavigate();
  const { username, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="sidebar-brand">
          <span className="brand-name">RegComply</span>
          <span className="brand-tag">Compliance Platform</span>
        </div>
        <nav className="sidebar-nav">
          <NavLink to="/" end className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <Box size={18} /> Products
          </NavLink>
          <NavLink to="/assistant" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <Sparkles size={18} /> AI Assistant
          </NavLink>
          <NavLink to="/evidence" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <Database size={18} /> Evidence Vault
          </NavLink>
          <NavLink to="/reports" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <FileText size={18} /> Reports
          </NavLink>
        </nav>
        <div className="sidebar-footer">
          <button className="btn btn-primary sidebar-new-btn" onClick={() => navigate('/products/new')}>
            <PlusCircle size={16} /> New Product
          </button>
          <div className="sidebar-user-wrap">
            <button
              type="button"
              className="sidebar-user"
              onClick={() => setMenuOpen((v) => !v)}
              title="Account"
            >
              <span className="sidebar-username">{username}</span>
            </button>
            {menuOpen && (
              <>
                <div className="sidebar-menu-backdrop" onClick={() => setMenuOpen(false)} />
                <div className="sidebar-menu">
                  <button
                    className="sidebar-menu-item"
                    onClick={() => { setMenuOpen(false); setPwOpen(true); }}
                  >
                    <KeyRound size={15} /> Change password
                  </button>
                  <button
                    className="sidebar-menu-item"
                    onClick={() => { setMenuOpen(false); logout(); navigate('/login'); }}
                  >
                    <LogOut size={15} /> Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </aside>
      <main className="app-main">
        <Outlet />
      </main>
      {pwOpen && <ChangePasswordModal onClose={() => setPwOpen(false)} />}
    </div>
  );
}

function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (next.length < 8) {
      setError('New password must be at least 8 characters.');
      return;
    }
    if (next !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setSubmitting(true);
    try {
      await api.changePassword(current, next);
      setSuccess(true);
      setCurrent(''); setNext(''); setConfirm('');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="pdp-modal-backdrop" onClick={onClose}>
      <div className="pdp-modal" onClick={(e) => e.stopPropagation()}>
        <div className="pdp-modal-header">
          <div>
            <h2><KeyRound size={18} /> Change password</h2>
            <p className="pdp-modal-sub">Enter your current password and choose a new one (min 8 chars).</p>
          </div>
          <button className="btn-icon" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        {success ? (
          <div className="pdp-share-empty" style={{ color: '#10b981', fontWeight: 600 }}>
            ✓ Password updated. You'll need to use the new one next time you sign in.
          </div>
        ) : (
          <form onSubmit={submit} className="pw-form">
            <label className="pw-label">
              Current password
              <input
                type="password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                disabled={submitting}
                autoFocus
                required
              />
            </label>
            <label className="pw-label">
              New password
              <input
                type="password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                disabled={submitting}
                required
                minLength={8}
              />
            </label>
            <label className="pw-label">
              Confirm new password
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                disabled={submitting}
                required
                minLength={8}
              />
            </label>
            {error && <div className="pdp-error">{error}</div>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.75rem' }}>
              <button type="button" className="btn btn-outline" onClick={onClose} disabled={submitting}>
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={submitting || !current || !next || !confirm}
              >
                {submitting ? 'Updating…' : 'Update password'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
