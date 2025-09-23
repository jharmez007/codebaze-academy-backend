import os
import requests
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app.models import Enrollment
from app.extensions import db

bp = Blueprint("payments", __name__)

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE_URL = "https://api.paystack.co"

@bp.route("/initiate", methods=["POST"])
@jwt_required()
def initiate_payment():
    data = request.get_json()
    email = data.get("email")
    amount = data.get("amount")  # in Naira (convert to kobo)
    course_id = data.get("course_id")

    if not all([email, amount, course_id]):
        return jsonify({"error": "Missing fields"}), 400

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "email": email,
        "amount": int(amount) * 100,  # convert to kobo
        "callback_url": "http://localhost:5000/payments/verify"  # change to prod
    }

    response = requests.post(
        f"{PAYSTACK_BASE_URL}/transaction/initialize",
        json=payload,
        headers=headers
    )

    if response.status_code != 200:
        return jsonify({"error": "Failed to initialize payment"}), 400

    resp_data = response.json()
    return jsonify(resp_data)


@bp.route("/verify", methods=["GET"])
def verify_payment():
    reference = request.args.get("reference")
    if not reference:
        return jsonify({"error": "No reference provided"}), 400

    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(
        f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
        headers=headers
    )

    if response.status_code != 200:
        return jsonify({"error": "Failed to verify payment"}), 400

    result = response.json()
    status = result["data"]["status"]

    if status == "success":
        # Example: mark user enrollment as paid
        # You can fetch enrollment by reference or course_id
        # enrollment = Enrollment.query.filter_by(reference=reference).first()
        # enrollment.status = "paid"
        # db.session.commit()
        return jsonify({"message": "Payment successful", "data": result["data"]})

    return jsonify({"message": "Payment not successful", "data": result["data"]})