from datetime import datetime, timedelta
from app.extensions import db

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)  # e.g. "WELCOME100"
    type = db.Column(db.Enum("general", "user_specific", "time_specific", "number_specific", "referral", name="coupon_type"), nullable=False, default="general")

    discount_type = db.Column(db.Enum("percent", "amount", name="discount_type"), nullable=False)
    discount_value = db.Column(db.Float, nullable=False)  # either amount or percent value

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)  # for user-specific coupons
    max_uses = db.Column(db.Integer, nullable=True)  # number of total allowed uses
    used_count = db.Column(db.Integer, default=0)
    valid_from = db.Column(db.DateTime, default=datetime.utcnow)
    valid_until = db.Column(db.DateTime, nullable=True)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # optional: referral link or referral credit
    commission = db.Column(db.Float, nullable=True, default=0.0)

    user = db.relationship("User", back_populates="coupons")
    course = db.relationship("Course", back_populates="coupons")
