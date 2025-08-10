import React from 'react';
import {
  BrowserRouter as Router,
  Routes,
  Route,
  NavLink
} from 'react-router-dom';

import AnalysisPage from './pages/Analysis';
import PortfolioPage from './pages/Portfolio';

const App = () => {
  const navStyle = ({ isActive }) => ({
    textDecoration: 'none',
    color: isActive ? '#007bff' : 'black',
    fontWeight: 'bold',
    padding: '10px 15px',
    borderBottom: isActive ? '3px solid #007bff' : '3px solid transparent'
  });

  return (
    <Router>
      <div style={{ padding: '20px', fontFamily: 'sans-serif', maxWidth: '1200px', margin: 'auto' }}>
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #ddd', paddingBottom: '10px' }}>
          <h1>Trader Intelligence</h1>
          <nav>
            <NavLink to="/" style={navStyle}>
              Analysis
            </NavLink>
            <NavLink to="/portfolio" style={navStyle}>
              Portfolio
            </NavLink>
          </nav>
        </header>

        <main style={{ paddingTop: '20px' }}>
          <Routes>
            <Route path="/" element={<AnalysisPage />} />
            <Route path="/portfolio" element={<PortfolioPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
};

export default App;
