from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth import role_required
from datetime import datetime
from app.extensions import db
from app.models.coupon import Coupon
from app.models.course import Course

bp = Blueprint("coupon", __name__)

# @bp.route("/coupons", methods=["POST"])
# @jwt_required()
# @role_required("admin")
# def create_coupon():
#     data = request.get_json()

#     code = data.get("code")
#     coupon_type = data.get("type", "general")
#     discount_type = data.get("discount_type", "percent")
#     discount_value = data.get("discount_value")
#     user_id = data.get("user_id")
#     max_uses = data.get("max_uses")
#     valid_until = data.get("valid_until")
#     commission = data.get("commission")
#     course_ids = data.get("course_ids", [])  # ✅ list of course IDs
#     applies_to_all = data.get("applies_to_all", False)  # ✅ flag for all courses

#     if not all([code, discount_type, discount_value]):
#         return jsonify({"error": "Missing required fields"}), 400

#     if Coupon.query.filter_by(code=code.upper()).first():
#         return jsonify({"error": "Coupon code already exists"}), 409

#     coupon = Coupon(
#         code=code.upper(),
#         type=coupon_type,
#         discount_type=discount_type,
#         discount_value=discount_value,
#         user_id=user_id,
#         max_uses=max_uses,
#         valid_until=datetime.fromisoformat(valid_until) if valid_until else None,
#         commission=commission,
#         applies_to_all=applies_to_all,  # ✅ store whether it applies to all
#     )

#     # ✅ If specific courses were provided, attach them
#     if not applies_to_all and course_ids:
#         courses = Course.query.filter(Course.id.in_(course_ids)).all()
#         if not courses:
#             return jsonify({"error": "No valid courses found for provided IDs"}), 400
#         coupon.courses = courses  # many-to-many relationship
#     elif applies_to_all:
#         coupon.courses = []  # can be left empty if all courses are valid

#     db.session.add(coupon)
#     db.session.commit()

#     return jsonify({
#         "message": "Coupon created successfully",
#         "coupon": {
#             "id": coupon.id,
#             "code": coupon.code,
#             "type": coupon.type,
#             "discount": f"{coupon.discount_value} ({coupon.discount_type})",
#             "expires": coupon.valid_until.isoformat() if coupon.valid_until else None,
#             "applies_to_all": coupon.applies_to_all,
#             "attached_courses": [c.title for c in coupon.courses] if coupon.courses else "All courses"
#         }
#     }), 201

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
    course_ids = data.get("course_ids", [])
    applies_to_all = data.get("applies_to_all", False)

    if not all([code, discount_type, discount_value]):
        return jsonify({"error": "Missing required fields"}), 400

    if Coupon.query.filter_by(code=code.upper()).first():
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
        applies_to_all=applies_to_all
    )

    # ✅ Attach courses only if not applying to all
    if not applies_to_all and course_ids:
        courses = Course.query.filter(Course.id.in_(course_ids)).all()
        if not courses:
            return jsonify({"error": "No valid courses found for provided IDs"}), 400
        coupon.courses = courses
    elif applies_to_all:
        coupon.courses = []  # empty since it applies globally

    db.session.add(coupon)
    db.session.commit()

    return jsonify({
        "message": "Coupon created successfully",
        "coupon": {
            "id": coupon.id,
            "code": coupon.code,
            "type": coupon.type,
            "discount": f"{coupon.discount_value} ({coupon.discount_type})",
            "applies_to_all": coupon.applies_to_all,
            "expires": coupon.valid_until.isoformat() if coupon.valid_until else None,
            "attached_courses": [c.title for c in coupon.courses] if coupon.courses else "All courses"
        }
    }), 201

# ---------------- VALIDATE ----------------
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

    now = datetime.utcnow()
    if coupon.valid_until and now > coupon.valid_until:
        return jsonify({"error": "Coupon expired"}), 400

    if coupon.type == "user_specific" and coupon.user_id != user_id:
        return jsonify({"error": "This coupon is not assigned to you"}), 403

    if coupon.max_uses and coupon.used_count >= coupon.max_uses:
        return jsonify({"error": "Coupon usage limit reached"}), 400

    course = Course.query.get(course_id)
    if not course:
        return jsonify({"error": "Invalid course"}), 404
    if not coupon.applies_to_all and course not in coupon.courses:
        return jsonify({"error": "Coupon not applicable to this course"}), 400

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


@bp.route("/coupons", methods=["GET"])
@jwt_required()
@role_required("admin")
def list_coupons():
    coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()
    result = []

    for c in coupons:
        if c.applies_to_all:
            course_info = "applies to all courses"
        else:
            course_info = ", ".join(course.title for course in c.courses)
        result.append({
            "id": c.id,
            "code": c.code,
            "type": c.type,
            "discount_type": c.discount_type,
            "discount_value": c.discount_value,
            "max_uses": c.max_uses,
            "used_count": c.used_count,
            "is_active": c.is_active,
            "course": course_info,
            "applies_to_all": c.applies_to_all,
            "valid_until": c.valid_until.isoformat() if c.valid_until else None,
            "created_at": c.created_at.isoformat() if c.created_at else None
        })
    return jsonify(result), 200



# ---------------- GET DETAILS ----------------
@bp.route("/coupons/<int:coupon_id>", methods=["GET"])
@jwt_required()
@role_required("admin")
def get_coupon(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    return jsonify({
        "id": coupon.id,
        "code": coupon.code,
        "type": coupon.type,
        "discount_type": coupon.discount_type,
        "discount_value": coupon.discount_value,
        "max_uses": coupon.max_uses,
        "used_count": coupon.used_count,
        "is_active": coupon.is_active,
        "valid_until": coupon.valid_until.isoformat() if coupon.valid_until else None,
        "commission": coupon.commission
    }), 200


# ---------------- UPDATE ----------------
@bp.route("/coupons/<int:coupon_id>", methods=["PATCH"])
@jwt_required()
@role_required("admin")
def update_coupon(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    data = request.get_json() or {}

    for field in ["type", "discount_type", "discount_value", "max_uses", "commission", "is_active"]:
        if field in data:
            setattr(coupon, field, data[field])

    if "valid_until" in data:
        coupon.valid_until = datetime.fromisoformat(data["valid_until"]) if data["valid_until"] else None

    db.session.commit()

    return jsonify({"message": "Coupon updated successfully"}), 200


# ---------------- DELETE -------------
@bp.route("/coupons/<int:coupon_id>", methods=["DELETE"])
@jwt_required()
@role_required("admin")
def delete_coupon(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    db.session.delete(coupon)
    db.session.commit()
    return jsonify({"message": "Coupon deleted successfully"}), 200
