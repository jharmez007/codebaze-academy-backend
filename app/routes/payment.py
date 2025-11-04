import os
import requests
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import Enrollment, User
from app.extensions import db

bp = Blueprint("payments", __name__)

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE_URL = "https://api.paystack.co"


@bp.route("/initiate", methods=["POST"])
@jwt_required()
def initiate_payment():
    """Initialize a Paystack transaction"""
    data = request.get_json()
    email = data.get("email")
    amount = data.get("amount")  # Naira
    course_id = data.get("course_id")

    if not all([email, amount, course_id]):
        return jsonify({"error": "Missing fields"}), 400

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "email": email,
        "amount": int(amount) * 100,  # Convert to kobo
        "callback_url": "http://localhost:5000/payments/verify",  # Update for production
    }

    response = requests.post(
        f"{PAYSTACK_BASE_URL}/transaction/initialize",
        json=payload,
        headers=headers
    )

    resp_data = response.json()

    if response.status_code != 200 or not resp_data.get("status"):
        return jsonify({
            "error": "Failed to initialize payment",
            "details": resp_data
        }), 400

    # Optional: store reference for tracking
    reference = resp_data["data"]["reference"]
    enrollment = Enrollment.query.filter_by(user_id=get_jwt_identity(), course_id=course_id).first()
    if enrollment:
        enrollment.payment_reference = reference
        db.session.commit()

    return jsonify({
        "message": "Payment initialized successfully",
        "authorization_url": resp_data["data"]["authorization_url"],
        "reference": reference
    }), 200


@bp.route("/verify", methods=["GET"])
def verify_payment():
    """Verify payment with Paystack"""
    reference = request.args.get("reference")
    if not reference:
        return jsonify({"error": "No reference provided"}), 400

    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(
        f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
        headers=headers
    )

    result = response.json()
    if response.status_code != 200 or not result.get("status"):
        return jsonify({
            "error": "Failed to verify payment",
            "details": result
        }), 400

    data = result["data"]
    status = data.get("status")

    if status == "success":
        enrollment = Enrollment.query.filter_by(payment_reference=reference).first()
        if enrollment:
            enrollment.status = "paid"
            db.session.commit()

        return jsonify({
            "message": "✅ Payment verified successfully",
            "data": data
        }), 200

    return jsonify({
        "message": "Payment not successful",
        "data": data
    }), 400
