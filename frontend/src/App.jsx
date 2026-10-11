import React from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import SimulationsList from './components/SimulationsList';
import ResultsView from './components/ResultsView';
import ChillerSimulationsList from './components/ChillerSimulationsList';
import ChillerResultsView from './components/ChillerResultsView';
import OptimizationsList from './components/OptimizationsList';
import OptimizationResultsView from './components/OptimizationResultsView';
import './styles/App.css';

function App() {
  // In development, point to backend directly. In production (Docker), use nginx proxy
  const isDevelopment = import.meta.env.DEV;
  const adminUrl = isDevelopment 
    ? 'http://localhost:8000/admin/' 
    : '/admin/';

  return (
    <div className="app">
      <nav className="navbar">
        <div className="navbar-brand">
          <h1>CONCAST Simulator</h1>
          <p>Calculation of Costs and Usage - Results Viewer</p>
        </div>
        <div className="navbar-links">
          <Link to="/">Production Simulations</Link>
          <Link to="/optimizations">Optimizations</Link>
          <Link to="/chiller-simulations">Chiller Simulations</Link>
          <a href={adminUrl} target="_blank" rel="noopener noreferrer">Admin Panel</a>
        </div>
      </nav>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<SimulationsList />} />
          <Route path="/results/:id" element={<ResultsView />} />
          <Route path="/optimizations" element={<OptimizationsList />} />
          <Route path="/optimization-results/:id" element={<OptimizationResultsView />} />
          <Route path="/chiller-simulations" element={<ChillerSimulationsList />} />
          <Route path="/chiller-results/:id" element={<ChillerResultsView />} />
        </Routes>
      </main>

      <footer className="footer">
        <p>© 2025 CONCAST Simulator - Energy Cost & Usage Analysis</p>
      </footer>
    </div>
  );
}

export default App;
