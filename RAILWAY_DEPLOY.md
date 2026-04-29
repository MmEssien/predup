# Railway Deployment Guide

## Files Created/Updated

- `Procfile` - Railway web process command
- `railway.json` - Railway project configuration
- `.env.railway.example` - Environment variables template
- `src/api/main.py` - Updated CORS for production

---

## Step 1: Connect GitHub Repository

1. Go to https://railway.app/
2. Sign up/Login
3. Click **"New Project"**
4. Select **"Deploy from GitHub repo"**
5. Choose your PredUp repository
6. Click **"Deploy Now"**

---

## Step 2: Add PostgreSQL Database

1. In Railway dashboard, click **"Add Plugin"**
2. Search for **"PostgreSQL"**
3. Click **"Add Database"**
4. Wait for it to provision (green status)

---

## Step 3: Configure Environment Variables

In Railway project settings, add these variables:

| Variable | Value |
|----------|-------|
| `APP_ENV` | `production` |
| `LOG_LEVEL` | `INFO` |
| `PORT` | `8000` |
| `ODDS_API_KEY` | `dca7069462322213519c88f447526adc` |
| `SPORTSGAMEODDS_KEY` | `47a8f5cb3d3e693009505ff6aa54488f` |
| `MIN_CONFIDENCE_THRESHOLD` | `0.75` |
| `ENSEMBLE_WEIGHT_XGB` | `0.4` |
| `ENSEMBLE_WEIGHT_LGBM` | `0.4` |
| `ENSEMBLE_WEIGHT_LOGREG` | `0.2` |

**Note:** `DATABASE_URL` will be automatically set by Railway PostgreSQL plugin.

---

## Step 4: Deploy

1. Click **"Deploy"** button in Railway dashboard
2. Wait for build and deployment to complete
3. Check the **"Deployments"** tab for status

---

## Step 5: Verify Endpoints

After deployment, test these URLs:

```bash
# Replace YOUR_PROJECT with your Railway project name
https://YOUR_PROJECT.up.railway.app/api/v1/dashboard
https://YOUR_PROJECT.up.railway.app/api/v1/predictions/live
https://YOUR_PROJECT.up.railway.app/api/v1/health
https://YOUR_PROJECT.up.railway.app/docs
```

---

## Troubleshooting

### Build Fails
- Check Dockerfile syntax
- Ensure all dependencies in requirements.txt are correct

### Database Connection Error
- Verify PostgreSQL plugin is added
- Check DATABASE_URL is set automatically

### CORS Errors
- Frontend URL must be in allowed_origins in main.py
- Current allowed: `http://localhost:3000`, `https://predup.vercel.app`

### 500 Internal Server Error
- Check Railway logs for error details
- Verify all environment variables are set

---

## Important Notes

1. **Railway uses PORT env variable** - The Procfile uses `$PORT`
2. **PostgreSQL** - Railway provides DATABASE_URL automatically
3. **CORS** - Only allows specific origins, not "*"
4. **Models** - The models/ folder is included in Docker build

---

## Quick Deploy via CLI (Alternative)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Init project
cd PredUp
railway init

# Add PostgreSQL
railway add postgresql

# Deploy
railway up
```

---

## Expected Output

After successful deployment, you should see:
- Backend API at: `https://api-predup.up.railway.app`
- API Docs at: `https://api-predup.up.railway.app/docs`
- Health check: `{"status": "healthy", "service": "predup"}`