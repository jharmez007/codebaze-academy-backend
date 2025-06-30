from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Enrollment, Course
from flask_jwt_extended import jwt_required, get_jwt_identity

bp = Blueprint("enrollment", __name__)

# Enroll in a course
@bp.route("/<int:course_id>", methods=["POST"])
@jwt_required()
def enroll(course_id):
    user_id = get_jwt_identity()

    # Check if course exists
    course = Course.query.get_or_404(course_id)

    # Check if already enrolled
    existing = Enrollment.query.filter_by(user_id=user_id, course_id=course_id).first()
    if existing:
        return jsonify({"message": "Already enrolled"}), 409

    enrollment = Enrollment(
        user_id=user_id,
        course_id=course_id
    )
    db.session.add(enrollment)
    db.session.commit()

    return jsonify({"message": "Enrollment successful"}), 201

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
 