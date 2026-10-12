import axios from 'axios';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// The backend uses Django session authentication: send the CSRF token on
// unsafe requests and send unauthenticated users to the Django login page.
const configureAuth = (client) => {
  client.defaults.withCredentials = true;
  client.defaults.xsrfCookieName = 'csrftoken';
  client.defaults.xsrfHeaderName = 'X-CSRFToken';
  client.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401) {
        const next = window.location.pathname + window.location.search;
        window.location.href = `/admin/login/?next=${encodeURIComponent(next)}`;
      }
      return Promise.reject(error);
    }
  );
};

configureAuth(axios); // Components that call axios directly
configureAuth(api);

// Simulations API
export const simulationApi = {
  // List all simulations
  listSimulations: () => api.get('/planning/simulations/'),
  
  // Get simulation by ID
  getSimulation: (id) => api.get(`/planning/simulations/${id}/`),
  
  // Create new simulation
  createSimulation: (data) => api.post('/planning/simulations/', data),
  
  // Update simulation
  updateSimulation: (id, data) => api.put(`/planning/simulations/${id}/`, data),
  
  // Delete simulation
  deleteSimulation: (id) => api.delete(`/planning/simulations/${id}/`),
  
  // Run simulation calculation
  runSimulation: (id) => api.post(`/planning/simulations/${id}/run/`),
};

// Simulation Results API
export const resultsApi = {
  // List all simulation results
  listResults: () => api.get('/simulation/simulation-results/'),
  
  // Get result by ID (without timestep data)
  getResult: (id) => api.get(`/simulation/simulation-results/${id}/`),
  
  // Get result by ID with timestep data
  getResultWithTimesteps: (id) => api.get(`/simulation/simulation-results/${id}/?include_timestep_data=true`),
  
  // Get only timestep data
  getTimestepData: (id) => api.get(`/simulation/simulation-results/${id}/timestep-data/`),
  
  // Export to CSV
  exportCsv: (id) => api.get(`/simulation/simulation-results/${id}/export-csv/`, {
    responseType: 'blob',
  }),
  
  // Run simulation by ID (alternative endpoint)
  runSimulation: (simulationId) => api.post('/simulation/simulation-results/run-simulation/', {
    simulation_id: simulationId,
  }),
};

// Production Plans API
export const productionPlanApi = {
  // List all production plans
  listPlans: () => api.get('/planning/weekly-production-plans/'),
  
  // Get plan by ID
  getPlan: (id) => api.get(`/planning/weekly-production-plans/${id}/`),
};

// Processes API
export const processApi = {
  // List all processes
  listProcesses: () => api.get('/planning/processes/'),
  
  // Get processes by production plan
  getProcessesByPlan: (planId) => api.get(`/planning/processes/?production_plan=${planId}`),
};

// Chiller Simulations API
export const chillerApi = {
  // List all chiller simulations
  listSimulations: () => api.get('/chillers/chiller-simulations/'),
  
  // Get chiller simulation by ID (with detailed results)
  getSimulation: (id) => api.get(`/chillers/chiller-simulations/${id}/`),
  
  // Create new chiller simulation
  createSimulation: (data) => api.post('/chillers/chiller-simulations/', data),
  
  // Run chiller simulation
  runSimulation: (id) => api.post(`/chillers/chiller-simulations/${id}/run/`),
  
  // Export chiller simulation to CSV
  exportCsv: (id) => api.get(`/chillers/chiller-simulations/${id}/export_csv/`, {
    responseType: 'blob',
  }),
};

export default api;
