from flask import Blueprint, request, jsonify, render_template, current_app
from app.extensions import db
from app.models import User
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, create_refresh_token
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import timedelta
from app.models.user import PendingUser
from datetime import datetime
from app.utils.mailer import send_email
import uuid
import random

bp = Blueprint('auth', __name__)

@bp.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    full_name = data.get('full_name')
    email = data.get('email', '').strip().lower()
    password = data.get('password')
    role = data.get('role', 'student')

    if not all([full_name, email, password]):
        return jsonify({"error": "Missing required fields"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 409

    verification_token = str(random.randint(100000, 999999))

    # ✅ Hash password before saving
    password_hash = generate_password_hash(password)

    pending = PendingUser(
        full_name=full_name.strip().title(),
        email=email,
        password_hash=password_hash,  # save hashed password
        one_time_token=verification_token,
        created_at=datetime.utcnow()
    )
    db.session.add(pending)
    db.session.commit()

    subject = "Verify Your Email - CodeBaze Academy"
    text_body = render_template(
        "emails/verify_email.txt",
        full_name=full_name,
        verification_code=verification_token
    )
    html_body = render_template(
        "emails/verify_email.html",
        full_name=full_name,
        verification_code=verification_token
    )

    try:
        send_email(to=email, subject=subject, body=text_body, html=html_body)
    except Exception as e:
        db.session.delete(pending)
        db.session.commit()
        return jsonify({"error": "Unable to send verification email"}), 500

    return jsonify({
        "message": "Registration successful. Please check your email to verify your account."
    }), 201

# Login endpoint
@bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()

    if user and user.check_password(password):
        # Generate tokens
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={"role": user.role}
        )
        refresh_token = create_refresh_token(identity=str(user.id))

        return jsonify({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role
            }
        }), 200

    return jsonify({"error": "Invalid credentials"}), 401

@bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)  # fetch user from DB
    
    new_access_token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role}
    )
    return jsonify({"access_token": new_access_token}), 200

# Get current user
@bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    return jsonify({
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role
    })

@bp.route("/auth/verify-token", methods=["POST"])
def verify_token_login():
    data = request.get_json()
    if not data or "email" not in data or "token" not in data:
        return jsonify({"error": "Email and token are required"}), 400

    email = data["email"].strip().lower()
    token = data["token"].strip()
    pending = PendingUser.query.filter_by(email=email).first()

    if not pending:
        return jsonify({"error": "No pending verification for this email"}), 404

    if pending.one_time_token != token:
        return jsonify({"error": "Invalid or expired token"}), 401

    # Move from PendingUser -> User
    new_user = User(
        full_name=pending.full_name,
        email=pending.email,
        role="student",
        is_active=True
    )
    new_user.password_hash = pending.password_hash
    db.session.add(new_user)
    db.session.delete(pending)
    db.session.commit()

    # ✅ FIXED: identity must be a string
    access_token = create_access_token(
        identity=str(new_user.id),
        additional_claims={"role": new_user.role},
        expires_delta=timedelta(hours=6)
    )

    return jsonify({
        "message": "Verification successful. Account created.",
        "access_token": access_token,
        "user": {
            "id": new_user.id,
            "email": new_user.email,
            "full_name": new_user.full_name,
            "role": new_user.role
        }
    }), 201

@bp.route("/auth/create-password", methods=["POST"])
@jwt_required()
def create_password():
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    # Validate password
    password = data.get("password")
    if not password:
        return jsonify({"error": "Password is required"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    # Validate user existence
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Optionally update full name
    full_name = data.get("full_name")
    if full_name:
        user.full_name = full_name.strip().title()  # formats properly

    user.set_password(password)
    db.session.commit()

    return jsonify({
        "message": "Password and profile updated successfully. You can now log in normally.",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name
        }
    }), 200

@bp.route("/auth/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()

    if not email:
        return jsonify({"error": "Email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "No account found with that email"}), 404

    # ✅ Generate a secure token
    reset_token = uuid.uuid4().hex

    # ✅ Create or update pending reset record
    pending = PendingUser.query.filter_by(email=email).first()
    if pending:
        pending.one_time_token = reset_token
        pending.created_at = datetime.utcnow()
    else:
        pending = PendingUser(email=email, one_time_token=reset_token)
        db.session.add(pending)

    db.session.commit()

    # ✅ Build reset link (frontend URL)
    reset_link = f"http://localhost:3000/reset-password?token={reset_token}&email={email}"

    # ✅ Send email
    subject = "Reset Your Password - CodeBaze Academy"
    text_body = render_template(
        "emails/reset_password.txt",
        full_name=user.full_name,
        reset_link=reset_link
    )
    html_body = render_template(
        "emails/reset_password.html",
        full_name=user.full_name,
        reset_link=reset_link
    )

    try:
        send_email(to=email, subject=subject, body=text_body, html=html_body)
    except Exception as e:
        current_app.logger.error(f"Failed to send reset email: {e}")
        return jsonify({"error": "Unable to send reset email at the moment"}), 500

    return jsonify({
        "message": "A password reset link has been sent to your email."
    }), 200

@bp.route("/auth/verify-reset-token", methods=["POST"])
def verify_reset_token():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    token = data.get("token", "").strip()

    if not all([email, token]):
        return jsonify({"error": "Email and token are required"}), 400

    pending = PendingUser.query.filter_by(email=email).first()
    if not pending or pending.one_time_token != token:
        return jsonify({"error": "Invalid or expired reset link"}), 401

    # Optional: add expiry check (e.g., 15 mins)
    if (datetime.utcnow() - pending.created_at).total_seconds() > 900:
        db.session.delete(pending)
        db.session.commit()
        return jsonify({"error": "Reset link has expired"}), 401

    return jsonify({
        "message": "Reset token is valid."
    }), 200


@bp.route("/auth/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    token = data.get("token", "").strip()
    new_password = data.get("password", "")

    if not all([email, token, new_password]):
        return jsonify({"error": "Email, token, and password are required"}), 400

    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    pending = PendingUser.query.filter_by(email=email).first()
    if not pending or pending.one_time_token != token:
        return jsonify({"error": "Invalid or expired reset token"}), 401

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # ✅ Update password
    user.set_password(new_password)
    db.session.delete(pending)  # clear token after successful reset
    db.session.commit()

    return jsonify({
        "message": "Password reset successful. You can now log in with your new password."
    }), 200
