from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth import role_required
from datetime import datetime
from app.extensions import db
from app.models.coupon import Coupon
from app.models.course import Course

bp = Blueprint("coupon", __name__)

@bp.route("/coupons", methods=["POST"])
@jwt_required()
@role_required("admin")
def create_coupon():
    data = request.get_json()

    code = data.get("code")
    coupon_type = data.get("type", "general")
    discount_type = data.get("discount_type", "percent")
    discount_value = data.get("discount_value")
    user_id = data.get("user_id")
    max_uses = data.get("max_uses")
    valid_until = data.get("valid_until")
    commission = data.get("commission")

    if not all([code, discount_type, discount_value]):
        return jsonify({"error": "Missing required fields"}), 400

    if Coupon.query.filter_by(code=code).first():
        return jsonify({"error": "Coupon code already exists"}), 409

    coupon = Coupon(
        code=code.upper(),
        type=coupon_type,
        discount_type=discount_type,
        discount_value=discount_value,
        user_id=user_id,
        max_uses=max_uses,
        valid_until=datetime.fromisoformat(valid_until) if valid_until else None,
        commission=commission,
    )

    db.session.add(coupon)
    db.session.commit()

    return jsonify({"message": "Coupon created successfully", "coupon": {
        "code": coupon.code,
        "type": coupon.type,
        "discount": f"{coupon.discount_value} ({coupon.discount_type})",
        "expires": coupon.valid_until.isoformat() if coupon.valid_until else None
    }}), 201

@bp.route("/coupons/validate", methods=["POST"])
@jwt_required()
def validate_coupon():
    data = request.get_json()
    code = data.get("code", "").strip().upper()
    course_id = data.get("course_id")
    user_id = get_jwt_identity()

    coupon = Coupon.query.filter_by(code=code, is_active=True).first()

    if not coupon:
        return jsonify({"error": "Invalid or inactive coupon"}), 404

    # ✅ Check time validity
    now = datetime.utcnow()
    if coupon.valid_until and now > coupon.valid_until:
        return jsonify({"error": "Coupon expired"}), 400

    # ✅ Check user-specific
    if coupon.type == "user_specific" and coupon.user_id != user_id:
        return jsonify({"error": "This coupon is not assigned to you"}), 403

    # ✅ Check usage limit
    if coupon.max_uses and coupon.used_count >= coupon.max_uses:
        return jsonify({"error": "Coupon usage limit reached"}), 400

    # ✅ Calculate discount
    course = Course.query.get(course_id)
    if not course:
        return jsonify({"error": "Invalid course"}), 404

    original_price = course.price
    if coupon.discount_type == "percent":
        discount_amount = (coupon.discount_value / 100) * original_price
    else:
        discount_amount = min(coupon.discount_value, original_price)

    final_price = max(original_price - discount_amount, 0)

    return jsonify({
        "message": "Coupon applied successfully",
        "original_price": original_price,
        "discount": discount_amount,
        "final_price": final_price,
        "coupon_type": coupon.type,
        "code": coupon.code
    }), 200
