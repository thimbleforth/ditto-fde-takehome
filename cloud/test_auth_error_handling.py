# test_auth_error_handling.py
import pytest
import json
import jwt
import datetime
import os
import tempfile

# Set up test database path before importing cloud_app
test_db_fd, test_db_path = tempfile.mkstemp(suffix='.sqlite')
os.environ['CLOUD_DB_PATH'] = test_db_path

from cloud_app import app, verify_token
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from data_models import Report, Base

# Create test engine and session
test_engine = create_engine(f"sqlite:///{test_db_path}")
TestSession = sessionmaker(bind=test_engine)

# Test configuration
@pytest.fixture
def client():
    """Create a test client for the Flask app"""
    app.config['TESTING'] = True
    # Ensure the app uses this test DB and reset rate cache between tests
    app.config['CLOUD_DB_PATH'] = test_db_path
    import cloud_app as cloud_app_module
    cloud_app_module._rate_cache = {}
    Base.metadata.create_all(test_engine)
    with app.test_client() as client:
        yield client
    Base.metadata.drop_all(test_engine)

@pytest.fixture
def valid_token():
    """Generate a valid JWT token for testing"""
    PRIVATE_KEY_PATH = "keys/private.pem"
    with open(PRIVATE_KEY_PATH, "rb") as f:
        private_key = f.read()
    
    payload = {
        "user": "test_edge",
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token

@pytest.fixture
def expired_token():
    """Generate an expired JWT token for testing"""
    PRIVATE_KEY_PATH = "keys/private.pem"
    with open(PRIVATE_KEY_PATH, "rb") as f:
        private_key = f.read()
    
    payload = {
        "user": "test_edge",
        "iat": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2),
        "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token

@pytest.fixture
def invalid_signature_token():
    """Generate a token with invalid signature (signed with different key)"""
    # Create a different private key for testing
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    
    different_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    different_key_pem = different_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    payload = {
        "user": "test_edge",
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
    }
    token = jwt.encode(payload, different_key_pem, algorithm="RS256")
    return token


# Test verify_token function directly
def test_verify_token_expired():
    """Test that verify_token returns specific error for expired tokens"""
    PRIVATE_KEY_PATH = "keys/private.pem"
    with open(PRIVATE_KEY_PATH, "rb") as f:
        private_key = f.read()
    
    payload = {
        "user": "test_edge",
        "iat": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2),
        "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")
    
    result = verify_token(token)
    
    assert "error" in result
    assert result["error"] == "expired_token"
    assert "expired" in result["details"].lower()


def test_verify_token_invalid_signature():
    """Test that verify_token returns specific error for invalid signatures"""
    # Create a token signed with a different key
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    
    different_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    different_key_pem = different_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    payload = {
        "user": "test_edge",
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
    }
    token = jwt.encode(payload, different_key_pem, algorithm="RS256")
    
    result = verify_token(token)
    
    assert "error" in result
    assert result["error"] == "invalid_signature"
    assert "signature" in result["details"].lower()


def test_verify_token_malformed():
    """Test that verify_token returns specific error for malformed tokens"""
    malformed_token = "this.is.not.a.valid.jwt.token"
    
    result = verify_token(malformed_token)
    
    assert "error" in result
    assert result["error"] in ["decode_error", "invalid_token"]


def test_verify_token_valid():
    """Test that verify_token returns payload for valid tokens"""
    PRIVATE_KEY_PATH = "keys/private.pem"
    with open(PRIVATE_KEY_PATH, "rb") as f:
        private_key = f.read()
    
    payload = {
        "user": "test_edge",
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")
    
    result = verify_token(token)
    
    assert "error" not in result
    assert result["user"] == "test_edge"


# Test API endpoint error responses
def test_api_expired_token_error_response(client, expired_token):
    """Test that API returns detailed error for expired tokens"""
    report_data = {
        "report_id": "test-report-001",
        "title": "Test Report",
        "content": "This is test content",
        "classification": "CUI",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "test_analyst"
    }
    
    response = client.post(
        '/api/sync',
        data=json.dumps(report_data),
        content_type='application/json',
        headers={'Authorization': f'Bearer {expired_token}'}
    )
    
    assert response.status_code == 401
    data = json.loads(response.data)
    assert 'error' in data
    assert data['error'] == 'expired_token'
    assert 'details' in data
    assert 'expired' in data['details'].lower()


def test_api_invalid_signature_error_response(client, invalid_signature_token):
    """Test that API returns detailed error for invalid signatures"""
    report_data = {
        "report_id": "test-report-002",
        "title": "Test Report",
        "content": "This is test content",
        "classification": "CUI",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "test_analyst"
    }
    
    response = client.post(
        '/api/sync',
        data=json.dumps(report_data),
        content_type='application/json',
        headers={'Authorization': f'Bearer {invalid_signature_token}'}
    )
    
    assert response.status_code == 401
    data = json.loads(response.data)
    assert 'error' in data
    assert data['error'] == 'invalid_signature'
    assert 'details' in data
    assert 'signature' in data['details'].lower()


def test_api_malformed_token_error_response(client):
    """Test that API returns detailed error for malformed tokens"""
    report_data = {
        "report_id": "test-report-003",
        "title": "Test Report",
        "content": "This is test content",
        "classification": "CUI",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "test_analyst"
    }
    
    response = client.post(
        '/api/sync',
        data=json.dumps(report_data),
        content_type='application/json',
        headers={'Authorization': 'Bearer not.a.valid.token'}
    )
    
    assert response.status_code == 401
    data = json.loads(response.data)
    assert 'error' in data
    assert 'details' in data
