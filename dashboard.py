from models import (
    get_overdue_followups,
    get_due_soon_followups,
    get_done_count
)


def print_section(title):
    print("\n" + "=" * 50)
    print(title)
    print("=" * 50)


def show_dashboard():
    overdue = get_overdue_followups()
    due_soon = get_due_soon_followups()
    done_count = get_done_count()

    print_section("🔥 OVERDUE FOLLOW-UPS")

    if not overdue:
        print("Nothing overdue. You’re on top of your game.")
    else:
        for f in overdue:
            print(f"[{f[0]}] {f[1]} | {f[2]} | Due: {f[3]}")

    print_section("⏰ DUE SOON")

    if not due_soon:
        print("No upcoming follow-ups.")
    else:
        for f in due_soon:
            print(f"[{f[0]}] {f[1]} | {f[2]} | Due: {f[3]}")

    print_section("✅ DONE")
    print(f"Completed follow-ups: {done_count}")


if __name__ == "__main__":
    show_dashboard()
