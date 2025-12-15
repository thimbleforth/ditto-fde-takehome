# test_query_endpoints.py
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

def test_get_all_reports_excludes_deleted_by_default(client, db_session):
    """Test that /api/reports excludes deleted reports by default"""
    # Create active report
    active_report = Report(
        report_id="report-001",
        title="Active Report",
        content="Active content",
        classification="CUI",
        updated_at=datetime.datetime.now(datetime.timezone.utc),
        updated_by="analyst1",
        is_deleted=0
    )
    db_session.add(active_report)
    
    # Create deleted report
    deleted_report = Report(
        report_id="report-002",
        title="Deleted Report",
        content="Deleted content",
        classification="IL4",
        updated_at=datetime.datetime.now(datetime.timezone.utc),
        updated_by="analyst2",
        is_deleted=1
    )
    db_session.add(deleted_report)
    db_session.commit()
    
    response = client.get('/api/reports')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) == 1
    assert data[0]['report_id'] == 'report-001'
    assert data[0]['title'] == 'Active Report'

def test_get_all_reports_includes_deleted_when_requested(client, db_session):
    """Test that /api/reports includes deleted reports when include_deleted=true"""
    # Create active report
    active_report = Report(
        report_id="report-001",
        title="Active Report",
        content="Active content",
        classification="CUI",
        updated_at=datetime.datetime.now(datetime.timezone.utc),
        updated_by="analyst1",
        is_deleted=0
    )
    db_session.add(active_report)
    
    # Create deleted report
    deleted_report = Report(
        report_id="report-002",
        title="Deleted Report",
        content="Deleted content",
        classification="IL4",
        updated_at=datetime.datetime.now(datetime.timezone.utc),
        updated_by="analyst2",
        is_deleted=1
    )
    db_session.add(deleted_report)
    db_session.commit()
    
    response = client.get('/api/reports?include_deleted=true')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) == 2
    report_ids = [r['report_id'] for r in data]
    assert 'report-001' in report_ids
    assert 'report-002' in report_ids

def test_get_latest_reports_excludes_deleted(client, db_session):
    """Test that /api/reports/latest excludes deleted reports"""
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # Create older active version
    older_active = Report(
        report_id="report-001",
        title="Version 1",
        content="First version",
        classification="CUI",
        updated_at=now - datetime.timedelta(hours=2),
        updated_by="analyst1",
        is_deleted=0
    )
    db_session.add(older_active)
    
    # Create newer deleted version (should be excluded)
    newer_deleted = Report(
        report_id="report-001",
        title="Version 2 Deleted",
        content="Deleted version",
        classification="CUI",
        updated_at=now - datetime.timedelta(hours=1),
        updated_by="analyst1",
        is_deleted=1
    )
    db_session.add(newer_deleted)
    db_session.commit()
    
    response = client.get('/api/reports/latest')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) == 1
    assert data[0]['report_id'] == 'report-001'
    assert data[0]['title'] == 'Version 1'  # Should return older active version

def test_last_write_wins_with_multiple_versions(client, db_session):
    """Test that last write wins logic returns the most recent non-deleted version"""
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # Create three versions of the same report
    version1 = Report(
        report_id="report-001",
        title="Version 1",
        content="First version",
        classification="CUI",
        updated_at=now - datetime.timedelta(hours=3),
        updated_by="analyst1",
        is_deleted=0
    )
    db_session.add(version1)
    
    version2 = Report(
        report_id="report-001",
        title="Version 2",
        content="Second version",
        classification="CUI",
        updated_at=now - datetime.timedelta(hours=2),
        updated_by="analyst2",
        is_deleted=0
    )
    db_session.add(version2)
    
    version3 = Report(
        report_id="report-001",
        title="Version 3",
        content="Third version",
        classification="IL4",
        updated_at=now - datetime.timedelta(hours=1),
        updated_by="analyst1",
        is_deleted=0
    )
    db_session.add(version3)
    db_session.commit()
    
    response = client.get('/api/reports/latest')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) == 1
    assert data[0]['report_id'] == 'report-001'
    assert data[0]['title'] == 'Version 3'  # Most recent version
    assert data[0]['classification'] == 'IL4'
    assert data[0]['updated_by'] == 'analyst1'

def test_empty_database_handling(client, db_session):
    """Test that endpoints handle empty database correctly"""
    # Test /api/reports
    response = client.get('/api/reports')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) == 0
    assert isinstance(data, list)
    
    # Test /api/reports/latest
    response = client.get('/api/reports/latest')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) == 0
    assert isinstance(data, list)

def test_multiple_report_ids_latest_query(client, db_session):
    """Test that latest query returns one report per report_id"""
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # Create multiple versions of report-001
    report1_v1 = Report(
        report_id="report-001",
        title="Report 1 Version 1",
        content="Content 1",
        classification="CUI",
        updated_at=now - datetime.timedelta(hours=2),
        updated_by="analyst1",
        is_deleted=0
    )
    db_session.add(report1_v1)
    
    report1_v2 = Report(
        report_id="report-001",
        title="Report 1 Version 2",
        content="Content 2",
        classification="CUI",
        updated_at=now - datetime.timedelta(hours=1),
        updated_by="analyst2",
        is_deleted=0
    )
    db_session.add(report1_v2)
    
    # Create multiple versions of report-002
    report2_v1 = Report(
        report_id="report-002",
        title="Report 2 Version 1",
        content="Content A",
        classification="IL4",
        updated_at=now - datetime.timedelta(hours=3),
        updated_by="analyst1",
        is_deleted=0
    )
    db_session.add(report2_v1)
    
    report2_v2 = Report(
        report_id="report-002",
        title="Report 2 Version 2",
        content="Content B",
        classification="IL4",
        updated_at=now - datetime.timedelta(minutes=30),
        updated_by="analyst3",
        is_deleted=0
    )
    db_session.add(report2_v2)
    db_session.commit()
    
    response = client.get('/api/reports/latest')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) == 2
    
    # Find each report in the response
    report1 = next(r for r in data if r['report_id'] == 'report-001')
    report2 = next(r for r in data if r['report_id'] == 'report-002')
    
    assert report1['title'] == 'Report 1 Version 2'
    assert report2['title'] == 'Report 2 Version 2'

def test_all_deleted_versions_excluded_from_latest(client, db_session):
    """Test that if all versions are deleted, report doesn't appear in latest"""
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # Create two deleted versions
    version1 = Report(
        report_id="report-001",
        title="Version 1 Deleted",
        content="First version",
        classification="CUI",
        updated_at=now - datetime.timedelta(hours=2),
        updated_by="analyst1",
        is_deleted=1
    )
    db_session.add(version1)
    
    version2 = Report(
        report_id="report-001",
        title="Version 2 Deleted",
        content="Second version",
        classification="CUI",
        updated_at=now - datetime.timedelta(hours=1),
        updated_by="analyst2",
        is_deleted=1
    )
    db_session.add(version2)
    db_session.commit()
    
    response = client.get('/api/reports/latest')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) == 0  # No reports should be returned

def test_is_deleted_field_included_in_response(client, db_session):
    """Test that is_deleted field is included in /api/reports response"""
    active_report = Report(
        report_id="report-001",
        title="Active Report",
        content="Active content",
        classification="CUI",
        updated_at=datetime.datetime.now(datetime.timezone.utc),
        updated_by="analyst1",
        is_deleted=0
    )
    db_session.add(active_report)
    
    deleted_report = Report(
        report_id="report-002",
        title="Deleted Report",
        content="Deleted content",
        classification="IL4",
        updated_at=datetime.datetime.now(datetime.timezone.utc),
        updated_by="analyst2",
        is_deleted=1
    )
    db_session.add(deleted_report)
    db_session.commit()
    
    response = client.get('/api/reports?include_deleted=true')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) == 2
    
    for report in data:
        assert 'is_deleted' in report
        if report['report_id'] == 'report-001':
            assert report['is_deleted'] == 0
        elif report['report_id'] == 'report-002':
            assert report['is_deleted'] == 1
