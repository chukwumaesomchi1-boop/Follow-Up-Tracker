from models import add_followup, get_overdue_followups

add_followup(
    "Test Client",
    "test@example.com",
    "invoice",
    "Invoice #001",
    "2024-01-01"
)

print(get_overdue_followups())
