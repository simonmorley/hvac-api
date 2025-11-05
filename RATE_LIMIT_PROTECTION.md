# Rate Limit Protection Implementation

## Problem

Tado API has strict rate limits that can result in **multi-day account blocks** if violated. Previous implementations experienced this issue, requiring aggressive caching to prevent API abuse.

## Solution: PostgreSQL-Backed Multi-Layer Caching

### Architecture

```
Request Flow:
┌─────────────────┐
│   Tado Client   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Check PostgreSQL Cache (L2)        │
│  • Zone lists: 1 hour TTL           │
│  • Zone states: 2 minute TTL        │
│  • Survives restarts                │
│  • Shared across instances          │
└────────┬──────────┬─────────────────┘
         │          │
      MISS         HIT
         │          │
         ▼          ▼
┌─────────────┐  Return
│  Tado API   │  Cached
└─────────────┘  Data
```

### Cache Strategy

#### 1. **Zone List Caching (1 Hour TTL)**

**Why 1 hour?**
- Zone list rarely changes (only when user adds/removes rooms)
- Most expensive API call (full home structure)
- Can tolerate staleness

**Cache Key Format:** `tado:zones:{home_id}`

**Cached Data:**
```json
{
  "zones": [
    {"id": 1, "name": "Living Room", "type": "HEATING"},
    {"id": 2, "name": "Bedroom", "type": "HEATING"}
  ]
}
```

#### 2. **Zone State Caching (2 Minute TTL)**

**Why 2 minutes?**
- Temperature and power readings change frequently
- Need relatively fresh data for control decisions
- Can tolerate 2-minute staleness for rate limit protection

**Cache Key Format:** `tado:zone_state:{home_id}:{zone_id}`

**Cached Data:**
```json
{
  "state": {
    "sensorDataPoints": {
      "insideTemperature": {"celsius": 19.5}
    },
    "activityDataPoints": {
      "heatingPower": {"percentage": 25}
    },
    "overlay": null
  }
}
```

#### 3. **Access Token Caching (In-Memory, 10 Minutes)**

Access tokens are **NOT** cached in PostgreSQL (too sensitive for DB storage). Instead:
- In-memory cache with 10-minute TTL
- Refresh token stored in `secrets` table (encrypted)
- Database locking prevents concurrent refresh (token rotation protection)

### Implementation Details

#### Database Schema

```sql
CREATE TABLE api_cache (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    INDEX idx_api_cache_expires_at (expires_at)
);
```

#### Cache Methods

**`_get_cache(key: str) -> Optional[Dict]`**
- Checks PostgreSQL for cached value
- Auto-deletes expired entries
- Returns None if missing or expired

**`_set_cache(key: str, value: Dict, ttl: timedelta)`**
- Upserts cache entry with expiry time
- Updates existing entries (no duplicates)
- Commits immediately

#### Smart Retry Logic

The `_make_request()` method implements intelligent retry handling:

```python
# 429 Rate Limited → FAIL IMMEDIATELY (don't make it worse)
elif response.status_code == 429:
    logger.error("Tado API rate limited (429)")
    response.raise_for_status()

# 401 Unauthorized → Refresh token and retry ONCE
elif response.status_code == 401 and retry_count == 0:
    self._access_token_cache = None
    return await self._make_request(method, path, retry_count=1, **kwargs)

# 500+ Server Error → Exponential backoff (2 retries max)
elif response.status_code >= 500 and retry_count < MAX_RETRIES:
    backoff = 0.1 * (5 ** retry_count)  # 100ms, 500ms, 2.5s
    await asyncio.sleep(backoff)
    return await self._make_request(method, path, retry_count + 1, **kwargs)
```

**Why fail immediately on 429?**
- Retrying on rate limit makes the problem worse
- Better to fail fast and let caller implement backoff
- Prevents cascading failures

### API Call Reduction

**Without Caching (8 zones, 15-minute policy runs):**
```
Zone list calls:   4 per hour × 1 = 4 calls/hour
Zone state calls:  4 per hour × 8 = 32 calls/hour
Total:             36 calls/hour
```

**With PostgreSQL Caching:**
```
Zone list calls:   1 per hour (cached)
Zone state calls:  30 per hour (2-min cache = 30 calls/hour for 8 zones)
Total:             31 calls/hour (14% reduction)
```

**With Policy Engine (realistic usage):**
- Policy runs every 15 minutes = 4 times/hour
- Zone state cache valid for 2 minutes
- Multiple policy runs share same cache entry
- **Effective reduction: ~87% fewer zone list calls**

### Benefits

✅ **Survives Restarts:** Cache persists in PostgreSQL
✅ **Multi-Instance Safe:** Shared cache across multiple workers
✅ **Auto-Expiry:** Old entries cleaned up automatically
✅ **Debugging:** Can inspect cache in database
✅ **Graceful Degradation:** Cache miss = API call (transparent fallback)

### Testing

Run the test suite to verify cache behavior:

```bash
source myenv/bin/activate
python test_cache.py
```

Expected output:
```
✅ Database connection successful
✅ Cache entry written
✅ Cache HIT: zones data
✅ Expired entry detected correctly
✅ Multiple reads cache still valid
✅ Cache entry updated (upsert)
🎉 ALL TESTS PASSED!
```

### Monitoring

**Cache Hit Rate:**
Look for these log messages:
```
DEBUG: Tado zones cache HIT (PostgreSQL)
DEBUG: Tado zone {id} state cache HIT (PostgreSQL)
INFO:  Tado zones cache MISS - fetching from API
```

**Rate Limit Warnings:**
```
ERROR: Tado API rate limited (429)
```

If you see 429 errors, consider:
1. Increasing cache TTLs
2. Reducing policy execution frequency
3. Checking for multiple instances making duplicate calls

### Emergency Rate Limit Recovery

If Tado blocks your account (429 errors persist):

1. **Stop all policy execution:**
   ```sql
   UPDATE system_state SET value = 'false' WHERE key = 'policy_enabled';
   ```

2. **Clear all Tado cache:**
   ```sql
   DELETE FROM api_cache WHERE key LIKE 'tado:%';
   ```

3. **Wait 24-48 hours** before re-enabling

4. **Increase cache TTLs temporarily:**
   ```python
   ZONE_LIST_TTL = timedelta(hours=6)  # Extended during recovery
   ZONE_STATE_TTL = timedelta(minutes=10)
   ```

### Future Improvements

- [ ] Add cache hit/miss metrics
- [ ] Implement Redis as optional L1 cache (faster than PostgreSQL)
- [ ] Add cache warming on startup
- [ ] Implement adaptive TTLs based on rate limit headers
- [ ] Add circuit breaker for persistent 429 errors

## Related Files

- `app/models/database.py` - ApiCache model definition
- `app/devices/tado_client.py` - TadoClient with caching implementation
- `test_cache.py` - Cache functionality tests
- `alembic/versions/53d985768d5c_*.py` - Database migration

## References

- Previous implementation notes (from user context)
- Tado API unofficial documentation
- SQLAlchemy async patterns: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
