from flask import Blueprint, request, jsonify, render_template, current_app
from app.extensions import db
from app.models import User
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, create_refresh_token
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import timedelta
from app.models.user import PendingUser, UserSession, Payment
from app.models.enrollment import Enrollment
from app.models.progress import Progress
from app.models.comment import Comment
from app.models.coupon import Coupon
from datetime import datetime, timedelta
from app.helpers.currency import get_client_ip
from app.utils.mailer import send_email
import uuid
import hashlib
import random

bp = Blueprint('auth', __name__)

@bp.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    full_name = data.get('full_name', '').strip().title()
    email = data.get('email', '').strip().lower()
    password = data.get('password')
    role = data.get('role', 'student')

    #Validate input
    if not all([full_name, email, password]):
        return jsonify({"error": "Missing required fields"}), 400

    # Check if user already verified
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists."}), 409

    # Check if user pending verification
    pending = PendingUser.query.filter_by(email=email).first()
    is_new = False

    # If pending exists, reuse existing token
    if pending:
        verification_token = pending.one_time_token
    else:
        verification_token = str(random.randint(100000, 999999))
        password_hash = generate_password_hash(password)

        pending = PendingUser(
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            one_time_token=verification_token,
            created_at=datetime.utcnow(),
            role=role
        )
        db.session.add(pending)
        db.session.commit()
        is_new = True

    # Send verification email
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
        if is_new:
            db.session.rollback()
        print("Email send error:", str(e))
        return jsonify({"error": f"Unable to send verification email: {str(e)}"}), 500

    return jsonify({
        "message": (
            "Registration successful. Please check your email to verify your account."
            if is_new
            else "Verification email resent successfully."
        )
    }), 200

@bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()

    if not email:
        return jsonify({"error": "Email is required"}), 400

    # 1️⃣ Check if already verified user
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "This email is already verified. Please log in."}), 400

    # 2️⃣ Check pending user
    pending = PendingUser.query.filter_by(email=email).first()
    if not pending:
        return jsonify({"error": "No pending registration found for this email."}), 404

    # Generate new token and update record
    new_token = str(random.randint(100000, 999999))
    pending.one_time_token = new_token
    pending.created_at = datetime.utcnow()
    db.session.commit()

    # 4️⃣ Resend email
    subject = "Resend Verification Code - CodeBaze Academy"
    text_body = render_template(
        "emails/verify_email.txt",
        full_name=pending.full_name,
        verification_code=new_token
    )
    html_body = render_template(
        "emails/verify_email.html",
        full_name=pending.full_name,
        verification_code=new_token
    )

    try:
        send_email(to=email, subject=subject, body=text_body, html=html_body)
    except Exception as e:
        db.session.rollback()
        print("Resend email error:", str(e))
        return jsonify({"error": f"Unable to resend verification email: {str(e)}"}), 500

    return jsonify({"message": "A new verification code has been sent to your email."}), 200

# Login endpoint
@bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401

    if not user.is_active:
        return jsonify({"error": "Account suspended"}), 403

    #          SESSION MANAGEMENT
    if user.role == "student":

        # Remove very old sessions (>30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        UserSession.query.filter(
            UserSession.created_at < thirty_days_ago,
            UserSession.user_id == user.id
        ).delete()
        db.session.commit()

        # Generate device fingerprint
        ip = request.remote_addr or "0.0.0.0"
        user_agent = request.headers.get("User-Agent", "Unknown")
        device_string = f"{user_agent}:{ip}".encode("utf-8")
        device_hash = hashlib.sha256(device_string).hexdigest()

        # Check if session from this device already exists
        existing_session = UserSession.query.filter_by(
            user_id=user.id,
            device_id=device_hash
        ).first()

        if not existing_session:
            # Count active sessions
            active_sessions = UserSession.query.filter_by(user_id=user.id).order_by(UserSession.created_at.asc()).all()

            if len(active_sessions) >= 5:
                # 👉 Auto-remove oldest session instead of blocking user
                oldest_session = active_sessions[0]
                db.session.delete(oldest_session)
                db.session.commit()

            # Create new session entry
            new_session = UserSession(
                user_id=user.id,
                device_info=user_agent,
                ip_address=ip,
                location="Unknown",
                device_id=device_hash,
                last_active=datetime.utcnow()
            )
            db.session.add(new_session)

        else:
            # Update existing session last_active
            existing_session.last_active = datetime.utcnow()

        db.session.commit()

    #                    TOKENS
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
            "role": user.role,
            "is_active": user.is_active
        }
    }), 200

@bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    user_id = get_jwt_identity()
    ip = request.remote_addr
    user_agent = request.headers.get("User-Agent", "Unknown")

    device_hash = hashlib.sha256(f"{user_agent}:{ip}".encode()).hexdigest()

    UserSession.query.filter_by(
        user_id=user_id,
        device_id=device_hash
    ).delete()

    db.session.commit()

    return jsonify({"message": "Logged out successfully"}), 200

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
    user = User.query.get(get_jwt_identity())
    return jsonify(user.to_dict()), 200

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
        role=pending.role,
        is_active=True
    )
    new_user.password_hash = pending.password_hash
    db.session.add(new_user)
    db.session.delete(pending)
    db.session.commit()

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

    #  Generate a secure reset token
    reset_token = uuid.uuid4().hex

    # Create or update pending reset record (reuse PendingUser table)
    pending = PendingUser.query.filter_by(email=email).first()
    if pending:
        pending.one_time_token = reset_token
        pending.created_at = datetime.utcnow()
    else:
        pending = PendingUser(
            email=email,
            full_name=user.full_name,
            one_time_token=reset_token,
            created_at=datetime.utcnow()
        )
        db.session.add(pending)

    db.session.commit()

    # Determine correct frontend URL based on role
    if user.role == "admin":
        reset_link = f"http://localhost:3000/admin-reset-password?token={reset_token}&email={email}"
    else:
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
        "message": f"A password reset link has been sent to your {user.role} email."
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

    # Update password
    user.set_password(new_password)
    db.session.delete(pending)  # clear token after successful reset
    db.session.commit()

    return jsonify({
        "message": "Password reset successful. You can now log in with your new password."
    }), 200

@bp.route('/delete-account', methods=['DELETE'])
@jwt_required()
def delete_account():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}
    password = data.get("password")

    if not user.check_password(password):
        return jsonify({"error": "Incorrect password"}), 401

    # Delete dependent rows first (to satisfy FK constraints)
    Payment.query.filter_by(user_id=user_id).delete()
    Enrollment.query.filter_by(user_id=user_id).delete()
    Progress.query.filter_by(user_id=user_id).delete()
    Comment.query.filter_by(user_id=user_id).delete()
    Coupon.query.filter_by(user_id=user_id).delete()
    UserSession.query.filter_by(user_id=user_id).delete()

    # Finally delete the user
    db.session.delete(user)
    db.session.commit()

    return jsonify({"message": "Account deleted successfully"}), 200


@bp.route("/auth/change-email", methods=["POST"])
@jwt_required()
def change_email():
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    new_email = data.get("new_email", "").strip().lower()
    if not new_email:
        return jsonify({"error": "New email is required"}), 400

    # Ensure email isn't already used
    if User.query.filter_by(email=new_email).first():
        return jsonify({"error": "Email already in use"}), 409

    # Generate a verification code
    verification_code = str(random.randint(100000, 999999))

    # Save/Update pending record
    pending = PendingUser.query.filter_by(email=new_email).first()
    if pending:
        pending.one_time_token = verification_code
        pending.created_at = datetime.utcnow()
        pending.full_name = User.query.get(user_id).full_name
    else:
        pending = PendingUser(
            email=new_email,
            full_name=User.query.get(user_id).full_name,
            one_time_token=verification_code,
            created_at=datetime.utcnow()
        )
        db.session.add(pending)

    db.session.commit()

    # Send verification email
    subject = "Verify Your New Email - CodeBaze Academy"
    text_body = render_template(
        "emails/change_email.txt",
        full_name=User.query.get(user_id).full_name,
        verification_code=verification_code
    )
    html_body = render_template(
        "emails/change_email.html",
        full_name=User.query.get(user_id).full_name,
        verification_code=verification_code
    )

    send_email(to=new_email, subject=subject, body=text_body, html=html_body)

    return jsonify({"message": "Verification code sent to new email."}), 200

@bp.route("/auth/verify-new-email", methods=["POST"])
@jwt_required()
def verify_new_email():
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    email = data.get("email", "").strip().lower()
    token = data.get("token", "").strip()

    if not all([email, token]):
        return jsonify({"error": "Email and token are required"}), 400

    pending = PendingUser.query.filter_by(email=email).first()
    if not pending or pending.one_time_token != token:
        return jsonify({"error": "Invalid or expired token"}), 401

    # Apply email change
    user = User.query.get(user_id)
    user.email = email

    db.session.delete(pending)  # cleanup
    db.session.commit()

    return jsonify({"message": "Email updated successfully.", "email": email}), 200

@bp.route("/auth/change-password", methods=["POST"])
@jwt_required()
def change_password():
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    old_password = data.get("old_password")
    new_password = data.get("new_password")

    if not all([old_password, new_password]):
        return jsonify({"error": "Old and new passwords are required"}), 400

    if len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400

    user = User.query.get(user_id)

    # Prevent crash if user has null password_hash
    if not user.password_hash:
        return jsonify({"error": "Password is not set for this account"}), 400

    # Validate old password via hashed comparison
    if not user.check_password(old_password):
        return jsonify({"error": "Incorrect old password"}), 401

    # Save hashed new password
    user.set_password(new_password)
    db.session.commit()

    return jsonify({"message": "Password updated successfully."}), 200

@bp.route("/test-ip")
def test_ip():
    return {"ip": get_client_ip()}