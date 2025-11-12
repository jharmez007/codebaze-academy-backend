import os
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models import Enrollment, User, Course
from app.models.coupon import Coupon
from app.models.user import Payment

bp = Blueprint("payments", __name__)

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE_URL = "https://api.paystack.co"


# ----------------------------------------------------------
# 1️⃣ INITIATE PAYMENT
# ----------------------------------------------------------
# @bp.route("/initiate", methods=["POST"])
# @jwt_required()
# def initiate_payment():
#     """Initialize a Paystack transaction."""
#     data = request.get_json()
#     email = data.get("email")
#     amount = data.get("amount")  # Naira
#     course_id = data.get("course_id")

#     user_id = get_jwt_identity()

#     if not all([email, amount, course_id]):
#         return jsonify({"error": "Missing fields"}), 400

#     # ✅ Check if course exists
#     course = Course.query.get(course_id)
#     if not course:
#         return jsonify({"error": "Invalid course"}), 404

#     # ✅ Check if user already enrolled or paid
#     existing_success = Payment.query.filter_by(
#         user_id=user_id, course_id=course_id, status="successful"
#     ).first()

#     coupon_code = data.get("coupon_code")
#     discount_amount = 0

#     if coupon_code:
#         coupon = Coupon.query.filter_by(code=coupon_code.upper(), is_active=True).first()
#         if coupon:
#             # same validation logic as above
#             if coupon.discount_type == "percent":
#                 discount_amount = (coupon.discount_value / 100) * amount
#             else:
#                 discount_amount = coupon.discount_value

#             amount = max(amount - discount_amount, 0)
#     if existing_success:
#         return jsonify({"error": "You have already paid for this course"}), 409

#     existing_enrollment = Enrollment.query.filter_by(
#         user_id=user_id, course_id=course_id
#     ).first()
#     # ✅ Initialize Paystack transaction
#     headers = {
#         "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
#         "Content-Type": "application/json",
#     }
#     slug = course.title.lower().replace(" ", "-")
#     payload = {
#         "email": email,
#         "amount": int(amount) * 100,  # convert to kobo
#         "callback_url": "http://localhost:5000/payments/verify",
#         "metadata": {
#             "slug": slug,
#             "course_id": course.id,
#             "redirect_url": f"http://localhost:3000/checkout/{slug}"  # frontend route
#         }
#     }

#     response = requests.post(
#         f"{PAYSTACK_BASE_URL}/transaction/initialize",
#         json=payload,
#         headers=headers,
#     )

#     resp_data = response.json()

#     if response.status_code != 200 or not resp_data.get("status"):
#         return jsonify({
#             "error": "Failed to initialize payment",
#             "details": resp_data,
#         }), 400

#     reference = resp_data["data"]["reference"]

#     # ✅ Save a Payment record (pending)
#     payment = Payment(
#         user_id=user_id,
#         provider="paystack", 
#         course_id=course_id,
#         amount=amount,
#         reference=reference,
#         status="pending",
#     )
#     db.session.add(payment)

#     # ✅ Save reference to enrollment (if exists) or create new
#     if existing_enrollment:
#         existing_enrollment.payment_reference = reference
#     else:
#         new_enrollment = Enrollment(
#             user_id=user_id,
#             course_id=course_id,
#             status="pending",
#             payment_reference=reference,
#         )
#         db.session.add(new_enrollment)

#     db.session.commit()

#     return jsonify({
#         "message": "Payment initialized successfully",
#         "authorization_url": resp_data["data"]["authorization_url"],
#         "reference": reference,
#     }), 200

@bp.route("/initiate", methods=["POST"])
@jwt_required()
def initiate_payment():
    """Initialize a Paystack transaction."""
    data = request.get_json()
    email = data.get("email")
    amount = float(data.get("amount", 0))  # ensure it's numeric
    course_id = data.get("course_id")
    coupon_code = data.get("coupon_code", "").strip().upper()

    user_id = get_jwt_identity()

    # ✅ Required field validation
    if not all([email, amount, course_id]):
        return jsonify({"error": "Missing fields"}), 400

    # ✅ Check if course exists
    course = Course.query.get(course_id)
    if not course:
        return jsonify({"error": "Invalid course"}), 404

    # ✅ Check if user already paid successfully
    existing_success = Payment.query.filter_by(
        user_id=user_id, course_id=course_id, status="successful"
    ).first()

    if existing_success:
        return jsonify({"error": "You have already paid for this course"}), 409

    # ✅ Coupon handling
    discount_amount = 0
    if coupon_code:
        coupon = Coupon.query.filter_by(code=coupon_code, is_active=True).first()

        if not coupon:
            return jsonify({"error": "Invalid coupon"}), 404

        now = datetime.utcnow()

        # Time validity
        if coupon.valid_until and now > coupon.valid_until:
            return jsonify({"error": "Coupon expired"}), 400

        # User-specific restriction
        if coupon.type == "user_specific" and coupon.user_id != user_id:
            return jsonify({"error": "This coupon is not assigned to you"}), 403

        # Course-specific restriction (FIXED)
        if not coupon.applies_to_all:
            valid_course_ids = [course.id for course in coupon.courses]
            if course_id not in valid_course_ids:
                return jsonify({"error": "This coupon is not valid for this course"}), 400

        # Usage limit
        if coupon.max_uses and coupon.used_count >= coupon.max_uses:
            return jsonify({"error": "Coupon usage limit reached"}), 400

        # Discount calculation
        if coupon.discount_type == "percent":
            discount_amount = (coupon.discount_value / 100) * amount
        else:
            discount_amount = min(coupon.discount_value, amount)

        amount = max(amount - discount_amount, 0)
        # coupon.used_count = (coupon.used_count or 0) + 1

    # ✅ Check if enrollment exists
    existing_enrollment = Enrollment.query.filter_by(
        user_id=user_id, course_id=course_id
    ).first()

    # ✅ Initialize Paystack transaction
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    slug = course.title.lower().replace(" ", "-")
    payload = {
        "email": email,
        "amount": int(amount * 100),  # convert to kobo correctly
        "callback_url": "http://localhost:5000/payments/verify",
        "metadata": {
            "slug": slug,
            "course_id": course.id,
            "coupon_code": coupon_code if coupon_code else None,
            "discount_amount": discount_amount,
            "redirect_url": f"http://localhost:3000/checkout/{slug}"
        }
    }

    response = requests.post(
        f"{PAYSTACK_BASE_URL}/transaction/initialize",
        json=payload,
        headers=headers,
    )

    resp_data = response.json()

    if response.status_code != 200 or not resp_data.get("status"):
        return jsonify({
            "error": "Failed to initialize payment",
            "details": resp_data,
        }), 400

    reference = resp_data["data"]["reference"]

    # ✅ Save a Payment record (pending)
    payment = Payment(
        user_id=user_id,
        provider="paystack",
        course_id=course_id,
        amount=amount,
        reference=reference,
        status="pending",
        coupon_code=coupon_code if coupon_code else None,
    )
    db.session.add(payment)

    # ✅ Save or update enrollment
    if existing_enrollment:
        existing_enrollment.payment_reference = reference
    else:
        db.session.add(Enrollment(
            user_id=user_id,
            course_id=course_id,
            status="pending",
            payment_reference=reference,
        ))

    db.session.commit()

    return jsonify({
        "message": "Payment initialized successfully",
        "authorization_url": resp_data["data"]["authorization_url"],
        "reference": reference,
        "discount_applied": discount_amount,
    }), 200



@bp.route("/verify", methods=["GET"])
def verify_payment():
    reference = request.args.get("reference")
    if not reference:
        return jsonify({"error": "Missing payment reference"}), 400

    payment = Payment.query.filter_by(reference=reference).first()
    if not payment:
        return jsonify({"error": "Payment not found"}), 404

    # If already successful, return early — allows retry without side effects
    if payment.status == "successful":
        return jsonify({"message": "Payment already verified"}), 200

    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}

    try:
        response = requests.get(
            f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
            headers=headers,
            timeout=10
        )
        data = response.json()
    except requests.exceptions.RequestException:
        # Don’t fail verification permanently — let client retry
        return jsonify({"error": "Could not reach Paystack. Try again."}), 502

    if not data.get("status"):
        return jsonify({"error": "Invalid Paystack response"}), 400

    pay_data = data["data"]

    if pay_data["status"] == "success":
        # ✅ Mark payment successful
        payment.status = "successful"
        db.session.commit()

        # ✅ Update enrollment
        enrollment = Enrollment.query.filter_by(
            user_id=payment.user_id, course_id=payment.course_id
        ).first()

        if enrollment:
            enrollment.status = "active"
        else:
            db.session.add(
                Enrollment(
                    user_id=payment.user_id,
                    course_id=payment.course_id,
                    status="active",
                    payment_reference=reference,
                )
            )

        # ✅ Coupon increment (only now)
        if payment.coupon_code:
            coupon = Coupon.query.filter_by(code=payment.coupon_code).first()
            if coupon:
                coupon.used_count = (coupon.used_count or 0) + 1

        db.session.commit()
        return jsonify({"message": "Payment verified successfully"}), 200

    elif pay_data["status"] == "failed":
        payment.status = "failed"
        db.session.commit()
        return jsonify({"error": "Payment failed"}), 400

    else:
        # Still pending on Paystack side
        return jsonify({"message": "Payment still pending, please retry"}), 202

# ----------------------------------------------------------
# 3️⃣ CALLBACK ENDPOINT (Paystack calls this URL)
# ----------------------------------------------------------
@bp.route("/callback", methods=["GET"])
def paystack_callback():
    """Handle Paystack redirect after payment"""
    reference = request.args.get("reference")
    if not reference:
        return jsonify({"error": "Invalid callback"}), 400

    # redirect to verify route
    verify_url = url_for("payments.verify_payment", reference=reference, _external=True)
    return redirect(verify_url)
