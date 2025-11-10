from datetime import datetime
from app.extensions import db

# ✅ many-to-many link table
coupon_courses = db.Table(
    "coupon_courses",
    db.Column("coupon_id", db.Integer, db.ForeignKey("coupon.id"), primary_key=True),
    db.Column("course_id", db.Integer, db.ForeignKey("course.id"), primary_key=True)
)

class Coupon(db.Model):
    __tablename__ = "coupon"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    type = db.Column(db.Enum(
        "general", "user_specific", "time_specific", "number_specific", "referral",
        name="coupon_type"
    ), nullable=False, default="general")

    discount_type = db.Column(db.Enum("percent", "amount", name="discount_type"), nullable=False)
    discount_value = db.Column(db.Float, nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    max_uses = db.Column(db.Integer, nullable=True)
    used_count = db.Column(db.Integer, default=0)
    valid_from = db.Column(db.DateTime, default=datetime.utcnow)
    valid_until = db.Column(db.DateTime, nullable=True)
    applies_to_all = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    commission = db.Column(db.Float, nullable=True, default=0.0)

    # ✅ Relationships
    user = db.relationship("User", back_populates="coupons")
    courses = db.relationship("Course", secondary=coupon_courses, back_populates="coupons")

    def __repr__(self):
        return f"<Coupon {self.code}>"
