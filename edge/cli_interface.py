"""CLI interface for edge device operations."""
import re
import os
import database_manager
import edge_app


def validate_report_id(report_id: str) -> bool:
    """Validate report_id format: alphanumeric and hyphens only."""
    if not report_id or len(report_id) > 255:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9\-]+", report_id))


def validate_classification(value: str) -> bool:
    """Ensure classification is one of the allowed values."""
    return value in ("CUI", "IL4", "IL5")


def validate_length(value: str, max_len: int) -> bool:
    """Ensure value length does not exceed max_len."""
    return value is not None and len(value) <= max_len


def display_menu(print_fn=print):
    print_fn("\nEdge CLI Menu")
    print_fn("1) Create Report")
    print_fn("2) View All Reports")
    print_fn("3) Update Report")
    print_fn("4) Delete Report")
    print_fn("5) Sync to Cloud")
    print_fn("0) Exit")


def get_user_choice(input_fn=input, print_fn=print):
    choice = input_fn("Select an option: ").strip()
    if not choice.isdigit():
        print_fn("Invalid choice. Enter a number.")
        return None
    return int(choice)


def handle_create_report(input_fn=input, print_fn=print, db=database_manager):
    report_id = input_fn("Report ID: ").strip()
    if not validate_report_id(report_id):
        print_fn("Invalid report_id. Use alphanumeric and hyphens only, max 255 chars.")
        return False

    title = input_fn("Title: ").strip()
    if not validate_length(title, 255):
        print_fn("Title too long (max 255 chars).")
        return False

    content = input_fn("Content: ").strip()
    if not validate_length(content, 2000):
        print_fn("Content too long (max 2000 chars).")
        return False

    classification = input_fn("Classification (CUI/IL4/IL5): ").strip()
    if not validate_classification(classification):
        print_fn("Invalid classification. Must be one of: CUI, IL4, IL5.")
        return False

    analyst = os.getenv("EDGE_USER", "cli_user")

    db_id = db.create_report(report_id, title, content, classification, analyst)
    print_fn(f"Report created with DB id: {db_id}")
    return True


def handle_view_reports(print_fn=print, db=database_manager):
    reports = db.read_all_reports()
    if not reports:
        print_fn("No reports found.")
        return

    print_fn("\n{:<4} {:<20} {:<30} {:<6} {:<20} {:<10}".format("ID", "Report ID", "Title", "Class", "Updated At", "Synced"))
    for r in reports:
        synced = "Y" if r.get("is_synchronized") else "N"
        print_fn("{:<4} {:<20} {:<30} {:<6} {:<20} {:<10}".format(r.get("id"), r.get("report_id"), (r.get("title")[:29] + ("" if len(r.get("title")) <= 29 else "…")), r.get("classification"), r.get("updated_at"), synced))


def handle_update_report(input_fn=input, print_fn=print, db=database_manager):
    report_id = input_fn("Report ID to update: ").strip()
    if not validate_report_id(report_id):
        print_fn("Invalid report_id format.")
        return False

    existing = db.read_report(report_id)
    if not existing:
        print_fn("Report not found.")
        return False

    title = input_fn(f"New Title [{existing.get('title')}]: ").strip() or existing.get('title')
    if not validate_length(title, 255):
        print_fn("Title too long (max 255 chars).")
        return False

    content = input_fn("New Content (leave blank to keep): ").strip() or existing.get('content')
    if not validate_length(content, 2000):
        print_fn("Content too long (max 2000 chars).")
        return False

    classification = input_fn(f"New Classification [{existing.get('classification')}]: ").strip() or existing.get('classification')
    if not validate_classification(classification):
        print_fn("Invalid classification. Must be one of: CUI, IL4, IL5.")
        return False

    analyst = os.getenv("EDGE_USER", "cli_user")
    db_id = db.update_report(report_id, title, content, classification, analyst)
    print_fn(f"Report updated; new DB id: {db_id}")
    return True


def handle_delete_report(input_fn=input, print_fn=print, db=database_manager):
    report_id = input_fn("Report ID to delete: ").strip()
    if not validate_report_id(report_id):
        print_fn("Invalid report_id format.")
        return False

    confirm = input_fn(f"Are you sure you want to delete {report_id}? (y/N): ").strip().lower()
    if confirm != 'y':
        print_fn("Delete cancelled.")
        return False

    analyst = os.getenv("EDGE_USER", "cli_user")
    db_id = db.delete_report(report_id, analyst)
    print_fn(f"Report soft-deleted; new DB id: {db_id}")
    return True


def handle_sync(print_fn=print, db=database_manager):
    summary = edge_app.sync_to_cloud()
    edge_app.display_sync_summary(summary)
    return summary


def run_cli_loop(input_fn=input, print_fn=print, db=database_manager):
    """Run the interactive CLI loop. Returns when user exits."""
    while True:
        display_menu(print_fn=print_fn)
        choice = get_user_choice(input_fn=input_fn, print_fn=print_fn)
        if choice is None:
            continue
        if choice == 0:
            print_fn("Exiting CLI.")
            break
        elif choice == 1:
            handle_create_report(input_fn=input_fn, print_fn=print_fn, db=db)
        elif choice == 2:
            handle_view_reports(print_fn=print_fn, db=db)
        elif choice == 3:
            handle_update_report(input_fn=input_fn, print_fn=print_fn, db=db)
        elif choice == 4:
            handle_delete_report(input_fn=input_fn, print_fn=print_fn, db=db)
        elif choice == 5:
            handle_sync(print_fn=print_fn, db=db)
        else:
            print_fn("Unknown choice. Please select a valid option.")
