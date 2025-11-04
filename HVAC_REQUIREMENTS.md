# HVAC Control System - Clean Requirements

**Purpose**: Automated heating control that manages Mitsubishi MELCloud AC units and Tado smart radiator thermostats based on schedules, weather, and occupancy while protecting equipment and respecting user manual changes.

**Status**: Requirements document for rebuilding the system properly.

---

## 📚 Documentation Set

This is part of a complete documentation set:

- **HVAC_REQUIREMENTS.md** (this file) - Core system requirements and control logic
- **API_SPECIFICATION.md** - Complete HTTP API reference (39 endpoints)
- **README_API_DOCS.md** - Quick API navigation and compatibility rules
- **API_QUICK_REFERENCE.md** - Fast endpoint lookup by category
- **ENDPOINT_USAGE_MATRIX.md** - Dashboard component → endpoint mapping

**IMPORTANT**: The dashboard expects specific API contracts. See [HTTP API Design](#http-api-design) section and API_SPECIFICATION.md for exact field names, types, and response formats.

---

## Table of Contents

1. [System Goals](#system-goals)
2. [External API Specifications](#external-api-specifications)
3. [Core Control Rules](#core-control-rules)
4. [Manual Override Detection](#manual-override-detection)
5. [Scheduling System](#scheduling-system)
6. [Configuration Data Model](#configuration-data-model)
7. [Key Behaviors](#key-behaviors)
8. [Notification Requirements](#notification-requirements)
9. [HTTP API Design](#http-api-design)

---

## System Goals

### What the System Must Do
1. **Maintain scheduled temperatures** across multiple rooms using AC and/or radiators
2. **Protect compressor equipment** with mandatory cooldown periods and minimum run times
3. **Respect user manual changes** by detecting them and pausing automation for 1 hour
4. **Select optimal heating source** based on outdoor temperature (AC when warm, radiators when cold)
5. **Prevent wasteful behavior** like starting heating <10 minutes before schedule drops
6. **Support flexible scheduling** with base house schedule + per-room overrides
7. **Provide visibility** via notifications when state changes or manual overrides detected

### What the System Must NOT Do
1. **Never ignore manual user changes** - if user turns something ON, don't immediately turn it OFF
2. **Never rapid-cycle devices** - use hysteresis control with deadband
3. **Never damage equipment** - respect cooldowns and minimum run times
4. **Never waste energy** - don't start heating when schedule is about to drop

---

## External API Specifications

### 1. Tado API (Smart Radiator Thermostats)

#### Authentication (OAuth2 Device Code Flow)

**Step 1: Initiate Device Code Flow**
```
POST https://login.tado.com/oauth2/device_authorize
Headers:
  content-type: application/x-www-form-urlencoded
Body:
  client_id=1bb50063-6b0c-4d11-bd99-387f4a91cc46
  scope=offline_access

Response:
{
  "device_code": "...",
  "user_code": "ABCD-1234",
  "verification_uri_complete": "https://login.tado.com/device?user_code=ABCD-1234",
  "expires_in": 600,
  "interval": 5
}
```

**Step 2: Token Refresh (use for all subsequent authentications)**
```
POST https://login.tado.com/oauth2/token
Headers:
  content-type: application/x-www-form-urlencoded
Body:
  client_id=1bb50063-6b0c-4d11-bd99-387f4a91cc46
  grant_type=refresh_token
  refresh_token=<REFRESH_TOKEN>

Response:
{
  "access_token": "eyJ...",
  "refresh_token": "new_refresh_token",  // IMPORTANT: Old refresh_token is now INVALID
  "token_type": "bearer",
  "expires_in": 599
}
```

**Important**: Tado uses **refresh token rotation** - every time you refresh, the old token becomes invalid. Store the new refresh_token immediately. Use distributed locking to prevent concurrent refresh attempts.

**Caching**:
- Access token: Cache for 10 minutes
- Refresh token: Store persistently (never cache, always use latest)

#### Get Zone List
```
GET https://my.tado.com/api/v2/homes/{HOME_ID}/zones
Headers:
  Authorization: Bearer <access_token>

Response:
[
  {"id": 1, "name": "Main Bed", "type": "HEATING"},
  {"id": 2, "name": "Doug", "type": "HEATING"},
  ...
]
```

**Caching**: 1 hour (zones rarely change)

#### Get Zone State (Temperature & Heating Status)
```
GET https://my.tado.com/api/v2/homes/{HOME_ID}/zones/{zone_id}/state
Headers:
  Authorization: Bearer <access_token>

Response:
{
  "activityDataPoints": {
    "heatingPower": {"percentage": 35}  // 0 = not heating, >0 = actively heating
  },
  "sensorDataPoints": {
    "temperature": {"celsius": 19.5}
  }
}
```

**Caching**: 2 minutes (temperatures change slowly)

**Note**: `heatingPower.percentage > 0` means the radiator is actively calling for heat.

#### Set Zone Temperature (Turn ON with Timer)
```
PUT https://my.tado.com/api/v2/homes/{HOME_ID}/zones/{zone_id}/overlay
Headers:
  Authorization: Bearer <access_token>
  content-type: application/json

Body:
{
  "setting": {
    "type": "HEATING",
    "power": "ON",
    "temperature": {"celsius": 20}
  },
  "termination": {
    "type": "TIMER",
    "durationInSeconds": 900  // Minimum 900 seconds (15 minutes)
  }
}
```

#### Turn OFF Zone
```
DELETE https://my.tado.com/api/v2/homes/{HOME_ID}/zones/{zone_id}/overlay
Headers:
  Authorization: Bearer <access_token>
```

**Note**: Deleting overlay returns zone to automatic schedule.

#### Retry Logic
- **401 Unauthorized**: Clear access token cache, refresh token, retry once
- **429 Rate Limited**: Do NOT retry, fail immediately
- Other errors: Retry up to 2 times with exponential backoff (100ms, 500ms)

---

### 2. MELCloud API (Mitsubishi AC Units)

#### Authentication (Session-Based)

**Login to get session token**
```
POST https://app.melcloud.com/Mitsubishi.Wifi.Client/Login/ClientLogin
Headers:
  content-type: application/json

Body:
{
  "Email": "user@example.com",
  "Password": "password",
  "Language": "0",
  "AppVersion": "1.19.5.1",
  "Persist": true
}

Response:
{
  "LoginData": {
    "ContextKey": "ABC123..."  // This is your session token
  }
}
```

**Use ContextKey in all subsequent requests**:
```
Headers:
  X-MitsContextKey: <ContextKey>
```

**Session lifetime**: Unknown, re-authenticate on 401 errors.

#### Get Device List

**Device Hierarchy**: MELCloud organizes devices in nested structures:
```
Response Array
  └─ Structure
      ├─ Devices[]
      ├─ Areas[]
      │   └─ Devices[]
      ├─ Floors[]
      │   └─ Devices[]
      └─ Children[] (recurse)
```

**API Call**:
```
GET https://app.melcloud.com/Mitsubishi.Wifi.Client/User/ListDevices
Headers:
  X-MitsContextKey: <session_token>

Response:
[
  {
    "Structure": {
      "Devices": [
        {
          "DeviceID": 12345,
          "DeviceName": "Master bedroom",
          "DeviceType": 0,  // 0 = Air-to-Air (ATA), only supported type
          "BuildingID": 67890
        }
      ],
      "Areas": [...],
      "Floors": [...]
    }
  }
]
```

**Device Traversal**: Recursively check `Devices`, `Areas`, `Floors`, `Structure`, and `Children` fields to collect all units. Only use DeviceType 0 (ATA units).

#### Get Device Status (Temperature & Power State)
```
GET https://app.melcloud.com/Mitsubishi.Wifi.Client/Device/Get?id={device_id}&buildingID={building_id}
Headers:
  X-MitsContextKey: <session_token>

Response:
{
  "Power": true,
  "SetTemperature": 22.0,      // Device's target temperature
  "RoomTemperature": 19.5,     // Current measured temperature
  "OperationMode": 1,          // 1=heat, 2=cool, 3=dry, 7=fan, 8=auto
  "SetFanSpeed": 3,            // 0=auto, 1-5=speed levels
  "VaneHorizontal": 0,         // 0=auto, 12=swing
  "VaneVertical": 0,           // 0=auto, 7=swing
  "DeviceType": 0
}
```

**Caching**: 1 minute (temperatures change slowly)

**Important**: `RoomTemperature` is the current measured temperature to use for control logic.

#### Force Refresh (Get Latest Hardware State)

Sometimes cached data is stale. Force device to poll hardware:

```
GET https://app.melcloud.com/Mitsubishi.Wifi.Client/Device/RequestRefresh?id={device_id}
Headers:
  X-MitsContextKey: <session_token>
```

**Important**: Wait 2 seconds after calling RequestRefresh before reading status.

#### Set Device State (Power, Temperature, Mode, Fan, Vanes)

**Critical**: Use EffectiveFlags bitmask to specify which fields are being set.

```
POST https://app.melcloud.com/Mitsubishi.Wifi.Client/Device/SetAta
Headers:
  X-MitsContextKey: <session_token>
  content-type: application/json

Body:
{
  "DeviceID": 12345,
  "BuildingID": 67890,
  "Power": true,
  "SetTemperature": 22.0,
  "OperationMode": 1,
  "SetFanSpeed": 3,
  "VaneHorizontal": 0,
  "VaneVertical": 0,
  "EffectiveFlags": 15,       // Bitmask: which fields to update
  "HasPendingCommand": true
}
```

#### EffectiveFlags Bitmask (CRITICAL)

**Bit mapping**:
```
Power          = 1    (bit 0)
OperationMode  = 2    (bit 1)
SetTemperature = 4    (bit 2)
SetFanSpeed    = 8    (bit 3)
VaneHorizontal = 16   (bit 4)
VaneVertical   = 256  (bit 8)
```

**Common combinations**:
- **Turn OFF only**: `EffectiveFlags = 1` (Power bit only)
- **Turn ON without vanes**: `EffectiveFlags = 15` (1+2+4+8: Power + Mode + Temp + Fan)
- **Turn ON with vanes**: `EffectiveFlags = 287` (1+2+4+8+16+256: all fields)

**Rule**: When turning device OFF, only set Power bit (EffectiveFlags=1). When turning ON, set Power + Mode + SetTemperature + Fan (+ vanes if supported).

#### AC Option Mappings

**OperationMode**:
- heat = 1
- cool = 2
- dry = 3
- fan = 7
- auto = 8

**SetFanSpeed**:
- auto = 0
- 1-5 = speed levels

**VaneHorizontal**:
- auto = 0
- swing = 12

**VaneVertical**:
- auto = 0
- swing = 7

**Vanes Supported**: Some units (ducted) do NOT support vane control. Set `vanes: false` for these units to avoid including vane fields in EffectiveFlags.

#### Retry Logic
- Retry up to 2 times with exponential backoff (100ms, 500ms)
- Re-authenticate on 401 errors

---

### 3. Weather API (Outdoor Temperature)

**Provider**: Open-Meteo (free, no auth required)

```
GET https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true

Response:
{
  "current_weather": {
    "temperature": 8.5  // Celsius
  }
}
```

**Caching**: 15 minutes (weather changes slowly)

**Usage**: Determines whether to use AC (outdoor ≥ 5°C) or Tado radiators (outdoor < 5°C).

---

### 4. Solar PV API (Optional - Stub Only)

**Purpose**: Boost heating setpoints when excess solar power available.

**Interface** (implement as stub returning null for now):
```
getCurrentPVOutput() → watts (number) or null
```

**Future implementation**: Growatt API or similar.

**Logic**: If PV output ≥ threshold (e.g., 600W), add boost delta (e.g., 0.5°C) to all setpoints.

---

## Core Control Rules

### 1. Hysteresis Control (Prevent Rapid Cycling)

**Purpose**: Prevent devices from turning ON and OFF repeatedly when temperature hovers near setpoint. Protects compressor and reduces energy waste.

**Rule**:
```
Given:
  - Current room temperature: T
  - Target setpoint: S
  - Deadband: D (default 0.5°C)
  - Current device power state: P (ON or OFF)

Decision:
  IF P is ON AND T > S + D:
    → Turn OFF (room is too warm)

  ELSE IF P is OFF AND T < S - D:
    → Turn ON (room is too cold)

  ELSE:
    → MAINTAIN current state (within deadband, no change)
```

**Example**: Setpoint = 20°C, Deadband = 0.5°C
- Device ON, Temp = 20.6°C → Turn OFF (20.6 > 20 + 0.5)
- Device OFF, Temp = 19.4°C → Turn ON (19.4 < 20 - 0.5)
- Device ON, Temp = 20.3°C → MAINTAIN ON (within 19.5-20.5°C)
- Device OFF, Temp = 19.7°C → MAINTAIN OFF (within 19.5-20.5°C)

**Important**: Use **strict inequalities** (>, <) to avoid boundary oscillation.

**Configuration**: Deadband adjustable via config (default 0.5°C, recommended 0.5-1.0°C).

---

### 2. Compressor Protection (Cooldown Timers)

**Purpose**: Prevent damage to AC compressors and valve actuators from rapid state changes.

#### AC Units (Compressor Protection)

**OFF → ON Transition**:
- Minimum wait: **5 minutes** since last state change
- Reason: Compressor needs time to equalize pressure before restart

**ON → OFF Transition**:
- Minimum wait: **5 minutes** since last state change
- Reason: Allow compressor cycle to complete properly

**Minimum ON Time**:
- Once turned ON, must stay ON for **15 minutes** before allowing turn OFF
- Reason: Prevent short-cycling that damages compressor

**Configuration**:
- `AC_COOLDOWN_OFF_TO_ON` (default: 5 minutes)
- `AC_COOLDOWN_ON_TO_OFF` (default: 5 minutes)
- `AC_MIN_ON_TIME` (default: 15 minutes)

#### Tado Radiators (Valve Protection)

**Any State Change**:
- Minimum wait: **3 minutes** since last state change
- Reason: TRV valve actuator needs time to complete movement

**Configuration**:
- `TADO_COOLDOWN` (default: 3 minutes)

#### Implementation Notes
- Store last state change timestamp per device
- Store "turned ON" timestamp for AC minimum ON time enforcement
- Check cooldown BEFORE attempting any state change
- If cooldown active, skip action and report wait time remaining

---

### 3. Heating Setpoint Offset (Prevent Device Thermostat Interference)

**Problem**: AC units have internal thermostats. If we set device to 20°C but use hysteresis to turn OFF at 20.5°C, the device's thermostat might interfere and turn itself OFF early.

**Solution**: Add offset to device setpoint so device thinks it needs to keep heating.

**Rule**:
```
Given:
  - Target room setpoint: S (what we want room to reach)
  - Heating offset: O (default 2.0°C)
  - Device mode: M (heating or cooling)

Device setpoint sent to API:
  IF M is heating:
    → Send S + O to device (e.g., 20°C + 2°C = 22°C)

  ELSE IF M is cooling:
    → Send S - O to device (e.g., 20°C - 2°C = 18°C)

  ELSE:
    → Send S (no offset)

Our control logic still uses:
  - Turn ON when T < S - deadband
  - Turn OFF when T > S + deadband
```

**Example**: Target 20°C, Offset 2°C, Deadband 0.5°C
- Send 22°C to AC device
- Turn ON when room < 19.5°C
- Turn OFF when room > 20.5°C
- Device thermostat sees room=20.5°C vs device setpoint=22°C → thinks room is cold, keeps heating
- Our hysteresis at 20.5°C triggers OFF → we explicitly turn device OFF
- Device thermostat never interferes

**Configuration**: `HEATING_SETPOINT_OFFSET` (default 2.0°C)

---

### 4. Weather-Based Source Selection

**Rule**: Choose heating source based on outdoor temperature efficiency.

```
Given:
  - Outdoor temperature: T_out
  - Room has AC: has_ac
  - Room has Tado radiator: has_tado
  - Minimum outdoor temp for AC: T_min (default 5°C)

Source selection:
  IF has_ac AND T_out ≥ T_min:
    → Use AC (heat pump efficient at moderate temps)

  ELSE IF has_tado:
    → Use Tado radiator (fallback when AC unavailable or too cold)

  ELSE:
    → No suitable heating source
```

**Rationale**:
- AC heat pumps are efficient above 5°C outdoor temperature
- Below 5°C, heat pump efficiency drops significantly
- Radiators (hydronic heating) provide consistent heat regardless of outdoor temp

**Configuration**: `AC_MIN_OUTDOOR_TEMP` (default 5°C)

**Note**: User confirmed threshold is **5°C**, not 2°C as found in current code.

---

### 5. Schedule Transition Block (Prevent Wasteful Heating)

**Problem**: If schedule drops from 20°C to 16°C in 10 minutes, and room is currently 19.5°C, there's no point starting the heating system. By the time it warms up, the schedule will drop.

**Rule**:
```
Given:
  - Current time: now
  - Next schedule period change: next_change_time
  - Time until change: delta = next_change_time - now
  - Next period setpoint: S_next
  - Current period setpoint: S_current
  - Decision: turn_on (from hysteresis logic)

Block turn_on if:
  delta < 10 minutes AND turn_on is true
```

**Example**:
- Current time: 21:52
- Current period: Evening (20°C) until 22:00
- Next period: Night (16°C) from 22:00
- Time until change: 8 minutes
- Room temp: 19.4°C
- Hysteresis says: Turn ON (19.4 < 20 - 0.5)
- **Block**: Don't turn ON, schedule drops in 8 minutes

**Configuration**: `SCHEDULE_TRANSITION_BLOCK_MINUTES` (default 10 minutes)

**User requirement**: Apply to **ALL schedule period transitions**, not just setpoint drops.

---

### 6. Blackout Windows (Prevent Heating During Specific Times)

**Purpose**: Prevent heating system from turning ON during specific times (e.g., kids getting ready for school with doors open, end of cheap electricity rate).

**Rule**:
```
Given:
  - Current time: now
  - Blackout windows: [{start, end, applies_to: ['tado'|'ac'], enabled}]
  - Device type: type
  - Decision: turn_on

Block turn_on if:
  Any enabled blackout window matches:
    - now is within [start, end] time range
    - type is in applies_to list
    - Decision is turn_on
```

**Example**:
```json
{
  "name": "Tado Morning Blackout",
  "start": "08:00",
  "end": "09:00",
  "applies_to": ["tado"],
  "enabled": true
}
```

At 08:30, Tado wants to turn ON → **Blocked** (within blackout window)
At 08:30, AC wants to turn ON → **Allowed** (blackout only applies to Tado)

**Important**: Blackout ONLY prevents turn_on. Devices wanting to turn_off proceed normally.

**Configuration**: Flexible per-device type, multiple windows supported.

---

## Manual Override Detection

### The Problem

**Scenario**: User's wife comes home and manually turns downstairs heating ON using the Tado app. The automation system immediately turns it OFF because room temperature is already at setpoint. This is unacceptable - it ignores user intent and will cause equipment damage from rapid cycling.

### The Solution: Simple State Tracking

**Concept**: After every control cycle, record what action the system took. On next cycle, compare actual device state to expected state. If different, user manually changed it.

**Algorithm**:

```
AFTER each control cycle:
  FOR each device controlled:
    Store: device_state[device] = {
      last_action: 'on' or 'off',
      timestamp: now
    }

BEFORE next control cycle:
  FOR each device to be controlled:
    Read: current_device_state from API (actual power state)
    Read: stored_state = device_state[device]

    IF stored_state exists:
      expected_state = stored_state.last_action ('on' or 'off')
      actual_state = current_device_state.power ('on' or 'off')

      IF actual_state != expected_state:
        → User manually changed device!
        → Mark device as overridden for 60 minutes
        → Skip device in policy control
        → Send Slack notification
```

**Example Flow**:

1. **Policy cycle 1** (10:00):
   - Room: 19°C, Setpoint: 20°C, Deadband: 0.5°C
   - Hysteresis: 19 < 19.5 → Turn ON
   - Execute: Turn device ON
   - Store: `device_state['Living'] = {last_action: 'on', timestamp: 10:00}`

2. **User action** (10:05):
   - User manually turns device OFF via app
   - System not aware yet

3. **Policy cycle 2** (10:15):
   - Read current state: Device is OFF
   - Read stored state: `last_action = 'on'`
   - Compare: OFF != ON → **Override detected!**
   - Action: Mark `device_override['Living'] = {detected_at: 10:15, expires_at: 11:15}`
   - Notify: "Manual override detected: Living turned OFF by user. Policy paused 1 hour."
   - Skip control for this device

4. **Policy cycles 3-7** (10:30-11:00):
   - Check: `device_override['Living']` exists and not expired
   - Skip device in policy control

5. **Policy cycle 8** (11:15):
   - Check: `device_override['Living']` expired
   - Resume normal policy control

**Important**: Only check for user changes when policy is **maintaining** state, not when actively changing it. If policy just commanded turn_on/turn_off, wait one cycle before checking (prevents false positives from API delay).

**Configuration**:
- `MANUAL_OVERRIDE_DURATION` (default 60 minutes)

**Notifications**: Send Slack message when override detected with device name, room, and user action.

---

## Scheduling System

### Base House Schedule (3-Period)

**Purpose**: Default temperature schedule for entire house when no room-specific override active.

**Structure**:
```json
{
  "base_schedule": {
    "type": "three-period",
    "morning": {
      "setpoint": 18,
      "start": "07:00"
    },
    "day": {
      "setpoint": 17,
      "start": "08:00"
    },
    "evening": {
      "setpoint": 20,
      "start": "18:00"
    },
    "night": {
      "setpoint": 16,
      "start": "22:00"
    }
  }
}
```

**Evaluation Logic**:
```
Given current time T:
  IF T in [morning.start, day.start): use morning.setpoint
  ELSE IF T in [day.start, evening.start): use day.setpoint
  ELSE IF T in [evening.start, night.start): use evening.setpoint
  ELSE: use night.setpoint
```

---

### Per-Room Schedule Overrides (Flexible)

**Purpose**: Allow specific rooms to have different temperatures at different times, overriding base schedule.

**Structure**:
```json
{
  "rooms": {
    "Living": {
      "schedule_overrides": [
        {
          "start": "08:00",
          "end": "10:00",
          "setpoint": 21,
          "days": ["mon", "tue", "wed", "thu", "fri"]  // Optional, defaults to all days
        },
        {
          "start": "12:00",
          "end": "13:00",
          "setpoint": 20,
          "days": ["mon", "tue", "wed", "thu", "fri"]
        }
      ]
    }
  }
}
```

**Evaluation Logic**:
```
Given room R and current time T:
  FOR each override in room.schedule_overrides:
    IF T in [override.start, override.end) AND current_day in override.days:
      → Use override.setpoint
      → STOP (first match wins)

  → Use base_schedule setpoint (default fallback)
```

**Example**: Living room on Monday at 08:30
- Override 1 matches: 08:30 in [08:00, 10:00) and Monday in days → Use 21°C
- Override 2 doesn't match: 08:30 not in [12:00, 13:00)
- Result: **21°C** (override wins)

Living room on Monday at 11:00
- Override 1 doesn't match: 11:00 not in [08:00, 10:00)
- Override 2 doesn't match: 11:00 not in [12:00, 13:00)
- Fallback to base_schedule at 11:00 → **17°C** (day period)

**Important**: Unlike current system with hardcoded schedules, this allows arbitrary time periods per room without code changes.

---

### Special Modes

#### Away Mode (Frost Protection)
- Overrides ALL setpoints to 5°C (prevent pipe freezing)
- Optional duration (30 min to 7 days) or indefinite
- Stored as: `{enabled: true, until: timestamp}`

#### Eco Mode (Energy Saving)
- Reduces all setpoints by delta (e.g., -2°C)
- Applied after schedule evaluation: `final_setpoint = scheduled_setpoint + eco_delta`
- Range: -5°C to 0°C
- Stored as: `{enabled: true, delta_c: -2}`

#### PV Boost (Solar-Powered Heating)
- When solar output ≥ threshold (e.g., 600W): add boost delta (e.g., +0.5°C)
- Applied after schedule evaluation: `final_setpoint = scheduled_setpoint + pv_boost`
- Stored as: `{boost_threshold_w: 600, boost_delta_c: 0.5}`

**Priority Order**:
1. Away mode (overrides everything)
2. Schedule evaluation (base + room overrides)
3. Eco mode (reduces)
4. PV boost (increases)

---

## Configuration Data Model

### Room Definition

**Purpose**: Map friendly room names to physical devices, define schedules, and configure AC options.

```json
{
  "rooms": {
    "Living": {
      "friendly_name": "Living Room",
      "devices": {
        "ac": ["Living"],           // MELCloud device names (can be multiple)
        "tado": "Main Bed"           // Tado zone name (single)
      },
      "ac_options": {
        "mode": "heat",
        "fan": 4,
        "vaneH": "auto",
        "vaneV": "auto",
        "vanes": true                // false for ducted units
      },
      "schedule_overrides": [
        {"start": "08:00", "end": "10:00", "setpoint": 21}
      ],
      "floor": "downstairs"
    },
    "Master": {
      "friendly_name": "Master Bedroom",
      "devices": {
        "ac": ["Master bedroom"],
        "tado": "Main Bed"
      },
      "ac_options": {
        "mode": "heat",
        "fan": "auto",
        "vanes": false               // Ducted unit
      }
    }
  }
}
```

**Key Features**:
- **Friendly names**: Display names for UI/logs
- **Multiple AC units per room**: `"ac": ["Unit1", "Unit2"]` controls both together
- **Room grouping**: Multiple devices treated as one room
- **Temperature source**: Use reading from active device (AC if using AC, Tado if using Tado)
- **Device name matching**: Must exactly match names from API (case-sensitive)

---

### Global Configuration

```json
{
  "base_schedule": {
    "type": "three-period",
    "morning": {"setpoint": 18, "start": "07:00"},
    "day": {"setpoint": 17, "start": "08:00"},
    "evening": {"setpoint": 20, "start": "18:00"},
    "night": {"setpoint": 16, "start": "22:00"}
  },
  "thresholds": {
    "ac_min_outdoor_temp": 5,              // °C
    "deadband": 0.5,                        // °C
    "heating_setpoint_offset": 2.0,        // °C
    "schedule_transition_block_minutes": 10
  },
  "cooldowns": {
    "ac_off_to_on_minutes": 5,
    "ac_on_to_off_minutes": 5,
    "ac_min_on_time_minutes": 15,
    "tado_minutes": 3
  },
  "manual_override_duration_minutes": 60,
  "ac_defaults": {
    "mode": "heat",
    "fan": "auto",
    "vaneH": "auto",
    "vaneV": "auto",
    "vanes": true
  },
  "exclusions": {
    "tado": ["Hot Water"],                 // Never control these zones
    "ac": []
  },
  "blackout_windows": [
    {
      "name": "Tado Morning Blackout",
      "start": "08:00",
      "end": "09:00",
      "applies_to": ["tado"],
      "enabled": true
    }
  ],
  "weather": {
    "latitude": 51.4184637,
    "longitude": 0.0135339
  },
  "pv": {
    "boost_threshold_w": 600,
    "boost_delta_c": 0.5
  },
  "timezone": "Europe/London",
  "rooms": { ... }
}
```

---

## Key Behaviors

### Decision Flow for Single Device

```
1. Check if device excluded (in exclusions list)
   → YES: Skip device
   → NO: Continue

2. Check if manual override active
   → YES: Skip device (respect user control)
   → NO: Continue

3. Get outdoor temperature from weather API

4. Select heating source:
   IF room has AC AND outdoor ≥ 5°C:
     → source = 'ac'
   ELSE IF room has Tado:
     → source = 'tado'
   ELSE:
     → Skip (no suitable device)

5. Get current room temperature from selected device API

6. Calculate target setpoint:
   a. Evaluate schedule (base + room overrides)
   b. Apply away mode override if enabled (→ 5°C)
   c. Apply eco mode delta if enabled
   d. Apply PV boost if solar output ≥ threshold

7. Apply hysteresis control:
   IF current_power is ON AND room_temp > setpoint + deadband:
     → decision = 'turn_off'
   ELSE IF current_power is OFF AND room_temp < setpoint - deadband:
     → decision = 'turn_on'
   ELSE:
     → decision = 'maintain'

8. Check schedule transition block:
   IF decision is 'turn_on' AND time_until_next_period < 10 minutes:
     → decision = 'skip' (don't start heating before schedule drops)

9. Check blackout window:
   IF decision is 'turn_on' AND current_time in blackout window for device type:
     → decision = 'skip'

10. Check cooldown timer:
    IF decision is 'turn_on' or 'turn_off':
      IF time_since_last_change < cooldown_period:
        → decision = 'skip' (cooldown active)

11. Execute decision:
    IF decision is 'turn_on':
      - Calculate device_setpoint = target_setpoint + heating_offset
      - Call device API to turn ON with device_setpoint
      - Store device_state[device] = {last_action: 'on', timestamp: now}
      - Store device_on_time[device] = now (for AC min ON time)
      - Send Slack notification

    ELSE IF decision is 'turn_off':
      - Call device API to turn OFF
      - Store device_state[device] = {last_action: 'off', timestamp: now}
      - Delete device_on_time[device]
      - Send Slack notification

    ELSE IF decision is 'maintain':
      - No API call
      - Log: "Maintaining current state"

    ELSE IF decision is 'skip':
      - No API call
      - Log: "Skipped due to [reason]"

12. After execution, check for manual override:
    IF decision was 'turn_on' or 'turn_off':
      Wait until next cycle to check
    ELSE:
      Read current device state
      IF current_state != stored_state.last_action:
        → Mark manual override for 60 minutes
        → Send Slack notification
```

### Multi-Device Rooms

**Problem**: Room has multiple AC units (e.g., "Downstairs" = ["Living", "Dining"])

**Solution**: Control all devices together as a group:
1. Use average temperature from all devices in room
2. Apply same control decision to all devices
3. Track cooldowns independently per device
4. If any device on cooldown, skip entire room (prevents partial heating)

**Configuration**:
```json
{
  "rooms": {
    "Downstairs": {
      "devices": {
        "ac": ["Living", "Dining", "Kitchen"]
      }
    }
  }
}
```

**Example**:
- Living temp: 19.0°C, Dining temp: 19.5°C, Kitchen temp: 19.2°C
- Average: 19.23°C
- Setpoint: 20°C, Deadband: 0.5°C
- Hysteresis: 19.23 < 19.5 → Turn ON all three units

---

## Notification Requirements

### Slack Webhook Integration

**Purpose**: Real-time visibility into system actions and user overrides.

**Configuration**: Single webhook URL in config.

### Notification Types

#### 1. Device State Change
**Trigger**: When system turns device ON or OFF
**Format**:
```
🔥 AC turned ON: Living
Room: Downstairs • Setpoint: 20°C • Time: 16:30:45
```

#### 2. Manual Override Detected
**Trigger**: When user manually changes device
**Format**:
```
🤚 Manual Override Detected
🔥 AC Living manually turned ON (Downstairs)
Policy control paused for 1 hour • 16:30:45
```

**Rate Limit**: Max 1 notification per device per hour (prevent spam)

#### 3. Authentication Failure
**Trigger**: When Tado/MELCloud login fails
**Format**:
```
🚨 Tado Authentication Failed
Error: Invalid refresh token
Action required: Re-authenticate via /tado/start
```

**Rate Limit**: Max 1 notification per service per hour

#### 4. Device Control Failure
**Trigger**: When device API call fails after retries
**Format**:
```
❌ Device Control Failed: Living
Room: Downstairs • Error: Timeout after 5000ms
```

**Rate Limit**: Max 1 notification per device per hour

#### 5. Policy Execution Summary (Optional)
**Trigger**: After each policy run (every 15 minutes)
**Format**:
```
✅ Policy Run Complete
Controlled: 8 devices • Succeeded: 7 • Failed: 1 • Skipped: 2
Overrides detected: 1 (Master bedroom)
```

**Rate Limit**: Only send if errors/overrides detected (no spam on success)

---

## Summary: What Must Work

### Critical Functionality
1. ✅ **Tado API calls** - OAuth flow, zone control with retry logic
2. ✅ **MELCloud API calls** - Session auth, device control with EffectiveFlags
3. ✅ **Hysteresis control** - Prevent rapid cycling with deadband
4. ✅ **Compressor protection** - Cooldown timers and minimum ON time
5. ✅ **Manual override detection** - Detect user changes, pause automation 1 hour
6. ✅ **Source selection** - AC when outdoor ≥ 5°C, Tado when colder
7. ✅ **Schedule system** - Base 3-period + per-room flexible overrides
8. ✅ **End-of-period block** - Don't start heating <10 min before schedule drops
9. ✅ **Blackout windows** - Prevent heating during specific times
10. ✅ **Room grouping** - Multiple devices per room, friendly names
11. ✅ **Temperature source** - Use reading from active device
12. ✅ **Slack notifications** - Real-time alerts for actions and overrides

### Known Issues to Fix
1. ❌ System NOT turning devices on/off (too much complexity)
2. ❌ System confusing its own actions with user actions
3. ❌ Ignoring manual user changes immediately turning devices back off/on
4. ❌ False override detections
5. ❌ Brittle error handling

---

## HTTP API Design

### Overview

The system exposes a REST API that the dashboard consumes. **39 endpoints** are documented in detail in `API_SPECIFICATION.md`.

**Complete API documentation** (separate files):
- **README_API_DOCS.md** - Start here: navigation guide and compatibility rules
- **API_SPECIFICATION.md** - Full endpoint reference with request/response schemas
- **API_QUICK_REFERENCE.md** - Fast lookup by category with examples
- **ENDPOINT_USAGE_MATRIX.md** - Dashboard component usage patterns

### Authentication

**All endpoints** (except `/healthz`) require:
```
Headers:
  x-api-key: <API_KEY>
```

**Unauthorized** returns:
```json
HTTP 401
{
  "error": "Unauthorized"
}
```

### Response Format Standard

**Success responses**:
```json
{
  "ok": true,
  "data": { ... },
  "timestamp": "2025-11-03T10:30:00.000Z"  // ISO 8601
}
```

**Error responses**:
```json
{
  "ok": false,
  "error": "Description of what went wrong",
  "timestamp": "2025-11-03T10:30:00.000Z"
}
```

### API Categories (39 Endpoints)

#### 1. Health & Status (2)
- `GET /healthz` - Health check (no auth)
- `GET /status` - System status with room states, outdoor temp, modes

#### 2. Configuration (2)
- `GET /config` - Retrieve configuration
- `PUT /config` - Update configuration

#### 3. Discovery (3)
- `GET /inventory` - Room and device inventory
- `GET /rooms` - List Tado zones and MELCloud units from APIs
- `GET /test-connections` - Test external API connectivity

#### 4. Room Control (1)
- `POST /control` - Manual room control with device selection

#### 5. Policy Management (3)
- `GET /policy-enabled` - Check if automated policy enabled
- `POST /policy-enabled` - Enable/disable policy
- `POST /apply-policy` - Execute policy engine (also triggered by cron)

#### 6. Room State (4)
- `GET /rooms/:room/disabled` - Check if room disabled
- `POST /rooms/:room/disable` - Disable room
- `POST /rooms/:room/enable` - Enable room
- `DELETE /rooms/:room/disabled` - (same as enable)

#### 7. Mode Controls (4)
- `GET /away-mode` - Get away mode status
- `POST /away-mode` - Set away mode
- `GET /eco-mode` - Get eco mode status
- `POST /eco-mode` - Set eco mode

#### 8. Tado Authentication (3)
- `POST /tado/start` - Initiate OAuth device code flow
- `POST /tado/poll` - Poll for authorization completion
- `GET /tado/status` - Check Tado connection status

#### 9. Monitoring (5)
- `GET /logs` - Retrieve system logs (query: `n=lines`)
- `GET /pv` - Current solar PV output
- `GET /weather` - Outdoor temperature
- `GET /device-state/:type/:name` - Get device state tracking
- `GET /device-states` - Get all device states

#### 10. Overrides (6)
- `GET /override/:device/:name` - Check device override status
- `POST /override/:device/:name/clear` - Clear specific override
- `POST /admin/clear-overrides` - Clear all overrides
- `GET /overrides` - List all active overrides
- `POST /override/:device/:name` - Manually set override
- `DELETE /override/:device/:name` - (same as clear)

#### 11. Admin (1)
- `POST /admin/clear-overrides` - Clear all override markers

#### 12. Debug (2)
- `GET /debug/state` - Dump all KV state
- `GET /debug/config` - Dump effective configuration

### Critical Compatibility Rules

**⚠️ When rebuilding, you MUST maintain these contracts:**

1. **Exact field names**: Dashboard expects specific field names (case-sensitive)
   - Example: `temperatureC` not `temperature_c`
   - See API_SPECIFICATION.md for exact schemas

2. **Exact parameter names**: Query params and path params must match
   - Example: `/logs?n=100` not `/logs?limit=100`

3. **Response structure**: Always include `ok` boolean field
   ```json
   {"ok": true, ...} or {"ok": false, "error": "..."}
   ```

4. **HTTP status codes**: Not everything is 200
   - 200: Success
   - 400: Bad request (invalid parameters)
   - 401: Unauthorized (missing/invalid API key)
   - 404: Not found (invalid room/device)
   - 500: Internal server error

5. **Polling intervals**: Dashboard polls certain endpoints
   - `/status`: Every 30 seconds (SimpleDashboard, SimonDashboard)
   - `/logs`: Every 5 seconds (LogsPanel)
   - `/policy-enabled`: Every 30 seconds (SimonDashboard)
   - Don't break these or dashboard will misbehave

6. **Temperature units**: Always Celsius (never Fahrenheit)

7. **Timestamps**: Always ISO 8601 format (`2025-11-03T10:30:00.000Z`)

8. **Device name matching**: Case-sensitive exact match
   - "Living" ≠ "living"
   - "Main Bed" ≠ "MainBed"

9. **Config preservation**: When updating config, preserve unknown fields
   - Dashboard may add fields you don't know about
   - Don't delete them on PUT /config

10. **Error messages**: Return helpful error messages in `error` field
    - Good: `"Room 'Foo' not found in configuration"`
    - Bad: `"Invalid request"`

### Example: Common Request Patterns

**Turn room ON**:
```
POST /control?rooms=Living&action=heat&setpoint=21&minutes=60
Headers:
  x-api-key: <KEY>

Response 200:
{
  "ok": true,
  "results": [
    {
      "room": "Living",
      "device": "ac",
      "action": "turn_on",
      "setpoint": 21,
      "success": true
    }
  ]
}
```

**Get system status**:
```
GET /status
Headers:
  x-api-key: <KEY>

Response 200:
{
  "ok": true,
  "rooms": [
    {
      "name": "Living",
      "temperature": 19.5,
      "setpoint": 20,
      "heating": true,
      "devices": [{"name": "Living", "type": "ac", "power": true}]
    }
  ],
  "outdoorTemp": 8.5,
  "modes": {"away": false, "eco": false, "policyEnabled": true}
}
```

**Enable away mode**:
```
POST /away-mode
Headers:
  x-api-key: <KEY>
Content-Type: application/json

Body:
{
  "enabled": true,
  "minutes": 480
}

Response 200:
{
  "ok": true,
  "mode": {
    "enabled": true,
    "setAt": "2025-11-03T10:30:00.000Z",
    "until": "2025-11-03T18:30:00.000Z"
  }
}
```

### Complete API Reference

**See**: `API_SPECIFICATION.md` for all 39 endpoints with complete request/response schemas, examples, and field definitions.

**Quick lookup**: `API_QUICK_REFERENCE.md` for category-organized endpoint list.

**Dashboard usage**: `ENDPOINT_USAGE_MATRIX.md` for which components call which endpoints.

---

**Document Status**: Ready for clean implementation
**Last Updated**: 2025-11-03
**Version**: 2.0 (requirements only, no implementation)
