# from flask import Blueprint, render_template, request, redirect, url_for, flash
# from models_saas import create_user, get_user_by_email
# from flask_login import login_user
# from flask_bcrypt import generate_password_hash
# from datetime import datetime, timedelta


# auth_bp = Blueprint("auth", __name__)

# @auth_bp.route("/register", methods=["GET", "POST"])
# def register():
#     if request.method == "POST":
#         name = request.form["name"]
#         email = request.form["email"]
#         password = request.form["password"]

#         pw_hash = generate_password_hash(password).decode("utf-8")
#         create_user(name, email, pw_hash)

#         flash("Account created. Please log in.")
#         return redirect(url_for("auth.login"))

#     return render_template("register.html")


# @auth_bp.route("/login", methods=["GET", "POST"])
# def login():
#     if request.method == "POST":
#         email = request.form["email"]
#         password = request.form["password"]

#         user = get_user_by_email(email)
#         if user and check_password(password, user["password_hash"]):
#             login_user(user)
#             return redirect(url_for("dashboard"))

#         flash("Invalid login")
#     return render_template("login.html")


# trial_days = 30
# trial_start = datetime.now().isoformat()
# trial_end = (datetime.now() + timedelta(days=trial_days)).isoformat()

# create_user(
#     name=name,
#     email=email,
#     password_hash=pw_hash,
#     trial_start=trial_start,
#     trial_end=trial_end
# )

from flask import Blueprint, render_template, request, redirect, url_for, flash
from models_saas import create_user, get_user_by_email
from flask_login import login_user
from flask_bcrypt import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask_login import UserMixin

auth_bp = Blueprint("auth", __name__)

# Minimal User wrapper for Flask-Login
class User(UserMixin):
    def __init__(self, data):
        self.id = data["id"]
        self.name = data["name"]
        self.email = data["email"]
        self.password_hash = data["password_hash"]

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        # Check if user already exists
        if get_user_by_email(email):
            flash("Email already registered.")
            return redirect(url_for("auth.register"))

        pw_hash = generate_password_hash(password).decode("utf-8")
        create_user(name, email, pw_hash)

        flash("Account created. Please log in.")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user_data = get_user_by_email(email)
        if user_data and check_password_hash(user_data["password_hash"], password):
            login_user(User(user_data))
            return redirect(url_for("dashboard"))

        flash("Invalid login credentials.")
    return render_template("login.html")
