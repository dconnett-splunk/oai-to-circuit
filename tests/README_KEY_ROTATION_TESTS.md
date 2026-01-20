# Key Rotation Tests

## Overview

Comprehensive test suite for key rotation functionality covering database operations, lifecycle management, and integration workflows.

## Test Files

- **`test_key_rotation.py`** - 18 tests, 100% pass rate

## Running Tests

### Run All Key Rotation Tests

```bash
cd /opt/oai-to-circuit
python3 -m pytest tests/test_key_rotation.py -v
```

### Run Specific Test Class

```bash
# Test lifecycle operations
python3 -m pytest tests/test_key_rotation.py::TestKeyLifecycle -v

# Test rotation script
python3 -m pytest tests/test_key_rotation.py::TestKeyRotationScript -v

# Test historical data preservation
python3 -m pytest tests/test_key_rotation.py::TestHistoricalDataPreservation -v

# Test integration workflow
python3 -m pytest tests/test_key_rotation.py::TestKeyRotationIntegration -v

# Test backward compatibility
python3 -m pytest tests/test_key_rotation.py::TestBackwardCompatibility -v
```

### Run Specific Test

```bash
python3 -m pytest tests/test_key_rotation.py::TestKeyLifecycle::test_revoked_key_rejected -v
```

## Test Coverage

### 1. TestKeyLifecycle (7 tests)

Tests for `key_lifecycle` table and `QuotaManager` integration:

| Test | Description |
|------|-------------|
| `test_lifecycle_table_created` | Verifies table creation on init |
| `test_lifecycle_indexes_created` | Verifies indexes on user_id and status |
| `test_key_without_lifecycle_is_active` | Keys without records treated as active |
| `test_revoked_key_rejected` | Revoked keys return 403 |
| `test_replaced_key_rejected` | Replaced keys return 403 |
| `test_active_key_in_lifecycle_accepted` | Explicit active status works |
| `test_key_not_in_quotas_rejected` | Non-existent keys rejected |

**Coverage:**
- ✅ Database schema validation
- ✅ Index creation
- ✅ QuotaManager authorization logic
- ✅ Lifecycle status checking

### 2. TestKeyRotationScript (7 tests)

Tests for `rotate_key.py` script functions:

| Test | Description |
|------|-------------|
| `test_get_key_info` | Retrieves key information |
| `test_get_key_info_nonexistent` | Handles missing keys |
| `test_revoke_key` | Revokes key and updates quotas |
| `test_revoke_nonexistent_key` | Handles revoking missing key |
| `test_revoke_already_revoked_key` | Prevents double revocation |
| `test_activate_key` | Activates key in lifecycle |
| `test_generate_subkey` | Generates unique secure keys |

**Coverage:**
- ✅ Key information retrieval
- ✅ Revocation operations
- ✅ quotas.json updates
- ✅ Lifecycle table updates
- ✅ Error handling
- ✅ Subkey generation

### 3. TestHistoricalDataPreservation (2 tests)

Tests that historical data remains after revocation:

| Test | Description |
|------|-------------|
| `test_usage_preserved_after_revocation` | Usage data remains in database |
| `test_name_preserved_after_revocation` | Friendly names remain accessible |

**Coverage:**
- ✅ Usage data preservation
- ✅ Name mapping preservation
- ✅ Historical reporting capability

### 4. TestKeyRotationIntegration (1 test)

End-to-end integration test:

| Test | Description |
|------|-------------|
| `test_full_rotation_workflow` | Complete rotation from start to finish |

**Workflow tested:**
1. ✅ Record usage with old key
2. ✅ Verify old key authorized
3. ✅ Generate new key
4. ✅ Add new key to database
5. ✅ Activate new key
6. ✅ Revoke old key
7. ✅ Verify old key rejected
8. ✅ Verify historical data preserved
9. ✅ Verify lifecycle relationships

### 5. TestBackwardCompatibility (1 test)

Tests compatibility with existing systems:

| Test | Description |
|------|-------------|
| `test_database_without_lifecycle_table` | Works with old database schema |

**Coverage:**
- ✅ Automatic table creation
- ✅ No breaking changes
- ✅ Graceful migration

## Test Results

```
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-7.4.0, pluggy-1.2.0
collected 18 items

tests/test_key_rotation.py::TestKeyLifecycle::test_active_key_in_lifecycle_accepted PASSED [  5%]
tests/test_key_rotation.py::TestKeyLifecycle::test_key_not_in_quotas_rejected PASSED [ 11%]
tests/test_key_rotation.py::TestKeyLifecycle::test_key_without_lifecycle_is_active PASSED [ 16%]
tests/test_key_rotation.py::TestKeyLifecycle::test_lifecycle_indexes_created PASSED [ 22%]
tests/test_key_rotation.py::TestKeyLifecycle::test_lifecycle_table_created PASSED [ 27%]
tests/test_key_rotation.py::TestKeyLifecycle::test_replaced_key_rejected PASSED [ 33%]
tests/test_key_rotation.py::TestKeyLifecycle::test_revoked_key_rejected PASSED [ 38%]
tests/test_key_rotation.py::TestKeyRotationScript::test_activate_key PASSED [ 44%]
tests/test_key_rotation.py::TestKeyRotationScript::test_generate_subkey PASSED [ 50%]
tests/test_key_rotation.py::TestKeyRotationScript::test_get_key_info PASSED [ 55%]
tests/test_key_rotation.py::TestKeyRotationScript::test_get_key_info_nonexistent PASSED [ 61%]
tests/test_key_rotation.py::TestKeyRotationScript::test_revoke_already_revoked_key PASSED [ 66%]
tests/test_key_rotation.py::TestKeyRotationScript::test_revoke_key PASSED [ 72%]
tests/test_key_rotation.py::TestKeyRotationScript::test_revoke_nonexistent_key PASSED [ 77%]
tests/test_key_rotation.py::TestHistoricalDataPreservation::test_name_preserved_after_revocation PASSED [ 83%]
tests/test_key_rotation.py::TestHistoricalDataPreservation::test_usage_preserved_after_revocation PASSED [ 88%]
tests/test_key_rotation.py::TestKeyRotationIntegration::test_full_rotation_workflow PASSED [ 94%]
tests/test_key_rotation.py::TestBackwardCompatibility::test_database_without_lifecycle_table PASSED [100%]

============================== 18 passed in 0.16s
```

✅ **All 18 tests passing**

## What's Tested

### Core Functionality
- ✅ Key lifecycle state management (active, revoked, replaced)
- ✅ Database schema and index creation
- ✅ QuotaManager authorization with lifecycle checking
- ✅ Key revocation with quotas.json updates
- ✅ Key activation and replacement
- ✅ Secure subkey generation

### Data Integrity
- ✅ Historical usage data preservation
- ✅ Friendly name preservation
- ✅ Lifecycle relationship tracking (replaced_by, replaces)
- ✅ Audit trail (timestamps, reasons)

### Integration
- ✅ End-to-end rotation workflow
- ✅ Database and quotas.json synchronization
- ✅ Multiple key operations in sequence

### Compatibility
- ✅ Works with databases missing lifecycle table
- ✅ Automatic migration
- ✅ No breaking changes

## What's NOT Tested

These require manual testing or integration tests:

- ❌ Actual HTTP requests with revoked keys (needs FastAPI integration)
- ❌ Splunk HEC event logging for rotations
- ❌ CLI argument parsing for rotate_key.py
- ❌ File I/O error handling (permissions, disk full)
- ❌ Concurrent rotation operations

## CI/CD Integration

Add to your CI pipeline:

```yaml
# .github/workflows/test.yml
- name: Run Key Rotation Tests
  run: |
    python3 -m pytest tests/test_key_rotation.py -v --cov=oai_to_circuit.quota --cov=rotate_key
```

## Manual Testing Checklist

After automated tests pass, manually verify:

- [ ] `python3 rotate_key.py --help` shows usage
- [ ] `python3 rotate_key.py --status KEY` works on production
- [ ] Revoked key receives 403 Unauthorized
- [ ] Historical Splunk data remains accessible
- [ ] quotas.json properly updated after revocation
- [ ] New keys work immediately after rotation
- [ ] Email-based Splunk aggregation works across rotations

## Test Data

Tests use temporary files and databases:
- Database: `tempfile.mkstemp(suffix='.db')`
- Quotas: `tempfile.mkstemp(suffix='.json')`
- Automatic cleanup in `tearDown()`

No production data touched by tests.

## Debugging Failed Tests

### Test fails with "table not found"

Check that `QuotaManager.__init__` creates all tables:
```python
self.quota_manager = QuotaManager(self.db_path, self.quotas)
# Should create: usage, subkey_names, key_lifecycle
```

### Test fails with "module not found"

Ensure path setup at top of test file:
```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
```

### Revocation test fails

Check that:
1. Key exists in `subkey_names`
2. quotas.json file is writable
3. Lifecycle table exists

## Future Test Enhancements

Potential additions:

1. **Performance tests** - Test with 1000+ keys
2. **Concurrent access** - Multiple rotations simultaneously
3. **Error recovery** - Database corruption, network failures
4. **CLI tests** - Full command-line argument testing
5. **Integration tests** - With running FastAPI server
6. **Load tests** - Authorization check performance

## Related Documentation

- **[Key Rotation Guide](../docs/operations/key-rotation.md)** - User documentation
- **[Database Queries](../docs/operations/database-queries.md)** - SQL reference
- **[Subkey Management](../docs/operations/subkey-management.md)** - Overall lifecycle

---

**Last Updated:** 2026-01-20  
**Test Suite Version:** 1.0  
**Status:** ✅ All passing

