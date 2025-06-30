from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Progress
from flask_jwt_extended import jwt_required, get_jwt_identity

bp = Blueprint("progress", __name__)

# Mark lesson complete
@bp.route("/complete", methods=["POST"])
@jwt_required()
def mark_complete():
    user_id = get_jwt_identity()
    data = request.get_json()
    lesson_id = data.get("lesson_id")

    if not lesson_id:
        return jsonify({"error": "Missing lesson_id"}), 400

    progress = Progress(
        user_id=user_id,
        lesson_id=lesson_id,
        completed=True
    )
    db.session.add(progress)
    db.session.commit()
    return jsonify({"message": "Lesson marked as complete"})
