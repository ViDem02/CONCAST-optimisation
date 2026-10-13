# SPARC - Frontend

React website showing the results of SPARC (optimisations, cost simulations, cold rooms,
production plans). Data are entered and calculations are set up in the Django admin, which the
website links to ("Manage data"); lists also have a "Calculate now" button.

In Docker the website is built and served by nginx, which forwards `/api`, `/admin` and `/static`
to the backend (see `nginx.conf`).

## Development

```bash
npm install
npm run dev      # http://localhost:3000, proxies /api, /admin and /static to http://localhost:8000
npm run build    # Output in dist/
```

You need the Django backend running on port 8000 and a user account: the API requires login,
and the website sends you to `/admin/login/` when you are not logged in.

## Structure

- `src/App.jsx`: navigation and routes (`/`, `/plans/:id`, `/optimizations/:id`,
  `/simulations/:id`, `/cold-rooms/:id`)
- `src/services/api.js`: API calls, login redirect, links to the admin
- `src/components/common.jsx`: formatting helpers, page header, "Calculate now" button
- `src/components/ResultsCharts.jsx`: charts of a cost simulation (resolution chosen from the
  length of the period)
- `src/components/ShiftsGantt.jsx`: one week of a production plan
