from app.extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)
    role = db.Column(db.Enum('student', 'admin'), nullable=False, default='student')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Profile fields
    bio = db.Column(db.Text, nullable=True)
    profile_photo = db.Column(db.String(255), nullable=True)
    social_facebook = db.Column(db.String(255), nullable=True)
    social_twitter = db.Column(db.String(255), nullable=True)
    social_linkedin = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(50), nullable=True)

    enrollments = db.relationship('Enrollment', back_populates='student')
    progress = db.relationship('Progress', back_populates='student')
    comments = db.relationship('Comment', back_populates='user')
    payments = db.relationship('Payment', back_populates='user')
    coupons = db.relationship("Coupon", back_populates="user", lazy=True)
    sessions = db.relationship('UserSession', back_populates='user', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    provider = db.Column(db.Enum('paystack', 'flutterwave', 'stripe'), nullable=False)
    reference = db.Column(db.String(100), unique=True, nullable=False)
    status = db.Column(db.Enum('pending', 'successful', 'failed'), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    coupon_code = db.Column(db.String(50), nullable=True)

    user = db.relationship('User', back_populates='payments')
    course = db.relationship('Course', backref='payments')

class PendingUser(db.Model):
    __tablename__ = "pending_users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    full_name = db.Column(db.String(120), default="Guest User")
    one_time_token = db.Column(db.String(120), nullable=False)  # hashed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.Enum('student', 'admin'), nullable=False, default='student')
    password_hash = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<PendingUser {self.email}>"

class UserSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    device_info = db.Column(db.String(255))  # e.g. 'Windows 10 - Chrome'
    ip_address = db.Column(db.String(100))
    location = db.Column(db.String(255))  # city or country from IP (optional)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="sessions")