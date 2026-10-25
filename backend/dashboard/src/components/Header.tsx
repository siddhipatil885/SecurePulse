import React from 'react';
import type { SystemStatus } from '../types';
import './Header.css';

interface HeaderProps {
  status: SystemStatus;
}

const Header: React.FC<HeaderProps> = ({ status }) => {
  return (
    <header className="header">
      <div className="header-left">
        <h1 className="header-logo">EDI SecurePulse</h1>
        <nav className="header-nav">
          <a href="#dashboard" className="nav-item active">Dashboard</a>
          <a href="#cameras" className="nav-item">Cameras</a>
          <a href="#events" className="nav-item">Events</a>
          <a href="#alerts" className="nav-item">Alerts</a>
        </nav>
      </div>
      
      <div className="header-right">
        <div className={`status-indicator ${status.online ? 'status-online' : 'status-offline'}`}>
          <span className="status-dot"></span>
          {status.online ? 'Dashboard connected' : 'Dashboard disconnected'}
        </div>
        <div className="user-profile">
          <span className="user-avatar">OP</span>
        </div>
      </div>
    </header>
  );
};

export default Header;
