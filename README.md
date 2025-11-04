# HVAC Control System - Python/FastAPI Implementation

Python/FastAPI reimplementation of the HVAC control system. Controls Mitsubishi MELCloud AC units and Tado smart radiator thermostats via time-based scheduling, hysteresis deadband control, weather-aware source selection, and manual override detection.

**Status**: Phase 1 (Foundation) - Basic project structure complete

## Features

- **Time-based scheduling** - Four schedule types: three-period, four-period, workday, simple
- **Hysteresis control** - Deadband logic prevents rapid on/off cycling
- **Weather-aware source selection** - AC vs radiator based on outdoor temperature
- **Manual override detection** - Pause automation when user manually changes devices
- **Equipment protection** - Cooldown timers and minimum run times
- **PostgreSQL storage** - Secrets, state, command history, structured logs
- **RESTful API** - 39 endpoints maintaining compatibility with React dashboard frontend

## Tech Stack

- **FastAPI** - Modern async web framework
- **PostgreSQL** - Primary database
- **SQLAlchemy 2.0+** - Async ORM
- **Alembic** - Database migrations
- **Pydantic v2** - Data validation
- **structlog** - Structured JSON logging
- **httpx** - Async HTTP client

## Project Structure

```
python-api/
├── app/
│   ├── main.py                    # FastAPI application entry point
│   ├── config.py                  # Configuration loader
│   ├── database.py                # Database connection & sessions
│   ├── models/
│   │   ├── config.py              # Pydantic models for config.json
│   │   └── database.py            # SQLAlchemy ORM models
│   ├── devices/                   # External API clients (Tado, MELCloud, Weather)
│   ├── control/                   # Control logic (hysteresis, source selection)
│   ├── logic/                     # Scheduling, override detection
│   ├── policy/                    # Policy engine orchestration
│   ├── routes/                    # API endpoints
│   └── utils/
│       └── logging.py             # Structured logging setup
├── tests/
│   ├── fixtures/
│   │   └── sample_config.json
│   └── test_config.py
├── alembic/
│   └── versions/                  # Database migration files
├── requirements.txt
├── .env.example
└── README.md
```

## Setup Instructions

### 1. Prerequisites

- Python 3.12+
- PostgreSQL 14+
- Virtual environment (recommended)

### 2. Create Virtual Environment

```bash
python3 -m venv myenv
source myenv/bin/activate  # On Windows: myenv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://hvac:hvac@localhost:5432/hvac

# API Keys
API_KEY=your-dashboard-api-key-here

# External APIs
MELCLOUD_EMAIL=your-email@example.com
MELCLOUD_PASSWORD=your-password
TADO_CLIENT_ID=1bb50063-6b0c-4d11-bd99-387f4a91cc46
TADO_HOME_ID=123456

# Notifications (optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Application
SIM_MODE=false
LOG_LEVEL=INFO
POLICY_INTERVAL_MINUTES=15
TZ=Europe/London
```

### 5. Database Setup

Create PostgreSQL database and user:

```bash
# Connect to PostgreSQL
psql postgres

# Create user and database
CREATE USER hvac WITH PASSWORD 'hvac';
CREATE DATABASE hvac OWNER hvac;
\q
```

Run Alembic migrations:

```bash
alembic upgrade head
```

This creates 7 tables:
- `secrets` - API tokens and credentials
- `system_state` - Policy engine state
- `device_commands` - Command history
- `device_overrides` - Active manual overrides
- `device_cooldowns` - Compressor protection timers
- `config_store` - Active configuration JSON
- `logs` - Structured logging

### 6. Configuration File

Create `config.json` in project root (or it will be loaded from database):

```json
{
  "exclude": {
    "tado": ["Hot Water"],
    "mel": []
  },
  "ac_defaults": {
    "mode": "heat",
    "fan": "auto",
    "vaneH": "auto",
    "vaneV": "auto",
    "vanes": true
  },
  "rooms": {
    "Master": {
      "tado": "Main Bed",
      "mel": "Master bedroom",
      "floor": "upstairs",
      "schedule": {
        "type": "three-period",
        "day": 17,
        "eve": 19,
        "night": 16,
        "day_start": "07:00",
        "eve_start": "18:00",
        "eve_end": "22:00"
      }
    }
  },
  "targets": {
    "spare": 17
  },
  "pv": {
    "boost_threshold_w": 600,
    "boost_delta_c": 0.5
  },
  "blackout_windows": [],
  "weather": {
    "lat": 51.4184637,
    "lon": 0.0135339,
    "provider": "open-meteo"
  },
  "thresholds": {
    "ac_min_outdoor_c": 2.0
  }
}
```

See `tests/fixtures/sample_config.json` for a complete example.

## Running the Application

### Development Server

```bash
# Activate virtual environment
source myenv/bin/activate

# Run with hot reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

### Health Check

```bash
curl http://localhost:8000/healthz
```

Expected response:
```json
{"ok": true}
```

## Testing

Run tests with pytest:

```bash
# Install test dependencies (already in requirements.txt)
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_config.py

# Run with coverage
pytest --cov=app tests/
```

## Database Migrations

### Create New Migration

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "Description of changes"

# Create empty migration
alembic revision -m "Description"
```

### Apply Migrations

```bash
# Upgrade to latest
alembic upgrade head

# Upgrade one version
alembic upgrade +1

# Downgrade one version
alembic downgrade -1
```

### View Migration History

```bash
alembic current
alembic history
```

## Development Workflow

1. **Make changes** to code in `app/`
2. **Update database models** if needed (`app/models/database.py`)
3. **Create migration** if models changed: `alembic revision --autogenerate -m "description"`
4. **Run tests**: `pytest`
5. **Run app**: `uvicorn app.main:app --reload`
6. **Test endpoints**: `curl http://localhost:8000/healthz`

## Configuration Management

Configuration is loaded with this priority:

1. Database (`config_store` table)
2. `config.json` file in project root
3. Environment variable defaults

Use the ConfigManager:

```python
from app.config import ConfigManager
from app.database import get_db

async with get_db() as db:
    cm = ConfigManager(db)
    config = await cm.load_config()
    print(config.rooms)
```

## Logging

The app uses structured JSON logging via structlog:

```python
from app.utils.logging import get_logger

log = get_logger(__name__)

log.info("config_loaded", rooms=5, outdoor_provider="open-meteo")
log.warning("device_timeout", device="Master bedroom", timeout_ms=5000)
log.error("api_call_failed", api="tado", error="401 Unauthorized")
```

Output format:
```json
{"event": "config_loaded", "level": "info", "timestamp": "2025-11-03T22:00:00Z", "rooms": 5, "outdoor_provider": "open-meteo"}
```

## API Endpoints (Phase 1 - Foundation Only)

Currently implemented:

- `GET /healthz` - Health check (no auth required)
- `GET /` - Basic app info

**Coming in Phase 2+**: 37 more endpoints for device control, policy management, override handling, etc.

## External API Integration (Coming Soon)

### Tado API
- OAuth2 device code flow + refresh token rotation
- Zone control with timer-based overlays

### MELCloud API
- Session-based authentication
- Device control with proper EffectiveFlags bitmask

### Weather API
- Open-Meteo (free, no auth)
- Provides outdoor temperature for source selection

## Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL is running
psql -U hvac -d hvac -c "SELECT 1"

# Verify DATABASE_URL in .env
echo $DATABASE_URL
```

### Import Errors

```bash
# Ensure virtual environment is activated
source myenv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Migration Issues

```bash
# Check current migration version
alembic current

# View migration history
alembic history

# Reset to specific version
alembic downgrade <revision>
```

## Project Phases

### ✅ Phase 1: Foundation (Current)
- [x] Project structure
- [x] Database schema (7 tables)
- [x] Configuration models (Pydantic)
- [x] Database utilities (SQLAlchemy async)
- [x] Basic FastAPI app
- [x] Structured logging
- [x] Alembic migrations
- [x] Basic tests

### Phase 2: External APIs
- [ ] Tado OAuth client
- [ ] MELCloud session client
- [ ] Weather API client
- [ ] Retry logic and error handling

### Phase 3: Core Control Logic
- [ ] Hysteresis control (wantPower)
- [ ] Equipment protection (cooldowns)
- [ ] Source selection
- [ ] Schedule evaluation

### Phase 4: Policy Engine
- [ ] Override detection
- [ ] Policy orchestrator
- [ ] Blackout window checking
- [ ] Background task scheduling

### Phase 5: API Endpoints
- [ ] All 39 endpoints
- [ ] API compatibility tests
- [ ] Authentication middleware

## Documentation

- `API_SPECIFICATION.md` - Complete API specification (39 endpoints)
- `HVAC_REQUIREMENTS.md` - Detailed system requirements
- `TECHNICAL_DESIGN_DOCUMENT.md` - Technical design details
- `CLAUDE.md` - Project-specific AI assistant guidance

## Contributing

1. Create feature branch from `main`
2. Make changes with tests
3. Run `pytest` to verify
4. Create pull request

## License

Private project - All rights reserved

## Support

For issues or questions, see project documentation in the repository root.
