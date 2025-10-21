from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Enrollment, Course, User
from app.models.user import PendingUser
from werkzeug.security import generate_password_hash
from datetime import datetime
import uuid
from flask_jwt_extended import jwt_required, get_jwt_identity

bp = Blueprint("enrollment", __name__)

# Enroll in a course
# @bp.route("/<int:course_id>", methods=["POST"])
# @jwt_required(optional=True)  # allow both logged in + guest users
# def enroll(course_id):
#     user_id = get_jwt_identity()
#     course = Course.query.filter_by(id=course_id).first()
#     if not course:
#         return jsonify({"error": "Course not found"}), 404

#     if user_id:  
#         # Logged-in user
#         existing = Enrollment.query.filter_by(user_id=user_id, course_id=course_id).first()
#         if existing:
#             return jsonify({"message": "Already enrolled"}), 409

#         enrollment = Enrollment(
#             user_id=user_id,
#             course_id=course_id,
#             progress=0.0,
#             status="active"
#         )
#     else:
#         # Guest user – collect email
#         data = request.get_json()
#         if not data or "email" not in data:
#             return jsonify({"error": "Email required for guest enrollment"}), 400
#         email = data["email"]

#         existing = Enrollment.query.filter_by(email=email, course_id=course_id).first()
#         if existing:
#             return jsonify({"message": "Already enrolled with this email"}), 409

#         enrollment = Enrollment(
#             course_id=course_id,
#             progress=0.0,
#             status="pending"  # guest enrollments stay pending until account created
#         )

#     db.session.add(enrollment)
#     db.session.commit()

#     return jsonify({
#         "message": "Enrollment successful",
#         "course_id": course.id,
#         "course_title": course.title,
#         "user_id": user_id,
#         "email": enrollment.email,
#         "progress": enrollment.progress,
#         "status": enrollment.status,
#         "enrolled_at": enrollment.enrolled_at.isoformat()
#     }), 201


# @bp.route("/request", methods=["POST"])
# def request_enrollment():
#     data = request.get_json()
#     if not data or "email" not in data:
#         return jsonify({"error": "Email is required"}), 400

#     email = data["email"].strip().lower()
#     existing_user = User.query.filter_by(email=email).first()
#     if existing_user:
#         return jsonify({
#             "message": "User already exists. Please log in to continue.",
#             "login_required": True
#         }), 200

#     # If email already pending, update token
#     pending = PendingUser.query.filter_by(email=email).first()
#     one_time_token = uuid.uuid4().hex[:8]
#     hashed_token = generate_password_hash(one_time_token)

#     if pending:
#         pending.one_time_token = one_time_token
#         pending.created_at = datetime.utcnow()
#     else:
#         pending = PendingUser(email=email, one_time_token=one_time_token)
#         db.session.add(pending)

#     db.session.commit()

#     return jsonify({
#         "message": "Verification token sent. Use it to verify your email.",
#         "email": email,
#         "one_time_token": one_time_token  # in real case, send via email
#     }), 201

@bp.route("/request", methods=["POST"])
def request_enrollment():
    data = request.get_json()
    if not data or "email" not in data:
        return jsonify({"error": "Email is required"}), 400

    email = data["email"].strip().lower()

    # CASE 1: Existing user — tell frontend to go to login
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({
            "state": "existing_user",
            "message": "User already exists. Please log in to continue.",
            "login_required": True
        }), 200

    # CASE 2/3: Pending or new user — send or refresh token
    one_time_token = uuid.uuid4().hex[:8]
    pending = PendingUser.query.filter_by(email=email).first()

    if pending:
        # Existing pending user — update token
        pending.one_time_token = one_time_token
        pending.created_at = datetime.utcnow()
        state = "pending_user"
        message = "Verification token re-sent. Use it to verify your email."
    else:
        # New pending user
        pending = PendingUser(email=email, one_time_token=one_time_token)
        db.session.add(pending)
        state = "new_user"
        message = "Verification token sent. Use it to verify your email."

    db.session.commit()

    return jsonify({
        "state": state,
        "message": message,
        "email": email,
        "one_time_token": one_time_token  # Normally sent by email
    }), 201

@bp.route("/<int:course_id>", methods=["POST"])
@jwt_required()
def enroll_course(course_id):
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404
    course = Course.query.filter_by(id=course_id).first()

    if not course:
        return jsonify({"error": "Course not found"}), 404

    existing = Enrollment.query.filter_by(user_id=user_id, course_id=course_id).first()
    if existing:
        return jsonify({"message": "Already enrolled"}), 409

    enrollment = Enrollment(
        user_id=user_id,
        course_id=course.id,
        progress=0.0,
        status="active"
    )

    db.session.add(enrollment)
    db.session.commit()

    return jsonify({
        "message": "Enrollment successful",
        "course_id": course.id,
        "course_title": course.title,
        "user_id": user_id,
        "status": enrollment.status,
        "password_created": bool(user.password_hash),
        "enrolled_at": enrollment.enrolled_at.isoformat()
    }), 201

# List user's enrolled courses
@bp.route("/", methods=["GET"])
@jwt_required()
def list_enrollments():
    user_id = get_jwt_identity()
    enrollments = Enrollment.query.filter_by(user_id=user_id).all()
    result = []
    for e in enrollments:
        result.append({
            "enrollment_id": e.id,
            "course_id": e.course_id,
            "enrolled_at": e.enrolled_at.isoformat(),
            "course_title": e.course.title
        })
    return jsonify(result)
 