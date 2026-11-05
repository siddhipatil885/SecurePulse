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
      </div>
      
      <div className="header-right">
        <div className={`status-indicator ${status.online ? 'status-online' : 'status-offline'}`}>
          <span className="status-dot"></span>
          {status.online ? 'Live updates connected' : 'Live updates disconnected'}
        </div>
      </div>
    </header>
  );
};

export default Header;
