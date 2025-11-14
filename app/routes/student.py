from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.user import UserSession, Payment
from app.extensions import db
from app.models import User, Enrollment, Course, Progress
from app.utils.auth import role_required
import os
from werkzeug.utils import secure_filename
from reportlab.pdfgen import canvas

from datetime import datetime

bp = Blueprint("students", __name__)

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


@bp.route("/sessions/new", methods=["POST"])
@jwt_required()
def create_session():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if user.role != "student":
        return jsonify({"error": "Only students can create sessions"}), 403

    # Check if already has 5 active sessions
    active_sessions = UserSession.query.filter_by(user_id=user_id).count()
    if active_sessions >= 5:
        return jsonify({"error": "Maximum session limit (5) reached"}), 403

    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', 'Unknown Device')

    new_session = UserSession(
        user_id=user_id,
        device_info=user_agent,
        ip_address=ip,
        location="Unknown",  # or resolved via IP service
    )
    db.session.add(new_session)
    db.session.commit()
    return jsonify({"message": "Session created successfully"}), 201


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
def get_profile():
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)

    return jsonify({
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "bio": user.bio,
        "profile_photo": user.profile_photo,
        "socials": {
            "facebook": user.social_facebook,
            "twitter": user.social_twitter,
            "linkedin": user.social_linkedin
        }
    }), 200


@bp.route("/profile", methods=["PATCH"])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    data = request.form

    user.full_name = data.get("full_name", user.full_name)
    user.bio = data.get("bio", user.bio)
    user.social_facebook = data.get("facebook", user.social_facebook)
    user.social_twitter = data.get("twitter", user.social_twitter)
    user.social_linkedin = data.get("linkedin", user.social_linkedin)

    if "photo" in request.files:
        photo = request.files["photo"]
        if photo and allowed_file(photo.filename):
            filename = secure_filename(photo.filename)
            photo.save(os.path.join(UPLOAD_FOLDER, filename))
            user.profile_photo = f"/{UPLOAD_FOLDER}/{filename}"

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

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(100, 800, "Course Payment Invoice")
    pdf.drawString(100, 780, f"Name: {payment.user.full_name}")
    pdf.drawString(100, 760, f"Email: {payment.user.email}")
    pdf.drawString(100, 740, f"Course: {payment.course.title}")
    pdf.drawString(100, 720, f"Amount Paid: ₦{payment.amount}")
    pdf.drawString(100, 700, f"Status: {payment.status}")
    pdf.drawString(100, 680, f"Date: {payment.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="invoice.pdf", mimetype="application/pdf")

@bp.route("/my-courses", methods=["GET"])
@jwt_required()
def get_student_courses():
    """
    Return courses the student has enrolled in, and courses they have paid for
    but enrollment has not been activated yet.
    """
    user_id = get_jwt_identity()
    student = User.query.get_or_404(user_id)

    if student.role != "student":
        return jsonify({"error": "Only students can access this endpoint"}), 403

    # --------------------------------------------------
    # Get ALL enrollments for this student
    # --------------------------------------------------
    enrollments = Enrollment.query.filter_by(user_id=user_id).all()

    enrolled_courses = []
    paid_not_enrolled = []

    for e in enrollments:
        if not e.course:
            continue  # avoid issues if course was deleted

        course = e.course

        data = {
            "course_id": course.id,
            "title": course.title,
            "slug": course.slug,
            "image": course.image,
            "total_lessons": course.total_lessons,
            "enrolled_at": e.enrolled_at.isoformat() if e.enrolled_at else None,
            "progress": e.progress,
            "status": e.status
        }

        # --------------------------------------------------
        # active → fully enrolled
        # paid → payment done but enrollment pending
        # --------------------------------------------------
        if e.status == "active":
            enrolled_courses.append(data)
        elif e.status == "paid":
            paid_not_enrolled.append(data)

    # --------------------------------------------------
    # Final structured response
    # --------------------------------------------------
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

        # Include full progress summary
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
