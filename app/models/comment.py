from app.extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    content = db.Column(db.Text, nullable=False)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False
    )

    lesson_id = db.Column(
        db.Integer,
        db.ForeignKey("lesson.id", ondelete="CASCADE"),
        nullable=False
    )

    reactions = db.Column(db.JSON, default=dict)

    # replies
    parent_id = db.Column(
        db.Integer,
        db.ForeignKey("comment.id", ondelete="CASCADE"),
        nullable=True
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # relationships
    user = db.relationship("User", back_populates="comments")
    lesson = db.relationship("Lesson", back_populates="comments")

    replies = db.relationship(
        "Comment",
        cascade="all, delete",
        backref=db.backref("parent", remote_side=[id])
    )

class ReportedComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    comment_id = db.Column(db.Integer, db.ForeignKey("comment.id"), nullable=False)
    reported_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    reason = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    status = db.Column(db.String(50), default="pending")  
    # pending | reviewed | dismissed

    # Relationships
    comment = db.relationship("Comment")
    reporter = db.relationship("User")