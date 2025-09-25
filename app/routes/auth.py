from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import User
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, create_refresh_token

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