from celery import Celery
from chase import process_auto_chase

celery = Celery("tasks", broker="redis://localhost:6379/0")

@celery.task
def run_auto_chase_for_all_users():
    # loop through users in DB
    from models_saas import get_all_users
    users = get_all_users()
    total_sent = 0
    for user in users:
        total_sent += process_auto_chase(user_id=user["id"])
    return total_sent
