# auth_google.py
import os
from authlib.integrations.flask_client import OAuth

def init_google_oauth(app):
    oauth = OAuth(app)

    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    return oauth
