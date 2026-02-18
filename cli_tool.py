from database import init_db
from models import add_followup, mark_followup_done, get_overdue_with_email
from dashboard import show_dashboard
from emailer import send_followup_email
from import_csv import import_followups_from_csv
from chase import process_auto_chase
from scheduler import start_scheduler


def menu():
    print("\nCLIENT FOLLOW-UP TRACKER")
    print("1. Add follow-up")
    print("2. Mark follow-up as done")
    print("3. View dashboard")
    print("4. Exit")
    print("5. Send overdue reminder emails")
    print("6. Import follow-ups from CSV")
    print("7. Run auto-chase engine")


def add_flow():
    client_name = input("Client name: ").strip()
    email = input("Client email: ").strip()
    followup_type = input("Type (invoice / proposal / email / other): ").strip()
    description = input("Description: ").strip()
    due_date = input("Due date (YYYY-MM-DD): ").strip()

    add_followup(
        client_name,
        email,
        followup_type,
        description,
        due_date
    )

    print("Follow-up added.")


def mark_done_flow():
    followup_id = input("Enter follow-up ID to mark as done: ").strip()

    if not followup_id.isdigit():
        print("Invalid ID.")
        return

    mark_followup_done(int(followup_id))
    print("Follow-up marked as done.")


def main():
    init_db()

    while True:
        menu()
        choice = input("Choose an option: ").strip()

        if choice == "1":
            add_flow()

        elif choice == "2":
            mark_done_flow()

        elif choice == "3":
            show_dashboard()

        elif choice == "4":
            print("Goodbye.")
            break

        elif choice == "5":
            overdue = get_overdue_with_email()

            for f in overdue:
                send_followup_email(*f)

            print(f"Sent {len(overdue)} reminder emails.")

        elif choice == "6":
            path = input("Enter CSV file path: ").strip()
            try:
                count = import_followups_from_csv(path)
                print(f"Imported {count} follow-ups.")
            except Exception as e:
                print(f"Import failed: {e}")
        elif choice == "7":
            sent = process_auto_chase()
            print(f"Auto-chase sent {sent} emails.")

        else:
            print("Invalid option.")


if __name__ == "__main__":
    main()

# if __name__ == "__main__":
#     start_scheduler()
#     app.run(debug=True)
