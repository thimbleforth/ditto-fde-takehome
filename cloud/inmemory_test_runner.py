"""In-memory test runner for cloud app.

Creates a persistent in-memory SQLite database, patches cloud_app to use
that DB for all sessions, and runs a set of validation checks that mirror
the repository's unit tests (sync handling, queries, health, rate limiting,
and security checks).

Run this file directly to execute the checks.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import datetime
import json

import os
import sys
# Ensure this directory (cloud/) is on sys.path so imports resolve when run from repo root
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import cloud_app as cloud_app
from data_models import Base, Report


def setup_inmemory_db():
    # Create a persistent in-memory SQLite engine that is shared across
    # connections (use StaticPool and check_same_thread=False).
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    # Patch cloud_app to use this session factory
    def get_session_override():
        return SessionLocal()

    cloud_app.get_session = get_session_override
    # Provide legacy Session symbol expected by some tests
    cloud_app.Session = get_session_override

    # Disable actual JWT verification by returning a simple claim
    cloud_app.verify_token = lambda token: {"user": "inmemory_test"}

    # Reset rate cache
    cloud_app._rate_cache = {}

    return engine, SessionLocal


def run_checks():
    engine, SessionLocal = setup_inmemory_db()
    client = cloud_app.app.test_client()
    passed = 0
    failed = 0

    def ok(name):
        nonlocal passed
        passed += 1
        print(f"PASS: {name}")

    def fail(name, details=""):
        nonlocal failed
        failed += 1
        print(f"FAIL: {name} {details}")

    # 1) Successful report storage
    name = "successful_report_storage"
    payload = {
        "report_id": "test-report-001",
        "title": "Test Report",
        "content": "This is test content",
        "classification": "CUI",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "tester",
    }
    resp = client.post("/api/sync", data=json.dumps(payload), content_type="application/json", headers={"Authorization": "Bearer fake"})
    if resp.status_code == 200:
        # Verify DB contains record
        session = SessionLocal()
        r = session.query(Report).filter_by(report_id="test-report-001").first()
        session.close()
        if r is not None:
            ok(name)
        else:
            fail(name, "record missing")
    else:
        fail(name, f"status {resp.status_code}")

    # 2) Validation: empty body returns 400
    name = "validation_empty_body"
    cloud_app._rate_cache = {}
    resp = client.post("/api/sync", data=json.dumps(None), content_type="application/json", headers={"Authorization": "Bearer fake"})
    if resp.status_code == 400:
        ok(name)
    else:
        fail(name, f"status {resp.status_code}")

    # 3) SQL injection content safe (table remains and record stored)
    name = "sql_injection_content_safe"
    malicious = "'; DROP TABLE reports; --"
    payload = {
        "report_id": "sql-test-001",
        "title": "Test",
        "content": malicious,
        "classification": "CUI",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "tester",
    }
    resp = client.post("/api/sync", data=json.dumps(payload), content_type="application/json", headers={"Authorization": "Bearer fake"})
    if resp.status_code == 200:
        session = SessionLocal()
        r = session.query(Report).filter_by(report_id="sql-test-001").first()
        session.close()
        if r is not None:
            ok(name)
        else:
            fail(name, "record missing after injection attempt")
    else:
        fail(name, f"status {resp.status_code}")

    # 4) Get reports excludes deleted by default / includes when requested
    name = "reports_include_deleted"
    # Create one active and one deleted
    session = SessionLocal()
    now = datetime.datetime.now(datetime.timezone.utc)
    active = Report(report_id="r-1", title="Active", content="A", classification="CUI", updated_at=now, updated_by="t", is_deleted=0)
    deleted = Report(report_id="r-2", title="Deleted", content="D", classification="IL4", updated_at=now, updated_by="t", is_deleted=1)
    session.add(active)
    session.add(deleted)
    session.commit()
    session.close()

    resp = client.get('/api/reports')
    if resp.status_code == 200 and all(r['report_id'] != 'r-2' for r in resp.get_json()):
        resp2 = client.get('/api/reports?include_deleted=true')
        if resp2.status_code == 200 and any(r['report_id'] == 'r-2' for r in resp2.get_json()):
            ok(name)
        else:
            fail(name, "include_deleted not working")
    else:
        fail(name, "deleted not excluded by default")

    # 5) Latest reports excludes deleted newer versions
    name = "latest_excludes_deleted"
    session = SessionLocal()
    now = datetime.datetime.now(datetime.timezone.utc)
    v1 = Report(report_id='rep-1', title='v1', content='c1', classification='CUI', updated_at=now - datetime.timedelta(hours=2), updated_by='a', is_deleted=0)
    v2 = Report(report_id='rep-1', title='v2-deleted', content='c2', classification='CUI', updated_at=now - datetime.timedelta(hours=1), updated_by='a', is_deleted=1)
    session.add(v1); session.add(v2); session.commit(); session.close()
    resp = client.get('/api/reports/latest')
    if resp.status_code == 200 and any(r['report_id'] == 'rep-1' and r['title'] == 'v1' for r in resp.get_json()):
        ok(name)
    else:
        fail(name, "latest returned incorrect record")

    # 6) Health endpoint report counts and last sync timestamp
    name = 'health_stats'
    resp = client.get('/api/health')
    if resp.status_code == 200:
        data = resp.get_json()
        if data.get('total_reports', 0) >= 1 and data.get('last_sync_timestamp'):
            ok(name)
        else:
            fail(name, f"unexpected data: {data}")
    else:
        fail(name, f"status {resp.status_code}")

    # 7) Rate limiting enforcement
    name = 'rate_limiting'
    cloud_app.RATE_LIMIT = 3
    cloud_app.RATE_WINDOW = 60
    cloud_app._rate_cache = {}
    payload = {
        "report_id": "rate-test-001",
        "title": "Test",
        "content": "test",
        "classification": "CUI",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_by": "tester",
    }
    ok_count = 0
    for i in range(cloud_app.RATE_LIMIT):
        r = client.post('/api/sync', data=json.dumps({**payload, 'report_id': f'rate-{i}'}), content_type='application/json', headers={"Authorization": "Bearer fake"})
        if r.status_code == 200:
            ok_count += 1
    r = client.post('/api/sync', data=json.dumps({**payload, 'report_id': 'rate-exceed'}), content_type='application/json', headers={"Authorization": "Bearer fake"})
    if ok_count == cloud_app.RATE_LIMIT and r.status_code == 429:
        ok(name)
    else:
        fail(name, f"ok_count={ok_count}, last_status={r.status_code}")

    # Summary
    print("\nSUMMARY:")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    return failed == 0


if __name__ == '__main__':
    success = run_checks()
    if not success:
        raise SystemExit(1)