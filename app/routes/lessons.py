from flask import Blueprint, request, jsonify, send_from_directory
from app.extensions import db
from app.models import Lesson, Course
from flask_jwt_extended import jwt_required
from app.utils import role_required
import os

bp = Blueprint("lessons", __name__)

# List lessons for a course
@bp.route("/course/<int:course_id>", methods=["GET"])
@jwt_required()
def list_lessons(course_id):
    lessons = Lesson.query.filter_by(course_id=course_id).all()
    result = []
    for l in lessons:
        result.append({
            "id": l.id,
            "title": l.title,
            "video_url": l.video_url,
            "notes_url": l.notes_url,
            "reference_link": l.reference_link,
            "created_at": l.created_at.isoformat()
        })
    return jsonify(result)

# Admin create a lesson
@bp.route("/", methods=["POST"])
@jwt_required()
@role_required("admin")
def create_lesson():
    data = request.get_json()
    course_id = data.get("course_id")
    title = data.get("title")
    video_url = data.get("video_url")
    notes_url = data.get("notes_url")
    reference_link = data.get("reference_link")

    # Validate course exists
    course = Course.query.get(course_id)
    if not course:
        return jsonify({"error": "Course does not exist"}), 404

    if not title:
        return jsonify({"error": "Missing title"}), 400

    lesson = Lesson(
        course_id=course_id,
        title=title,
        video_url=video_url,
        notes_url=notes_url,
        reference_link=reference_link
    )
    db.session.add(lesson)
    db.session.commit()
    return jsonify({"message": "Lesson created", "id": lesson.id}), 201

@bp.route("/<int:lesson_id>/document", methods=["GET"])
@jwt_required(optional=True)
def download_lesson_document(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)

    if not lesson.document_url:
        return jsonify({"error": "No document available"}), 404

    # document_url example: /static/uploads/docs/file.pdf
    filename = os.path.basename(lesson.document_url)
    directory = os.path.join("static", "uploads", "docs")

    return send_from_directory(
        directory=directory,
        path=filename,
        as_attachment=True
    )