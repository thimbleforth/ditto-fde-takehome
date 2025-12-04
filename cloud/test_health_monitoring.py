# test_health_monitoring.py
import pytest
import json
import datetime
import os
import tempfile

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

def test_health_endpoint_response_format(client, db_session):
    """Test that health endpoint returns correct response format"""
    response = client.get('/api/health')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    
    # Verify required fields are present
    assert 'status' in data
    assert 'time' in data
    assert 'database_status' in data
    assert 'total_reports' in data
    assert 'last_sync_timestamp' in data
    
    # Verify field values
    assert data['status'] == 'running'
    assert data['database_status'] == 'connected'
    assert isinstance(data['total_reports'], int)
    
    # Verify timestamp is in ISO 8601 format
    try:
        datetime.datetime.fromisoformat(data['time'])
    except ValueError:
        pytest.fail("Time field is not in valid ISO 8601 format")

def test_health_database_connectivity_check(client, db_session):
    """Test that health endpoint checks database connectivity"""
    response = client.get('/api/health')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    
    # Database should be connected
    assert data['database_status'] == 'connected'
    assert data['total_reports'] == 0  # Empty database initially

def test_health_report_count_statistics(client, db_session):
    """Test that health endpoint returns accurate report count"""
    # Add some test reports to the database
    report1 = Report(
        report_id="test-001",
        title="Test Report 1",
        content="Content 1",
        classification="CUI",
        updated_at=datetime.datetime.now(datetime.timezone.utc),
        updated_by="analyst1"
    )
    report2 = Report(
        report_id="test-002",
        title="Test Report 2",
        content="Content 2",
        classification="IL4",
        updated_at=datetime.datetime.now(datetime.timezone.utc),
        updated_by="analyst2"
    )
    report3 = Report(
        report_id="test-003",
        title="Test Report 3",
        content="Content 3",
        classification="IL5",
        updated_at=datetime.datetime.now(datetime.timezone.utc),
        updated_by="analyst3"
    )
    
    db_session.add(report1)
    db_session.add(report2)
    db_session.add(report3)
    db_session.commit()
    
    response = client.get('/api/health')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    
    # Should report 3 total reports
    assert data['total_reports'] == 3
    assert data['database_status'] == 'connected'

def test_health_last_sync_timestamp(client, db_session):
    """Test that health endpoint returns last sync timestamp"""
    # Add reports with different timestamps
    older_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
    newer_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    
    report1 = Report(
        report_id="test-001",
        title="Older Report",
        content="Content 1",
        classification="CUI",
        updated_at=older_time,
        updated_by="analyst1"
    )
    report2 = Report(
        report_id="test-002",
        title="Newer Report",
        content="Content 2",
        classification="IL4",
        updated_at=newer_time,
        updated_by="analyst2"
    )
    
    db_session.add(report1)
    db_session.add(report2)
    db_session.commit()
    
    response = client.get('/api/health')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    
    # Should return the most recent timestamp
    assert data['last_sync_timestamp'] is not None
    last_sync = datetime.datetime.fromisoformat(data['last_sync_timestamp'])
    
    # Ensure both datetimes are timezone-aware for comparison
    if last_sync.tzinfo is None:
        last_sync = last_sync.replace(tzinfo=datetime.timezone.utc)
    if newer_time.tzinfo is None:
        newer_time = newer_time.replace(tzinfo=datetime.timezone.utc)
    
    # The last sync should be the newer report's timestamp
    assert abs((last_sync - newer_time).total_seconds()) < 1  # Within 1 second

def test_health_no_reports_last_sync_null(client, db_session):
    """Test that last_sync_timestamp is null when no reports exist"""
    response = client.get('/api/health')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    
    # With no reports, last_sync_timestamp should be None
    assert data['last_sync_timestamp'] is None
    assert data['total_reports'] == 0

def test_health_without_authentication(client):
    """Test that health check does not require authentication"""
    # Call health endpoint without any authentication headers
    response = client.get('/api/health')
    
    # Should succeed without authentication
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'running'

def test_health_database_unreachable(client, monkeypatch):
    """Test that health endpoint returns 503 when database is unreachable"""
    # Mock the Session to raise an exception
    def mock_session():
        raise Exception("Database connection failed")
    
    # Patch the Session in cloud_app module
    import cloud_app
    original_session = cloud_app.Session
    
    def failing_session():
        raise Exception("Database connection failed")
    
    monkeypatch.setattr(cloud_app, 'Session', failing_session)
    
    response = client.get('/api/health')
    
    # Should return 503 Service Unavailable
    assert response.status_code == 503
    data = json.loads(response.data)
    
    assert data['status'] == 'degraded'
    assert data['database_status'] == 'unreachable'
    assert 'error' in data
    
    # Restore original Session
    monkeypatch.setattr(cloud_app, 'Session', original_session)
