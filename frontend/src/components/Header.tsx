import { Search, Bell, Settings } from 'lucide-react';
import './Header.css';

export default function Header() {
  return (
    <header className="top-header">
      <div className="search-container">
        <Search className="search-icon" size={18} />
        <input 
          type="text" 
          placeholder="Search Assessments..." 
          className="search-input"
        />
      </div>
      
      <div className="header-actions">
        <button className="action-btn">
          <Bell size={20} />
        </button>
        <button className="action-btn">
          <Settings size={20} />
        </button>
        <div className="ledger-badge">
          REGCOMPLY PLATFORM
        </div>
      </div>
    </header>
  );
}
