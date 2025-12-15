# test_sync_handler.py
import pytest
import json
import jwt
import datetime
import os
import tempfile
import sys

# Set up test database path before importing cloud_app
test_db_fd, test_db_path = tempfile.mkstemp(suffix='.sqlite')
os.environ['CLOUD_DB_PATH'] = test_db_path

from cloud_app import app
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
def db_session():
    """Create a fresh database session for each test"""
    Base.metadata.create_all(test_engine)
    session = TestSession()
    yield session
    session.close()
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

def test_successful_report_storage(client, db_session, valid_token):
    """Test successful report synchronization and storage"""
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
        headers={'Authorization': f'Bearer {valid_token}'}
    )
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'ok'
    
    # Verify report was stored in database
    report = db_session.query(Report).filter_by(report_id="test-report-001").first()
    assert report is not None
    assert report.title == "Test Report"
    assert report.content == "This is test content"
    assert report.classification == "CUI"
    assert report.updated_by == "test_analyst"
    assert report.is_deleted == 0

def test_validation_missing_report_id(client, valid_token):
    """Test validation error when report_id is missing"""
    report_data = {
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
        headers={'Authorization': f'Bearer {valid_token}'}
    )
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'report_id' in data['details']

def test_validation_missing_multiple_fields(client, valid_token):
    """Test validation error when multiple required fields are missing"""
    report_data = {
        "report_id": "test-report-002"
    }
    
    response = client.post(
        '/api/sync',
        data=json.dumps(report_data),
        content_type='application/json',
        headers={'Authorization': f'Bearer {valid_token}'}
    )
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'Missing required field' in data['details']

def test_validation_empty_request_body(client, valid_token):
    """Test validation error when request body is empty"""
    response = client.post(
        '/api/sync',
        data=json.dumps(None),
        content_type='application/json',
        headers={'Authorization': f'Bearer {valid_token}'}
    )
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'Request body is required' in data['details']

def test_soft_delete_handling(client, db_session, valid_token):
    """Test that soft deleted reports are stored with is_deleted flag"""
    report_data = {
        "report_id": "test-report-003",
        "title": "Deleted Report",
        "content": "This report was deleted",
        "classification": "IL4",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "test_analyst",
        "is_deleted": 1
    }
    
    response = client.post(
        '/api/sync',
        data=json.dumps(report_data),
        content_type='application/json',
        headers={'Authorization': f'Bearer {valid_token}'}
    )
    
    assert response.status_code == 200
    
    # Verify report was stored with is_deleted flag
    report = db_session.query(Report).filter_by(report_id="test-report-003").first()
    assert report is not None
    assert report.is_deleted == 1
    assert report.title == "Deleted Report"

def test_authentication_missing_header(client):
    """Test that requests without Authorization header are rejected"""
    report_data = {
        "report_id": "test-report-004",
        "title": "Test Report",
        "content": "This is test content",
        "classification": "CUI",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "test_analyst"
    }
    
    response = client.post(
        '/api/sync',
        data=json.dumps(report_data),
        content_type='application/json'
    )
    
    assert response.status_code == 401
    data = json.loads(response.data)
    assert 'error' in data

def test_authentication_invalid_token(client):
    """Test that requests with invalid tokens are rejected"""
    report_data = {
        "report_id": "test-report-005",
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
        headers={'Authorization': 'Bearer invalid_token_here'}
    )
    
    assert response.status_code == 401
    data = json.loads(response.data)
    assert 'error' in data

def test_authentication_expired_token(client, expired_token):
    """Test that requests with expired tokens are rejected"""
    report_data = {
        "report_id": "test-report-006",
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
