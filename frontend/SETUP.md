# Quick Start Guide - CONCAST Simulator Frontend

## Prerequisites Check

Before starting, ensure you have:

✅ Node.js 18+ installed (`node --version`)  
✅ npm installed (`npm --version`)  
✅ Django backend running on http://localhost:8000  
✅ At least one production plan in the database  
✅ Generation and prices datasets imported  

## Installation Steps

### 1. Install Dependencies

```bash
cd simulator_project/frontend
npm install
```

This will install:
- React 18.2.0
- React Router 6.20.0
- Axios 1.6.2
- Recharts 2.10.3
- Vite 5.0.8

### 2. Configure Backend Connection (if needed)

The frontend is pre-configured to connect to `http://localhost:8000`.

If your Django backend runs on a different URL, edit `vite.config.js`:

```javascript
server: {
  proxy: {
    '/api': {
      target: 'http://YOUR_BACKEND_URL:PORT',
      changeOrigin: true,
    }
  }
}
```

### 3. Ensure Django CORS Settings

Add to your Django `settings.py`:

```python
# Install django-cors-headers first:
# pip install django-cors-headers

INSTALLED_APPS = [
    ...
    'corsheaders',
    ...
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Add near the top
    'django.middleware.common.CommonMiddleware',
    ...
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Or for development only:
# CORS_ALLOW_ALL_ORIGINS = True
```

### 4. Start the Development Server

```bash
npm run dev
```

The app will open at: **http://localhost:3000**

## First-Time Setup Workflow

### Step 1: Verify Backend Connection

Open http://localhost:3000 - you should see the simulator interface.

If you see errors, check:
- Django is running: `python manage.py runserver`
- No CORS errors in browser console (F12)

### Step 2: Create Your First Simulation

1. Click **"New Simulation"** in the navigation
2. Fill in:
   - Name: "Test Simulation"
   - Production Plan: Select from dropdown
   - Start Date: e.g., 2024-01-01
   - End Date: e.g., 2024-01-07
3. Click **"Create Simulation"**

### Step 3: Run the Simulation

1. You'll be redirected to the simulation detail page
2. Review the information
3. Click **"Run Simulation"**
4. Wait for calculation (typically 5-30 seconds depending on period)
5. You'll be redirected to the results page

### Step 4: View and Export Results

1. See summary metrics (costs, energy, CO₂)
2. Explore interactive charts
3. Switch chart types and time resolutions
4. Export to CSV for MATLAB analysis

## Common Issues & Solutions

### Issue: "Failed to load simulations"

**Cause**: Backend not running or CORS not configured

**Fix**:
```bash
# In backend terminal
cd simulator_project
python manage.py runserver

# Check Django logs for errors
```

### Issue: "No production plans available"

**Cause**: No production plans in database

**Fix**:
```bash
# Import a production plan via Django command
python manage.py import_production_plan \
  path/to/plan.csv \
  path/to/config.yaml \
  --plan-name "My Plan"

# Or create one in Django admin
# http://localhost:8000/admin/
```

### Issue: "Simulation failed to run"

**Cause**: Missing or incomplete datasets

**Fix**: Ensure you have:
- Generation dataset covering the simulation period
- Prices dataset covering the simulation period
- Check Django backend logs for specific error

Import datasets:
```bash
python manage.py import_generation_records dataset_name generation.csv
python manage.py import_prices_records dataset_name prices.csv
```

### Issue: Charts not displaying

**Cause**: No timestep data or browser compatibility

**Fix**:
- Ensure simulation completed successfully
- Check browser console for errors
- Try a different browser (Chrome, Firefox recommended)

## Development Tips

### Hot Reload

The dev server supports hot module replacement. Changes to React components will automatically reload in the browser.

### Browser DevTools

- Press F12 to open developer tools
- Check Console tab for JavaScript errors
- Check Network tab for API request/response details

### Debugging API Calls

In `src/services/api.js`, the axios instance can be configured with interceptors for debugging:

```javascript
api.interceptors.request.use(request => {
  console.log('Starting Request', request);
  return request;
});

api.interceptors.response.use(response => {
  console.log('Response:', response);
  return response;
});
```

## Production Deployment

### Build for Production

```bash
npm run build
```

This creates optimized files in `dist/` directory.

### Serve Production Build

Option 1: Using a web server (nginx, Apache)
```bash
# Copy dist/ contents to web server root
cp -r dist/* /var/www/html/
```

Option 2: Using Python HTTP server (testing only)
```bash
cd dist
python -m http.server 3000
```

### Environment Variables

For production, configure:
- API base URL (if not on same domain)
- Build optimizations
- CDN paths if needed

## Next Steps

1. ✅ Run your first simulation
2. ✅ Explore different chart visualizations
3. ✅ Export results to CSV for MATLAB
4. 📚 Learn about optimization features (coming soon)
5. 📚 Explore chillers planning (coming soon)

## Support

If you encounter issues:

1. Check this guide first
2. Review Django backend logs
3. Check browser console errors
4. Verify data exists in Django admin
5. Ensure all prerequisites are met

## Additional Resources

- React Documentation: https://react.dev/
- Recharts Documentation: https://recharts.org/
- Vite Documentation: https://vitejs.dev/
- Django REST Framework: https://www.django-rest-framework.org/
