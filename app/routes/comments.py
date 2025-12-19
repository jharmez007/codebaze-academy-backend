from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models import Comment, User
from app.models.comment import ReportedComment
from app.utils.mailer import send_email
from datetime import datetime

bp = Blueprint("comments", __name__)

def serialize_comment(c, current_user_id=None):
    user = User.query.get(c.user_id)
    replies = Comment.query.filter_by(parent_id=c.id).order_by(Comment.created_at.asc()).all()

    reacted_by_user = {}
    if current_user_id and c.reactions:
        for k in c.reactions.keys():
            reacted_by_user[k] = False  # You can improve this later with a reaction table

    return {
        "id": c.id,
        "lesson_id": c.lesson_id,
        "author": user.full_name if user else "Unknown",
        "role": user.role if user else None,
        "avatar": user.profile_photo if user else None,
        "text": c.content,
        "timestamp": c.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "reactions": c.reactions or {},
        "reactedByUser": reacted_by_user,
        "replies": [serialize_comment(r, current_user_id) for r in replies]
    }


# --- Add comment ---
@bp.route("/", methods=["POST"])
@jwt_required()
def add_comment():
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    lesson_id = data.get("lesson_id")
    content = data.get("content")
    parent_id = data.get("parent_id")

    if not lesson_id or not content:
        return jsonify({"error": "lesson_id and content are required"}), 400

    comment = Comment(
        lesson_id=lesson_id,
        user_id=user_id,
        content=content,
        parent_id=parent_id,
        reactions={}
    )

    db.session.add(comment)
    db.session.commit()

    return jsonify(serialize_comment(comment, user_id)), 201


# --- List comments for a course ---
@bp.route("/course/<int:lesson_id>", methods=["GET"])
@jwt_required(optional=True)
def list_comments(lesson_id):
    current_user_id = get_jwt_identity()

    comments = Comment.query.filter_by(
        lesson_id=lesson_id,
        parent_id=None
    ).order_by(Comment.created_at.desc()).all()

    return jsonify([
        serialize_comment(c, current_user_id) for c in comments
    ]), 200

@bp.route("/<int:comment_id>/react", methods=["POST"])
@jwt_required()
def react_to_comment(comment_id):
    user_id = str(get_jwt_identity())  # store as string for JSON key
    data = request.get_json() or {}

    new_reaction = data.get("reaction")
    if not new_reaction:
        return jsonify({"error": "Reaction type is required"}), 400

    comment = Comment.query.get_or_404(comment_id)

    # Initialize if empty
    reactions = comment.reactions or {}
    user_reactions = getattr(comment, "user_reactions", {}) or {}

    previous_reaction = user_reactions.get(user_id)

    # Decrement old reaction count if it exists
    if previous_reaction:
        reactions[previous_reaction] = max(reactions.get(previous_reaction, 1) - 1, 0)
        # Remove key if count reaches 0
        if reactions[previous_reaction] == 0:
            del reactions[previous_reaction]

    # Add new reaction
    reactions[new_reaction] = reactions.get(new_reaction, 0) + 1
    user_reactions[user_id] = new_reaction

    # Re-assign to trigger SQLAlchemy update
    comment.reactions = reactions
    comment.user_reactions = user_reactions

    db.session.commit()

    return jsonify({
        "message": f"Reaction updated to '{new_reaction}'",
        "reactions": comment.reactions
    }), 200

@bp.route("/<int:comment_id>", methods=["PUT"])
@jwt_required()
def edit_comment(comment_id):
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    comment = Comment.query.get_or_404(comment_id)

    if comment.user_id != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    comment.content = data.get("content", comment.content)
    db.session.commit()

    return jsonify({
        "message": "Comment updated",
        "comment": serialize_comment(comment, user_id)
    }), 200

@bp.route("/<int:comment_id>", methods=["DELETE"])
@jwt_required()
def delete_comment(comment_id):
    user_id = int(get_jwt_identity())

    comment = Comment.query.get_or_404(comment_id)

    if comment.user_id != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    db.session.delete(comment)
    db.session.commit()

    return jsonify({"message": "Comment deleted"}), 200


@bp.route("/<int:comment_id>/report", methods=["POST"])
@jwt_required()
def report_comment(comment_id):
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    reason = data.get("reason")

    if not reason:
        return jsonify({"error": "Reason is required"}), 400

    comment = Comment.query.get_or_404(comment_id)

    already_reported = ReportedComment.query.filter_by(
        comment_id=comment_id,
        reported_by=user_id
    ).first()

    if already_reported:
        return jsonify({"error": "You already reported this comment"}), 409

    report = ReportedComment(
        comment_id=comment_id,
        reported_by=user_id,
        reason=reason
    )

    db.session.add(report)
    db.session.commit()

    # Notify Admin via Email
    admin_emails = [
        u.email for u in User.query.filter_by(role="admin").all()
    ]

    if admin_emails:
        text_body = render_template(
            "emails/comment_reported.txt",
            comment=comment,
            reporter_id=user_id,
            reason=reason
        )

        html_body = render_template(
            "emails/comment_reported.html",
            comment=comment,
            reporter_id=user_id,
            reason=reason
        )

        send_email(
            to=admin_emails,
            subject="New Comment Reported",
            body=text_body,
            html=html_body
        )


    return jsonify({"message": "Comment reported successfully"}), 201

@bp.route("/<int:comment_id>/reactions", methods=["GET"])
@jwt_required(optional=True)
def get_comment_reactions(comment_id):
    comment = Comment.query.get_or_404(comment_id)

    return jsonify({
        "comment_id": comment.id,
        "reactions": comment.reactions or {
            "like": 0,
            "wow": 0,
            "love": 0,
            "clap": 0
        }
    }), 200