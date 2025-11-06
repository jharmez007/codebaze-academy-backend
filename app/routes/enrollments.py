from flask import Blueprint, request, jsonify, render_template, current_app
from app.extensions import db
from app.models import Enrollment, Course, User
from app.models.user import PendingUser
from werkzeug.security import generate_password_hash
from datetime import datetime
import uuid
import random
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.mailer import send_email

bp = Blueprint("enrollment", __name__)

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
            "message": "User already exists. Please log in to continue.",
            "login_required": True
        }), 200

    # CASE 2/3: Pending or new user — send or refresh token
    one_time_token = f"{random.randint(100000, 999999)}"
    pending = PendingUser.query.filter_by(email=email).first()

    if pending:
        # Existing pending user — update token
        pending.one_time_token = one_time_token
        pending.created_at = datetime.utcnow()
        message = "Verification token re-sent. Use it to verify your email."
    else:
        # New pending user
        pending = PendingUser(email=email, one_time_token=one_time_token)
        db.session.add(pending)
        message = "Verification token sent. Use it to verify your email."

    db.session.commit()
    
    try:
        html_body = render_template(
            "emails/pending_user_verification.html",
            token=one_time_token,
            email=email,
            verify_url=f"http://localhost:3000/verify"
        )

        send_email(
            to=email,
            subject="Your Verification Code",
            body=f"Your verification code is {one_time_token}",
            html=html_body
        )

    except Exception as e:
        current_app.logger.error(f"Error sending verification email: {e}")
        return jsonify({
            "message": "Error sending email, please try again later."
        }), 500

    return jsonify({
        "message": message,
        "email": email
    }), 201

@bp.route("/<int:course_id>", methods=["POST"])
@jwt_required()
def enroll_course(course_id):
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    course = Course.query.get(course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    # ✅ Check if user already has any enrollment for this course
    existing = Enrollment.query.filter_by(user_id=user_id, course_id=course_id).first()

    if existing:
        # If already active → block
        if existing.status == "active":
            return jsonify({
                "message": "Already enrolled and active",
                "status": existing.status
            }), 409

        # If status is 'paid' or 'pending', just activate it instead of creating new
        if existing.status in ["paid", "pending"]:
            existing.status = "active"
            existing.progress = 0.0
            db.session.commit()

            return jsonify({
                "message": "Enrollment reactivated",
                "course_id": course.id,
                "course_title": course.title,
                "user_id": user_id,
                "status": existing.status,
                "full_name": user.full_name,
                "has_password": bool(user.password_hash and user.password_hash.strip()),
                "enrolled_at": existing.enrolled_at.isoformat()
            }), 200

    # ✅ Otherwise, create new enrollment
    new_enrollment = Enrollment(
        user_id=user_id,
        course_id=course.id,
        progress=0.0,
        status="active"
    )

    db.session.add(new_enrollment)
    db.session.commit()

    has_password = bool(user.password_hash and user.password_hash.strip())

    return jsonify({
        "message": "Enrollment successful",
        "course_id": course.id,
        "course_title": course.title,
        "user_id": user_id,
        "status": new_enrollment.status,
        "full_name": user.full_name,
        "has_password": has_password,
        "enrolled_at": new_enrollment.enrolled_at.isoformat()
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
 