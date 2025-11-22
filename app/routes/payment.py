import os
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models import Enrollment, User, Course
from app.models.coupon import Coupon
from app.models.user import Payment
from app.helpers.currency import detect_currency, convert_ngn_to_usd, get_client_ip

bp = Blueprint("payments", __name__)

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE_URL = "https://api.paystack.co"
    
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

    # Required field validation
    if not all([email, amount, course_id]):
        return jsonify({"error": "Missing fields"}), 400

    # Check if course exists
    course = Course.query.get(course_id)
    if not course:
        return jsonify({"error": "Invalid course"}), 404

    
    # Check if user already paid successfully
    existing_success = Payment.query.filter_by(
        user_id=user_id, course_id=course_id, status="successful"
    ).first()

    if existing_success:
        return jsonify({"error": "You have already paid for this course"}), 409

    # Coupon handling
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

    # Check if enrollment exists
    existing_enrollment = Enrollment.query.filter_by(
        user_id=user_id, course_id=course_id
    ).first()

    # Initialize Paystack transaction
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    slug = course.title.lower().replace(" ", "-")
    currency = detect_currency()
    final_amount = amount

    if currency == "USD":
        final_amount = convert_ngn_to_usd(amount)
    payload = {
        "email": email,
        "amount": int(final_amount * 100),  # convert to kobo correctly
        "currency": currency,
        "callback_url": "http://localhost:5000/payments/verify",
        "metadata": {
            "slug": slug,
            "course_id": course.id,
            "coupon_code": coupon_code if coupon_code else None,
            "currency_used": currency,
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

    # Save a Payment record (pending)
    payment = Payment(
        user_id=user_id,
        provider="paystack",
        course_id=course_id,
        amount=final_amount,
        currency=currency,
        reference=reference,
        status="pending",
        coupon_code=coupon_code if coupon_code else None,
    )
    db.session.add(payment)

    # Save or update enrollment
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

    print("SENT CURRENCY:", currency)
    print("PAYSTACK RESPONSE:", resp_data)
    return jsonify({
        "message": "Payment initialized successfully",
        "authorization_url": resp_data["data"]["authorization_url"],
        "reference": reference,
        "discount_applied": discount_amount,
        "detected_currency": currency,
        "client_ip": get_client_ip(),
        "final_amount": final_amount
    }), 200



@bp.route("/verify", methods=["GET"])
def verify_payment():
    reference = request.args.get("reference") or request.args.get("trxref")
    if not reference:
        return jsonify({"error": "Missing reference"}), 400

    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}

    try:
        response = requests.get(
            f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
            headers=headers,
            timeout=10
        )
    except requests.exceptions.RequestException:
        return jsonify({"error": "Could not reach Paystack. Try again."}), 502

    if response.status_code != 200:
        return jsonify({"error": "Paystack verification failed", "details": response.text}), 400

    data = response.json()
    if not data.get("status"):
        return jsonify({"error": "Invalid Paystack response"}), 400

    trx_data = data["data"]
    pay_status = trx_data["status"]
    is_successful = pay_status == "success"
    amount = trx_data.get("amount", 0) / 100
    metadata = trx_data.get("metadata", {}) or {}

    course_id = metadata.get("course_id")
    redirect_url = metadata.get("redirect_url", "http://localhost:3000")

    # Lookup payment
    payment = Payment.query.filter_by(reference=reference).first()
    if not payment:
        return jsonify({"error": "Payment not found"}), 404

    # Prevent double processing
    if payment.status == "successful":
        return redirect(f"{redirect_url}?payment_status=success&reference={reference}")

    if is_successful:
        payment.status = "successful"
        payment.amount = amount

        # Update enrollment
        enrollment = Enrollment.query.filter_by(
            user_id=payment.user_id, course_id=payment.course_id
        ).first()
        if enrollment:
            enrollment.status = "paid"
        else:
            db.session.add(Enrollment(
                user_id=payment.user_id,
                course_id=payment.course_id,
                status="paid",
                payment_reference=reference,
            ))

        # Increment coupon (only after success)
        if payment.coupon_code:
            coupon = Coupon.query.filter_by(code=payment.coupon_code).first()
            if coupon:
                coupon.used_count = (coupon.used_count or 0) + 1

        db.session.commit()
        return redirect(f"{redirect_url}?payment_status=success&reference={reference}")

    elif pay_status == "failed":
        payment.status = "failed"
        db.session.commit()
        return redirect(f"{redirect_url}?payment_status=failed&reference={reference}")

    else:
        # Still pending
        payment.status = "pending"
        db.session.commit()
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
