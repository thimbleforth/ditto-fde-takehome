# Implementation Plan

- [x] 1. Enhance edge database schema with synchronization tracking

  - Add `is_deleted` column to track soft deletes
  - Add `is_synchronized` column to track sync status
  - Add indexes on `report_id` and `is_synchronized` for query performance
  - Update `init_db()` function in `edge/edge_app.py` to create enhanced schema
  - _Requirements: 1.4, 1.8, 2.6_

- [x] 2. Implement CRUD operations in edge application

- [x] 2.1 Create database manager module for edge device

  - Create new file `edge/database_manager.py` with functions for all CRUD operations
  - Implement `create_report()` function to insert new reports with sync status
  - Implement `read_report(report_id)` function to retrieve single report
  - Implement `read_all_reports()` function to retrieve all reports including from other analysts
  - Implement `update_report()` function to create new version with updated timestamp
  - Implement `delete_report()` function to soft delete with deletion timestamp
  - Implement `get_unsynchronized_reports()` function to query reports where `is_synchronized = 0`
  - Implement `mark_as_synchronized(report_id)` function to update sync status
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 2.2 Write unit tests for database manager

  - Create `edge/test_database_manager.py` with tests for each CRUD operation
  - Test report creation with valid data
  - Test report retrieval and filtering
  - Test update creates new version
  - Test soft delete functionality
  - Test synchronization status tracking
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 3. Implement enhanced sync engine with user feedback

- [x] 3.1 Refactor sync engine to use database manager

  - Update `sync_to_cloud()` in `edge/edge_app.py` to call `get_unsynchronized_reports()`
  - Implement sync summary tracking with counts of successful and failed syncs
  - Implement `sync_single_report()` function to handle individual report transmission
  - Add error handling for network failures with detailed error messages
  - Call `mark_as_synchronized()` after successful sync
  - _Requirements: 2.1, 2.6, 2.7_

- [x] 3.2 Add user feedback for sync operations

  - Implement `display_sync_summary()` function to print sync results to console
  - Display list of successfully synchronized reports with report_ids
  - Display list of failed synchronizations with error details
  - Print total counts of successful vs failed syncs
  - _Requirements: 2.3_

- [x] 3.3 Write integration tests for sync engine

  - Create `edge/test_sync_engine.py` with end-to-end sync tests
  - Test successful sync of multiple reports
  - Test handling of network failures
  - Test sync summary generation
  - Test synchronization status updates
  - _Requirements: 2.1, 2.3, 2.6_

- [x] 4. Enhance cloud database schema for soft deletes

  - Add `is_deleted` column to `Report` model in `cloud/data_models.py`
  - Set default value to 0 (not deleted)
  - Update SQLAlchemy model with new column definition
  - _Requirements: 1.4, 4.5_

- [x] 5. Implement enhanced sync handler in cloud application

- [x] 5.1 Add request validation to sync endpoint

  - Update `/api/sync` endpoint in `cloud/cloud_app.py` to validate all required fields
  - Check for presence of: report_id, title, content, classification, updated_at, updated_by
  - Return HTTP 400 with detailed error message if validation fails
  - _Requirements: 2.4_

- [x] 5.2 Handle soft delete synchronization

  - Check for `is_deleted` flag in incoming sync requests
  - Store deleted reports with `is_deleted = 1` in cloud database
  - Preserve deletion timestamp and analyst who performed deletion
  - _Requirements: 1.4, 2.8_

- [x] 5.3 Improve error handling in sync endpoint

  - Wrap database operations in try-except blocks
  - Return HTTP 500 for database errors with error details
  - Log all sync errors with timestamp and source user
  - Implement transaction rollback on failures
  - _Requirements: 2.4_

- [x] 5.4 Write unit tests for sync handler

  - Create `cloud/test_sync_handler.py` with tests for sync endpoint
  - Test successful report storage
  - Test validation error handling
  - Test soft delete handling
  - Test database error handling
  - _Requirements: 2.4, 2.5_

- [x] 6. Enhance report query endpoints

- [x] 6.1 Update latest reports query to exclude deleted reports

  - Modify `/api/reports/latest` endpoint in `cloud/cloud_app.py`
  - Filter out reports where `is_deleted = 1` when determining latest version
  - Ensure last write wins logic considers only non-deleted reports
  - _Requirements: 4.2, 4.4_

- [x] 6.2 Add filtering option for all reports endpoint

  - Update `/api/reports` endpoint to support optional query parameter `include_deleted`
  - Default behavior excludes deleted reports
  - When `include_deleted=true`, return all reports including deleted ones
  - _Requirements: 4.1, 4.5, 5.4_

- [x] 6.3 Write unit tests for query endpoints

  - Create `cloud/test_query_endpoints.py` with tests for report retrieval
  - Test latest reports excludes deleted
  - Test all reports filtering
  - Test last write wins logic with multiple versions
  - Test empty database handling
  - _Requirements: 4.2, 4.4, 5.4_

- [x] 7. Enhance web interface for better report viewing

- [x] 7.1 Update HTML template with improved layout

  - Modify `cloud/templates/index.html` to display reports in a structured table
  - Add columns for: ID, Report ID, Title, Content, Classification, Updated At, Updated By, Status
  - Add visual indicator for deleted reports (e.g., strikethrough or red text)
  - Improve button styling and layout
  - _Requirements: 10.2, 10.5_

- [x] 7.2 Add JavaScript for dynamic report loading

  - Implement AJAX calls to `/api/reports` and `/api/reports/latest` endpoints
  - Parse JSON responses and populate table dynamically
  - Add loading indicators while fetching data
  - Handle and display error messages from API
  - _Requirements: 10.2, 10.3_

- [x] 7.3 Add conflict visualization for shared reports

  - Highlight reports with same report_id but different versions
  - Add special styling for "shared-report-050" to demonstrate conflict handling
  - Show version count for reports with multiple versions
  - _Requirements: 10.4_

- [x] 8. Implement comprehensive error logging

- [x] 8.1 Add logging to edge application

  - Create logging configuration in `edge/edge_app.py`
  - Log to file `/app/data/edge.log`
  - Include timestamp, log level, component, and message in all log entries
  - Log all sync attempts, successes, and failures
  - Log authentication token generation
  - _Requirements: 2.7_

- [x] 8.2 Add logging to cloud application

  - Create logging configuration in `cloud/cloud_app.py`
  - Log to file `/app/data/cloud.log`
  - Include timestamp, log level, endpoint, user, and message in all log entries
  - Log all authentication attempts and failures
  - Log all sync requests with source user
  - Log all database errors
  - _Requirements: 3.6, 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 8.3 Write tests for logging functionality

  - Create tests to verify log entries are created for key operations
  - Test log file creation and rotation
  - Test log format compliance
  - _Requirements: 5.5_

- [x] 9. Add retry logic for failed synchronizations

- [x] 9.1 Implement exponential backoff for sync retries

  - Add retry counter to edge database schema
  - Implement exponential backoff algorithm (1s, 2s, 4s, 8s, max 60s)
  - Limit maximum retry attempts to 5 per report
  - Track retry count in database
  - _Requirements: 2.7_

- [x] 9.2 Add retry scheduling mechanism

  - Implement background thread or scheduled task for retry attempts
  - Check for failed reports periodically (e.g., every 5 minutes)
  - Attempt to resync failed reports using retry logic
  - Reset retry counter after successful sync
  - _Requirements: 2.7_

- [x] 9.3 Write tests for retry logic

  - Create tests for exponential backoff calculation
  - Test retry limit enforcement
  - Test retry counter reset after success
  - _Requirements: 2.7_

- [x] 10. Enhance authentication error handling

- [x] 10.1 Improve JWT token error responses

  - Update `verify_token()` in `cloud/cloud_app.py` to return detailed error information
  - Distinguish between expired tokens and invalid signatures
  - Return specific error messages in HTTP 401 responses
  - _Requirements: 3.5_

- [x] 10.2 Add token regeneration on edge device

  - Detect HTTP 401 responses in edge sync engine
  - Automatically regenerate JWT token and retry once
  - Log authentication failures for troubleshooting
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 10.3 Write tests for authentication error handling

  - Create tests for expired token handling
  - Test invalid signature detection
  - Test token regeneration and retry
  - _Requirements: 3.5_

- [ ] 11. Add health monitoring enhancements

- [x] 11.1 Expand health check endpoint

  - Add database connectivity check to `/api/health` endpoint
  - Add report count statistics to health response
  - Add last sync timestamp to health response
  - Return HTTP 503 if database is unreachable
  - _Requirements: 6.1, 6.2, 6.4_

- [x] 11.2 Write tests for health monitoring

  - Create tests for health endpoint response format
  - Test database connectivity check
  - Test health check without authentication requirement
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
-

- [ ] 12. Update Docker configuration for enhanced features

- [x] 12.1 Update Dockerfiles with logging support

  - Ensure log directories are created in both edge and cloud Dockerfiles
  - Set appropriate permissions for log files
  - Verify non-root user can write to log directories
  - _Requirements: 9.1, 9.2_

- [x] 12.2 Update docker-compose.yml for log persistence

  - Add volume mounts for log directories
  - Ensure log files persist across container restarts
  - Update environment variables if needed for new features
  - _Requirements: 9.5_

- [x] 12.3 Test Docker deployment end-to-end

  - Build and start all containers using docker-compose
  - Verify edge devices can create and sync reports
  - Verify cloud server receives and stores reports
  - Verify web interface displays reports correctly
  - Verify logs are created and persisted
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 13. Add input validation and security hardening
- [x] 13.1 Implement input sanitization for report fields
  - Add validation for report_id format (alphanumeric and hyphens only)
  - Add length limits for title (255 chars) and content (2000 chars)
  - Validate classification is one of: CUI, IL4, IL5
  - Sanitize content to prevent SQL injection
  - Escape HTML in content to prevent XSS
  - _Requirements: 1.5, 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 13.2 Add rate limiting to cloud endpoints
  - Implement rate limiting middleware for `/api/sync` endpoint
  - Limit to 100 requests per minute per edge device
  - Return HTTP 429 when rate limit exceeded
  - Log rate limit violations
  - _Requirements: 3.5_

- [x] 13.3 Write security tests
  - Create tests for SQL injection attempts
  - Test XSS prevention in report content
  - Test rate limiting enforcement
  - Test input validation for all fields
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 14. Implement CLI interface for edge device
  - [x] 14.1 Create CLI menu module
  - Create new file `edge/cli_interface.py` with interactive menu system
  - Implement `display_menu()` function to show menu options
  - Implement `get_user_choice()` function with input validation
  - Implement main loop that continues until user selects Exit
  - _Requirements: 11.1, 11.2, 11.8_

- [x] 14.2 Implement CLI CRUD operations
  - Implement `handle_create_report()` function to prompt for and create reports
  - Implement `handle_view_reports()` function to display all local reports in formatted table
  - Implement `handle_update_report()` function to prompt for report_id and update fields
  - Implement `handle_delete_report()` function to prompt for report_id and confirm deletion
  - Implement `handle_sync()` function to trigger sync and display results
  - _Requirements: 11.3, 11.4, 11.5, 11.6, 11.7_

- [x] 14.3 Add CLI input validation
  - Implement `validate_report_id()` function to check format (alphanumeric and hyphens)
  - Implement `validate_classification()` function to ensure value is CUI, IL4, or IL5
  - Implement `validate_length()` function for title and content limits
  - Display clear error messages for invalid inputs
  - _Requirements: 11.9_

- [x] 14.4 Add CLI success/error messaging
  - Display success confirmations after each operation with details
  - Display error messages with specific failure reasons
  - Format output for readability with proper spacing and alignment
  - _Requirements: 11.9, 11.10_

- [x] 14.5 Integrate CLI with edge application
  - Update `edge/edge_app.py` to support CLI mode via command-line argument
  - Add `--cli` flag to launch interactive menu instead of automatic sync
  - Ensure CLI uses database_manager module for all operations
  - _Requirements: 11.1, 11.2_

- [x] 14.6 Write tests for CLI interface
  - Create `edge/test_cli_interface.py` with tests for menu functions
  - Test input validation functions
  - Test CRUD operation handlers with mocked database
  - Test menu loop and exit functionality
  - _Requirements: 11.1 through 11.10_

- [x] 15. Implement web interface for edge device
- [x] 15.1 Create Flask web server for edge device
  - Create new file `edge/web_server.py` with Flask application
  - Configure Flask to run on port 5000 (configurable via environment variable)
  - Set up route handlers for web pages and API endpoints
  - Ensure web server uses database_manager module for all operations
  - _Requirements: 12.1, 12.2_

- [x] 15.2 Create HTML template for edge web interface
  - Create `edge/templates/index.html` based on cloud template design
  - Include report table with columns: ID, Report ID, Title, Content, Classification, Updated At, Updated By, Sync Status, Actions
  - Add Create Report button and modal form
  - Add Edit and Delete action buttons for each report
  - Add Sync to Cloud button
  - Add buttons for View All Reports and View Latest Reports
  - _Requirements: 12.2, 12.3, 12.4, 12.7_

- [x] 15.3 Implement edge web API endpoints
  - Implement `GET /api/reports` endpoint to return all local reports as JSON
  - Implement `GET /api/reports/latest` endpoint to return latest version of each report_id
  - Implement `POST /api/reports` endpoint to create new report with validation
  - Implement `PUT /api/reports/<id>` endpoint to update existing report
  - Implement `DELETE /api/reports/<id>` endpoint to soft delete report
  - Implement `POST /api/sync` endpoint to trigger cloud synchronization
  - _Requirements: 12.14_

- [x] 15.4 Add JavaScript for edge web interface
  - Create `edge/static/app.js` with AJAX functions for all API calls
  - Implement dynamic table population from API responses
  - Implement Create Report form submission with validation
  - Implement Edit Report form with pre-population and submission
  - Implement Delete Report confirmation dialog
  - Implement Sync to Cloud with progress indicator and results display
  - _Requirements: 12.5, 12.6, 12.8, 12.9, 12.10, 12.11_

- [x] 15.5 Add sync status indicators to edge web interface
  - Display sync status for each report (synchronized, pending, failed)
  - Use color coding: green for synchronized, yellow for pending, red for failed
  - Update sync status dynamically after sync operations
  - Show sync timestamp for synchronized reports
  - _Requirements: 12.7, 12.12_

- [x] 15.6 Implement form validation in edge web interface
  - Add client-side validation for report_id format
  - Add client-side validation for title and content length limits
  - Add client-side validation for classification dropdown
  - Display validation error messages near form fields
  - Prevent form submission if validation fails
  - _Requirements: 12.6, 12.13_

- [x] 15.7 Add error handling to edge web interface
  - Display error messages from API in user-friendly format
  - Show network error messages when API calls fail
  - Display validation errors from server-side validation
  - Add error message display area at top of page
  - _Requirements: 12.13_

- [x] 15.8 Integrate web server with edge application
  - Update `edge/edge_app.py` to support web mode via command-line argument
  - Add `--web` flag to launch Flask web server instead of automatic sync
  - Ensure web server can run concurrently with sync operations
  - Add graceful shutdown handling for web server
  - _Requirements: 12.1_

- [x] 15.9 Update Docker configuration for edge web interface
  - Update `edge/Dockerfile` to expose port 5000
  - Update `docker-compose.yml` to map edge device port 5000 to host ports
  - Use different host ports for edge1 (5001) and edge2 (5002)
  - Add environment variable for web server port configuration
  - _Requirements: 12.1, 9.3_

- [x] 15.10 Write tests for edge web interface
  - Create `edge/test_web_server.py` with tests for all API endpoints
  - Test GET /api/reports returns all reports
  - Test POST /api/reports creates report with validation
  - Test PUT /api/reports/<id> updates report
  - Test DELETE /api/reports/<id> soft deletes report
  - Test POST /api/sync triggers synchronization
  - Test error handling for invalid inputs
  - _Requirements: 12.1 through 12.14_

- [x] 16. Create documentation and examples
  - Docs created in `docs/` (openapi.yaml, api_examples.md, user_guide.md)
- [x] 16.1 Update README with new features
  - Updated `README.md` with feature summary and docs links
  - Document CLI interface usage and commands
  - Document web interface access and features
  - Document CRUD operations available in edge application
  - Document sync feedback and status reporting
  - Document soft delete functionality
  - Document query filtering options
  - Update API endpoint documentation for both cloud and edge
  - _Requirements: All_

- [x] 16.2 Create API documentation
  - Added `docs/openapi.yaml` and `docs/api_examples.md`
  - Document all REST API endpoints for cloud server with request/response examples
  - Document all REST API endpoints for edge device with request/response examples
  - Document authentication requirements
  - Document error codes and messages
  - Create OpenAPI/Swagger specification file
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.5, 6.1, 7.1, 7.2, 7.3, 7.4, 7.5, 12.14_

- [x] 16.3 Create user guide
  - Added `docs/user_guide.md` and screenshot placeholders
  - Write guide for field analysts on using CLI interface
  - Write guide for field analysts on using edge web interface
  - Write guide for headquarters staff on using cloud web interface
  - Document troubleshooting common issues
  - Include screenshots or examples of each interface
  - _Requirements: All_
