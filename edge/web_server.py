from flask import Flask, request, jsonify, render_template
import os
import re
import datetime

import database_manager

app = Flask(__name__, static_folder='static', template_folder='templates')

VALID_CLASSIFICATIONS = {"CUI", "IL4", "IL5"}
REPORT_ID_REGEX = re.compile(r"^[A-Za-z0-9\-]+$")


def validate_report_payload(data):
    if not isinstance(data, dict):
        return False, "Request body must be a JSON object"
    required = ["report_id", "title", "content", "classification", "updated_by"]
    missing = [r for r in required if r not in data]
    if missing:
        return False, f"Missing required field(s): {', '.join(missing)}"

    if not REPORT_ID_REGEX.match(data.get("report_id", "")):
        return False, "Invalid report_id format: only alphanumeric and hyphens allowed"
    if data.get("classification") not in VALID_CLASSIFICATIONS:
        return False, f"Invalid classification: must be one of {', '.join(sorted(VALID_CLASSIFICATIONS))}"
    if not data.get("title") or len(data.get("title")) > 255:
        return False, "Title is required and must be 1-255 characters"
    if not data.get("content") or len(data.get("content")) > 2000:
        return False, "Content is required and must be 1-2000 characters"

    # Set updated_at if not provided
    if "updated_at" not in data or not data.get("updated_at"):
        data["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return True, "ok"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/reports", methods=["GET"])
def get_reports():
    include_deleted = request.args.get("include_deleted", "false").lower() == "true"
    reports = database_manager.read_all_reports()
    if not include_deleted:
        reports = [r for r in reports if r.get("is_deleted") == 0]
    return jsonify(reports)


@app.route("/api/reports/latest", methods=["GET"])
def get_latest_reports():
    include_deleted = request.args.get("include_deleted", "false").lower() == "true"
    reports = database_manager.read_all_reports()
    # sort by report_id then updated_at desc
    reports_sorted = sorted(reports, key=lambda r: (r.get("report_id"), r.get("updated_at")), reverse=True)
    latest = {}
    for r in reports_sorted:
        rid = r.get("report_id")
        if rid in latest:
            continue
        if not include_deleted and r.get("is_deleted") == 1:
            continue
        latest[rid] = r
    return jsonify(list(latest.values()))


@app.route("/api/reports", methods=["POST"])
def create_report():
    data = request.json
    valid, detail = validate_report_payload(data)
    if not valid:
        return jsonify({"error": "invalid_request", "details": detail}), 400

    db_id = database_manager.create_report(
        data["report_id"], data["title"], data["content"], data["classification"], data["updated_by"]
    )
    return jsonify({"status": "ok", "id": db_id})


@app.route("/api/reports/<int:db_id>", methods=["PUT"])
def update_report(db_id):
    data = request.json
    # Basic validation for fields to update (title/content/classification/updated_by)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid_request", "details": "Request body must be JSON"}), 400

    # fetch existing record to get report_id
    try:
        # reuse database_manager to find by iterating
        records = database_manager.read_all_reports()
        record = next((r for r in records if r.get("id") == db_id), None)
        if not record:
            return jsonify({"error": "not_found"}), 404
        report_id = record.get("report_id")
        title = data.get("title", record.get("title"))
        content = data.get("content", record.get("content"))
        classification = data.get("classification", record.get("classification"))
        updated_by = data.get("updated_by", record.get("updated_by", "web"))

        # Validate
        valid, detail = validate_report_payload({"report_id": report_id, "title": title, "content": content, "classification": classification, "updated_by": updated_by})
        if not valid:
            return jsonify({"error": "invalid_request", "details": detail}), 400

        new_db_id = database_manager.update_report(report_id, title, content, classification, updated_by)
        return jsonify({"status": "ok", "id": new_db_id})
    except Exception as e:
        return jsonify({"error": "internal_error", "details": str(e)}), 500


@app.route("/api/reports/<int:db_id>", methods=["DELETE"])
def delete_report(db_id):
    data = request.json or {}
    updated_by = data.get("updated_by", "web")
    # find record
    records = database_manager.read_all_reports()
    record = next((r for r in records if r.get("id") == db_id), None)
    if not record:
        return jsonify({"error": "not_found"}), 404
    try:
        new_db_id = database_manager.delete_report(record.get("report_id"), updated_by)
        return jsonify({"status": "ok", "id": new_db_id})
    except Exception as e:
        return jsonify({"error": "internal_error", "details": str(e)}), 500


@app.route("/api/sync", methods=["POST"])
def trigger_sync():
    # Import here to avoid circular import at module import time
    import edge_app
    try:
        summary = edge_app.sync_to_cloud()
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": "internal_error", "details": str(e)}), 500


if __name__ == "__main__":
    # Ensure DB exists
    database_manager.init_db()
    port = int(os.getenv("EDGE_WEB_PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
