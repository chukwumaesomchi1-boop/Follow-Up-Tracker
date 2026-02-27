import stripe
from flask import url_for, redirect
from models_saas import activate_subscription

stripe.api_key = "YOUR_STRIPE_SECRET_KEY"

PRICE_ID = "price_XXXXXXXXXXXX"  # Get from Stripe Dashboard


def create_checkout_session(user_id, domain_url):
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price": PRICE_ID,
            "quantity": 1,
        }],
        mode="subscription",
        success_url=f"{domain_url}/billing/success?user_id={user_id}",
        cancel_url=f"{domain_url}/billing"
    )
    return session.url


def handle_success(user_id):
    """Mark user as subscribed after successful payment"""
    activate_subscription(user_id)
