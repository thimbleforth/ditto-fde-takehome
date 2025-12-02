# Design Document

## Overview

The Edge-to-Cloud Data Synchronization System is a distributed application that enables field analysts to work with classified intelligence reports in disconnected environments. The system consists of two primary components:

1. **Edge Application**: A Python-based client application running on field devices with local SQLite storage
2. **Cloud Application**: A Flask-based REST API server with centralized database storage

The architecture follows an eventually consistent model where edge devices maintain local state and periodically synchronize with the cloud when connectivity is available. The system uses JWT-based authentication with RSA-2048 asymmetric encryption for secure communication.

### Key Design Principles

- **Offline-First**: Edge devices operate independently without requiring constant connectivity
- **Eventually Consistent**: Data converges across all nodes through periodic synchronization
- **Audit-Focused**: All changes are logged with timestamps and user identifiers for compliance
- **Security by Design**: Cryptographic authentication and classification-aware data handling
- **Last Write Wins**: Simple conflict resolution based on timestamps for operational simplicity

## Architecture

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Cloud Environment                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           Cloud Application (Flask)                    │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │ │
│  │  │ Auth Module  │  │ Sync Handler │  │ Web UI      │ │ │
│  │  │ (JWT Verify) │  │              │  │             │ │ │
│  │  └──────────────┘  └──────────────┘  └─────────────┘ │ │
│  │           │                │                │          │ │
│  │           └────────────────┴────────────────┘          │ │
│  │                          │                              │ │
│  │                   ┌──────▼──────┐                      │ │
│  │                   │  SQLAlchemy │                      │ │
│  │                   │     ORM     │                      │ │
│  │                   └──────┬──────┘                      │ │
│  │                          │                              │ │
│  │                   ┌──────▼──────┐                      │ │
│  │                   │   SQLite    │                      │ │
│  │                   │  (Cloud DB) │                      │ │
│  │                   └─────────────┘                      │ │
│  └────────────────────────────────────────────────────────┘ │
│                          ▲                                   │
└──────────────────────────┼───────────────────────────────────┘
                           │ HTTPS + JWT
                           │ (Port 8443)
        ┌──────────────────┴──────────────────┐
        │                                      │
┌───────▼────────┐                  ┌─────────▼───────┐
│  Edge Device 1 │                  │  Edge Device 2  │
│ ┌────────────┐ │                  │ ┌─────────────┐ │
│ │Edge App    │ │                  │ │ Edge App    │ │
│ │(Python)    │ │                  │ │ (Python)    │ │
│ │            │ │                  │ │             │ │
│ │┌──────────┐│ │                  │ │┌──────────┐ │ │
│ ││JWT Signer││ │                  │ ││JWT Signer││ │
│ │└──────────┘│ │                  │ │└──────────┘ │ │
│ │┌──────────┐│ │                  │ │┌──────────┐ │ │
│ ││  Sync    ││ │                  │ ││  Sync    ││ │
│ ││  Engine  ││ │                  │ ││  Engine  ││ │
│ │└──────────┘│ │                  │ │└──────────┘ │ │
│ └─────┬──────┘ │                  │ └──────┬──────┘ │
│       │        │                  │        │        │
│ ┌─────▼──────┐ │                  │ ┌──────▼─────┐ │
│ │  SQLite    │ │                  │ │  SQLite    │ │
│ │ (Edge DB)  │ │                  │ │ (Edge DB)  │ │
│ └────────────┘ │                  │ └────────────┘ │
└────────────────┘                  └────────────────┘
```

### Component Responsibilities

**Edge Application**:
- Local report CRUD operations
- JWT token generation and signing
- Periodic synchronization with cloud
- Local SQLite database management
- Offline operation support

**Cloud Application**:
- JWT token verification
- Report ingestion and storage
- Conflict resolution (last write wins)
- Audit log maintenance
- REST API endpoints
- Web-based report viewing interface

### Technology Stack

**Edge Device**:
- Python 3.x
- SQLite3 (local database)
- PyJWT (token generation)
- Requests (HTTP client)
- Cryptography libraries (RSA key handling)

**Cloud Server**:
- Python 3.x
- Flask (web framework)
- SQLAlchemy (ORM)
- SQLite (can be replaced with PostgreSQL for production)
- PyJWT (token verification)
- Jinja2 (template rendering)

**Infrastructure**:
- Docker containers
- Docker Compose (orchestration)
- Volume mounts for data persistence
- Read-only volume mounts for cryptographic keys

## Components and Interfaces

### Edge Application Components

#### 1. Database Manager

**Purpose**: Manages local SQLite database operations for report storage and retrieval.

**Responsibilities**:
- Initialize database schema on first run
- Execute CRUD operations on reports table
- Track synchronization status of reports
- Handle database connections and transactions

**Key Functions**:
```python
init_db() -> None
create_report(report_id, title, content, classification, analyst) -> int
read_report(report_id) -> dict
read_all_reports() -> list[dict]
update_report(report_id, title, content, classification, analyst) -> int
delete_report(report_id, analyst) -> int
get_unsynchronized_reports() -> list[dict]
mark_as_synchronized(report_id) -> None
```

**Database Schema**:
```sql
CREATE TABLE reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    classification TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    is_deleted INTEGER DEFAULT 0,
    is_synchronized INTEGER DEFAULT 0,
    INDEX idx_report_id (report_id),
    INDEX idx_synchronized (is_synchronized)
)
```

#### 2. JWT Token Manager

**Purpose**: Generates and signs JWT tokens for authentication with the cloud server.

**Responsibilities**:
- Load RSA private key from secure storage
- Generate JWT tokens with appropriate claims
- Set token expiration times
- Sign tokens using RS256 algorithm

**Key Functions**:
```python
load_private_key(key_path) -> bytes
issue_token(user_id) -> str
```

**Token Payload Structure**:
```json
{
  "user": "edge1",
  "iat": 1701234567,
  "exp": 1701236367
}
```

#### 3. Sync Engine

**Purpose**: Orchestrates synchronization of local reports to the cloud server.

**Responsibilities**:
- Identify unsynchronized reports
- Transmit reports to cloud endpoint
- Handle authentication headers
- Retry failed synchronizations
- Update synchronization status
- Provide user feedback on sync operations

**Key Functions**:
```python
sync_to_cloud() -> dict  # Returns sync summary
sync_single_report(report) -> bool
handle_sync_failure(report, error) -> None
display_sync_summary(results) -> None
```

**Sync Summary Structure**:
```python
{
    "total": 10,
    "successful": 8,
    "failed": 2,
    "reports": [
        {"report_id": "...", "status": "success"},
        {"report_id": "...", "status": "failed", "error": "..."}
    ]
}
```

### Cloud Application Components

#### 1. Authentication Middleware

**Purpose**: Validates JWT tokens from edge devices before processing requests.

**Responsibilities**:
- Load RSA public key from secure storage
- Extract Bearer tokens from Authorization headers
- Verify token signatures
- Validate token expiration
- Extract user claims for audit logging

**Key Functions**:
```python
load_public_key(key_path) -> bytes
verify_token(token) -> dict | None
extract_bearer_token(auth_header) -> str | None
```

#### 2. Sync Handler

**Purpose**: Processes incoming report synchronization requests from edge devices.

**Responsibilities**:
- Validate incoming report data
- Parse and normalize timestamps
- Store reports in database
- Preserve audit information
- Return synchronization status

**Key Functions**:
```python
handle_sync_request(data, claims) -> tuple[dict, int]
validate_report_data(data) -> bool
fix_timestamp(timestamp_str) -> datetime
store_report(report_data, user_id) -> int
```

**API Endpoint**: `POST /api/sync`

**Request Format**:
```json
{
  "report_id": "edge1-report-1234",
  "title": "Field Report",
  "content": "Report content...",
  "classification": "IL4",
  "updated_at": "2024-12-02T10:30:00.000000+00:00",
  "updated_by": "edge1"
}
```

**Response Format**:
```json
{
  "status": "ok"
}
```

#### 3. Report Query Service

**Purpose**: Provides API endpoints for retrieving reports and audit history.

**Responsibilities**:
- Query all reports including historical versions
- Query latest versions using last write wins logic
- Format responses with proper timestamp serialization
- Support filtering and ordering

**Key Functions**:
```python
get_all_reports() -> list[dict]
get_latest_reports() -> list[dict]
format_report_response(report) -> dict
```

**API Endpoints**:
- `GET /api/reports` - Returns all report versions
- `GET /api/reports/latest` - Returns latest version of each report_id

#### 4. Web Interface

**Purpose**: Provides HTML interface for viewing synchronized reports.

**Responsibilities**:
- Render report data in user-friendly format
- Display sync status and conflict information
- Provide buttons for fetching all vs latest reports
- Show classification levels and audit information

**Key Functions**:
```python
render_index() -> str
```

**Template Structure**:
- Main page with report display area
- Buttons for "Get Reports" and "Get Latest Reports"
- JavaScript for AJAX calls to API endpoints
- Table display with columns: ID, Report ID, Title, Content, Classification, Updated At, Updated By

#### 5. Health Monitor

**Purpose**: Provides system health and status information.

**Responsibilities**:
- Return operational status
- Provide current server timestamp
- Enable monitoring and troubleshooting

**Key Functions**:
```python
health_check() -> tuple[dict, int]
```

**API Endpoint**: `GET /api/health`

**Response Format**:
```json
{
  "status": "running",
  "time": "2024-12-02T10:30:00.000000+00:00"
}
```

### Data Models

#### Report Model (SQLAlchemy)

```python
class Report(Base):
    __tablename__ = "reports"
    
    id = Column(Integer, primary_key=True)
    report_id = Column(String(64), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(String(2000), nullable=False)
    classification = Column(String(20), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    updated_by = Column(String(100), nullable=False)
    is_deleted = Column(Integer, default=0)
```

**Field Descriptions**:
- `id`: Auto-incrementing primary key for database record
- `report_id`: Logical identifier for the report (can have multiple versions)
- `title`: Report title
- `content`: Report body content
- `classification`: Security classification (CUI, IL4, IL5)
- `updated_at`: Timestamp of last modification (timezone-aware)
- `updated_by`: Analyst identifier who made the change
- `is_deleted`: Soft delete flag (0=active, 1=deleted)

### Communication Protocols

#### Authentication Flow

```
Edge Device                          Cloud Server
     │                                    │
     │  1. Generate JWT Token             │
     │     (signed with private key)      │
     │                                    │
     │  2. POST /api/sync                 │
     │     Authorization: Bearer <token>  │
     ├───────────────────────────────────>│
     │                                    │
     │                                    │  3. Verify token
     │                                    │     (using public key)
     │                                    │
     │                                    │  4. Extract user claim
     │                                    │
     │                                    │  5. Process request
     │                                    │
     │  6. Response                       │
     │<───────────────────────────────────┤
     │                                    │
```

#### Synchronization Flow

```
Edge Device                          Cloud Server
     │                                    │
     │  1. Query unsynchronized reports   │
     │                                    │
     │  2. For each report:               │
     │     - Generate JWT token           │
     │     - Send POST /api/sync          │
     ├───────────────────────────────────>│
     │                                    │
     │                                    │  3. Authenticate
     │                                    │  4. Validate data
     │                                    │  5. Store in DB
     │                                    │
     │  6. {"status": "ok"}               │
     │<───────────────────────────────────┤
     │                                    │
     │  7. Mark as synchronized           │
     │                                    │
     │  8. Display sync summary to user   │
     │                                    │
```

## Error Handling

### Edge Application Error Scenarios

#### 1. Network Connectivity Failures

**Scenario**: Cloud server is unreachable during sync operation.

**Handling**:
- Catch `requests.exceptions.ConnectionError` and `requests.exceptions.Timeout`
- Log error with timestamp and report_id
- Keep report marked as unsynchronized
- Retry on next sync attempt
- Display user-friendly error message

**Implementation**:
```python
try:
    response = requests.post(url, json=payload, headers=headers, timeout=30)
except requests.exceptions.ConnectionError:
    log_error(f"Connection failed for report {report_id}")
    return {"status": "failed", "error": "network_unreachable"}
except requests.exceptions.Timeout:
    log_error(f"Timeout for report {report_id}")
    return {"status": "failed", "error": "timeout"}
```

#### 2. Authentication Failures

**Scenario**: JWT token is rejected by cloud server.

**Handling**:
- Check for HTTP 401 response
- Regenerate token and retry once
- If still failing, log error and alert user
- Do not mark report as synchronized

#### 3. Database Errors

**Scenario**: Local SQLite database is corrupted or locked.

**Handling**:
- Catch `sqlite3.Error` exceptions
- Implement retry logic with exponential backoff
- Log detailed error information
- Alert user if database is unrecoverable

### Cloud Application Error Scenarios

#### 1. Invalid JWT Tokens

**Scenario**: Edge device sends expired or malformed token.

**Handling**:
- Return HTTP 401 Unauthorized
- Include error message in response body
- Log authentication failure with source IP
- Do not process the request

**Response**:
```json
{
  "error": "Invalid token",
  "details": "Token has expired"
}
```

#### 2. Malformed Request Data

**Scenario**: Sync request missing required fields or invalid data types.

**Handling**:
- Validate all required fields before processing
- Return HTTP 400 Bad Request with details
- Log validation errors
- Do not store incomplete data

**Response**:
```json
{
  "error": "Invalid request",
  "details": "Missing required field: report_id"
}
```

#### 3. Database Write Failures

**Scenario**: Unable to write to cloud database.

**Handling**:
- Catch SQLAlchemy exceptions
- Rollback transaction
- Return HTTP 500 Internal Server Error
- Log full error stack trace
- Alert operations team

#### 4. Timestamp Parsing Errors

**Scenario**: Edge device sends timestamp in unexpected format.

**Handling**:
- Implement multiple timestamp parsing strategies
- Try ISO 8601 format first
- Fall back to alternative formats
- If all fail, use current server time and log warning

**Implementation**:
```python
def fix_timestamp(timestamp_str):
    try:
        return datetime.fromisoformat(timestamp_str)
    except ValueError:
        try:
            return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%f%z")
        except ValueError:
            log_warning(f"Could not parse timestamp: {timestamp_str}")
            return datetime.now(timezone.utc)
```

### Error Logging Strategy

**Edge Device**:
- Log to local file: `/app/data/edge.log`
- Include: timestamp, log level, component, message, stack trace
- Rotate logs daily, keep 7 days

**Cloud Server**:
- Log to file: `/app/data/cloud.log`
- Include: timestamp, log level, endpoint, user, message, stack trace
- Rotate logs daily, keep 30 days for compliance
- Send critical errors to monitoring system

## Testing Strategy

### Unit Testing

#### Edge Application Tests

**Database Manager Tests**:
- Test report creation with valid data
- Test report retrieval by report_id
- Test report updates create new versions
- Test soft delete functionality
- Test synchronization status tracking
- Test database initialization

**JWT Token Manager Tests**:
- Test token generation with valid private key
- Test token includes correct claims
- Test token expiration is set correctly
- Test token signature is valid

**Sync Engine Tests**:
- Test identification of unsynchronized reports
- Test sync summary generation
- Test error handling for network failures
- Test retry logic

#### Cloud Application Tests

**Authentication Middleware Tests**:
- Test valid token verification
- Test expired token rejection
- Test malformed token rejection
- Test missing Authorization header handling
- Test user claim extraction

**Sync Handler Tests**:
- Test valid report storage
- Test timestamp parsing and normalization
- Test audit field preservation
- Test duplicate report_id handling
- Test invalid data rejection

**Report Query Service Tests**:
- Test retrieval of all reports
- Test latest report query with multiple versions
- Test last write wins logic
- Test empty database handling
- Test response formatting

### Integration Testing

#### End-to-End Sync Test

**Scenario**: Edge device creates report and syncs to cloud.

**Steps**:
1. Start cloud server
2. Start edge device
3. Create report on edge device
4. Trigger sync operation
5. Verify report appears in cloud database
6. Verify audit fields are preserved
7. Query via API and verify response

**Expected Result**: Report successfully synchronized with all fields intact.

#### Conflict Resolution Test

**Scenario**: Two edge devices update same report_id.

**Steps**:
1. Edge1 creates report with report_id "shared-001" at T1
2. Edge2 creates report with report_id "shared-001" at T2 (T2 > T1)
3. Both sync to cloud
4. Query latest reports
5. Verify Edge2's version is returned (last write wins)
6. Query all reports
7. Verify both versions are stored

**Expected Result**: Latest version by timestamp is returned, all versions preserved.

#### Authentication Failure Test

**Scenario**: Edge device uses invalid private key.

**Steps**:
1. Configure edge device with wrong private key
2. Attempt to sync report
3. Verify cloud returns HTTP 401
4. Verify report remains unsynchronized on edge
5. Verify error is logged

**Expected Result**: Sync fails gracefully, report can be retried later.

### Performance Testing

#### Sync Performance Test

**Metrics**:
- Time to sync 100 reports
- Time to sync 1000 reports
- Network bandwidth usage
- Database write performance

**Acceptance Criteria**:
- 100 reports sync in < 10 seconds
- 1000 reports sync in < 60 seconds
- No memory leaks during extended sync operations

#### Query Performance Test

**Metrics**:
- Time to query all reports (10,000 records)
- Time to query latest reports (1,000 unique report_ids)
- API response time under load

**Acceptance Criteria**:
- All reports query < 2 seconds for 10,000 records
- Latest reports query < 1 second for 1,000 unique IDs
- API maintains < 500ms response time under 10 req/sec load

### Security Testing

#### Authentication Security Tests

- Test token replay attacks (expired tokens rejected)
- Test token tampering (signature validation fails)
- Test missing authentication (401 returned)
- Test SQL injection in report fields
- Test XSS in report content

#### Cryptographic Tests

- Verify RSA-2048 key strength
- Verify RS256 algorithm usage
- Verify key file permissions (read-only)
- Verify no private keys on cloud server

### Deployment Testing

#### Docker Container Tests

- Verify containers run as non-root users
- Verify volume mounts are correct
- Verify network connectivity between containers
- Verify environment variables are passed correctly
- Verify containers restart on failure

#### Multi-Edge Deployment Test

**Scenario**: Deploy 3 edge devices and 1 cloud server.

**Steps**:
1. Start cloud server
2. Start edge1, edge2, edge3
3. Each edge creates unique reports
4. All edges sync simultaneously
5. Verify all reports appear in cloud
6. Verify no data corruption
7. Verify audit trails are correct

**Expected Result**: All reports synchronized successfully, no conflicts or data loss.

## Security Considerations

### Authentication and Authorization

- **Asymmetric Cryptography**: RSA-2048 keys provide strong authentication without sharing secrets
- **Token Expiration**: 30-minute token lifetime limits exposure window
- **No Shared Secrets**: Private keys never leave edge devices, public keys never sign
- **User Attribution**: Every sync includes authenticated user identity for audit

### Data Protection

- **Classification Awareness**: System tracks and preserves classification levels
- **Audit Logging**: Complete history of who changed what and when
- **Soft Deletes**: Deleted reports retained for compliance and forensics
- **Timestamp Integrity**: Original timestamps preserved to prevent tampering

### Container Security

- **Non-Root Execution**: All containers run as unprivileged users
- **Read-Only Mounts**: Cryptographic keys mounted read-only
- **Volume Isolation**: Each edge device has isolated data volume
- **Network Segmentation**: Containers communicate only through defined ports

### Production Hardening Recommendations

**Current Limitations** (noted in README):
- Using HTTP instead of HTTPS
- Using Flask development server instead of production WSGI
- SQLite instead of PostgreSQL for cloud database

**Production Requirements**:
1. **HTTPS/TLS**: Deploy behind reverse proxy with TLS termination
2. **Production WSGI**: Use Gunicorn or uWSGI for cloud application
3. **PostgreSQL**: Replace SQLite with managed PostgreSQL (AWS RDS)
4. **Key Management**: Use AWS KMS or Azure Key Vault for key storage
5. **Secrets Management**: Use environment-specific secret injection
6. **Rate Limiting**: Implement rate limiting on sync endpoint
7. **Input Validation**: Add comprehensive input sanitization
8. **Security Headers**: Add HSTS, CSP, X-Frame-Options headers
9. **Monitoring**: Implement security event monitoring and alerting
10. **Compliance Controls**: Use AWS Security Hub or equivalent

## Scalability Considerations

### Current Architecture Limitations

- **Client-Server Model**: All edge devices sync directly to single cloud endpoint
- **Synchronous Processing**: Each sync request processed sequentially
- **Single Database**: No horizontal scaling of data layer

### Scaling to 100+ Edge Locations

#### Recommended Enhancements

**1. Edge-to-Edge Synchronization**

Implement peer-to-peer sync between nearby edge devices to reduce cloud load:
- Use distance/hop-based routing
- Implement gossip protocol for report propagation
- Reduce bandwidth to cloud by aggregating changes

**2. Cloud Load Balancing**

- Deploy Application Load Balancer in front of multiple cloud instances
- Use session affinity for consistent routing
- Implement health checks for automatic failover

**3. Serverless Architecture**

Convert cloud application to AWS Lambda or Azure Functions:
- Auto-scaling based on request volume
- Pay-per-use pricing model
- Reduced operational overhead

**4. Database Scaling**

- Use managed PostgreSQL with read replicas
- Implement connection pooling
- Consider sharding by geographic region
- Use S3 for report content storage with database metadata only

**5. Message Queue Integration**

Decouple sync ingestion from processing:
- Edge devices publish to SQS/Service Bus
- Lambda functions process queue asynchronously
- Enables retry logic and dead letter queues

**6. Caching Layer**

- Implement Redis/ElastiCache for latest reports
- Cache frequently accessed data
- Reduce database load for read operations

### Monitoring and Observability

**Metrics to Track**:
- Sync success/failure rates per edge device
- Sync latency (time from edge to cloud)
- Database write throughput
- API response times
- Authentication failure rates
- Report conflict frequency

**Alerting Thresholds**:
- Sync failure rate > 5%
- API response time > 1 second
- Authentication failures > 10/minute
- Database connection pool exhaustion

## Deployment Architecture

### Docker Compose Configuration

**Services**:
1. `cloud`: Cloud application container
2. `edge1`: First edge device container
3. `edge2`: Second edge device container

**Volumes**:
- `./keys`: Cryptographic keys (read-only)
- `./cloud/cloud_data`: Cloud database persistence
- `./edge1_data`: Edge1 database persistence
- `./edge2_data`: Edge2 database persistence

**Network**:
- Default bridge network
- Cloud exposes port 8443 to host
- Edge devices communicate with cloud via internal DNS

### Production Deployment (AWS Example)

**Architecture**:
```
Internet
   │
   ▼
Application Load Balancer (HTTPS)
   │
   ├─> ECS Task 1 (Cloud App)
   ├─> ECS Task 2 (Cloud App)
   └─> ECS Task 3 (Cloud App)
         │
         ▼
   RDS PostgreSQL (Multi-AZ)
         │
         ▼
   S3 (Report Content Storage)
```

**Edge Devices**:
- Deployed on field hardware or edge computing devices
- VPN connection to AWS for sync operations
- Local SQLite for offline operation
- Periodic sync when connectivity available

This design provides a robust, secure, and scalable foundation for the edge-to-cloud synchronization system while maintaining the simplicity needed for field operations.
