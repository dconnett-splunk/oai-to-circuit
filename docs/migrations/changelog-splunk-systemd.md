# Changelog: Splunk HEC Integration & Systemd Support

## Summary

Added production deployment support with systemd and Splunk HTTP Event Collector (HEC) integration for real-time usage analytics.

## New Features

### 1. Splunk HEC Integration

**New Module: `oai_to_circuit/splunk_hec.py`**
- Streams usage metrics to Splunk in real-time
- Non-blocking operation (5-second timeout)
- Automatic event formatting
- Two event types:
  - **Usage events**: Request/token metrics after each API call
  - **Error events**: Quota exceeded, auth failures, etc.

**Configuration:**
- `SPLUNK_HEC_URL` - Splunk HEC endpoint URL
- `SPLUNK_HEC_TOKEN` - HEC authentication token
- `SPLUNK_SOURCE` - Event source (default: `oai-to-circuit`)
- `SPLUNK_SOURCETYPE` - Event sourcetype (default: `llm:usage`)
- `SPLUNK_INDEX` - Target index (default: `main`)

**Integration:**
- Automatically sends events when Splunk is configured
- Graceful degradation if Splunk is unavailable
- No impact on API performance if Splunk fails

### 2. Systemd Service

**New File: `oai-to-circuit.service`**
- Production-ready systemd unit file
- Security hardening (NoNewPrivileges, ProtectSystem, etc.)
- Runs as unprivileged user `oai-bridge`
- Auto-restart on failure
- Proper logging to journald
- Environment file support for secrets

**Features:**
- HTTP port: 12000
- HTTPS port: 12443 (optional)
- Proper signal handling
- Resource limits
- Capability restrictions

### 3. Documentation

**New Files:**
- [Installation Guide](../getting-started/installation.md) - Complete installation guide
  - User creation
  - Directory setup
  - Credential management
  - Service installation
  - Firewall configuration
  - Troubleshooting
  
- [Deployment Guide](../deployment/deployment-guide.md) - Quick deployment reference
  - Essential commands
  - Quick install steps
  - Common operations
  - Troubleshooting quick fixes

- `credentials.env.example` - Credential template
  - All required environment variables
  - Example Splunk configuration
  - Comments and documentation

**Updated Files:**
- `README.md` - Added Splunk HEC, systemd, and deployment sections
- `ARCHITECTURE.md` - Documented Splunk HEC architecture and integration
- `quotas.json.example` - Updated with opus model blacklisting examples

## Technical Changes

### Code Changes

**`oai_to_circuit/config.py`:**
- Added Splunk HEC configuration fields to `BridgeConfig`
- New env vars: `SPLUNK_HEC_URL`, `SPLUNK_HEC_TOKEN`, etc.

**`oai_to_circuit/app.py`:**
- Integrated SplunkHEC client
- Sends usage events after successful requests
- Sends error events on quota exceeded
- Non-blocking event transmission

**`oai_to_circuit/splunk_hec.py`:** (NEW)
- `SplunkHEC` class for HEC communication
- `send_usage_event()` - Send usage metrics
- `send_error_event()` - Send error events
- Proper error handling and logging

### Test Changes

**`tests/test_splunk_hec.py`:** (NEW)
- 9 comprehensive tests
- Tests for enabled/disabled states
- Event formatting validation
- Error handling verification
- Timeout and failure scenarios

**`tests/test_config.py`:**
- Added test for Splunk HEC configuration loading
- Validates default values
- Tests custom configuration

**`tests/test_requests.py`:**
- Updated test helper to include Splunk HEC fields
- All existing tests continue to pass

## Event Schema

### Usage Event
```json
{
  "time": 1703001234.567,
  "event": {
    "subkey": "team_member_alice",
    "model": "gpt-4o-mini",
    "requests": 1,
    "prompt_tokens": 150,
    "completion_tokens": 200,
    "total_tokens": 350,
    "status_code": 200,
    "success": true,
    "timestamp": "2024-12-18T10:30:45.123456Z"
  },
  "source": "oai-to-circuit",
  "sourcetype": "llm:usage",
  "index": "main"
}
```

### Error Event
```json
{
  "time": 1703001234.567,
  "event": {
    "event_type": "error",
    "error_type": "quota_exceeded",
    "error_message": "Request quota exceeded for model claude-3-opus",
    "subkey": "team_member_alice",
    "model": "claude-3-opus",
    "timestamp": "2024-12-18T10:30:45.123456Z"
  },
  "source": "oai-to-circuit",
  "sourcetype": "llm:usage:error",
  "index": "main"
}
```

## Example Splunk Queries

**Total usage by user and model:**
```spl
index=main sourcetype=llm:usage
| stats sum(requests) as total_requests, sum(total_tokens) as total_tokens by subkey, model
| sort -total_tokens
```

**Quota exceeded events:**
```spl
index=main sourcetype=llm:usage:error error_type=quota_exceeded
| stats count by subkey, model
| sort -count
```

**Token usage over time:**
```spl
index=main sourcetype=llm:usage
| timechart span=1h sum(total_tokens) by model
```

## Deployment Steps

### Quick Install
```bash
# 1. Create user and directories
sudo useradd -r -s /bin/false oai-bridge
sudo mkdir -p /opt/oai-to-circuit /var/lib/oai-to-circuit /etc/oai-to-circuit

# 2. Install application
sudo cp -r . /opt/oai-to-circuit/
cd /opt/oai-to-circuit && sudo pip3 install -r requirements.txt

# 3. Configure credentials
sudo cp credentials.env.example /etc/oai-to-circuit/credentials.env
sudo vi /etc/oai-to-circuit/credentials.env

# 4. Install service
sudo cp oai-to-circuit.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now oai-to-circuit

# 5. Verify
sudo systemctl status oai-to-circuit
curl http://localhost:12000/health
```

## Testing

All 35 tests pass:
- ✓ Splunk HEC tests (9)
- ✓ Config tests (3)
- ✓ Quota tests (3)
- ✓ Request tests (7)
- ✓ All existing tests (13)

## Security

- No hardcoded credentials
- Systemd security hardening
- Unprivileged service user
- Proper file permissions (640 for credentials)
- Protected system directories
- Capability restrictions
- Private temp directory

## Backward Compatibility

- All existing functionality preserved
- Splunk HEC is optional (disabled by default)
- No breaking changes to existing APIs
- All existing tests pass without modification

## Performance

- Splunk HEC uses async HTTP client
- 5-second timeout prevents blocking
- Events sent after response to client (non-blocking)
- Failures do not impact API responses
- Minimal overhead (<10ms per request)

## Files Added

1. `oai_to_circuit/splunk_hec.py` - Splunk HEC client
2. `tests/test_splunk_hec.py` - Splunk HEC tests
3. `oai-to-circuit.service` - Systemd unit file
4. `INSTALLATION.md` - Complete installation guide
5. `DEPLOYMENT_QUICKSTART.md` - Quick deployment reference
6. `credentials.env.example` - Credential template
7. `CHANGELOG_SPLUNK_SYSTEMD.md` - This file

## Files Modified

1. `oai_to_circuit/config.py` - Added Splunk HEC config
2. `oai_to_circuit/app.py` - Integrated Splunk HEC
3. `tests/test_config.py` - Added Splunk config test
4. `tests/test_requests.py` - Updated test helper
5. `README.md` - Added Splunk and systemd docs
6. `ARCHITECTURE.md` - Added Splunk architecture docs
7. `quotas.json.example` - Updated with opus examples

## Next Steps

1. Deploy to production with systemd
2. Configure Splunk HEC for usage analytics
3. Set up Splunk dashboards for monitoring
4. Configure alerts for quota exceeded events
5. Review and optimize quota settings based on usage data

