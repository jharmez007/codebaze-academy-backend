from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Enrollment, Course, User
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

@bp.route("/<int:course_id>", methods=["POST"])
@jwt_required(optional=True)
def enroll(course_id):
    user_id = get_jwt_identity()
    course = Course.query.filter_by(id=course_id).first()
    if not course:
        return jsonify({"error": "Course not found"}), 404

    # If logged in
    if user_id:
        existing = Enrollment.query.filter_by(user_id=user_id, course_id=course_id).first()
        if existing:
            return jsonify({"message": "Already enrolled"}), 409

        user = User.query.get(user_id)
        enrollment = Enrollment(
            user_id=user.id,
            course_id=course.id,
            progress=0.0,
            status="active"
        )
        email = user.email

    else:
        # Guest user flow
        data = request.get_json()
        if not data or "email" not in data:
            return jsonify({"error": "Email required for guest enrollment"}), 400

        email = data["email"].strip().lower()

        # Check if user already exists
        user = User.query.filter_by(email=email).first()
        if not user:
            # Create temporary guest user with one-time password/token
            one_time_token = uuid.uuid4().hex[:8]  # simple random token
            user = User(
                full_name="Guest User",
                email=email,
                role="student",
                is_active=True,
            )
            user.set_password(one_time_token)
            db.session.add(user)
            db.session.flush()  # ensures user.id is available before Enrollment

            # TODO: Send token to email (e.g., via Flask-Mail)
            # send_welcome_email(email, one_time_token)

        # Check if already enrolled
        existing = Enrollment.query.filter_by(user_id=user.id, course_id=course_id).first()
        if existing:
            return jsonify({"message": "Already enrolled with this email"}), 409

        enrollment = Enrollment(
            user_id=user.id,
            course_id=course.id,
            progress=0.0,
            status="pending"  # until guest confirms
        )

    db.session.add(enrollment)
    db.session.commit()

    return jsonify({
        "message": "Enrollment successful",
        "course_id": course.id,
        "course_title": course.title,
        "user_id": user.id,
        "email": email,
        "progress": enrollment.progress,
        "status": enrollment.status,
        "one_time_token": one_time_token if not user_id else None,
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
 