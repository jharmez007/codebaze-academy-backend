from flask import Blueprint, request, jsonify, send_from_directory
from app.extensions import db
from werkzeug.utils import secure_filename
from app.models import Course, Lesson, Enrollment
from app.models.user import Payment
from app.models.course import Section
from app.models.lesson import Quiz
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth import role_required
from app.helpers.currency import detect_currency, convert_ngn_to_usd
import json
from moviepy import VideoFileClip
import os, uuid, re

UPLOAD_VIDEO_FOLDER = os.path.join("static", "uploads", "videos")
UPLOAD_IMAGE_FOLDER = os.path.join("static", "uploads", "images")
UPLOAD_DOC_FOLDER = os.path.join("static", "uploads", "docs")
# Make sure the folders exist
os.makedirs(UPLOAD_VIDEO_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_DOC_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_IMAGE_FOLDER, exist_ok=True)
ALLOWED_VIDEO_EXT = {"mp4", "mov", "avi", "mkv", "mp3"}
ALLOWED_DOC_EXT = {"pdf", "docx", "pptx"}
ALLOWED_IMG_EXT = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename, allowed_ext):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_ext

def get_video_metadata(video_path):
    try:
        clip = VideoFileClip(video_path, audio=False)  # ✅ disable audio reading unless needed
        duration = round(clip.duration, 2) if clip.duration else None
        size = os.path.getsize(video_path)
        return duration, size
    except Exception as e:
        print(f"Error analyzing video: {e}")
        return None, None
    finally:
        # safely close without assuming attributes exist
        try:
            if "clip" in locals():
                if hasattr(clip, "reader") and hasattr(clip.reader, "close"):
                    clip.reader.close()
                if hasattr(clip, "audio") and clip.audio and hasattr(clip.audio, "reader"):
                    if hasattr(clip.audio.reader, "close_proc"):
                        clip.audio.reader.close_proc()
                del clip
        except Exception as cleanup_err:
            print(f"Cleanup warning: {cleanup_err}")
    
def slugify(text):
    text = re.sub(r'[^a-zA-Z0-9]+', '-', text)
    return text.strip('-').lower()

def format_duration(seconds):
    """Convert float seconds to HH:MM:SS string."""
    if not seconds:
        return "00:00:00"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{secs:02}"


def format_size(bytes_size):
    """Convert bytes to human-readable GB/MB/KB."""
    if not bytes_size:
        return "0 KB"
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"

bp = Blueprint("courses", __name__)

# List all published courses
@bp.route("/", methods=["GET"])
def list_courses():
    user_currency = detect_currency()
    courses = Course.query.filter_by(is_published=True).all()
    result = []
    for c in courses:
        if user_currency == "USD":
            price = convert_ngn_to_usd(c.price)
        else:
            price = c.price

        result.append({
            "id": c.id,
            "image": c.image,
            "slug": c.slug,
            "title": c.title,
            "description": c.description,
            "price": price,
            "currency": user_currency,
            "is_published": c.is_published,
            "total_lessons": c.total_lessons,
            "created_at": c.created_at.isoformat()
        })
    return jsonify(result)

@bp.route("/admin", methods=["GET"])
def list_courses_all():
    courses = Course.query.all()
    result = []
    for c in courses:
        result.append({
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "price": c.price,
            "is_published": c.is_published,
            "total_lessons": c.total_lessons,
            "created_at": c.created_at.isoformat()
        })
    return jsonify(result)

@bp.route("/<int:course_id>", methods=["GET"])
@jwt_required(optional=True)
def get_course(course_id):
    course = Course.query.get_or_404(course_id)
    user_id = get_jwt_identity()
    user_currency = detect_currency()

    # Default values
    is_paid = False
    is_enrolled = False

    # Check enrollment & payment only if user is logged in
    if user_id:
        enrollment = Enrollment.query.filter_by(
            user_id=user_id,
            course_id=course.id,
            status="active"
        ).first()

        if enrollment:
            is_enrolled = True

        payment = (
            Payment.query.join(
                Enrollment, Enrollment.payment_reference == Payment.reference
            )
            .filter(
                Payment.user_id == user_id,
                Payment.status == "successful",
                Enrollment.course_id == course.id
            )
            .first()
        )

        if payment:
            is_paid = True

    # -----------------------------------
    # Currency conversion
    # -----------------------------------
    if user_currency == "USD":
        price = convert_ngn_to_usd(course.price)
    else:
        price = course.price

    # -----------------------------------
    # Build response
    # -----------------------------------
    response = {
        "id": course.id,
        "title": course.title,
        "slug": course.slug,
        "description": course.description,
        "long_description": course.long_description,
        "price": price,
        "currency": user_currency,
        "is_published": course.is_published,
        "total_lessons": course.total_lessons,
        "created_at": course.created_at.isoformat(),
        "image": course.image,
        "sections": [],
        "user_id": user_id,
        "is_enrolled": is_enrolled,
        "is_paid": is_paid
    }

    for section in course.sections:
        sub_data = {
            "id": section.id,
            "name": section.name,
            "description": section.description,
            "lessons": []
        }

        for lesson in section.lessons:
            lesson_data = {
                "id": lesson.id,
                "title": lesson.title,
                "duration": lesson.duration,
                "size": lesson.size
            }
            sub_data["lessons"].append(lesson_data)

        response["sections"].append(sub_data)

    return jsonify(response)


@bp.route("/<int:course_id>/full", methods=["GET"])
@jwt_required(optional=True)
def get_full_course(course_id):
    """
    Returns full course data including all sections, lessons, and quizzes.
    """
    course = Course.query.get_or_404(course_id)

    # Build deep nested response
    course_data = {
        "id": course.id,
        "title": course.title,
        "slug": getattr(course, "slug", None),
        "description": course.description,
        "long_description": course.long_description,
        "price": course.price,
        "is_published": course.is_published,
        "total_lessons": course.total_lessons,
        "created_at": course.created_at.isoformat(),
        "image": course.image,
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
                "quizzes": []
            }

            # include quizzes per lesson
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


@bp.route("/", methods=["POST"])
@jwt_required()
@role_required("admin")
def create_course():
    data = request.form.get("data")
    if not data:
        return jsonify({"error": "Missing course data"}), 400
    
    try:
        data = json.loads(data)
    except:
        return jsonify({"error": "Invalid JSON format"}), 400

    title = data.get("title")
    description = data.get("description")
    long_description = data.get("long_description")
    price = data.get("price")
    sections_data = data.get("sections", [])

    if not all([title, description, price]):
        return jsonify({"error": "Missing fields"}), 400

    # Handle course image
    image_file = request.files.get("image")
    image_path = None
    if image_file and allowed_file(image_file.filename, ALLOWED_IMG_EXT):
        filename = secure_filename(image_file.filename)
        image_path = os.path.join(UPLOAD_IMAGE_FOLDER, filename)
        image_file.save(image_path)

    # Create course
    course = Course(
        title=title,
        description=description,
        long_description=long_description,
        price=price,
        slug=slugify(title),
        image=image_path,
        is_published=False
    )

    # Build sections & lessons
    for i, sub in enumerate(sections_data):
        section = Section(
            name=sub["name"],
            slug=slugify(sub["name"]),
            description=sub.get("description"),
            course=course
        )

        for j, lesson_data in enumerate(sub.get("lessons", [])):
            video_file = request.files.get(f"sub_{i}_lesson_{j}_video")
            doc_file = request.files.get(f"sub_{i}_lesson_{j}_doc")

            video_path, doc_path, duration, size = None, None, None, None

            if video_file and allowed_file(video_file.filename, ALLOWED_VIDEO_EXT):
                filename = secure_filename(video_file.filename)
                video_path = os.path.join(UPLOAD_VIDEO_FOLDER, filename)
                video_file.save(video_path)
                duration, size = get_video_metadata(video_path)

            if doc_file and allowed_file(doc_file.filename, ALLOWED_DOC_EXT):
                filename = secure_filename(doc_file.filename)
                doc_path = os.path.join(UPLOAD_DOC_FOLDER, filename)
                doc_file.save(doc_path)

            lesson = Lesson(
                title=lesson_data["title"],
                slug=slugify(lesson_data["title"]),
                notes=lesson_data.get("notes"),
                reference_link=lesson_data.get("references"),
                video_url=video_path,
                document_url=doc_path,
                duration=duration,
                size=size,
                section=section 
            )
            section.lessons.append(lesson)

        course.sections.append(section)

    db.session.add(course)
    db.session.commit()

    return jsonify({
        "message": "Course created",
        "id": course.id,
        "slug": course.slug,
        "title": course.title,
        "image": course.image,
        "is_published": course.is_published,
        "sections": [
            {
                "id": sub.id,
                "slug": sub.slug,
                "name": sub.name,
                "lessons": [
                    {
                        "id": lesson.id,
                        "slug": lesson.slug,
                        "title": lesson.title,
                        "duration": lesson.duration,
                        "size": lesson.size
                    }
                    for lesson in sub.lessons
                ]
            } for sub in course.sections
        ]
    }), 201

@bp.route("/<int:course_id>/publish", methods=["PATCH"])
@jwt_required()
@role_required("admin")
def toggle_publish(course_id):
    course = Course.query.get_or_404(course_id)

    # Toggle publish state
    course.is_published = not course.is_published
    db.session.commit()

    return jsonify({
        "message": "Course status updated",
        "id": course.id,
        "is_published": course.is_published
    }), 200

@bp.route("/<int:course_id>", methods=["DELETE"])
@jwt_required()
@role_required("admin")
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()

    return jsonify({
        "message": "Course deleted successfully",
        "id": course_id
    }), 200

@bp.route("/<int:course_id>/add-lesson", methods=["POST"])
@jwt_required()
@role_required("admin")
def add_lesson(course_id):
    data = request.form.get("data")
    if not data:
        return jsonify({"error": "Missing lesson data"}), 400

    try:
        data = json.loads(data)
    except:
        return jsonify({"error": "Invalid JSON format"}), 400

    course = Course.query.get(course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    subcategory_id = data.get("subcategory_id")
    sections = sections.query.get(subcategory_id)
    if not sections or sections.course_id != course_id:
        return jsonify({"error": "Invalid sections"}), 400

    # Handle file uploads
    video_file = request.files.get("video")
    doc_file = request.files.get("document")

    video_path, doc_path = None, None

    if video_file and allowed_file(video_file.filename, ALLOWED_VIDEO_EXT):
        filename = secure_filename(video_file.filename)
        video_path = os.path.join(UPLOAD_VIDEO_FOLDER, filename)
        video_file.save(video_path)

        duration, size = get_video_metadata(video_path)

    if doc_file and allowed_file(doc_file.filename, ALLOWED_DOC_EXT):
        filename = secure_filename(doc_file.filename)
        doc_path = os.path.join(UPLOAD_DOC_FOLDER, filename)
        doc_file.save(doc_path)

    lesson = Lesson(
        title=data["title"],
        notes=data.get("notes"),
        reference_link=data.get("references"),
        video_url=video_path,
        document_url=doc_path,
        duration=duration,
        size=size,
        course=course,
        sections=sections
    )

    db.session.add(lesson)
    db.session.commit()

    return jsonify({"message": "Lesson added", "lesson_id": lesson.id}), 201

@bp.route("/<int:course_id>", methods=["PUT"])
@jwt_required()
@role_required("admin")
def update_course(course_id):
    course = Course.query.get_or_404(course_id)

    raw_data = request.form.get("data")
    if not raw_data:
        return jsonify({"error": "Missing course data"}), 400

    try:
        data = json.loads(raw_data)
    except:
        return jsonify({"error": "Invalid JSON format"}), 400

    # ✅ Update base fields
    new_title = data.get("title", course.title)
    course.title = new_title
    course.slug = slugify(new_title)  # ✅ Always update slug to match title/topic
    course.description = data.get("description", course.description)
    course.price = data.get("price", course.price)
    course.long_description = data.get("long_description", course.long_description)

    # ✅ Handle new course image if uploaded
    image_file = request.files.get("image")
    if image_file and allowed_file(image_file.filename, ALLOWED_IMG_EXT):
        filename = secure_filename(image_file.filename)
        image_path = os.path.join(UPLOAD_IMAGE_FOLDER, filename)
        image_file.save(image_path)
        course.image = image_path

    # ✅ Handle sections & lessons
    sections_data = data.get("sections", [])
    for i, sub in enumerate(sections_data):
        section_id = sub.get("id")
        if section_id:
            section = Section.query.filter_by(id=section_id, course_id=course.id).first()
            if section:
                section.name = sub.get("name", section.name)
                section.slug = slugify(section.name)  # ✅ keep section slug updated
                section.description = sub.get("description", section.description)
            else:
                continue
        else:
            section = Section(
                name=sub["name"],
                slug=slugify(sub["name"]),
                description=sub.get("description", ""),
                course=course
            )
            db.session.add(section)

        # ✅ Handle lessons
        for j, lesson_data in enumerate(sub.get("lessons", [])):
            lesson_id = lesson_data.get("id")
            if lesson_id:
                lesson = Lesson.query.filter_by(id=lesson_id, section_id=section.id).first()
                if lesson:
                    lesson.title = lesson_data.get("title", lesson.title)
                    lesson.slug = slugify(lesson.title)  # ✅ keep lesson slug updated
                    lesson.notes = lesson_data.get("notes", lesson.notes)
                    lesson.reference_link = lesson_data.get("reference_link", lesson.reference_link)
                else:
                    continue
            else:
                video_file = request.files.get(f"sub_{i}_lesson_{j}_video")
                doc_file = request.files.get(f"sub_{i}_lesson_{j}_doc")

                video_path, doc_path, duration, size = None, None, None, None

                if video_file and allowed_file(video_file.filename, ALLOWED_VIDEO_EXT):
                    filename = secure_filename(video_file.filename)
                    video_path = os.path.join(UPLOAD_VIDEO_FOLDER, filename)
                    video_file.save(video_path)
                    duration, size = get_video_metadata(video_path)

                if doc_file and allowed_file(doc_file.filename, ALLOWED_DOC_EXT):
                    filename = secure_filename(doc_file.filename)
                    doc_path = os.path.join(UPLOAD_DOC_FOLDER, filename)
                    doc_file.save(doc_path)

                lesson = Lesson(
                    title=lesson_data["title"],
                    slug=slugify(lesson_data["title"]),
                    notes=lesson_data.get("notes"),
                    reference_link=lesson_data.get("reference_link"),
                    video_url=video_path,
                    document_url=doc_path,
                    duration=duration,
                    size=size,
                    section=section
                )
                db.session.add(lesson)

    db.session.commit()

    return jsonify({"message": "✅ Course and related data updated successfully"}), 200


# Delete a Section and all its Lessons
@bp.route("/<int:course_id>/sections/<int:section_id>", methods=["DELETE"])
@jwt_required()
@role_required("admin")
def delete_section(course_id, section_id):
    course = Course.query.get_or_404(course_id)
    section = Section.query.filter_by(id=section_id, course_id=course.id).first()

    if not section:
        return jsonify({"error": "Section not found"}), 404

    # Deleting section will also delete lessons if cascade is set in the model
    db.session.delete(section)
    db.session.commit()

    return jsonify({
        "message": "Section deleted successfully",
        "section_id": section_id,
        "course_id": course_id
    }), 200


# Delete a single Lesson
@bp.route("/<int:course_id>/sections/<int:section_id>/lessons/<int:lesson_id>", methods=["DELETE"])
@jwt_required()
@role_required("admin")
def delete_lesson(course_id, section_id, lesson_id):
    course = Course.query.get_or_404(course_id)
    section = Section.query.filter_by(id=section_id, course_id=course.id).first()
    if not section:
        return jsonify({"error": "Section not found"}), 404

    lesson = Lesson.query.filter_by(id=lesson_id, section_id=section.id).first()
    if not lesson:
        return jsonify({"error": "Lesson not found"}), 404

    db.session.delete(lesson)
    db.session.commit()

    return jsonify({
        "message": "Lesson deleted successfully",
        "lesson_id": lesson_id,
        "section_id": section_id,
        "course_id": course_id
    }), 200

@bp.route("/<int:course_id>/lessons/<int:lesson_id>", methods=["PUT"])
@jwt_required()
@role_required("admin")
def update_lesson(course_id, lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)

    # Ensure lesson belongs to this course (via section → course)
    if lesson.section.course_id != course_id:
        return jsonify({"error": "Lesson does not belong to this course"}), 400

    raw_data = request.form.get("data")
    if not raw_data:
        return jsonify({"error": "Missing lesson data"}), 400

    try:
        data = json.loads(raw_data)
    except Exception:
        return jsonify({"error": "Invalid JSON format"}), 400

    # --- Update fields ---
    lesson.title = data.get("title", lesson.title)
    lesson.notes = data.get("notes", lesson.notes)
    ref_links = data.get("reference_link")
    if isinstance(ref_links, list):
        lesson.reference_link = json.dumps(ref_links)  # store array as JSON string
    elif isinstance(ref_links, str):
        lesson.reference_link = ref_links  # fallback (in case frontend still sends string)
    lesson.duration = data.get("duration", lesson.duration)

    # --- Handle new file uploads ---
    video_file = request.files.get("video")
    doc_file = request.files.get("document")

    if video_file and allowed_file(video_file.filename, ALLOWED_VIDEO_EXT):
        filename = secure_filename(video_file.filename)
        video_path = os.path.join(UPLOAD_VIDEO_FOLDER, filename)
        video_file.save(video_path)
        lesson.video_url = f"/static/uploads/videos/{filename}"

        duration, size = get_video_metadata(video_path)
        if duration:
            lesson.duration = duration
        if size:
            lesson.size = size

    if doc_file and allowed_file(doc_file.filename, ALLOWED_DOC_EXT):
        filename = secure_filename(doc_file.filename)
        doc_path = os.path.join(UPLOAD_DOC_FOLDER, filename)
        doc_file.save(doc_path)
        lesson.document_url = f"/static/uploads/docs/{filename}"

    db.session.commit()

    return jsonify({
        "message": "Lesson updated successfully",
        "lesson": {
            "id": lesson.id,
            "title": lesson.title,
            "video_url": lesson.video_url,
            "document_url": lesson.document_url,
            "document_url": lesson.document_url,
            "duration": format_duration(lesson.duration),
            "size": format_size(lesson.size),
            "notes": lesson.notes,
            "reference_link": lesson.reference_link
        }
    }), 200


@bp.route("/lessons/<int:lesson_id>", methods=["GET"])
@jwt_required(optional=True)
def get_lesson_details(lesson_id):
    """
    Returns full details of a specific lesson including video, document, notes, and quizzes.
    """
    lesson = Lesson.query.get_or_404(lesson_id)

    # build lesson response
    lesson_data = {
        "id": lesson.id,
        "title": lesson.title,
        "slug": lesson.slug,
        "notes": lesson.notes,
        "reference_link": lesson.reference_link,
        "video_url": lesson.video_url,
        "document_url": lesson.document_url,
         
        "created_at": lesson.created_at.isoformat(),
        "section": {
            "id": lesson.section.id,
            "name": lesson.section.name,
            "course_id": lesson.section.course_id
        } if lesson.section else None,
        "quizzes": []
    }

    # include related quizzes
    if hasattr(lesson, "quizzes") and lesson.quizzes:
        for quiz in lesson.quizzes:
            lesson_data["quizzes"].append({
                "id": quiz.id,
                "question": quiz.question,
                "options": quiz.options,
                "correct_answer": quiz.correct_answer,
                "explanation": quiz.explanation
            })

    return jsonify(lesson_data), 200


@bp.route("/<int:course_id>/lessons/<int:lesson_id>/add-quiz", methods=["POST"])
@jwt_required()
@role_required("admin")
def add_quiz(course_id, lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)

    if lesson.section.course_id != course_id:
        return jsonify({"error": "Lesson does not belong to this course"}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing quiz data"}), 400

    question = data.get("question")
    options = data.get("options")
    correct_answer = data.get("correct_answer")
    quiz_type = data.get("quiz_type")
    explanation = data.get("explanation")

    if not question or not correct_answer or not quiz_type:
        return jsonify({"error": "Incomplete quiz data"}), 400

    # Validate quiz_type
    valid_types = ["multiple_choice", "true_false", "free_text"]
    if quiz_type not in valid_types:
        return jsonify({"error": f"Invalid quiz type. Must be one of {valid_types}"}), 400

    # For multiple choice, options are required
    if quiz_type == "multiple_choice" and (not options or not isinstance(options, list)):
        return jsonify({"error": "Options must be provided for multiple choice quizzes"}), 400

    quiz = Quiz(
        question=question,
        options=options,
        correct_answer=correct_answer,
        quiz_type=quiz_type,
        explanation=explanation,
        lesson=lesson
    )

    db.session.add(quiz)
    db.session.commit()

    return jsonify({
        "message": "Quiz added successfully",
        "quiz": {
            "id": quiz.id,
            "question": quiz.question,
            "options": quiz.options,
            "correct_answer": quiz.correct_answer,
            "quiz_type": quiz.quiz_type,
            "explanation": quiz.explanation
        }
    }), 201


@bp.route("/lessons/<int:lesson_id>/quizzes/<int:quiz_id>", methods=["PUT"])
@jwt_required()
@role_required("admin")
def update_quiz(lesson_id, quiz_id):
    quiz = Quiz.query.get(quiz_id)
    if not quiz:
        return jsonify({"error": "Quiz not found"}), 404
    if quiz.lesson_id != lesson_id:
        return jsonify({"error": "Quiz does not belong to this lesson"}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing data"}), 400

    quiz.question = data.get("question", quiz.question)
    quiz.options = data.get("options", quiz.options)
    quiz.correct_answer = data.get("correct_answer", quiz.correct_answer)
    quiz.quiz_type = data.get("quiz_type", quiz.quiz_type)
    quiz.explanation = data.get("explanation", quiz.explanation)

    # Validate quiz_type when updating
    valid_types = ["multiple_choice", "true_false", "free_text"]
    if quiz.quiz_type not in valid_types:
        return jsonify({"error": f"Invalid quiz type. Must be one of {valid_types}"}), 400

    db.session.commit()

    return jsonify({
        "message": "Quiz updated successfully",
        "quiz": {
            "id": quiz.id,
            "question": quiz.question,
            "options": quiz.options,
            "correct_answer": quiz.correct_answer,
            "quiz_type": quiz.quiz_type,
            "explanation": quiz.explanation
        }
    }), 200

@bp.route("/lessons/<int:lesson_id>/quizzes/<int:quiz_id>", methods=["DELETE"])
@jwt_required()
@role_required("admin")
def delete_quiz(lesson_id, quiz_id):
    """
    Delete a specific quiz under a lesson.
    """
    quiz = Quiz.query.get_or_404(quiz_id)

    if quiz.lesson_id != lesson_id:
        return jsonify({"error": "Quiz does not belong to this lesson"}), 400

    db.session.delete(quiz)
    db.session.commit()

    return jsonify({"message": "Quiz deleted successfully"}), 200

@bp.route("/<int:lesson_id>/document", methods=["GET"])
@jwt_required(optional=True)
def download_lesson_document(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)

    if not lesson.document_url:
        return jsonify({"error": "No document available"}), 404

    # document_url example: /static/uploads/docs/file.pdf
    filename = os.path.basename(lesson.document_url)
    directory = os.path.join("static", "uploads", "docs")

    return send_from_directory(
        directory=directory,
        path=filename,
        as_attachment=True
    )