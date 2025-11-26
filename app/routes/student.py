from flask import Blueprint, jsonify, request, send_file, current_app, render_template, url_for
import uuid
import io
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.user import UserSession, Payment
from app.extensions import db
from app.models import User, Enrollment, Course, Progress
from app.utils.auth import role_required
import os
import json
from werkzeug.utils import secure_filename
# from reportlab.pdfgen import canvas
# from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
# from reportlab.lib.pagesizes import LETTER
# from reportlab.lib.styles import getSampleStyleSheet
# from reportlab.lib.units import inch
# from reportlab.lib import colors
# import io
from weasyprint import HTML
from datetime import datetime

bp = Blueprint("students", __name__)
UPLOAD_FOLDER = os.path.join("static", "uploads", "profile_photos")


@bp.route("/", methods=["GET"])
@jwt_required()
@role_required("admin")
def get_all_students():
    students = User.query.filter_by(role="student").all()
    result = []

    for s in students:
        # Collect course titles for this student
        course_titles = [enrollment.course.title for enrollment in s.enrollments if enrollment.course]

        result.append({
            "id": s.id,
            "name": s.full_name,  # Assuming your User model has a full_name property
            "email": s.email,
            "is_active": s.is_active,
            "date_joined": s.created_at,
            "courses_enrolled": len(course_titles),
            "course_titles": course_titles 
        })

    return jsonify({
        "total_students": len(result),
        "students": result
    }), 200



@bp.route("/courses/<int:course_id>/students", methods=["GET"])
@jwt_required()
@role_required("admin")
def get_students_by_course(course_id):
    enrollments = Enrollment.query.filter_by(course_id=course_id).all()
    if not enrollments:
        return jsonify({"message": "No students enrolled in this course"}), 404

    students = []
    for e in enrollments:
        students.append({
            "student_id": e.student.id,
            "student_name": e.student.name,
            "email": e.student.email,
            "progress": e.progress,
            "enrolled_on": e.enrolled_on
        })
    return jsonify({
        "course_id": course_id,
        "total_students": len(students),
        "students": students
    }), 200


@bp.route("/<int:student_id>", methods=["GET"])
@jwt_required()
@role_required("admin")
def get_student_profile(student_id):
    student = User.query.filter_by(id=student_id, role="student").first()
    if not student:
        return jsonify({"error": "Student not found"}), 404

    enrollments = []
    for e in student.enrollments:  # student.enrollments should be a relationship
        enrollments.append({
            "course_id": e.course_id,
            "course_title": e.course.title if e.course else None,
            "progress": e.progress,
            "enrolled_at": e.enrolled_at
        })

    return jsonify({
        "id": student.id,
        "name": student.full_name,
        "email": student.email,
        "is_active": student.is_active,
        "date_joined": student.created_at,
        "enrollments": enrollments
    }), 200


@bp.route("/<int:student_id>/status", methods=["PATCH"])
@jwt_required()
@role_required("admin")
def update_student_status(student_id):
    data = request.get_json() or {}
    action = data.get("action", "").lower()

    if action not in ["activate", "suspend"]:
        return jsonify({"error": "Invalid or missing 'action'. Use 'activate' or 'suspend'."}), 400

    student = User.query.filter_by(id=student_id, role="student").first_or_404()

    if action == "suspend":
        if not student.is_active:
            return jsonify({"message": "Student already suspended"}), 400
        student.is_active = False
        message = f"Student {student.full_name} has been suspended."

    elif action == "activate":
        if student.is_active:
            return jsonify({"message": "Student already active"}), 400
        student.is_active = True
        message = f"Student {student.full_name} has been activated."

    db.session.commit()
    return jsonify({"message": message, "is_active": student.is_active}), 200

@bp.route("/sessions", methods=["GET"])
@jwt_required()
def list_sessions():
    user_id = get_jwt_identity()
    sessions = UserSession.query.filter_by(user_id=user_id).all()
    result = [{
        "id": s.id,
        "device": s.device_info,
        "ip": s.ip_address,
        "location": s.location,
        "created_at": s.created_at,
        "last_active": s.last_active
    } for s in sessions]
    return jsonify(result), 200


@bp.route("/sessions/<int:session_id>", methods=["DELETE"])
@jwt_required()
def delete_session(session_id):
    user_id = get_jwt_identity()
    session = UserSession.query.filter_by(id=session_id, user_id=user_id).first_or_404()
    db.session.delete(session)
    db.session.commit()
    return jsonify({"message": "Session deleted"}), 200

UPLOAD_FOLDER = "static/uploads/profile_photos"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route("/profile", methods=["GET"])
@jwt_required()
def me():
    user = User.query.get(get_jwt_identity())
    return jsonify(user.to_dict()), 200

@bp.route("/profile", methods=["PATCH"])
@jwt_required()
def update_profile():
    import json
    from flask import current_app

    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    data = request.form

    # Basic field updates
    user.full_name = data.get("full_name", user.full_name)
    user.bio = data.get("bio", user.bio)

    # Ensure social_handles is initialized
    if user.social_handles is None:
        user.social_handles = {}

    # Parse social_handles JSON string
    social_handles_raw = data.get("social_handles")
    if social_handles_raw:
        try:
            social_handles = json.loads(social_handles_raw)
            if isinstance(social_handles, dict):
                for platform, link in social_handles.items():
                    if link:
                        user.social_handles[platform] = link
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid social_handles JSON"}), 400

    # Handle photo upload
    if "photo" in request.files:
        photo = request.files["photo"]
        if photo and allowed_file(photo.filename):
            filename = secure_filename(photo.filename)

            upload_path = os.path.join(
                current_app.static_folder,
                "uploads",
                "profile_photos"
            )
            os.makedirs(upload_path, exist_ok=True)

            save_path = os.path.join(upload_path, filename)
            photo.save(save_path)

            # Save as public URL
            user.profile_photo = f"/static/uploads/profile_photos/{filename}"

    db.session.commit()

    return jsonify({"message": "Profile updated successfully"}), 200

@bp.route("/payments", methods=["GET"])
@jwt_required()
def list_payments():
    user_id = get_jwt_identity()
    payments = Payment.query.filter_by(user_id=user_id).all()

    result = [{
        "id": p.id,
        "course": p.course.title if p.course else None,
        "amount": p.amount,
        "status": p.status,
        "date": p.created_at
    } for p in payments]

    return jsonify(result), 200

@bp.route("/payments/<int:payment_id>/invoice", methods=["GET"])
@jwt_required()
def download_invoice(payment_id):
    user_id = get_jwt_identity()
    payment = Payment.query.filter_by(id=payment_id, user_id=user_id).first_or_404()

    invoice_number = str(uuid.uuid4())[:8].upper()  # Example: 'A93F12C8'

    # Logo path inside static folder
    logo_url = url_for('static', filename='images/codebaze_logo.png', _external=True)

    html = render_template(
        "invoice.html",
        logo_url=logo_url,
        invoice_number=invoice_number,
        name=payment.user.full_name,
        email=payment.user.email,
        course=payment.course.title,
        status=payment.status.title(),
        amount=f"{payment.amount:,.2f}",
        date=payment.created_at.strftime("%B %d, %Y")
    )

    pdf = HTML(string=html).write_pdf()

    return send_file(
        io.BytesIO(pdf),
        download_name=f"invoice_{invoice_number}.pdf",
        as_attachment=True,
        mimetype="application/pdf"
    )
# @bp.route("/payments/<int:payment_id>/invoice", methods=["GET"])
# @jwt_required()
# def download_invoice(payment_id):
#     user_id = get_jwt_identity()
#     payment = Payment.query.filter_by(id=payment_id, user_id=user_id).first_or_404()

#     buffer = io.BytesIO()

#     # Styled PDF
#     doc = SimpleDocTemplate(buffer, pagesize=LETTER)
#     styles = getSampleStyleSheet()
#     elements = []

#     # Header / Title
#     title_style = styles["Title"]
#     elements.append(Paragraph("Course Payment Invoice", title_style))
#     elements.append(Spacer(1, 0.3 * inch))

#     # Customer Info
#     info_data = [
#         ["Name", payment.user.full_name],
#         ["Email", payment.user.email],
#         ["Course", payment.course.title],
#         ["Amount Paid", f"{payment.amount:,}Naira"],
#         ["Status", payment.status.title()],
#         ["Date", payment.created_at.strftime('%Y-%m-%d %H:%M:%S')],
#     ]

#     table = Table(info_data, colWidths=[120, 300])
#     table.setStyle(TableStyle([
#         ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
#         ('BOX', (0, 0), (-1, -1), 1, colors.black),
#         ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
#         ('FONT', (0, 0), (-1, -1), 'Helvetica'),
#         ('FONTSIZE', (0, 0), (-1, -1), 11),
#         ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#         ('BACKGROUND', (0, 1), (-1, -1), colors.white),
#     ]))

#     elements.append(table)
#     elements.append(Spacer(1, 0.5 * inch))

#     # Footer
#     footer = Paragraph(
#         "Thank you for your payment.<br/>CodeBaze Academy © 2025",
#         styles["Normal"]
#     )
#     elements.append(footer)

#     doc.build(elements)

#     buffer.seek(0)

#     return send_file(
#         buffer,
#         as_attachment=True,
#         download_name=f"invoice_{payment.id}.pdf",
#         mimetype="application/pdf"
#     )

@bp.route("/my-courses", methods=["GET"])
@jwt_required()
def get_student_courses():
    user_id = get_jwt_identity()
    student = User.query.get_or_404(user_id)

    if student.role != "student":
        return jsonify({"error": "Only students can access this endpoint"}), 403

    enrollments = Enrollment.query.filter_by(user_id=user_id).all()

    enrolled_courses = []
    paid_not_enrolled = []

    for e in enrollments:
        if not e.course:
            continue

        course = e.course

        # ✅ CALCULATE REAL PROGRESS HERE
        progress_data = calculate_progress(course, user_id)

        data = {
            "course_id": course.id,
            "title": course.title,
            "slug": course.slug,
            "image": course.image,
            "total_lessons": course.total_lessons,
            "enrolled_at": e.enrolled_at.isoformat() if e.enrolled_at else None,
            "status": e.status,

            # PROGRESS
            "progress": progress_data["overall_percentage"],
            "completed_lessons": progress_data["completed_lessons"],
            "total_lessons": progress_data["total_lessons"]
        }

        if e.status == "active":
            enrolled_courses.append(data)
        elif e.status == "paid":
            paid_not_enrolled.append(data)

    return jsonify({
        "student_id": user_id,
        "enrolled_courses": enrolled_courses,
        "paid_but_not_enrolled": paid_not_enrolled,
        "counts": {
            "enrolled": len(enrolled_courses),
            "paid_not_enrolled": len(paid_not_enrolled)
        }
    }), 200

def calculate_progress(course, user_id):
    total_lessons = 0
    completed_lessons = 0
    completed_lesson_ids = []

    section_progress_list = []

    for section in course.sections:
        sec_total = len(section.lessons)
        sec_completed = 0

        for lesson in section.lessons:
            total_lessons += 1

            progress = Progress.query.filter_by(
                user_id=user_id,
                lesson_id=lesson.id,
                is_completed=True
            ).first()

            if progress:
                completed_lessons += 1
                sec_completed += 1
                completed_lesson_ids.append(lesson.id)

        section_progress_list.append({
            "section_id": section.id,
            "section_name": section.name,
            "completed": sec_completed,
            "total": sec_total,
            "percentage": round((sec_completed / sec_total) * 100, 2) if sec_total > 0 else 0
        })

    overall_percentage = (
        round((completed_lessons / total_lessons) * 100, 2)
        if total_lessons > 0 else 0
    )

    return {
        "completed_lessons": completed_lessons,
        "completed_lesson_ids": completed_lesson_ids,
        "total_lessons": total_lessons,
        "overall_percentage": overall_percentage,
        "sections": section_progress_list
    }

@bp.route("/courses/<int:course_id>/full", methods=["GET"])
@jwt_required()
def get_student_full_course(course_id):
    """
    Returns full course data ONLY for enrolled students including progress.
    """
    user_id = get_jwt_identity()
    student = User.query.get_or_404(user_id)

    # Allow only students
    if student.role != "student":
        return jsonify({"error": "Only students can access full course content"}), 403

    course = Course.query.get_or_404(course_id)

    # Check active enrollment
    enrollment = Enrollment.query.filter_by(
        user_id=user_id,
        course_id=course_id,
        status="active"
    ).first()

    if not enrollment:
        return jsonify({
            "error": "You are not enrolled in this course. Enroll to gain full access."
        }), 403

    # ---- Calculate Progress ----
    progress_data = calculate_progress(course, user_id)

    # ---- Build deep course structure ----
    course_data = {
        "id": course.id,
        "title": course.title,
        "slug": course.slug,
        "description": course.description,
        "long_description": course.long_description,
        "price": course.price,
        "is_published": course.is_published,
        "total_lessons": course.total_lessons,
        "created_at": course.created_at.isoformat(),
        "image": course.image,

        # Include updated progress summary
        "progress": progress_data,

        "sections": []
    }

    for section in course.sections:
        section_data = {
            "id": section.id,
            "name": section.name,
            "slug": section.slug,
            "description": section.description,
            "lessons": []
        }

        for lesson in section.lessons:
            # check if student completed this lesson
            progress = Progress.query.filter_by(
                user_id=user_id,
                lesson_id=lesson.id,
                is_completed=True
            ).first()

            lesson_data = {
                "id": lesson.id,
                "title": lesson.title,
                "slug": lesson.slug,
                "notes": lesson.notes,
                "reference_link": lesson.reference_link,
                "video_url": lesson.video_url,
                "document_url": lesson.document_url,
                "duration": lesson.duration,
                "size": lesson.size,
                "created_at": lesson.created_at.isoformat(),
                "is_completed": bool(progress),
                "completed_at": progress.completed_at.isoformat() if progress else None,
                "quizzes": []
            }

            # include lesson quizzes
            if hasattr(lesson, "quizzes"):
                for quiz in lesson.quizzes:
                    lesson_data["quizzes"].append({
                        "id": quiz.id,
                        "question": quiz.question,
                        "options": quiz.options,
                        "correct_answer": quiz.correct_answer
                    })

            section_data["lessons"].append(lesson_data)

        course_data["sections"].append(section_data)

    return jsonify(course_data), 200