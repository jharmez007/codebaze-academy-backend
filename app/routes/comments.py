from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Comment, Course
from flask_jwt_extended import jwt_required, get_jwt_identity

bp = Blueprint("comments", __name__)

# Add comment
@bp.route("/", methods=["POST"])
@jwt_required()
def add_comment():
    user_id = get_jwt_identity()
    data = request.get_json()
    course_id = data.get("course_id")
    content = data.get("content")

    if not all([course_id, content]):
        return jsonify({"error": "Missing fields"}), 400

    comment = Comment(
        course_id=course_id,
        user_id=user_id,
        content=content
    )
    db.session.add(comment)
    db.session.commit()
    return jsonify({"message": "Comment added", "id": comment.id}), 201

# List comments for a course
@bp.route("/course/<int:course_id>", methods=["GET"])
def list_comments(course_id):
    comments = Comment.query.filter_by(course_id=course_id).order_by(Comment.created_at.desc()).all()
    result = []
    for c in comments:
        result.append({
            "id": c.id,
            "user_id": c.user_id,
            "content": c.content,
            "created_at": c.created_at.isoformat()
        })
    return jsonify(result)
