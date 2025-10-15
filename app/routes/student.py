from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from app.extensions import db
from app.models import User, Enrollment, Course
from app.utils.auth import role_required

from datetime import datetime

bp = Blueprint("students", __name__)

@bp.route("/", methods=["GET"])
@jwt_required()
@role_required("admin")
def get_all_students():
    students = User.query.filter_by(role="student").all()
    result = []
    for s in students:
        result.append({
            "id": s.id,
            "name": s.name,
            "email": s.email,
            "is_active": s.is_active,
            "date_joined": s.created_at,
            "courses_enrolled": len(s.enrollments)
        })
    return jsonify({
        "total_students": len(result),
        "students": result
    }), 200



@bp.route("/courses/<int:course_id>/students", methods=["GET"])
@jwt_required()
@role_required("admin")
def get_students_by_course(course_id):
    enrollments = Enrollment.query.filter_by(course_id=course_id).all()
    if not enrollments:
        return jsonify({"message": "No students enrolled in this course"}), 404

    students = []
    for e in enrollments:
        students.append({
            "student_id": e.student.id,
            "student_name": e.student.name,
            "email": e.student.email,
            "progress": e.progress,
            "enrolled_on": e.enrolled_on
        })
    return jsonify({
        "course_id": course_id,
        "total_students": len(students),
        "students": students
    }), 200


@bp.route("/students/<int:student_id>", methods=["GET"])
@jwt_required()
@role_required("admin")
def get_student_profile(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    enrollments = []
    for e in student.enrollments:
        enrollments.append({
            "course_id": e.course_id,
            "progress": e.progress,
            "enrolled_on": e.enrolled_on
        })
    return jsonify({
        "id": student.id,
        "name": student.name,
        "email": student.email,
        "is_active": student.is_active,
        "date_joined": student.created_at,
        "enrollments": enrollments
    }), 200



@bp.route("/students/<int:student_id>/suspend", methods=["PUT"])
@jwt_required()
@role_required("admin")
def suspend_student(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    if not student.is_active:
        return jsonify({"message": "Student already suspended"}), 400
    student.is_active = False
    db.session.commit()
    return jsonify({"message": f"Student {student.name} has been suspended."}), 200


@bp.route("/students/<int:student_id>/activate", methods=["PUT"])
@jwt_required()
@role_required("admin")
def activate_student(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    if student.is_active:
        return jsonify({"message": "Student already active"}), 400
    student.is_active = True
    db.session.commit()
    return jsonify({"message": f"Student {student.name} has been activated."}), 200
