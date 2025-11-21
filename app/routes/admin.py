from flask import Blueprint, jsonify, request
import requests
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.user import ExchangeRate
from app.models import User, Course, Enrollment
from app.models.coupon import Coupon
from app.models.user import Payment
from sqlalchemy import func, extract
from datetime import datetime
from app.extensions import db
from app.helpers.currency import get_client_ip, get_country_from_ip, detect_currency    

bp = Blueprint("admin", __name__)

@bp.route("/overview", methods=["GET"])
@jwt_required()
def analytics_overview():
    """Return analytics summary for admin dashboard"""

    # === Basic Stats ===
    total_students = User.query.filter_by(role="student").count()
    total_courses = Course.query.count()
    total_promotions = Coupon.query.count()

    total_revenue = (
        db.session.query(func.sum(Payment.amount))
        .filter_by(status="successful")
        .scalar()
    ) or 0

    # === Monthly Revenue ===
    monthly = (
        db.session.query(
            extract("month", Payment.created_at).label("month"),
            func.sum(Payment.amount).label("revenue")
        )
        .filter(Payment.status == "successful")
        .group_by("month")
        .all()
    )

    monthly_revenue = [
        {"month": datetime(2025, int(m), 1).strftime("%b"), "revenue": float(r)}
        for m, r in monthly
    ]

    # === Revenue by Course ===
    revenue_by_course = (
        db.session.query(
            Course.title.label("course"),
            func.sum(Payment.amount).label("revenue")
        )
        .join(Payment, Payment.course_id == Course.id)
        .filter(Payment.status == "successful")
        .group_by(Course.id)
        .all()
    )

    revenue_by_course_data = [
        {"course": c, "revenue": float(r)} for c, r in revenue_by_course
    ]

    # === Enrollment Count by Course ===
    enrollments = (
        db.session.query(
            Course.title.label("course"),
            func.count(Enrollment.id).label("count")
        )
        .join(Enrollment, Enrollment.course_id == Course.id)
        .group_by(Course.id)
        .all()
    )

    enrollments_data = {
        "labels": [c for c, _ in enrollments],
        "datasets": [{"label": "Enrollments", "data": [int(cnt) for _, cnt in enrollments]}],
    }

    # === Recent Activity ===
    recent = (
        db.session.query(User.full_name, Course.title, Enrollment.enrolled_at)
        .join(Enrollment, Enrollment.user_id == User.id)
        .join(Course, Course.id == Enrollment.course_id)
        .order_by(Enrollment.enrolled_at.desc())
        .limit(3)
        .all()
    )

    recent_activity = [
        {
            "text": f"{name} enrolled in {course}",
            "date": f"{(datetime.utcnow() - e).seconds // 3600}h ago" if e else "recently",
        }
        for name, course, e in recent
    ]

    return jsonify({
        "statsData": [
            {"label": "Students", "value": total_students, "icon": "Users"},
            {"label": "Courses", "value": total_courses, "icon": "BookOpen"},
            {"label": "Revenue", "value": total_revenue, "icon": "DollarSign"},
            {"label": "Promotions", "value": total_promotions, "icon": "Tag"},
        ],
        "monthlyRevenue": monthly_revenue,
        "revenueByCourse": revenue_by_course_data,
        "enrollmentsData": enrollments_data,
        "recentActivity": recent_activity,
    }), 200

@bp.route("/exchange-rate", methods=["GET"])
@jwt_required()
def get_exchange_rate():
    user = User.query.get(get_jwt_identity())
    if user.role != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    rate = ExchangeRate.query.first()

    # FIX: Auto-create default if missing
    if not rate:
        rate = ExchangeRate(ngn_to_usd=1500)
        db.session.add(rate)
        db.session.commit()

    return jsonify({
        "ngn_to_usd": rate.ngn_to_usd,
        "updated_at": rate.updated_at.isoformat()
    })

@bp.route("/exchange-rate", methods=["POST"])
@jwt_required()
def update_exchange_rate():
    user = User.query.get(get_jwt_identity())
    if user.role != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    new_rate = data.get("ngn_to_usd")

    if not new_rate:
        return jsonify({"error": "Missing 'ngn_to_usd'"}), 400

    rate = ExchangeRate.query.first()

    # If rate does not exist, create it
    if not rate:
        rate = ExchangeRate(ngn_to_usd=float(new_rate))
        db.session.add(rate)
    else:
        rate.ngn_to_usd = float(new_rate)
        rate.updated_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        "message": "Rate updated successfully",
        "ngn_to_usd": rate.ngn_to_usd
    }), 200

@bp.route("/debug/currency")
# def debug_currency():
#     ip = get_client_ip()
#     country, currency = get_country_from_ip(ip)
#     detected = detect_currency()

#     return {
#         "client_ip": ip,
#         "country": country,
#         "api_currency": currency,
#         "final_detected_currency": detected
#     }
def debug_currency():
    ip = get_client_ip()

    # FULL RESPONSE FOR DEBUGGING
    api_response = requests.get(f"https://ipwho.is/{ip}").json()

    country, currency = get_country_from_ip(ip)
    detected = detect_currency()

    return {
        "client_ip": ip,
        "api_raw": api_response,   # <-- add this
        "country": country,
        "api_currency": currency,
        "final_detected_currency": detected
    }