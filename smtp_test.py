from database import get_connection
def disconnect_all_gmail():
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET gmail_token = NULL")
    conn.commit()
    conn.close()
