from app.extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# class Lesson(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     title = db.Column(db.String(120), nullable=False)
#     video_url = db.Column(db.String(255), nullable=True)
#     # course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)
#     reference_link = db.Column(db.String(500), nullable=True)
#     notes = db.Column(db.Text, nullable=True)
#     document_url = db.Column(db.String(255), nullable=True)
#     slug = db.Column(db.String(150), unique=True, nullable=False)
#     duration = db.Column(db.Float, nullable=True)   # duration in seconds or minutes
#     size = db.Column(db.Integer, nullable=True)  # size in bytes

#     course = db.relationship('Course', back_populates='lessons')
#     progress = db.relationship('Progress', back_populates='lesson')
#     sections_id = db.Column(db.Integer, db.ForeignKey("sections.id"), nullable=False)

#     # Relationships
#     section = db.relationship("Section", backref="lessons")
#     progress = db.relationship("Progress", back_populates="lesson")

class Lesson(db.Model):
    __tablename__ = "lesson"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(150), unique=True, nullable=False)

    video_url = db.Column(db.String(255), nullable=True)
    reference_link = db.Column(db.String(500), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    document_url = db.Column(db.String(255), nullable=True)
    duration = db.Column(db.Float, nullable=True)
    size = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ✅ each Lesson belongs to a Section (not Course directly)
    section_id = db.Column(db.Integer, db.ForeignKey("sections.id"), nullable=False)

    progress = db.relationship("Progress", back_populates="lesson")