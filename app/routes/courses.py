from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Course
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.auth import role_required

bp = Blueprint("courses", __name__)

# List all published courses
@bp.route("/", methods=["GET"])
def list_courses():
    courses = Course.query.filter_by(is_published=True).all()
    result = []
    for c in courses:
        result.append({
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "price": c.price,
            "created_at": c.created_at.isoformat()
        })
    return jsonify(result)

# Get details of a single course
@bp.route("/<int:course_id>", methods=["GET"])
def get_course(course_id):
    course = Course.query.get_or_404(course_id)
    return jsonify({
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "price": course.price,
        "is_published": course.is_published,
        "created_at": course.created_at.isoformat()
    })

# Create a course (admin only)
@bp.route("/", methods=["POST"])
@jwt_required()
@role_required("admin")
def create_course():
    data = request.get_json()
    title = data.get("title")
    description = data.get("description")
    price = data.get("price")

    if not all([title, description, price]):
        return jsonify({"error": "Missing fields"}), 400

    course = Course(
        title=title,
        description=description,
        price=price,
        is_published=True
    )
    db.session.add(course)
    db.session.commit()
    return jsonify({"message": "Course created", "id": course.id}), 201

# Update a course (admin only)
@bp.route("/<int:course_id>", methods=["PUT"])
@jwt_required()
@role_required("admin")
def update_course(course_id):
    course = Course.query.get_or_404(course_id)
    data = request.get_json()
    course.title = data.get("title", course.title)
    course.description = data.get("description", course.description)
    course.price = data.get("price", course.price)
    course.is_published = data.get("is_published", course.is_published)
    db.session.commit()
    return jsonify({"message": "Course updated"})

# Delete a course (admin only)
@bp.route("/<int:course_id>", methods=["DELETE"])
@jwt_required()
@role_required("admin")
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    return jsonify({"message": "Course deleted"})
