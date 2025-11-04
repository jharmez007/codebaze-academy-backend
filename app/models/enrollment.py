from app.extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    progress = db.Column(db.Float, default=0.0)  # percentage
    status = db.Column(db.String(50), default="active")
    payment_reference = db.Column(db.String(120), unique=True, nullable=True)

    student = db.relationship('User', back_populates='enrollments')
    course = db.relationship('Course', back_populates='enrollments')

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    course_id = db.Column(db.Integer)
    amount = db.Column(db.Integer)
    reference = db.Column(db.String(120), unique=True)
    status = db.Column(db.String(20))  # pending, success, failed
    created_at = db.Column(db.DateTime, default=db.func.now()) 