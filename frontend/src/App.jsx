import React from 'react';
import { Link, Navigate, NavLink, Route, Routes } from 'react-router-dom';
import Home from './components/Home';
import OptimizationsList from './components/OptimizationsList';
import OptimizationResultsView from './components/OptimizationResultsView';
import SimulationsList from './components/SimulationsList';
import SimulationResultsView from './components/SimulationResultsView';
import ChillerSimulationsList from './components/ChillerSimulationsList';
import ChillerResultsView from './components/ChillerResultsView';
import PlansList from './components/PlansList';
import { adminUrl } from './services/api';
import './styles/App.css';

function App() {
  return (
    <div className="app">
      <nav className="navbar">
        <Link to="/" className="navbar-brand">
          <img src="/sparc-logo.png" alt="" />
          <div>
            <h1>SPARC</h1>
            <p>Energy-aware production planning · CONCAST</p>
          </div>
        </Link>
        <div className="navbar-links">
          <NavLink to="/" end>Home</NavLink>
          <NavLink to="/plans">Production plans</NavLink>
          <NavLink to="/optimizations">Optimisations</NavLink>
          <NavLink to="/simulations">Cost simulations</NavLink>
          <NavLink to="/cold-rooms">Cold rooms</NavLink>
          <a href={adminUrl()} className="manage-link">Manage data</a>
        </div>
      </nav>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/plans" element={<PlansList />} />
          <Route path="/plans/:id" element={<PlansList />} />
          <Route path="/optimizations" element={<OptimizationsList />} />
          <Route path="/optimizations/:id" element={<OptimizationResultsView />} />
          <Route path="/simulations" element={<SimulationsList />} />
          <Route path="/simulations/:id" element={<SimulationResultsView />} />
          <Route path="/cold-rooms" element={<ChillerSimulationsList />} />
          <Route path="/cold-rooms/:id" element={<ChillerResultsView />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <footer className="footer">
        <p>SPARC · Simulation, Production Analysis &amp; Refrigeration Control</p>
      </footer>
    </div>
  );
}

export default App;
