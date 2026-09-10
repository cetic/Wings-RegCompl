import { LayoutDashboard, CheckSquare, Database, FileText, Settings, HelpCircle, ScrollText, Sparkles } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import './Sidebar.css';

export default function Sidebar() {
  const mainLinks = [
    { to: '/', icon: LayoutDashboard, label: 'Overview' },
    { to: '/assistant', icon: Sparkles, label: 'AI Assistant' },
    { to: '/assess', icon: CheckSquare, label: 'Assess' },
    { to: '/obligations', icon: ScrollText, label: 'Obligations' },
    { to: '/evidence', icon: Database, label: 'Evidence Vault' },
    { to: '/reports', icon: FileText, label: 'Compliance Reports' },
  ];

  const bottomLinks = [
    { to: '/settings', icon: Settings, label: 'Settings' },
    { to: '/support', icon: HelpCircle, label: 'Support' },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h2>RegComply</h2>
        <span className="subtitle">REGULATORY COMPLIANCE</span>
      </div>

      <nav className="sidebar-nav">
        <ul className="nav-list">
          {mainLinks.map((link) => {
            const Icon = link.icon;
            return (
              <li key={link.to}>
                <NavLink 
                  to={link.to} 
                  className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                >
                  <Icon size={20} className="nav-icon" />
                  <span>{link.label}</span>
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="sidebar-bottom">
        <div className="bottom-nav">
          {bottomLinks.map((link) => {
            const Icon = link.icon;
            return (
              <NavLink 
                key={link.to} 
                to={link.to} 
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              >
                <Icon size={20} className="nav-icon" />
                <span>{link.label}</span>
              </NavLink>
            );
          })}
        </div>
        
        <div className="user-profile">
          <div className="avatar">
            <span className="avatar-fallback">AC</span>
          </div>
          <div className="user-info">
            <span className="user-name">Admin Console</span>
            <span className="user-role">Verified Institute</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
