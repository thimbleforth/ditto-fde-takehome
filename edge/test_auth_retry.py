# test_auth_retry.py
import pytest
import jwt
import datetime
import os
import tempfile
import sqlite3
from unittest.mock import Mock, patch, MagicMock
import sys

# Set up test database path
test_db_fd, test_db_path = tempfile.mkstemp(suffix='.sqlite')
os.environ['EDGE_DB_PATH'] = test_db_path
os.environ['EDGE_USER'] = 'test_edge'
os.environ['CLOUD_URL'] = 'http://test-cloud:8443'
os.environ['PRIVATE_KEY_PATH'] = 'keys/private.pem'

import edge_app
import database_manager


@pytest.fixture
def test_db():
    """Create a test database"""
    database_manager.init_db()
    yield test_db_path
    # Cleanup
    try:
        if os.path.exists(test_db_path):
            os.unlink(test_db_path)
    except Exception:
        pass


@pytest.fixture
def sample_report():
    """Create a sample report for testing"""
    return {
        "id": 1,
        "report_id": "test-report-001",
        "title": "Test Report",
        "content": "Test content",
        "classification": "CUI",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "test_edge",
        "is_deleted": 0,
        "is_synchronized": 0
    }


def test_sync_single_report_success_on_first_try(test_db, sample_report):
    """Test successful sync on first attempt"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}
    
    with patch('edge_app.requests.post', return_value=mock_response) as mock_post:
        result = edge_app.sync_single_report(sample_report)
        
        assert result["status"] == "success"
        assert result["report_id"] == "test-report-001"
        assert mock_post.call_count == 1


def test_sync_single_report_401_triggers_retry(test_db, sample_report):
    """Test that 401 error triggers token regeneration and retry"""
    # First call returns 401, second call succeeds
    mock_response_401 = Mock()
    mock_response_401.status_code = 401
    mock_response_401.json.return_value = {
        "error": "expired_token",
        "details": "Token has expired"
    }
    
    mock_response_200 = Mock()
    mock_response_200.status_code = 200
    mock_response_200.json.return_value = {"status": "ok"}
    
    with patch('edge_app.requests.post', side_effect=[mock_response_401, mock_response_200]) as mock_post:
        with patch('edge_app.issue_token', return_value='new_token') as mock_issue:
            result = edge_app.sync_single_report(sample_report)
            
            # Should succeed after retry
            assert result["status"] == "success"
            assert result["report_id"] == "test-report-001"
            
            # Should have called post twice (original + retry)
            assert mock_post.call_count == 2
            
            # Should have issued token twice (original + regenerated)
            assert mock_issue.call_count == 2


def test_sync_single_report_401_twice_fails(test_db, sample_report):
    """Test that two consecutive 401 errors result in failure"""
    # Both calls return 401
    mock_response_401 = Mock()
    mock_response_401.status_code = 401
    mock_response_401.json.return_value = {
        "error": "invalid_signature",
        "details": "Token signature verification failed"
    }
    mock_response_401.text = '{"error": "invalid_signature"}'
    
    with patch('edge_app.requests.post', return_value=mock_response_401) as mock_post:
        with patch('edge_app.issue_token', return_value='token') as mock_issue:
            result = edge_app.sync_single_report(sample_report)
            
            # Should fail after retry
            assert result["status"] == "failed"
            assert result["report_id"] == "test-report-001"
            assert "401" in result["error"]
            
            # Should have called post twice (original + retry)
            assert mock_post.call_count == 2
            
            # Should have issued token twice
            assert mock_issue.call_count == 2


def test_sync_single_report_no_retry_on_other_errors(test_db, sample_report):
    """Test that non-401 errors do not trigger retry"""
    mock_response_500 = Mock()
    mock_response_500.status_code = 500
    mock_response_500.text = "Internal Server Error"
    
    with patch('edge_app.requests.post', return_value=mock_response_500) as mock_post:
        result = edge_app.sync_single_report(sample_report)
        
        # Should fail without retry
        assert result["status"] == "failed"
        assert "500" in result["error"]
        
        # Should have called post only once (no retry)
        assert mock_post.call_count == 1


def test_sync_single_report_retry_auth_false_prevents_retry(test_db, sample_report):
    """Test that retry_auth=False prevents retry on 401"""
    mock_response_401 = Mock()
    mock_response_401.status_code = 401
    mock_response_401.json.return_value = {
        "error": "expired_token",
        "details": "Token has expired"
    }
    mock_response_401.text = '{"error": "expired_token"}'
    
    with patch('edge_app.requests.post', return_value=mock_response_401) as mock_post:
        result = edge_app.sync_single_report(sample_report, retry_auth=False)
        
        # Should fail without retry
        assert result["status"] == "failed"
        assert "401" in result["error"]
        
        # Should have called post only once
        assert mock_post.call_count == 1


def test_sync_single_report_logs_auth_error_details(test_db, sample_report):
    """Test that authentication error details are logged"""
    mock_response_401 = Mock()
    mock_response_401.status_code = 401
    mock_response_401.json.return_value = {
        "error": "expired_token",
        "details": "Token has expired"
    }
    
    mock_response_200 = Mock()
    mock_response_200.status_code = 200
    
    with patch('edge_app.requests.post', side_effect=[mock_response_401, mock_response_200]):
        with patch('edge_app.log_warning') as mock_log_warning:
            with patch('edge_app.log_info') as mock_log_info:
                result = edge_app.sync_single_report(sample_report)
                
                # Should have logged the authentication failure
                warning_calls = [str(call) for call in mock_log_warning.call_args_list]
                assert any('Authentication failed' in str(call) for call in warning_calls)
                
                # Should have logged the error details
                info_calls = [str(call) for call in mock_log_info.call_args_list]
                assert any('expired_token' in str(call) for call in info_calls)


def test_sync_single_report_connection_error_no_retry(test_db, sample_report):
    """Test that connection errors do not trigger auth retry"""
    with patch('edge_app.requests.post', side_effect=Exception("Connection refused")) as mock_post:
        result = edge_app.sync_single_report(sample_report)
        
        # Should fail without retry
        assert result["status"] == "failed"
        assert "Connection refused" in result["error"] or "Unexpected error" in result["error"]
        
        # Should have called post only once
        assert mock_post.call_count == 1


def test_token_regeneration_creates_new_token():
    """Test that issue_token generates valid JWT tokens"""
    import time
    
    token1 = edge_app.issue_token()
    
    # Wait a moment to ensure different timestamp
    time.sleep(1)
    
    token2 = edge_app.issue_token()
    
    # Tokens should be different (different iat timestamps)
    assert token1 != token2
    
    # Both should be valid JWT tokens
    assert isinstance(token1, str)
    assert isinstance(token2, str)
    assert len(token1) > 0
    assert len(token2) > 0
    
    # Verify tokens can be decoded
    PUBLIC_KEY_PATH = "keys/public.pem"
    with open(PUBLIC_KEY_PATH, "rb") as f:
        public_key = f.read()
    
    payload1 = jwt.decode(token1, public_key, algorithms=["RS256"])
    payload2 = jwt.decode(token2, public_key, algorithms=["RS256"])
    
    assert payload1["user"] == "test_edge"
    assert payload2["user"] == "test_edge"
    assert payload1["iat"] < payload2["iat"]  # Second token should have later timestamp
