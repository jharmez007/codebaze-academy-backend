from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Progress
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime

bp = Blueprint("progress", __name__)

# Mark lesson complete
@bp.route("/complete", methods=["POST"])
@jwt_required()
def mark_complete():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    lesson_id = data.get("lesson_id")

    if not lesson_id:
        return jsonify({"error": "Missing lesson_id"}), 400

    progress = Progress.query.filter_by(
        user_id=user_id,
        lesson_id=lesson_id
    ).first()

    # If already exists, update it
    if progress:
        if progress.is_completed:
            return jsonify({"message": "Lesson already marked as complete"}), 200
        progress.is_completed = True
        progress.completed_at = datetime.utcnow()
    else:
        progress = Progress(
            user_id=user_id,
            lesson_id=lesson_id,
            is_completed=True,
            completed_at=datetime.utcnow()
        )
        db.session.add(progress)

    db.session.commit()
    return jsonify({"message": "Lesson marked as complete"}), 200

@bp.route("/uncomplete", methods=["POST"])
@jwt_required()
def uncomplete_lesson():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    lesson_id = data.get("lesson_id")

    if not lesson_id:
        return jsonify({"error": "Missing lesson_id"}), 400

    progress = Progress.query.filter_by(
        user_id=user_id,
        lesson_id=lesson_id
    ).first()

    if not progress:
        return jsonify({"error": "Progress record not found"}), 404

    progress.is_completed = False
    progress.completed_at = None

    db.session.commit()

    return jsonify({"message": "Lesson marked as incomplete"}), 200

