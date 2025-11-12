from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models import Comment, User
from datetime import datetime

bp = Blueprint("comments", __name__)

# --- Add comment ---
@bp.route("/", methods=["POST"])
@jwt_required()
def add_comment():
    user_id = get_jwt_identity()
    data = request.get_json()
    course_id = data.get("course_id")
    content = data.get("content")
    parent_id = data.get("parent_id")  # For nested replies

    if not all([course_id, content]):
        return jsonify({"error": "Missing fields"}), 400

    comment = Comment(
        course_id=course_id,
        user_id=user_id,
        content=content,
        parent_id=parent_id,
        created_at=datetime.utcnow()
    )
    db.session.add(comment)
    db.session.commit()
    return jsonify({"message": "Comment added", "id": comment.id}), 201


# --- List comments for a course ---
@bp.route("/course/<int:course_id>", methods=["GET"])
def list_comments(course_id):
    comments = Comment.query.filter_by(course_id=course_id, parent_id=None)\
        .order_by(Comment.created_at.desc()).all()

    def serialize_comment(c):
        user = User.query.get(c.user_id)
        replies = Comment.query.filter_by(parent_id=c.id).all()
        return {
            "id": c.id,
            "author": user.full_name if user else "Unknown",
            "role": user.role if user else None,
            "avatar": f"https://i.pravatar.cc/150?u={user.id}" if user else None,
            "text": c.content,
            "timestamp": c.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "reactions": {},  # future extension
            "reactedByUser": {},
            "replies": [serialize_comment(r) for r in replies],
        }

    serialized = [serialize_comment(c) for c in comments]
    return jsonify(serialized), 200
