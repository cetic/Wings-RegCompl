import { useState } from 'react';
import type { FormEvent } from 'react';
import { useAuth } from '../components/AuthContext';
import { Navigate } from 'react-router-dom';
import { Shield, Lock, User, AlertCircle, ArrowRight, Loader2 } from 'lucide-react';
import './Login.css';

export default function Login() {
  const { authenticated, login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  if (authenticated) return <Navigate to="/" replace />;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      {/* Left branding panel */}
      <div className="login-brand-panel">
        <div className="login-brand-content">
          <div className="login-brand-icon">
            <Shield size={40} strokeWidth={1.5} />
          </div>
          <h1 className="login-brand-title">RegComply</h1>
          <p className="login-brand-subtitle">
            Regulatory compliance assessment platform for European Regulations and directives
          </p>
          <div className="login-brand-features">
            <div className="login-feature">
              <div className="login-feature-dot" />
              <span>AI-powered obligation mapping</span>
            </div>
            <div className="login-feature">
              <div className="login-feature-dot" />
              <span>Automated verification workflows</span>
            </div>
            <div className="login-feature">
              <div className="login-feature-dot" />
              <span>Evidence management & reporting</span>
            </div>
          </div>
        </div>
        <div className="login-brand-footer">
          <span>WINGS4 Research Project</span>
        </div>
      </div>

      {/* Right form panel */}
      <div className="login-form-panel">
        <div className="login-form-wrapper">
          <div className="login-form-header">
            <h2>Welcome back</h2>
            <p>Enter your credentials to access the platform</p>
          </div>

          {error && (
            <div className="login-error">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="login-form">
            <div className="login-field">
              <label htmlFor="username">Username</label>
              <div className="login-input-wrapper">
                <User size={18} className="login-input-icon" />
                <input
                  id="username"
                  type="text"
                  placeholder="Enter your username"
                  autoComplete="username"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  disabled={loading}
                  autoFocus
                />
              </div>
            </div>

            <div className="login-field">
              <label htmlFor="password">Password</label>
              <div className="login-input-wrapper">
                <Lock size={18} className="login-input-icon" />
                <input
                  id="password"
                  type="password"
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  disabled={loading}
                />
              </div>
            </div>

            <button type="submit" className="login-btn" disabled={loading || !username || !password}>
              {loading ? (
                <>
                  <Loader2 size={18} className="login-spinner" />
                  Signing in...
                </>
              ) : (
                <>
                  Sign in
                  <ArrowRight size={18} />
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
