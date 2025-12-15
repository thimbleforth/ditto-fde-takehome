import pytest
import json
import jwt
import datetime
import os
import tempfile

# Setup a test DB path
test_db_fd, test_db_path = tempfile.mkstemp(suffix='.sqlite')
os.environ['CLOUD_DB_PATH'] = test_db_path

from cloud_app import app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from data_models import Report, Base
import cloud_app as cloud_module

test_engine = create_engine(f"sqlite:///{test_db_path}")
TestSession = sessionmaker(bind=test_engine)

@pytest.fixture
def client():
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
    Base.metadata.create_all(test_engine)
    session = TestSession()
    yield session
    session.close()
    Base.metadata.drop_all(test_engine)

@pytest.fixture
def valid_token():
    PRIVATE_KEY_PATH = "keys/private.pem"
    with open(PRIVATE_KEY_PATH, "rb") as f:
        private_key = f.read()
    payload = {
        "user": "security_test_edge",
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token

def test_invalid_report_id_format(client, valid_token):
    data = {
        "report_id": "bad id!@#",
        "title": "Test",
        "content": "test",
        "classification": "CUI",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "tester"
    }
    resp = client.post('/api/sync', data=json.dumps(data), content_type='application/json', headers={'Authorization': f'Bearer {valid_token}'})
    assert resp.status_code == 400
    j = json.loads(resp.data)
    assert 'report_id' in j['details'] or 'Invalid report_id' in j['details']

def test_invalid_classification(client, valid_token):
    data = {
        "report_id": "test-001",
        "title": "Test",
        "content": "test",
        "classification": "TOPSECRET",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "tester"
    }
    resp = client.post('/api/sync', data=json.dumps(data), content_type='application/json', headers={'Authorization': f'Bearer {valid_token}'})
    assert resp.status_code == 400
    j = json.loads(resp.data)
    assert 'Invalid classification' in j['details']

def test_title_length_exceeded(client, valid_token):
    data = {
        "report_id": "test-002",
        "title": "A" * 256,
        "content": "test",
        "classification": "IL4",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "tester"
    }
    resp = client.post('/api/sync', data=json.dumps(data), content_type='application/json', headers={'Authorization': f'Bearer {valid_token}'})
    assert resp.status_code == 400
    j = json.loads(resp.data)
    assert 'Title is required' in j['details']

def test_content_length_exceeded(client, valid_token):
    data = {
        "report_id": "test-003",
        "title": "Test",
        "content": "A" * 2001,
        "classification": "IL5",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "tester"
    }
    resp = client.post('/api/sync', data=json.dumps(data), content_type='application/json', headers={'Authorization': f'Bearer {valid_token}'})
    assert resp.status_code == 400
    j = json.loads(resp.data)
    assert 'Content is required' in j['details']

def test_sql_injection_content_safe(client, db_session, valid_token):
    malicious = "'; DROP TABLE reports; --"
    data = {
        "report_id": "sql-test-001",
        "title": "Test",
        "content": malicious,
        "classification": "CUI",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "tester"
    }
    resp = client.post('/api/sync', data=json.dumps(data), content_type='application/json', headers={'Authorization': f'Bearer {valid_token}'})
    assert resp.status_code == 200
    # Table should still exist and record should be stored
    report = db_session.query(Report).filter_by(report_id="sql-test-001").first()
    assert report is not None
    assert report.content == malicious

def test_xss_safe_rendering_template(client, valid_token):
    script_content = "<script>alert('xss')</script>"
    data = {
        "report_id": "xss-test-001",
        "title": "Test",
        "content": script_content,
        "classification": "CUI",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "tester"
    }
    resp = client.post('/api/sync', data=json.dumps(data), content_type='application/json', headers={'Authorization': f'Bearer {valid_token}'})
    assert resp.status_code == 200
    # Get the index page and ensure the template uses safe textContent rendering
    index_resp = client.get('/')
    assert index_resp.status_code == 200
    body = index_resp.data.decode('utf-8')
    # Check that the details rendering uses textContent or escapeHtml (both are safe approaches)
    assert ('pre.textContent' in body) or ('escapeHtml(' in body)

def test_rate_limit_exceeded(client, valid_token):
    # Configure a low rate limit for testing
    cloud_module.RATE_LIMIT = 3
    cloud_module._rate_cache = {}
    data = {
        "report_id": "rate-test-001",
        "title": "Test",
        "content": "test",
        "classification": "CUI",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "tester"
    }
    # Make RATE_LIMIT requests - these should succeed
    for _ in range(cloud_module.RATE_LIMIT):
        r = client.post('/api/sync', data=json.dumps(data), content_type='application/json', headers={'Authorization': f'Bearer {valid_token}'})
        assert r.status_code == 200
    # Next request should be rate-limited
    r2 = client.post('/api/sync', data=json.dumps(data), content_type='application/json', headers={'Authorization': f'Bearer {valid_token}'})
    assert r2.status_code == 429
