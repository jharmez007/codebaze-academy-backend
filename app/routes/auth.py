from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import User
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, create_refresh_token
from werkzeug.security import check_password_hash
from datetime import timedelta
from app.models.user import PendingUser

bp = Blueprint('auth', __name__)

# Register endpoint
@bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    full_name = data.get('full_name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'student')

    if not all([full_name, email, password]):
        return jsonify({"error": "Missing required fields"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 409

    user = User(full_name=full_name, email=email, role=role)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "User registered successfully"}), 201

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
    new_user.set_password(token)  # temporary password = token
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
    data = request.get_json()

    if not data or "password" not in data:
        return jsonify({"error": "Password is required"}), 400

    password = data["password"]
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    user.set_password(password)
    db.session.commit()

    return jsonify({"message": "Password created successfully. You can now log in normally."}), 200