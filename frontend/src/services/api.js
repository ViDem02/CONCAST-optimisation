import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

// The backend uses Django session authentication: send the CSRF token on
// unsafe requests and send unauthenticated users to the login page.
api.defaults.withCredentials = true;
api.defaults.xsrfCookieName = 'csrftoken';
api.defaults.xsrfHeaderName = 'X-CSRFToken';
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const next = window.location.pathname + window.location.search;
      window.location.href = `/admin/login/?next=${encodeURIComponent(next)}`;
    }
    return Promise.reject(error);
  }
);

/** List endpoints are paginated: return the items. */
const items = (response) => response.data.results || response.data;

/** Readable message of a failed request (the backend explains what went wrong). */
export const errorMessage = (err) =>
  err.response?.data?.error || err.response?.data?.message || err.message;

/** Pages of the admin, where data are entered (same address as this website). */
export const adminUrl = (path = '') => `/admin/${path}`;

export const simulationApi = {
  list: () => api.get('/planning/simulations/').then(items),
  get: (id) => api.get(`/planning/simulations/${id}/`).then((r) => r.data),
  run: (id) => api.post(`/planning/simulations/${id}/run/`),
  resultsWithTimesteps: (resultsId) =>
    api.get(`/simulation/simulation-results/${resultsId}/?include_timestep_data=true`).then((r) => r.data),
  exportCsv: (resultsId) =>
    api.get(`/simulation/simulation-results/${resultsId}/export-csv/`, { responseType: 'blob' }),
};

export const optimizationApi = {
  list: () => api.get('/optimizer/optimizations/').then(items),
  get: (id) => api.get(`/optimizer/optimizations/${id}/`).then((r) => r.data),
  run: (id) => api.post(`/optimizer/optimizations/${id}/run/`),
};

export const chillerApi = {
  list: () => api.get('/chillers/chiller-simulations/').then(items),
  get: (id) => api.get(`/chillers/chiller-simulations/${id}/`).then((r) => r.data),
  run: (id) => api.post(`/chillers/chiller-simulations/${id}/run/`),
  exportCsv: (id) => api.get(`/chillers/chiller-simulations/${id}/export_csv/`, { responseType: 'blob' }),
};

export const planApi = {
  list: () => api.get('/planning/production-plans/').then(items),
  get: (id) => api.get(`/planning/production-plans/${id}/`).then((r) => r.data),
};

export const datasetApi = {
  generation: () => api.get('/datasets/generation-datasets/').then(items),
  prices: () => api.get('/datasets/prices-datasets/').then(items),
  temperature: () => api.get('/datasets/temperature-datasets/').then(items),
};

/** Save a file returned by the API. */
export const download = (response, filename) => {
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};

export default api;
