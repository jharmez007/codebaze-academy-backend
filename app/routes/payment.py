# import os
# import requests
# from flask import Blueprint, request, jsonify
# from flask_jwt_extended import jwt_required, get_jwt_identity
# from app.models import Enrollment, User
# from app.extensions import db

# bp = Blueprint("payments", __name__)

# PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
# PAYSTACK_BASE_URL = "https://api.paystack.co"


# @bp.route("/initiate", methods=["POST"])
# @jwt_required()
# def initiate_payment():
#     """Initialize a Paystack transaction"""
#     data = request.get_json()
#     email = data.get("email")
#     amount = data.get("amount")  # Naira
#     course_id = data.get("course_id")

#     if not all([email, amount, course_id]):
#         return jsonify({"error": "Missing fields"}), 400

#     headers = {
#         "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
#         "Content-Type": "application/json",
#     }

#     payload = {
#         "email": email,
#         "amount": int(amount) * 100,  # Convert to kobo
#         "callback_url": "http://localhost:5000/payments/verify",  # Update for production
#     }

#     response = requests.post(
#         f"{PAYSTACK_BASE_URL}/transaction/initialize",
#         json=payload,
#         headers=headers
#     )

#     resp_data = response.json()

#     if response.status_code != 200 or not resp_data.get("status"):
#         return jsonify({
#             "error": "Failed to initialize payment",
#             "details": resp_data
#         }), 400

#     # Optional: store reference for tracking
#     reference = resp_data["data"]["reference"]
#     enrollment = Enrollment.query.filter_by(user_id=get_jwt_identity(), course_id=course_id).first()
#     if enrollment:
#         enrollment.payment_reference = reference
#         db.session.commit()

#     return jsonify({
#         "message": "Payment initialized successfully",
#         "authorization_url": resp_data["data"]["authorization_url"],
#         "reference": reference
#     }), 200


# @bp.route("/verify", methods=["GET"])
# def verify_payment():
#     """Verify payment with Paystack"""
#     reference = request.args.get("reference")
#     if not reference:
#         return jsonify({"error": "No reference provided"}), 400

#     headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
#     response = requests.get(
#         f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
#         headers=headers
#     )

#     result = response.json()
#     if response.status_code != 200 or not result.get("status"):
#         return jsonify({
#             "error": "Failed to verify payment",
#             "details": result
#         }), 400

#     data = result["data"]
#     status = data.get("status")

#     if status == "success":
#         enrollment = Enrollment.query.filter_by(payment_reference=reference).first()
#         if enrollment:
#             enrollment.status = "paid"
#             db.session.commit()

#         return jsonify({
#             "message": "✅ Payment verified successfully",
#             "data": data
#         }), 200

#     return jsonify({
#         "message": "Payment not successful",
#         "data": data
#     }), 400
import os
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models import Enrollment, Payment, User, Course

bp = Blueprint("payments", __name__)

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE_URL = "https://api.paystack.co"


# ----------------------------------------------------------
# 1️⃣ INITIATE PAYMENT
# ----------------------------------------------------------
@bp.route("/initiate", methods=["POST"])
@jwt_required()
def initiate_payment():
    """Initialize a Paystack transaction."""
    data = request.get_json()
    email = data.get("email")
    amount = data.get("amount")  # Naira
    course_id = data.get("course_id")

    user_id = get_jwt_identity()

    if not all([email, amount, course_id]):
        return jsonify({"error": "Missing fields"}), 400

    # ✅ Check if course exists
    course = Course.query.get(course_id)
    if not course:
        return jsonify({"error": "Invalid course"}), 404

    # ✅ Check if user already enrolled or paid
    existing_enrollment = Enrollment.query.filter_by(
        user_id=user_id, course_id=course_id
    ).first()
    if existing_enrollment and existing_enrollment.status == "paid":
        return jsonify({"error": "You have already paid for this course"}), 409

    # ✅ Initialize Paystack transaction
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "email": email,
        "amount": int(amount) * 100,  # convert to kobo
        "callback_url": "http://localhost:5000/payments/callback",
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
        course_id=course_id,
        amount=amount,
        reference=reference,
        status="pending",
    )
    db.session.add(payment)

    # ✅ Save reference to enrollment (if exists) or create new
    if existing_enrollment:
        existing_enrollment.payment_reference = reference
    else:
        new_enrollment = Enrollment(
            user_id=user_id,
            course_id=course_id,
            status="pending",
            payment_reference=reference,
        )
        db.session.add(new_enrollment)

    db.session.commit()

    return jsonify({
        "message": "Payment initialized successfully",
        "authorization_url": resp_data["data"]["authorization_url"],
        "reference": reference,
    }), 200


# ----------------------------------------------------------
# 2️⃣ VERIFY PAYMENT
# ----------------------------------------------------------
@bp.route("/verify", methods=["GET"])
def verify_payment():
    """Verify payment with Paystack"""
    reference = request.args.get("reference")
    if not reference:
        return jsonify({"error": "No reference provided"}), 400

    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(
        f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
        headers=headers,
    )

    result = response.json()
    if response.status_code != 200 or not result.get("status"):
        return jsonify({
            "error": "Failed to verify payment",
            "details": result,
        }), 400

    data = result["data"]
    status = data.get("status")

    payment = Payment.query.filter_by(reference=reference).first()
    enrollment = Enrollment.query.filter_by(payment_reference=reference).first()

    if status == "success":
        # ✅ Mark payment as successful
        if payment:
            payment.status = "success"

        # ✅ Update enrollment
        if enrollment:
            enrollment.status = "paid"
            enrollment.enrolled_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            "message": "✅ Payment verified successfully",
            "data": data
        }), 200

    elif status == "failed":
        if payment:
            payment.status = "failed"
        if enrollment:
            enrollment.status = "failed"
        db.session.commit()

        return jsonify({
            "message": "❌ Payment failed",
            "data": data
        }), 400

    return jsonify({
        "message": "Payment not completed yet",
        "data": data
    }), 400


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
