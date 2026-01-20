#!/usr/bin/env python3
"""
Tests for key rotation functionality.

Tests cover:
- Key lifecycle management (revoke, rotate, replace)
- Database schema and operations
- QuotaManager integration with lifecycle status
- Historical data preservation
- Backward compatibility
"""

import json
import os
import secrets
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the modules we're testing
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from oai_to_circuit.quota import QuotaManager


class TestKeyLifecycle(unittest.TestCase):
    """Test key_lifecycle table operations."""
    
    def setUp(self):
        """Create temporary database for testing."""
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.quotas = {
            'test_key_active': {
                'gpt-4o': {'requests': 100, 'total_tokens': 50000}
            },
            'test_key_revoked': {
                'gpt-4o': {'requests': 0}
            }
        }
        self.quota_manager = QuotaManager(self.db_path, self.quotas)
    
    def tearDown(self):
        """Clean up temporary database."""
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def test_lifecycle_table_created(self):
        """Test that key_lifecycle table is created on initialization."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='key_lifecycle'"
        )
        self.assertIsNotNone(cursor.fetchone(), "key_lifecycle table should exist")
        
        # Check columns
        cursor.execute("PRAGMA table_info(key_lifecycle)")
        columns = {row[1] for row in cursor.fetchall()}
        expected_columns = {
            'subkey', 'user_id', 'status', 'revoked_at', 
            'revoke_reason', 'replaced_by', 'replaces'
        }
        self.assertEqual(columns, expected_columns)
        
        conn.close()
    
    def test_lifecycle_indexes_created(self):
        """Test that indexes are created for key_lifecycle table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='key_lifecycle'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        
        # Should have indexes on user_id and status
        self.assertIn('idx_lifecycle_user_id', indexes)
        self.assertIn('idx_lifecycle_status', indexes)
        
        conn.close()
    
    def test_key_without_lifecycle_is_active(self):
        """Test that keys without lifecycle records are treated as active."""
        # Key exists in quotas but not in lifecycle table
        self.assertTrue(self.quota_manager.is_subkey_authorized('test_key_active'))
    
    def test_revoked_key_rejected(self):
        """Test that revoked keys are rejected."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Insert revoked key
        cursor.execute("""
            INSERT INTO key_lifecycle (subkey, status, revoked_at, revoke_reason)
            VALUES (?, 'revoked', ?, 'Testing revocation')
        """, ('test_key_revoked', datetime.now(timezone.utc).isoformat()))
        conn.commit()
        conn.close()
        
        # Key should be rejected even though it's in quotas
        self.assertFalse(self.quota_manager.is_subkey_authorized('test_key_revoked'))
    
    def test_replaced_key_rejected(self):
        """Test that replaced keys are rejected."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Insert replaced key
        cursor.execute("""
            INSERT INTO key_lifecycle (subkey, status, revoked_at, revoke_reason, replaced_by)
            VALUES (?, 'replaced', ?, 'Key rotation', 'test_key_new')
        """, ('test_key_active', datetime.now(timezone.utc).isoformat()))
        conn.commit()
        conn.close()
        
        # Key should be rejected
        self.assertFalse(self.quota_manager.is_subkey_authorized('test_key_active'))
    
    def test_active_key_in_lifecycle_accepted(self):
        """Test that explicitly active keys in lifecycle table are accepted."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Insert active key
        cursor.execute("""
            INSERT INTO key_lifecycle (subkey, status, user_id)
            VALUES (?, 'active', 'test@example.com')
        """, ('test_key_active',))
        conn.commit()
        conn.close()
        
        # Key should be accepted
        self.assertTrue(self.quota_manager.is_subkey_authorized('test_key_active'))
    
    def test_key_not_in_quotas_rejected(self):
        """Test that keys not in quotas are rejected regardless of lifecycle."""
        # Key not in quotas should be rejected
        self.assertFalse(self.quota_manager.is_subkey_authorized('nonexistent_key'))


class TestKeyRotationScript(unittest.TestCase):
    """Test rotate_key.py script functionality."""
    
    def setUp(self):
        """Set up test database and quotas file."""
        # Create temporary database
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        
        # Create temporary quotas file
        self.quotas_fd, self.quotas_path = tempfile.mkstemp(suffix='.json')
        os.write(self.quotas_fd, json.dumps({
            'test_key_1': {
                'gpt-4o': {'requests': 100, 'total_tokens': 50000}
            }
        }).encode())
        os.close(self.quotas_fd)
        
        # Initialize database
        self.quotas = {'test_key_1': {'gpt-4o': {'requests': 100}}}
        self.quota_manager = QuotaManager(self.db_path, self.quotas)
        
        # Add test key to subkey_names
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO subkey_names (subkey, friendly_name, email)
            VALUES (?, 'Test User', 'test@example.com')
        """, ('test_key_1',))
        conn.commit()
        conn.close()
        
        # Import rotate_key functions
        import rotate_key
        self.rotate_key = rotate_key
    
    def tearDown(self):
        """Clean up temporary files."""
        os.close(self.db_fd)
        os.unlink(self.db_path)
        os.unlink(self.quotas_path)
    
    def test_get_key_info(self):
        """Test retrieving key information."""
        info = self.rotate_key.get_key_info(self.db_path, 'test_key_1')
        
        self.assertIsNotNone(info)
        self.assertEqual(info['subkey'], 'test_key_1')
        self.assertEqual(info['friendly_name'], 'Test User')
        self.assertEqual(info['email'], 'test@example.com')
        self.assertEqual(info['status'], 'active')
    
    def test_get_key_info_nonexistent(self):
        """Test getting info for nonexistent key."""
        info = self.rotate_key.get_key_info(self.db_path, 'nonexistent_key')
        self.assertIsNone(info)
    
    def test_revoke_key(self):
        """Test key revocation."""
        success = self.rotate_key.revoke_key(
            self.db_path,
            self.quotas_path,
            'test_key_1',
            'Testing revocation'
        )
        
        self.assertTrue(success)
        
        # Check lifecycle table
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status, revoke_reason FROM key_lifecycle WHERE subkey=?",
            ('test_key_1',)
        )
        row = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 'revoked')
        self.assertEqual(row[1], 'Testing revocation')
        
        # Check quotas.json updated
        with open(self.quotas_path, 'r') as f:
            quotas = json.load(f)
        
        # Quotas should be set to 0
        self.assertEqual(quotas['test_key_1']['gpt-4o']['requests'], 0)
        self.assertEqual(quotas['test_key_1']['gpt-4o']['total_tokens'], 0)
        
        # Should have revocation metadata
        self.assertIn('_REVOKED_test_key_1', quotas)
    
    def test_revoke_nonexistent_key(self):
        """Test revoking a key that doesn't exist."""
        success = self.rotate_key.revoke_key(
            self.db_path,
            self.quotas_path,
            'nonexistent_key',
            'Testing'
        )
        
        self.assertFalse(success)
    
    def test_revoke_already_revoked_key(self):
        """Test revoking a key that's already revoked."""
        # First revocation
        self.rotate_key.revoke_key(
            self.db_path,
            self.quotas_path,
            'test_key_1',
            'First revocation'
        )
        
        # Second revocation should fail
        success = self.rotate_key.revoke_key(
            self.db_path,
            self.quotas_path,
            'test_key_1',
            'Second revocation'
        )
        
        self.assertFalse(success)
    
    def test_activate_key(self):
        """Test activating a key."""
        success = self.rotate_key.activate_key(
            self.db_path,
            'test_key_1',
            user_id='test@example.com'
        )
        
        self.assertTrue(success)
        
        # Check lifecycle table
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status, user_id FROM key_lifecycle WHERE subkey=?",
            ('test_key_1',)
        )
        row = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 'active')
        self.assertEqual(row[1], 'test@example.com')
    
    def test_generate_subkey(self):
        """Test subkey generation."""
        key1 = self.rotate_key.generate_subkey('test_prefix')
        key2 = self.rotate_key.generate_subkey('test_prefix')
        
        # Should start with prefix
        self.assertTrue(key1.startswith('test_prefix_'))
        
        # Should be unique
        self.assertNotEqual(key1, key2)
        
        # Should be reasonably long (prefix + _ + 32 chars)
        self.assertGreater(len(key1), 40)


class TestHistoricalDataPreservation(unittest.TestCase):
    """Test that historical data is preserved when keys are revoked."""
    
    def setUp(self):
        """Create database with usage history."""
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.quotas = {
            'test_key_historical': {
                'gpt-4o': {'requests': 100}
            }
        }
        self.quota_manager = QuotaManager(self.db_path, self.quotas)
        
        # Add key with name
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO subkey_names (subkey, friendly_name, email)
            VALUES (?, 'Historical User', 'hist@example.com')
        """, ('test_key_historical',))
        conn.commit()
        conn.close()
        
        # Record some usage
        self.quota_manager.record_usage(
            'test_key_historical',
            'gpt-4o',
            request_inc=10,
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500
        )
    
    def tearDown(self):
        """Clean up."""
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def test_usage_preserved_after_revocation(self):
        """Test that usage data is preserved after key revocation."""
        # Revoke the key
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO key_lifecycle (subkey, status, revoked_at, revoke_reason)
            VALUES (?, 'revoked', ?, 'Testing')
        """, ('test_key_historical', datetime.now(timezone.utc).isoformat()))
        conn.commit()
        conn.close()
        
        # Usage data should still be there
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT requests, total_tokens FROM usage WHERE subkey=? AND model=?",
            ('test_key_historical', 'gpt-4o')
        )
        row = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 10)  # requests
        self.assertEqual(row[1], 1500)  # total_tokens
    
    def test_name_preserved_after_revocation(self):
        """Test that friendly name is preserved after revocation."""
        # Revoke the key
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO key_lifecycle (subkey, status, revoked_at)
            VALUES (?, 'revoked', ?)
        """, ('test_key_historical', datetime.now(timezone.utc).isoformat()))
        conn.commit()
        conn.close()
        
        # Name should still be there
        name = self.quota_manager.get_friendly_name('test_key_historical')
        self.assertEqual(name, 'Historical User')


class TestKeyRotationIntegration(unittest.TestCase):
    """Integration tests for key rotation workflow."""
    
    def setUp(self):
        """Set up complete test environment."""
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.quotas_fd, self.quotas_path = tempfile.mkstemp(suffix='.json')
        
        # Initial quotas
        initial_quotas = {
            'old_key': {
                'gpt-4o': {'requests': 100, 'total_tokens': 50000}
            }
        }
        os.write(self.quotas_fd, json.dumps(initial_quotas).encode())
        os.close(self.quotas_fd)
        
        # Initialize
        self.quota_manager = QuotaManager(self.db_path, initial_quotas)
        
        # Add key to names
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO subkey_names (subkey, friendly_name, email)
            VALUES (?, 'Alice Smith', 'alice@example.com')
        """, ('old_key',))
        conn.commit()
        conn.close()
        
        import rotate_key
        self.rotate_key = rotate_key
    
    def tearDown(self):
        """Clean up."""
        os.close(self.db_fd)
        os.unlink(self.db_path)
        os.unlink(self.quotas_path)
    
    def test_full_rotation_workflow(self):
        """Test complete key rotation workflow."""
        # 1. Record usage with old key
        self.quota_manager.record_usage('old_key', 'gpt-4o', 
                                        request_inc=5, total_tokens=1000)
        
        # 2. Verify old key works
        self.assertTrue(self.quota_manager.is_subkey_authorized('old_key'))
        
        # 3. Generate new key
        new_key = self.rotate_key.generate_subkey('test')
        
        # 4. Add new key to database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO subkey_names (subkey, friendly_name, email, description)
            VALUES (?, 'Alice Smith', 'alice@example.com', 'Rotated key')
        """, (new_key,))
        conn.commit()
        conn.close()
        
        # 5. Activate new key
        self.rotate_key.activate_key(self.db_path, new_key, replaces='old_key')
        
        # 6. Revoke old key
        success = self.rotate_key.revoke_key(
            self.db_path,
            self.quotas_path,
            'old_key',
            'Key rotation',
            replaced_by=new_key
        )
        self.assertTrue(success)
        
        # 7. Verify old key is rejected
        # Need to reload quotas since they were updated
        with open(self.quotas_path, 'r') as f:
            new_quotas = json.load(f)
        self.quota_manager = QuotaManager(self.db_path, new_quotas)
        
        self.assertFalse(self.quota_manager.is_subkey_authorized('old_key'))
        
        # 8. Verify historical data preserved
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT requests, total_tokens FROM usage WHERE subkey=? AND model=?",
            ('old_key', 'gpt-4o')
        )
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 5)
        self.assertEqual(row[1], 1000)
        
        # 9. Verify lifecycle relationship
        cursor.execute(
            "SELECT status, replaced_by FROM key_lifecycle WHERE subkey=?",
            ('old_key',)
        )
        old_row = cursor.fetchone()
        self.assertEqual(old_row[0], 'replaced')
        self.assertEqual(old_row[1], new_key)
        
        cursor.execute(
            "SELECT status, replaces FROM key_lifecycle WHERE subkey=?",
            (new_key,)
        )
        new_row = cursor.fetchone()
        self.assertEqual(new_row[0], 'active')
        self.assertEqual(new_row[1], 'old_key')
        
        conn.close()


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility with existing systems."""
    
    def test_database_without_lifecycle_table(self):
        """Test that system works with database missing lifecycle table."""
        # Create database manually without lifecycle table
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create only usage and subkey_names tables
        cursor.execute("""
            CREATE TABLE usage (
                subkey TEXT NOT NULL,
                model TEXT NOT NULL,
                requests INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (subkey, model)
            )
        """)
        cursor.execute("""
            CREATE TABLE subkey_names (
                subkey TEXT PRIMARY KEY,
                friendly_name TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        
        # QuotaManager should create lifecycle table on init
        quotas = {'test_key': {'gpt-4o': {'requests': 100}}}
        quota_manager = QuotaManager(db_path, quotas)
        
        # Should work fine
        self.assertTrue(quota_manager.is_subkey_authorized('test_key'))
        
        # Lifecycle table should now exist
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='key_lifecycle'"
        )
        self.assertIsNotNone(cursor.fetchone())
        conn.close()
        
        # Clean up
        os.close(db_fd)
        os.unlink(db_path)


if __name__ == '__main__':
    unittest.main()

