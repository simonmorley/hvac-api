# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python/FastAPI reimplementation of the HVAC control system. Controls Mitsubishi MELCloud AC units and Tado smart radiator thermostats via time-based scheduling, hysteresis deadband control, weather-aware source selection, and manual override detection.

**Status**: New implementation to replace the existing Node.js/Cloudflare Workers backend while maintaining exact API compatibility with the React dashboard frontend.

## Critical Constraints

**IMMUTABLE API CONTRACT**: The dashboard frontend expects exact field names, types, and response formats. See `API_SPECIFICATION.md` for all 39 endpoints with precise schemas. Do NOT change:
- Field names or types in responses
- HTTP status codes
- Error response formats
- Authentication mechanism (x-api-key header)

## Development Commands

```bash
# Activate virtual environment
source myenv/bin/activate  # or myenv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Run development server (FastAPI with hot reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest

# Type checking
mypy app/

# Database migrations
alembic upgrade head                  # Apply migrations
alembic revision --autogenerate -m "description"  # Create new migration
alembic downgrade -1                  # Rollback one migration
```

## Architecture

### Tech Stack
- **FastAPI** - Web framework
- **PostgreSQL** - Primary database (secrets, state, command history, logs)
- **SQLAlchemy** - ORM
- **Alembic** - Database migrations
- **Pydantic** - Data validation and config models
- **httpx** - Async HTTP client for external APIs

### Key Design Decisions

**Database over KV Store**: Unlike the Cloudflare Workers version which uses KV namespaces, this uses PostgreSQL for:
- Secrets storage (Tado tokens, MELCloud sessions)
- System state (policy engine enabled/disabled, last run time)
- Command history (for override detection)
- Append-only logs

**Stateful Architecture**: This implementation runs as a persistent service, not serverless functions. Use background tasks for periodic policy execution instead of cron triggers.

**Async by Default**: All external API calls (Tado, MELCloud, weather) use async/await to prevent blocking.

### Project Structure

```
app/
├── main.py                    # FastAPI app entry point
├── config.py                  # Config loader (reads config.json + env vars)
├── database.py                # DB connection & session management
├── models/
│   ├── config.py              # Pydantic models for config.json structure
│   ├── database.py            # SQLAlchemy ORM models (secrets, state, commands, logs)
│   └── decisions.py           # Decision/command dataclasses (control logic outputs)
├── devices/
│   ├── tado.py                # Tado API client (OAuth2, zone control)
│   ├── melcloud.py            # MELCloud API client (session auth, device control)
│   └── weather.py             # Open-Meteo API client
├── control/
│   ├── hysteresis.py          # Deadband control logic (wantPower function)
│   ├── source_selection.py   # AC vs radiator selection based on outdoor temp
│   └── equipment_protection.py  # Cooldown periods, minimum run times
├── logic/
│   ├── scheduler.py           # Time-based schedule evaluation
│   ├── override_detector.py  # Manual override detection (compare commands vs actual)
│   └── blackout_windows.py   # Schedule blackout handling
├── policy/
│   └── engine.py              # Main policy engine (orchestrates control decisions)
├── routes/
│   ├── health.py              # /healthz, /health
│   ├── config.py              # GET/PUT /config
│   ├── inventory.py           # GET /inventory, GET /rooms
│   ├── control.py             # POST /control, POST /boost
│   ├── policy.py              # POST /apply-policy
│   ├── overrides.py           # Override management endpoints
│   ├── tado_auth.py           # POST /tado/start, POST /tado/poll
│   └── logs.py                # GET /logs
└── utils/
    ├── logging.py             # Structured logging setup
    └── auth.py                # API key validation middleware

tests/
├── fixtures/                  # Sample configs, mocked API responses
├── test_hysteresis.py
├── test_scheduler.py
├── test_override_detection.py
└── test_api_compatibility.py  # Validates responses match API_SPECIFICATION.md

alembic/
└── versions/                  # Migration files
```

## Core Control Logic

### Policy Engine Flow (`app/policy/engine.py`)

1. **Check if enabled**: Read `system_state.policy_enabled` from database
2. **Check blackout windows**: Skip execution if current time falls within blackout
3. **Load configuration**: Merge config.json + environment variable defaults
4. **Fetch external data**:
   - Weather API → outdoor temperature
   - MELCloud API → current AC unit states (temp, power, mode)
   - Tado API → current zone states (temp, heating, overlay)
5. **Evaluate schedules**: For each room, calculate target setpoint from time-based schedule
6. **Detect overrides**: Compare last command sent vs current device state
   - If mismatch AND last command was >5 minutes ago → manual override detected
   - Pause automation for that device (1 hour hold)
7. **Apply hysteresis control**: For non-overridden devices:
   - Turn ON if: `room_temp <= (setpoint - deadband)`
   - Turn OFF if: `room_temp >= (setpoint + deadband)`
   - Otherwise: maintain current state
8. **Equipment protection checks**:
   - Enforce minimum 5-minute cooldown between AC power cycles
   - Enforce minimum 10-minute run time for AC (don't turn off prematurely)
9. **Send commands**: Call Tado/MELCloud APIs with new settings
10. **Record commands**: Insert into `device_commands` table with timestamp
11. **Log actions**: Insert into `logs` table
12. **Send notifications**: Slack webhook on state changes

### Hysteresis Control (`app/control/hysteresis.py`)

**Purpose**: Prevent rapid on/off cycling (flickering) by using a deadband around the setpoint.

```python
def want_power(current_temp: float, setpoint: float, current_power: bool, deadband: float = 0.5) -> bool:
    """
    Returns True if heating should be ON, False if OFF.

    Uses hysteresis:
    - Turn ON if temp drops to (setpoint - deadband)
    - Turn OFF if temp rises to (setpoint + deadband)
    - Maintain current state if within deadband
    """
    if current_temp <= setpoint - deadband:
        return True
    elif current_temp >= setpoint + deadband:
        return False
    else:
        return current_power  # Keep current state
```

**Deadband Default**: 0.5°C (configurable via `AC_DEADBAND` env var)

### Override Detection (`app/logic/override_detector.py`)

**How it Works**:
1. Before sending command, record it in `device_commands` table
2. On next policy run, fetch device's actual state from API
3. Compare: did our last command succeed?
   - If YES → continue automation
   - If NO AND >5 minutes passed → user manually changed it → pause automation
4. Insert override record with 1-hour expiry
5. Skip automated control for that device until override expires

**Why 5 minutes?**: Allows for API propagation delays and device response time.

### Source Selection (`app/control/source_selection.py`)

**Rules**:
- If room has AC AND outdoor temp >= `ac_min_outdoor_c` (default 2°C) → use AC
- Else if room has Tado zone (not excluded) → use radiator
- Skip devices in exclusion lists (`config.exclude.tado`, `config.exclude.mel`)

### Schedule Types (`app/logic/scheduler.py`)

**three-period**: Day/Eve/Night
```json
{
  "type": "three-period",
  "day": 17,
  "eve": 19,
  "night": 16,
  "day_start": "07:00",
  "eve_start": "18:00",
  "eve_end": "22:00"
}
```

**four-period**: Morning/Day/Evening/Night (for living spaces)
```json
{
  "type": "four-period",
  "morning": 21,
  "day": 18,
  "evening": 19,
  "night": 16,
  "morning_start": "07:00",
  "morning_end": "08:00",
  "evening_start": "17:30",
  "evening_end": "22:00"
}
```

**workday**: Office hours
```json
{
  "type": "workday",
  "work": 20,
  "idle": 17,
  "start": "08:00",
  "end": "20:00"
}
```

**simple**: Static setpoint (for zones like hallways)
```json
{
  "type": "simple",
  "setpoint": 17
}
```

## External API Integration

### Tado API (`app/devices/tado.py`)

**Authentication**: OAuth2 Device Code Flow + Refresh Token Rotation

**CRITICAL**: Tado uses refresh token rotation - every refresh invalidates the old token. Use database locking to prevent concurrent refresh attempts.

```python
# Refresh token flow (use for all authentications)
POST https://login.tado.com/oauth2/token
Body: client_id=1bb50063-6b0c-4d11-bd99-387f4a91cc46
      grant_type=refresh_token
      refresh_token=<STORED_REFRESH_TOKEN>

Response:
{
  "access_token": "eyJ...",
  "refresh_token": "new_refresh_token",  # OLD TOKEN NOW INVALID
  "expires_in": 599
}

# MUST store new refresh_token immediately in database
```

**Key Endpoints**:
- `GET /api/v2/homes/{HOME_ID}/zones` - List zones
- `GET /api/v2/homes/{HOME_ID}/zones/{ZONE_ID}/state` - Get current state
- `PUT /api/v2/homes/{HOME_ID}/zones/{ZONE_ID}/overlay` - Set temperature overlay

**Overlay Structure** (for setting temperature):
```json
{
  "setting": {
    "type": "HEATING",
    "power": "ON",
    "temperature": {"celsius": 21.0}
  },
  "termination": {
    "type": "TIMER",
    "durationInSeconds": 3600
  }
}
```

### MELCloud API (`app/devices/melcloud.py`)

**Authentication**: Session-based (login returns ContextKey)

```python
POST https://app.melcloud.com/Mitsubishi.Wifi.Client/Login/ClientLogin
Body: {"Email": "...", "Password": "...", "AppVersion": "1.32.1.0"}

Response: {"LoginData": {"ContextKey": "..."}}

# Use ContextKey in X-MitsContextKey header for all subsequent requests
```

**Device Hierarchy**: Site → Building → Structure → Devices

Helper function `collectMelUnits()` flattens this nested structure into a list.

**Control Payload** (use `buildMelPayload()` helper):
```json
{
  "DeviceID": 12345,
  "EffectiveFlags": 3,  # Bitmask: Power(1) + SetTemperature(2) + Mode(4) + Fan(8) + Vanes(16)
  "Power": true,
  "SetTemperature": 21.0,
  "OperationMode": 1,   # 1=heat, 2=cool, 3=dry, 7=fan, 8=auto
  "SetFanSpeed": 0,     # 0=auto, 1-5=speed
  "VaneHorizontal": 0,  # 0=auto, 12=swing
  "VaneVertical": 0,    # 0=auto, 7=swing
  "HasPendingCommand": true
}
```

**Important**: Ducted AC units don't support vane control - set `vanes: false` in config.

### Weather API (`app/devices/weather.py`)

**Provider**: Open-Meteo (free, no auth required)

```python
GET https://api.open-meteo.com/v1/forecast
Params: latitude={lat}&longitude={lon}&current=temperature_2m

Response: {"current": {"temperature_2m": 12.5}}
```

## Database Schema

### `secrets` Table
```sql
CREATE TABLE secrets (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Keys: 'tado_refresh_token', 'melcloud_context_key', 'slack_webhook'
```

### `system_state` Table
```sql
CREATE TABLE system_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Keys: 'policy_enabled' (true/false), 'last_policy_run' (ISO timestamp)
```

### `device_commands` Table
```sql
CREATE TABLE device_commands (
    id SERIAL PRIMARY KEY,
    device_name TEXT NOT NULL,
    device_type TEXT NOT NULL,  -- 'ac' or 'tado'
    command JSONB NOT NULL,     -- Full command payload
    timestamp TIMESTAMP DEFAULT NOW(),
    INDEX idx_device_time (device_name, timestamp DESC)
);
```

### `device_overrides` Table
```sql
CREATE TABLE device_overrides (
    device_name TEXT PRIMARY KEY,
    detected_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    reason TEXT
);
```

### `logs` Table
```sql
CREATE TABLE logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    level TEXT NOT NULL,  -- 'info', 'warn', 'error'
    message TEXT NOT NULL,
    metadata JSONB
);
```

## Configuration Management

Configuration is loaded from `config.json` with environment variable fallbacks:

**Environment Variables**:
- `API_KEY` - API authentication key (required)
- `DATABASE_URL` - PostgreSQL connection string (required)
- `MELCLOUD_EMAIL`, `MELCLOUD_PASSWORD` - MELCloud credentials (required)
- `TADO_HOME_ID` - Tado home ID (required)
- `SLACK_WEBHOOK_URL` - Notification webhook (optional)
- `TZ` - Timezone for schedule calculations (default: Europe/London)
- `AC_DEADBAND` - Hysteresis deadband in °C (default: 0.5)
- `POLICY_INTERVAL_MINUTES` - How often to run policy engine (default: 15)

**Config Merging**: `app/config.py` loads config.json and fills missing fields from env vars.

## Testing Requirements

**API Compatibility Tests** (`tests/test_api_compatibility.py`):
- For EVERY endpoint in API_SPECIFICATION.md, validate:
  - Response field names match exactly
  - Response types match (string, number, boolean, array, object)
  - HTTP status codes match
  - Error responses have correct format

**Control Logic Tests**:
- `test_hysteresis.py` - Verify deadband behavior (ON/OFF thresholds)
- `test_scheduler.py` - Test all schedule types with various times
- `test_override_detection.py` - Verify override detection logic
- `test_equipment_protection.py` - Verify cooldown and minimum run time enforcement

**Integration Tests**:
- Mock external APIs (Tado, MELCloud, Weather)
- Test full policy engine execution flow
- Verify command recording and override detection

## Common Gotchas

1. **Tado refresh token rotation** - Always store new refresh token immediately after refresh
2. **MELCloud EffectiveFlags** - Must include bitmask of all fields being changed
3. **Ducted AC units** - Set `vanes: false` in config or API calls fail
4. **Override detection timing** - 5-minute grace period before detecting overrides
5. **Database sessions** - Always use dependency injection for DB sessions, never create global session
6. **Async/await consistency** - All external API calls must be async
7. **Equipment protection** - Never skip cooldown checks, even in manual control endpoints
8. **Timezone handling** - Always use configured TZ env var for schedule calculations
9. **Exclusion lists** - Check before controlling ANY device
10. **API compatibility** - Never change response field names without updating dashboard code

## Background Task Management

Use FastAPI BackgroundTasks for periodic policy execution:

```python
from fastapi import BackgroundTasks
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup_event():
    scheduler.add_job(
        run_policy_engine,
        'interval',
        minutes=int(os.getenv('POLICY_INTERVAL_MINUTES', '15'))
    )
    scheduler.start()
```

## Security Notes

- Store all secrets in `secrets` table, never in code or config.json
- Use environment variables for initial bootstrap credentials only
- API_KEY validation on all routes except /healthz
- No CORS restrictions (dashboard is separate domain)
- Log all device commands for audit trail
- Rate limit external API calls to prevent account lockout

## References

- `API_SPECIFICATION.md` - Complete API specification with exact schemas
- `HVAC_REQUIREMENTS.md` - Detailed system requirements and control logic
- `config.json` - Example configuration structure
- `prompt1.md` - Phase 1 implementation guide (foundation layer)
