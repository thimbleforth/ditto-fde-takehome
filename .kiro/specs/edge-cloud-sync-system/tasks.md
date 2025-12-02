# Implementation Plan

- [ ] 1. Enhance edge database schema with synchronization tracking
  - Add `is_deleted` column to track soft deletes
  - Add `is_synchronized` column to track sync status
  - Add indexes on `report_id` and `is_synchronized` for query performance
  - Update `init_db()` function in `edge/edge_app.py` to create enhanced schema
  - _Requirements: 1.4, 1.8, 2.6_

- [ ] 2. Implement CRUD operations in edge application
- [ ] 2.1 Create database manager module for edge device
  - Create new file `edge/database_manager.py` with functions for all CRUD operations
  - Implement `create_report()` function to insert new reports with sync status
  - Implement `read_report(report_id)` function to retrieve single report
  - Implement `read_all_reports()` function to retrieve all reports including from other analysts
  - Implement `update_report()` function to create new version with updated timestamp
  - Implement `delete_report()` function to soft delete with deletion timestamp
  - Implement `get_unsynchronized_reports()` function to query reports where `is_synchronized = 0`
  - Implement `mark_as_synchronized(report_id)` function to update sync status
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [ ] 2.2 Write unit tests for database manager
  - Create `edge/test_database_manager.py` with tests for each CRUD operation
  - Test report creation with valid data
  - Test report retrieval and filtering
  - Test update creates new version
  - Test soft delete functionality
  - Test synchronization status tracking
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 3. Implement enhanced sync engine with user feedback
- [ ] 3.1 Refactor sync engine to use database manager
  - Update `sync_to_cloud()` in `edge/edge_app.py` to call `get_unsynchronized_reports()`
  - Implement sync summary tracking with counts of successful and failed syncs
  - Implement `sync_single_report()` function to handle individual report transmission
  - Add error handling for network failures with detailed error messages
  - Call `mark_as_synchronized()` after successful sync
  - _Requirements: 2.1, 2.6, 2.7_

- [ ] 3.2 Add user feedback for sync operations
  - Implement `display_sync_summary()` function to print sync results to console
  - Display list of successfully synchronized reports with report_ids
  - Display list of failed synchronizations with error details
  - Print total counts of successful vs failed syncs
  - _Requirements: 2.3_

- [ ] 3.3 Write integration tests for sync engine
  - Create `edge/test_sync_engine.py` with end-to-end sync tests
  - Test successful sync of multiple reports
  - Test handling of network failures
  - Test sync summary generation
  - Test synchronization status updates
  - _Requirements: 2.1, 2.3, 2.6_

- [ ] 4. Enhance cloud database schema for soft deletes
  - Add `is_deleted` column to `Report` model in `cloud/data_models.py`
  - Set default value to 0 (not deleted)
  - Update SQLAlchemy model with new column definition
  - _Requirements: 1.4, 4.5_

- [ ] 5. Implement enhanced sync handler in cloud application
- [ ] 5.1 Add request validation to sync endpoint
  - Update `/api/sync` endpoint in `cloud/cloud_app.py` to validate all required fields
  - Check for presence of: report_id, title, content, classification, updated_at, updated_by
  - Return HTTP 400 with detailed error message if validation fails
  - _Requirements: 2.4_

- [ ] 5.2 Handle soft delete synchronization
  - Check for `is_deleted` flag in incoming sync requests
  - Store deleted reports with `is_deleted = 1` in cloud database
  - Preserve deletion timestamp and analyst who performed deletion
  - _Requirements: 1.4, 2.8_

- [ ] 5.3 Improve error handling in sync endpoint
  - Wrap database operations in try-except blocks
  - Return HTTP 500 for database errors with error details
  - Log all sync errors with timestamp and source user
  - Implement transaction rollback on failures
  - _Requirements: 2.4_

- [ ] 5.4 Write unit tests for sync handler
  - Create `cloud/test_sync_handler.py` with tests for sync endpoint
  - Test successful report storage
  - Test validation error handling
  - Test soft delete handling
  - Test database error handling
  - _Requirements: 2.4, 2.5_

- [ ] 6. Enhance report query endpoints
- [ ] 6.1 Update latest reports query to exclude deleted reports
  - Modify `/api/reports/latest` endpoint in `cloud/cloud_app.py`
  - Filter out reports where `is_deleted = 1` when determining latest version
  - Ensure last write wins logic considers only non-deleted reports
  - _Requirements: 4.2, 4.4_

- [ ] 6.2 Add filtering option for all reports endpoint
  - Update `/api/reports` endpoint to support optional query parameter `include_deleted`
  - Default behavior excludes deleted reports
  - When `include_deleted=true`, return all reports including deleted ones
  - _Requirements: 4.1, 4.5, 5.4_

- [ ] 6.3 Write unit tests for query endpoints
  - Create `cloud/test_query_endpoints.py` with tests for report retrieval
  - Test latest reports excludes deleted
  - Test all reports filtering
  - Test last write wins logic with multiple versions
  - Test empty database handling
  - _Requirements: 4.2, 4.4, 5.4_

- [ ] 7. Enhance web interface for better report viewing
- [ ] 7.1 Update HTML template with improved layout
  - Modify `cloud/templates/index.html` to display reports in a structured table
  - Add columns for: ID, Report ID, Title, Content, Classification, Updated At, Updated By, Status
  - Add visual indicator for deleted reports (e.g., strikethrough or red text)
  - Improve button styling and layout
  - _Requirements: 10.2, 10.5_

- [ ] 7.2 Add JavaScript for dynamic report loading
  - Implement AJAX calls to `/api/reports` and `/api/reports/latest` endpoints
  - Parse JSON responses and populate table dynamically
  - Add loading indicators while fetching data
  - Handle and display error messages from API
  - _Requirements: 10.2, 10.3_

- [ ] 7.3 Add conflict visualization for shared reports
  - Highlight reports with same report_id but different versions
  - Add special styling for "shared-report-050" to demonstrate conflict handling
  - Show version count for reports with multiple versions
  - _Requirements: 10.4_

- [ ] 8. Implement comprehensive error logging
- [ ] 8.1 Add logging to edge application
  - Create logging configuration in `edge/edge_app.py`
  - Log to file `/app/data/edge.log`
  - Include timestamp, log level, component, and message in all log entries
  - Log all sync attempts, successes, and failures
  - Log authentication token generation
  - _Requirements: 2.7_

- [ ] 8.2 Add logging to cloud application
  - Create logging configuration in `cloud/cloud_app.py`
  - Log to file `/app/data/cloud.log`
  - Include timestamp, log level, endpoint, user, and message in all log entries
  - Log all authentication attempts and failures
  - Log all sync requests with source user
  - Log all database errors
  - _Requirements: 3.6, 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 8.3 Write tests for logging functionality
  - Create tests to verify log entries are created for key operations
  - Test log file creation and rotation
  - Test log format compliance
  - _Requirements: 5.5_

- [ ] 9. Add retry logic for failed synchronizations
- [ ] 9.1 Implement exponential backoff for sync retries
  - Add retry counter to edge database schema
  - Implement exponential backoff algorithm (1s, 2s, 4s, 8s, max 60s)
  - Limit maximum retry attempts to 5 per report
  - Track retry count in database
  - _Requirements: 2.7_

- [ ] 9.2 Add retry scheduling mechanism
  - Implement background thread or scheduled task for retry attempts
  - Check for failed reports periodically (e.g., every 5 minutes)
  - Attempt to resync failed reports using retry logic
  - Reset retry counter after successful sync
  - _Requirements: 2.7_

- [ ] 9.3 Write tests for retry logic
  - Create tests for exponential backoff calculation
  - Test retry limit enforcement
  - Test retry counter reset after success
  - _Requirements: 2.7_

- [ ] 10. Enhance authentication error handling
- [ ] 10.1 Improve JWT token error responses
  - Update `verify_token()` in `cloud/cloud_app.py` to return detailed error information
  - Distinguish between expired tokens and invalid signatures
  - Return specific error messages in HTTP 401 responses
  - _Requirements: 3.5_

- [ ] 10.2 Add token regeneration on edge device
  - Detect HTTP 401 responses in edge sync engine
  - Automatically regenerate JWT token and retry once
  - Log authentication failures for troubleshooting
  - _Requirements: 3.1, 3.2, 3.3_

- [ ] 10.3 Write tests for authentication error handling
  - Create tests for expired token handling
  - Test invalid signature detection
  - Test token regeneration and retry
  - _Requirements: 3.5_

- [ ] 11. Add health monitoring enhancements
- [ ] 11.1 Expand health check endpoint
  - Add database connectivity check to `/api/health` endpoint
  - Add report count statistics to health response
  - Add last sync timestamp to health response
  - Return HTTP 503 if database is unreachable
  - _Requirements: 6.1, 6.2, 6.4_

- [ ] 11.2 Write tests for health monitoring
  - Create tests for health endpoint response format
  - Test database connectivity check
  - Test health check without authentication requirement
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 12. Update Docker configuration for enhanced features
- [ ] 12.1 Update Dockerfiles with logging support
  - Ensure log directories are created in both edge and cloud Dockerfiles
  - Set appropriate permissions for log files
  - Verify non-root user can write to log directories
  - _Requirements: 9.1, 9.2_

- [ ] 12.2 Update docker-compose.yml for log persistence
  - Add volume mounts for log directories
  - Ensure log files persist across container restarts
  - Update environment variables if needed for new features
  - _Requirements: 9.5_

- [ ] 12.3 Test Docker deployment end-to-end
  - Build and start all containers using docker-compose
  - Verify edge devices can create and sync reports
  - Verify cloud server receives and stores reports
  - Verify web interface displays reports correctly
  - Verify logs are created and persisted
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 13. Add input validation and security hardening
- [ ] 13.1 Implement input sanitization for report fields
  - Add validation for report_id format (alphanumeric and hyphens only)
  - Add length limits for title (255 chars) and content (2000 chars)
  - Validate classification is one of: CUI, IL4, IL5
  - Sanitize content to prevent SQL injection
  - Escape HTML in content to prevent XSS
  - _Requirements: 1.5, 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 13.2 Add rate limiting to cloud endpoints
  - Implement rate limiting middleware for `/api/sync` endpoint
  - Limit to 100 requests per minute per edge device
  - Return HTTP 429 when rate limit exceeded
  - Log rate limit violations
  - _Requirements: 3.5_

- [ ] 13.3 Write security tests
  - Create tests for SQL injection attempts
  - Test XSS prevention in report content
  - Test rate limiting enforcement
  - Test input validation for all fields
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 14. Create documentation and examples
- [ ] 14.1 Update README with new features
  - Document CRUD operations available in edge application
  - Document sync feedback and status reporting
  - Document soft delete functionality
  - Document query filtering options
  - Update API endpoint documentation
  - _Requirements: All_

- [ ] 14.2 Create API documentation
  - Document all REST API endpoints with request/response examples
  - Document authentication requirements
  - Document error codes and messages
  - Create OpenAPI/Swagger specification file
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.5, 6.1, 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 14.3 Create user guide
  - Write guide for field analysts on using edge application
  - Write guide for headquarters staff on using web interface
  - Document troubleshooting common issues
  - _Requirements: All_
