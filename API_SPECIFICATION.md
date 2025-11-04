# HVAC Control System - Complete API Specification

This document specifies all HTTP endpoints that the dashboard connects to, with exact request/response schemas for compatibility.

**Base URL**: `${VITE_API_BASE}` (e.g., `https://hvac.example.workers.dev`)  
**Authentication**: All endpoints except `/healthz` require `x-api-key` header with API_KEY value  
**Content-Type**: `application/json` for POST/PUT requests

---

## Table of Contents

1. [Health & Status](#health--status)
2. [Configuration](#configuration)
3. [Inventory & Device Discovery](#inventory--device-discovery)
4. [Room Control](#room-control)
5. [Policy Management](#policy-management)
6. [Room State Management](#room-state-management)
7. [Mode Controls (Away, Eco)](#mode-controls-away-eco)
8. [Tado Authentication](#tado-authentication)
9. [Monitoring & Logs](#monitoring--logs)
10. [Override Management](#override-management)
11. [Admin Operations](#admin-operations)

---

## Health & Status

### GET /healthz

**Authentication**: None required

**Response (200 OK)**:
```json
{
  "ok": true
}
```

---

### GET /health

**Authentication**: Required

**Response (200 OK)**:
```json
{
  "ok": true,
  "timestamp": "2024-01-01T12:00:00.000Z",
  "services": {
    "kv": {
      "CONFIG": true,
      "STATE": true,
      "LOGS": true
    },
    "stateTracker": "simple"
  }
}
```

---

## Configuration

### GET /config

Retrieve current HVAC configuration from server.

**Authentication**: Required (x-api-key header)

**Response (200 OK)**:
```json
{
  "exclude": {
    "tado": ["Hot Water", "Bathroom"],
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
    "downstairs": {
      "tado": "Living Room",
      "mel": ["Downstairs AC Unit 1"],
      "mel_multi": ["Downstairs AC Unit 1"],
      "ac": {
        "mode": "heat",
        "fan": "auto",
        "vaneH": "auto",
        "vaneV": "auto",
        "vanes": true
      }
    },
    "master": {
      "tado": "Master Bedroom",
      "mel": "Master AC",
      "ac": {
        "mode": "heat",
        "fan": "auto"
      }
    }
  },
  "targets": {
    "spare": 16
  },
  "pv": {
    "boost_threshold_w": 600,
    "boost_delta_c": 0.5
  },
  "blackout_windows": [],
  "weather": {
    "lat": 51.5074,
    "lon": -0.1278,
    "provider": "open-meteo"
  },
  "thresholds": {
    "ac_min_outdoor_c": 2
  }
}
```

**Error Response (401)**:
```json
{
  "ok": false,
  "error": "unauthorized"
}
```

---

### PUT /config

Update HVAC configuration. Accepts partial or complete config object. Server merges with defaults.

**Authentication**: Required (x-api-key header)

**Request Body**:
```json
{
  "ac_defaults": {
    "mode": "heat",
    "fan": "auto"
  },
  "rooms": {
    "downstairs": {
      "ac": {
        "mode": "cool"
      }
    }
  }
}
```

**Response (200 OK)**:
```json
{
  "ok": true
}
```

**Error Response (400)**:
```json
{
  "ok": false,
  "error": "invalid body"
}
```

---

## Inventory & Device Discovery

### GET /inventory

List all available rooms with their device mappings and available Tado zones/MELCloud units.

**Authentication**: Required (x-api-key header)

**Response (200 OK)**:
```json
{
  "rooms": [
    {
      "key": "downstairs",
      "tado": "Living Room",
      "mel": ["Downstairs AC"],
      "mel_multi": ["Downstairs AC"],
      "hasRad": true,
      "hasAC": true
    },
    {
      "key": "master",
      "tado": "Master Bedroom",
      "mel": "Master AC",
      "hasRad": true,
      "hasAC": true
    },
    {
      "key": "kids",
      "tado": null,
      "mel": "Kids AC",
      "hasRad": false,
      "hasAC": true
    }
  ],
  "tado_zones": [
    "Living Room",
    "Master Bedroom",
    "Hot Water",
    "Bathroom"
  ],
  "mel_units": [
    "Downstairs AC",
    "Master AC",
    "Kids AC"
  ]
}
```

---

### GET /rooms

List available Tado zones and MELCloud units (simpler version of /inventory).

**Authentication**: Required (x-api-key header)

**Response (200 OK)**:
```json
{
  "tado_zones": [
    "Living Room",
    "Master Bedroom",
    "Hot Water",
    "Bathroom"
  ],
  "mel_units": [
    "Downstairs AC",
    "Master AC",
    "Kids AC"
  ]
}
```

---

### GET /test-connections

Test connectivity to Tado, MELCloud, and PV APIs.

**Authentication**: Required (x-api-key header)

**Response (200 OK)**:
```json
{
  "tado_ok": true,
  "mel_ok": true,
  "pv_ok": true,
  "pv_watts": 1250,
  "zones": [
    "Living Room",
    "Master Bedroom"
  ],
  "units": [
    "Downstairs AC",
    "Master AC"
  ]
}
```

**Error Response (500)**:
```json
{
  "ok": false,
  "error": "Failed to connect to Tado: authentication failed"
}
```

---

## Room Control

### POST /control

Execute manual control action on rooms (heat or turn off). Supports per-room or whole-house control with optional temperature setpoint override.

**Authentication**: Required (x-api-key header)

**Query Parameters** (or Body JSON):
- `rooms` (required): Single room name, comma-separated list, or "all"
- `room` (alternative to rooms): Single room name
- `action` (required): "heat" or "off"
- `setpoint` (optional): Absolute target temperature (Celsius)
- `delta` (optional): Temperature boost above scheduled setpoint
- `minutes` (optional, default: 60): Duration of control (max: 360)
- `device` (optional, default: "auto"): "auto", "ac", "rad", or "tado"
- `mode`, `fan`, `vaneH`, `vaneV`, `vanes` (optional): AC-specific options

**Request Body (Example)**:
```json
{
  "rooms": "downstairs,master",
  "action": "heat",
  "setpoint": 23,
  "minutes": 30,
  "device": "ac",
  "mode": "heat",
  "fan": "auto"
}
```

**Response (200 OK)**:
```json
{
  "ok": true,
  "summary": "Controlled 2 rooms",
  "results": [
    {
      "room": "downstairs",
      "device": "ac",
      "action": "heat",
      "setpoint": 23
    },
    {
      "room": "master",
      "device": "ac",
      "action": "heat",
      "setpoint": 23
    }
  ]
}
```

**Error Response (400)**:
```json
{
  "ok": false,
  "error": "missing room/rooms parameter"
}
```

**Error Response (404)**:
```json
{
  "ok": false,
  "error": "No rooms found matching: downstairs,invalid"
}
```

**Error Response (429)**:
```json
{
  "ok": false,
  "error": "Cooldown protection: device changed recently"
}
```

---

## Policy Management

### GET /policy-enabled

Check if automated policy engine is enabled.

**Authentication**: Required (x-api-key header)

**Response (200 OK)**:
```json
{
  "enabled": true
}
```

---

### POST /policy-enabled

Enable or disable automated policy engine.

**Authentication**: Required (x-api-key header)

**Request Body**:
```json
{
  "enabled": false
}
```

**Response (200 OK)**:
```json
{
  "ok": true,
  "enabled": false
}
```

**Error Response (400)**:
```json
{
  "ok": false,
  "error": "body must contain {enabled: boolean}"
}
```

---

### POST /apply-policy

Manually trigger the policy engine (normally runs every 15 minutes via cron).

**Authentication**: Required (x-api-key header)

**Request Body**: None (empty POST)

**Response (200 OK)**:
```json
{
  "ok": true,
  "summary": "Applied policy to 4 rooms",
  "errors": [],
  "timestamp": "2024-01-01T12:00:00.000Z"
}
```

**Response (200 OK - Policy Disabled)**:
```json
{
  "ok": false,
  "reason": "policy disabled"
}
```

**Error Response (500)**:
```json
{
  "ok": false,
  "error": "Failed to fetch device status from MELCloud"
}
```

---

## Room State Management

### GET /status

Get current state of all rooms (temperature, setpoint, power state, etc.).

**Authentication**: Required (x-api-key header)

**Response (200 OK)**:
```json
{
  "rooms": [
    {
      "name": "downstairs",
      "temp": 19.5,
      "setpoint": 21,
      "scheduledTarget": 21,
      "heatingPercent": 75,
      "acPower": true,
      "source": "ac",
      "activeSource": "ac",
      "hasRad": true,
      "hasAC": true,
      "disabled": false,
      "floor": "downstairs"
    },
    {
      "name": "master",
      "temp": 18.2,
      "setpoint": 20,
      "scheduledTarget": 20,
      "heatingPercent": 60,
      "acPower": false,
      "source": "tado",
      "activeSource": "none",
      "hasRad": true,
      "hasAC": false,
      "disabled": false,
      "floor": "upstairs"
    }
  ]
}
```

**Field Definitions**:
- `name`: Room identifier (matches config keys)
- `temp`: Current room temperature from Tado/MELCloud (null if unavailable)
- `setpoint`: Currently targeted temperature from policy
- `scheduledTarget`: Scheduled setpoint from time-based schedule
- `heatingPercent`: Tado radiator heating level (0-100)
- `acPower`: AC unit on/off state (true = on)
- `source`: Policy-calculated optimal source ("ac", "tado", or "none")
- `activeSource`: Currently active heating source (populated by status endpoint)
- `hasRad`: Room has Tado radiator
- `hasAC`: Room has MELCloud AC unit
- `disabled`: Room is excluded from policy control (manual disable)
- `floor`: Floor classification ("upstairs", "downstairs", or null)

---

### POST /rooms/:room/disable

Disable a room from automated policy control temporarily.

**Authentication**: Required (x-api-key header)

**Path Parameters**:
- `room`: Room name (e.g., "downstairs", "master")

**Query Parameters**:
- `minutes` (optional, default: 60): Duration to disable (5 min to 24 hours)

**Response (200 OK)**:
```json
{
  "ok": true,
  "room": "downstairs",
  "disabled": true,
  "minutes": 60
}
```

---

### POST /rooms/:room/enable

Re-enable a previously disabled room.

**Authentication**: Required (x-api-key header)

**Path Parameters**:
- `room`: Room name (e.g., "downstairs", "master")

**Response (200 OK)**:
```json
{
  "ok": true,
  "room": "downstairs",
  "disabled": false
}
```

---

### GET /rooms/:room/disabled

Check if a room is currently disabled.

**Authentication**: Required (x-api-key header)

**Path Parameters**:
- `room`: Room name (e.g., "downstairs", "master")

**Response (200 OK)**:
```json
{
  "room": "downstairs",
  "disabled": false
}
```

---

## Mode Controls (Away, Eco)

### GET /away-mode

Check if away mode (frost protection) is currently active.

**Authentication**: Required (x-api-key header)

**Response (200 OK - Disabled)**:
```json
{
  "enabled": false
}
```

**Response (200 OK - Enabled with Duration)**:
```json
{
  "enabled": true,
  "until": 1704110400000,
  "minutes": 120
}
```

**Response (200 OK - Enabled Indefinitely)**:
```json
{
  "enabled": true
}
```

---

### POST /away-mode

Enable or disable away mode (frost protection).

**Authentication**: Required (x-api-key header)

**Request Body**:
```json
{
  "enabled": true,
  "minutes": 120
}
```

Or to disable:
```json
{
  "enabled": false
}
```

**Response (200 OK)**:
```json
{
  "ok": true,
  "enabled": true,
  "until": 1704110400000,
  "minutes": 120
}
```

**Error Response (400)**:
```json
{
  "ok": false,
  "error": "body must contain {enabled: boolean, minutes?: number}"
}
```

---

### GET /eco-mode

Check if eco mode (temperature reduction) is currently active.

**Authentication**: Required (x-api-key header)

**Response (200 OK)**:
```json
{
  "enabled": false,
  "delta_c": -1
}
```

Or when enabled:
```json
{
  "enabled": true,
  "delta_c": -1.5
}
```

---

### POST /eco-mode

Enable or disable eco mode with temperature delta.

**Authentication**: Required (x-api-key header)

**Request Body**:
```json
{
  "enabled": true,
  "delta_c": -1.5
}
```

Or to disable:
```json
{
  "enabled": false
}
```

**Response (200 OK)**:
```json
{
  "ok": true,
  "enabled": true,
  "delta_c": -1.5
}
```

**Error Response (400)**:
```json
{
  "ok": false,
  "error": "delta_c must be between -5 and 0 (negative reduces temperature)"
}
```

---

## Tado Authentication

### GET /tado/status

Check Tado authentication status and token validity.

**Authentication**: Required (x-api-key header)

**Response (200 OK - Connected)**:
```json
{
  "connected": true,
  "hasRefreshToken": true,
  "tokenValid": true,
  "error": null,
  "needsAuth": false
}
```

**Response (200 OK - Not Connected)**:
```json
{
  "connected": false,
  "hasRefreshToken": false,
  "tokenValid": false,
  "error": "Token expired",
  "needsAuth": true
}
```

---

### POST /tado/start

Start OAuth device code authentication flow with Tado.

**Authentication**: Required (x-api-key header)

**Request Body**: None (empty POST)

**Response (200 OK)**:
```json
{
  "user_code": "ABC123",
  "verify_url": "https://auth.tado.com/device?user_code=ABC123",
  "hint": "Open URL, approve; then POST /tado/poll"
}
```

---

### POST /tado/poll

Poll for OAuth device code completion (call repeatedly every 5 seconds after /tado/start).

**Authentication**: Required (x-api-key header)

**Request Body**: None (empty POST)

**Response (200 OK - Still Pending)**:
```json
{
  "pending": true,
  "message": "Waiting for user approval"
}
```

**Response (200 OK - Success)**:
```json
{
  "ok": true,
  "message": "Tado authentication successful! Token saved and verified. Will persist across restarts.",
  "verified": true
}
```

**Response (200 OK - Error)**:
```json
{
  "ok": false,
  "error": "Device code expired"
}
```

**Error Response (400)**:
```json
{
  "ok": false,
  "error": "no device_code saved (run /tado/start again)"
}
```

---

## Monitoring & Logs

### GET /logs

Retrieve system logs (last N lines).

**Authentication**: Required (x-api-key header)

**Query Parameters**:
- `n` (optional, default: 200): Number of log lines to retrieve

**Response (200 OK)**:
```json
{
  "lines": [
    "[2024-01-01T12:00:00Z] [INFO] Policy applied: downstairs AC heat 23°C",
    "[2024-01-01T12:05:00Z] [WARN] MELCloud device 'Downstairs AC' not responding",
    "[2024-01-01T12:10:00Z] [DEBUG] Tado zones fetched: 4 zones available"
  ]
}
```

---

### GET /weather

Get current outdoor temperature from configured weather API.

**Authentication**: Required (x-api-key header)

**Response (200 OK)**:
```json
{
  "outdoorC": 8.5
}
```

---

### GET /pv

Get current solar PV output in watts.

**Authentication**: Required (x-api-key header)

**Response (200 OK - Available)**:
```json
{
  "watts": 1250
}
```

**Response (200 OK - Not Configured/Unavailable)**:
```json
{
  "watts": null
}
```

---

### GET /pv/debug

Debug solar PV integration (includes detailed status).

**Authentication**: Required (x-api-key header)

**Response (200 OK)**:
```json
{
  "token_configured": true,
  "plant_id": "12345",
  "plant_name": "Home Solar",
  "watts": 1250,
  "timestamp": "2024-01-01T12:00:00.000Z"
}
```

---

## Override Management

### GET /override/:device/:name

Check if a device has a manual override active.

**Authentication**: Required (x-api-key header)

**Path Parameters**:
- `device`: "ac" or "tado"
- `name`: Device name (e.g., "Downstairs AC", "Living Room")

**Response (200 OK)**:
```json
{
  "hasOverride": false,
  "minutesRemaining": 0
}
```

Or when override is active:
```json
{
  "hasOverride": true,
  "minutesRemaining": 45
}
```

---

### POST /override/:device/:name/clear

Clear a manual override for a device.

**Authentication**: Required (x-api-key header)

**Path Parameters**:
- `device`: "ac" or "tado"
- `name`: Device name (e.g., "Downstairs AC", "Living Room")

**Response (200 OK)**:
```json
{
  "ok": true,
  "device": "ac",
  "name": "Downstairs AC",
  "cleared": true
}
```

**Error Response (400)**:
```json
{
  "ok": false,
  "error": "device must be \"ac\" or \"tado\""
}
```

---

### GET /overrides

List all active overrides (simple implementation).

**Authentication**: Required (x-api-key header)

**Response (200 OK)**:
```json
{
  "overrides": [],
  "stats": {
    "total": 0,
    "active": 0
  }
}
```

---

### POST /overrides/:deviceId/set

Set a manual override for a device.

**Authentication**: Required (x-api-key header)

**Path Parameters**:
- `deviceId`: Format "ac:Device Name" or "tado:Zone Name"

**Request Body**:
```json
{
  "durationMinutes": 60
}
```

**Response (200 OK)**:
```json
{
  "isOverridden": true,
  "expiresAt": "2024-01-01T13:00:00.000Z",
  "minutesRemaining": 60
}
```

---

### POST /overrides/:deviceId/clear

Clear a manual override.

**Authentication**: Required (x-api-key header)

**Path Parameters**:
- `deviceId`: Format "ac:Device Name" or "tado:Zone Name"

**Response (200 OK)**:
```json
{
  "ok": true,
  "deviceId": "ac:Downstairs AC",
  "cleared": true
}
```

---

### GET /action-log

Get action history (limited implementation).

**Authentication**: Required (x-api-key header)

**Response (200 OK)**:
```json
{
  "devices": [],
  "stats": {
    "total": 0
  },
  "message": "Action history not available with simple state tracker - check /logs endpoint"
}
```

---

### GET /action-log/:deviceId

Get action history for a specific device.

**Authentication**: Required (x-api-key header)

**Path Parameters**:
- `deviceId`: Device identifier

**Response (200 OK)**:
```json
{
  "deviceId": "ac:Downstairs AC",
  "actions": [],
  "count": 0,
  "message": "Action history not available with simple state tracker - check /logs endpoint"
}
```

---

## Admin Operations

### POST /admin/clear-overrides

Clear all active device overrides system-wide.

**Authentication**: Required (x-api-key header)

**Request Body**: None (empty POST)

**Response (200 OK)**:
```json
{
  "ok": true,
  "cleared": 3,
  "keys": [
    "device_override:ac:Downstairs AC",
    "device_override:tado:Living Room",
    "device_override:ac:Master AC"
  ]
}
```

---

## Debug Endpoints

### GET /debug

Simple debug endpoint (reveals API key presence).

**Response**:
```json
{
  "seen": "sk-...",
  "hasEnv": true,
  "envLen": 32
}
```

---

### GET /debug-tado-token

Check Tado refresh token status.

**Authentication**: Required (x-api-key header)

**Response**:
```json
{
  "hasRefreshToken": true,
  "tokenPrefix": "eyJhbGc..."
}
```

---

## Error Response Format

All errors follow this format (except 404 not found):

```json
{
  "ok": false,
  "error": "error message"
}
```

HTTP Status Codes:
- `200 OK` - Successful operation
- `400 Bad Request` - Invalid parameters or body
- `401 Unauthorized` - Missing or invalid API key
- `404 Not Found` - Endpoint or resource not found
- `429 Too Many Requests` - Rate limit exceeded (cooldown protection)
- `500 Internal Server Error` - Server-side error

---

## Authentication Details

### Header Format

All authenticated requests must include:
```
x-api-key: <API_KEY_VALUE>
```

Where `<API_KEY_VALUE>` matches the `API_KEY` environment variable set on the Cloudflare Worker.

### Authentication Behavior

- `/healthz` - **No authentication required**
- All other endpoints - **Authentication required**
- Invalid/missing key returns `401 Unauthorized`

---

## Dashboard Integration Guide

### SimonDashboard.tsx Uses:
- GET `/test-connections` - Check system health
- GET `/weather` - Fetch outdoor temperature
- GET `/status` - Fetch room states (polls every 10 seconds)
- GET `/policy-enabled` - Check policy state
- POST `/policy-enabled` - Toggle policy
- POST `/control` - Manual room control
- POST `/apply-policy` - Trigger policy (debug)

### SimpleDashboard.tsx Uses:
- GET `/status` - Fetch room states (polls every 30 seconds)
- GET `/weather` - Fetch outdoor temperature
- POST `/control` - Manual room control

### Config.tsx Uses:
- GET `/config` - Load configuration
- PUT `/config` - Save configuration

### Inventory.tsx Uses:
- GET `/inventory` - Load room inventory
- GET `/config` - Load configuration
- GET `/status` - Poll room states (every 10 seconds)
- PUT `/config` - Save per-room AC overrides
- POST `/control` - Manual device control

### LogsPanel.tsx / Logs.tsx Use:
- GET `/logs?n=20|500` - Fetch recent logs (polls every 5 seconds)

### Settings.tsx Uses:
- GET `/tado/status` - Check Tado connection status
- POST `/tado/start` - Start OAuth device code flow
- POST `/tado/poll` - Poll for OAuth completion (every 5 seconds)

---

## Compatibility Notes

1. **Room Names**: Case-insensitive in API calls, normalized to lowercase
2. **Device Names**: Case-sensitive, must match exactly from /inventory or /rooms
3. **Temperature**: All in Celsius
4. **Timestamps**: ISO 8601 format in responses
5. **AC Options**: Maps to MELCloud API modes (1=heat, 2=cool, 3=dry, 7=fan, 8=auto)
6. **Tado Overlays**: Use TIMER termination type with configurable duration
7. **Config Merging**: Sparse config objects are merged server-side with defaults from environment variables

