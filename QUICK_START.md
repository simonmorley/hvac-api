# Quick Start Guide - HVAC Control System

**Current Status**: Phase 2 Complete (Device Communication Layer) ✅

---

## Quick Start (5 minutes)

### 1. Activate Virtual Environment

```bash
cd python-api
source myenv/bin/activate
```

### 2. Set Environment Variables

Create a `.env` file or set in terminal:

```bash
# REQUIRED for sim mode testing
export SIM_MODE=true
export API_KEY="test-key-12345"

# Database (required even in sim mode)
export DATABASE_URL="postgresql+asyncpg://hvac:hvac@localhost:5432/hvac"

# Optional (only needed for real API calls)
export TADO_HOME_ID="12345"
export MELCLOUD_EMAIL="your-email@example.com"
export MELCLOUD_PASSWORD="your-password"
export WEATHER_LAT="51.4184637"
export WEATHER_LON="0.0135339"
```

### 3. Start the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### 4. Test the API

Open another terminal and test the endpoints:

```bash
# Health check (no auth required)
curl http://localhost:8000/healthz

# Test connections (requires API key)
curl -H "x-api-key: test-key-12345" http://localhost:8000/test-connections

# View API docs
open http://localhost:8000/docs
```

**Expected Response** (sim mode):
```json
{
  "tado_ok": true,
  "melcloud_ok": true,
  "weather_ok": true,
  "sim_mode": true,
  "details": {
    "tado": "Connected",
    "melcloud": "Connected",
    "weather": "Connected"
  }
}
```

---

## Running with Real APIs (Production Mode)

### 1. Setup PostgreSQL Database

```bash
# Install PostgreSQL (macOS)
brew install postgresql@14
brew services start postgresql@14

# Create database
createdb hvac
```

### 2. Run Database Migrations

```bash
alembic upgrade head
```

This creates 7 tables for storing secrets, state, logs, etc.

### 3. Disable Sim Mode

```bash
export SIM_MODE=false

# Add real credentials
export TADO_HOME_ID="your-real-home-id"
export MELCLOUD_EMAIL="your-real-email"
export MELCLOUD_PASSWORD="your-real-password"
```

### 4. First-Time Tado OAuth Setup

The Tado API requires OAuth authentication. On first run:

```bash
# Start OAuth flow (returns URL and code)
curl -X POST http://localhost:8000/tado/start

# Visit the URL and enter the code
# Then poll for completion
curl -X POST http://localhost:8000/tado/poll?device_code=YOUR_CODE
```

The refresh token will be stored in the database automatically.

### 5. Test Real Connections

```bash
curl http://localhost:8000/test-connections
```

Should return `sim_mode: false` with actual API connectivity.

---

## Available Endpoints (Phase 2)

### Testing & Health
- `GET /healthz` - Health check (no auth)
- `GET /` - App info
- `GET /test-connections` - Test external API connectivity

### Tado OAuth (coming)
- `POST /tado/start` - Initiate OAuth flow
- `POST /tado/poll` - Poll OAuth completion

---

## Development Tips

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/unit/test_devices/test_tado_sim.py -v

# With coverage
pytest --cov=app tests/
```

All 50 tests should pass in sim mode.

### Viewing Logs

The app uses structured JSON logging. To pretty-print:

```bash
# Run with Python's JSON tool
uvicorn app.main:app --reload 2>&1 | python -m json.tool
```

Or set `LOG_LEVEL=DEBUG` for more detail:

```bash
export LOG_LEVEL=DEBUG
uvicorn app.main:app --reload
```

### Hot Reload

The `--reload` flag automatically restarts the server when you change code:

```bash
# Edit any .py file
vim app/devices/tado_client.py

# Server automatically reloads!
```

### Interactive API Docs

FastAPI provides automatic interactive documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## Troubleshooting

### "No module named 'app'"

Make sure you're in the `python-api` directory and virtual environment is activated:

```bash
cd python-api
source myenv/bin/activate
which python  # Should show myenv path
```

### "Connection refused" to database

If you're just testing with sim mode, the database isn't strictly required for device tests. But the app still needs the DATABASE_URL set:

```bash
export DATABASE_URL="postgresql+asyncpg://hvac:hvac@localhost:5432/hvac"
```

To actually use the database:

```bash
# Start PostgreSQL
brew services start postgresql@14

# Create database if needed
createdb hvac
```

### Port 8000 already in use

```bash
# Kill existing process
lsof -ti:8000 | xargs kill -9

# Or use different port
uvicorn app.main:app --reload --port 8001
```

### Import errors after adding new files

```bash
# Restart the server
# Press CTRL+C and run again:
uvicorn app.main:app --reload
```

---

## What Works Now (Phase 2 Complete)

✅ Device clients with sim mode
✅ Tado OAuth flow (device code)
✅ MELCloud session authentication
✅ Weather API integration
✅ Secrets manager (database-backed)
✅ Test connections endpoint
✅ 50 comprehensive tests

---

## Coming Next (Phase 3)

🔜 Hysteresis control logic
🔜 Equipment protection (cooldowns)
🔜 Schedule evaluation
🔜 Override detection
🔜 Policy engine orchestration

---

## Environment Variables Reference

### Required (Sim Mode)
```bash
SIM_MODE=true
API_KEY=test-key-12345
DATABASE_URL=postgresql+asyncpg://hvac:hvac@localhost:5432/hvac
```

### Required (Production)
```bash
SIM_MODE=false
API_KEY=your-secure-api-key-here
DATABASE_URL=postgresql+asyncpg://hvac:hvac@localhost:5432/hvac
TADO_HOME_ID=123456
MELCLOUD_EMAIL=your-email@example.com
MELCLOUD_PASSWORD=your-password
WEATHER_LAT=51.4184637
WEATHER_LON=0.0135339
```

### Optional
```bash
API_KEY=your-dashboard-api-key
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK
LOG_LEVEL=INFO
POLICY_INTERVAL_MINUTES=15
TZ=Europe/London
```

---

## Quick Commands Cheat Sheet

```bash
# Start server (sim mode)
export SIM_MODE=true API_KEY=test-key && uvicorn app.main:app --reload

# Run tests
pytest -v

# Run specific test
pytest tests/unit/test_devices/test_tado_sim.py::test_tado_turn_on_sim_mode -v

# Check code quality
mypy app/

# View API docs
open http://localhost:8000/docs

# Test connections (with API key)
curl -H "x-api-key: test-key" http://localhost:8000/test-connections | jq

# Database migrations
alembic upgrade head
alembic current
alembic history

# Health check
curl http://localhost:8000/healthz
```

---

**Need More Help?**

- See `README.md` for full documentation
- See `PHASE2_COMPLETE.md` for Phase 2 details
- See `API_SPECIFICATION.md` for complete API reference
- See `.env.example` for all environment variables
