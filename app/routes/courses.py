from flask import Blueprint, request, jsonify, send_from_directory, current_app
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
import tempfile

# Import S3 helper functions
from app.utils.s3_helper import (
    upload_to_s3, 
    generate_presigned_url, 
    delete_from_s3,
    get_s3_file_size,
    s3_file_exists
)

# Keep local folders for temporary processing only
TEMP_VIDEO_FOLDER = tempfile.gettempdir()
UPLOAD_IMAGE_FOLDER = os.path.join("static", "uploads", "images")
os.makedirs(UPLOAD_IMAGE_FOLDER, exist_ok=True)

ALLOWED_VIDEO_EXT = {"mp4", "mov", "avi", "mkv", "mp3"}
ALLOWED_DOC_EXT = {"pdf", "docx", "pptx"}
ALLOWED_IMG_EXT = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename, allowed_ext):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_ext

def get_video_metadata(video_path):
    """Get video duration from a local file"""
    try:
        clip = VideoFileClip(video_path, audio=False)
        duration = round(clip.duration, 2) if clip.duration else None
        return duration
    except Exception as e:
        print(f"Error analyzing video: {e}")
        return None
    finally:
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

    # Currency conversion
    if user_currency == "USD":
        price = convert_ngn_to_usd(course.price)
    else:
        price = course.price

    # Build response
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
                "duration": format_duration(lesson.duration),
                "size": format_size(lesson.size),
                "created_at": lesson.created_at.isoformat(),
                "quizzes": []
            }

            # Add quizzes if they exist
            if hasattr(lesson, 'quizzes') and lesson.quizzes:
                for quiz in lesson.quizzes:
                    lesson_data["quizzes"].append({
                        "id": quiz.id,
                        "question": quiz.question,
                        "options": quiz.options,
                        "correct_answer": quiz.correct_answer,
                        "quiz_type": quiz.quiz_type,
                        "explanation": quiz.explanation
                    })

            section_data["lessons"].append(lesson_data)

        course_data["sections"].append(section_data)

    return jsonify(course_data)

@bp.route("/", methods=["POST"])
@jwt_required()
@role_required("admin")
def create_course():
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "Title is required"}), 400

    title = data.get("title")
    slug = slugify(title)
    description = data.get("description", "")
    long_description = data.get("long_description", "")
    price = data.get("price", 0)
    is_published = data.get("is_published", False)

    new_course = Course(
        title=title,
        slug=slug,
        description=description,
        long_description=long_description,
        price=price,
        is_published=is_published
    )
    db.session.add(new_course)
    db.session.commit()

    return jsonify({
        "message": "Course created successfully",
        "course": {
            "id": new_course.id,
            "title": new_course.title,
            "slug": new_course.slug,
            "description": new_course.description,
            "price": new_course.price,
            "is_published": new_course.is_published
        }
    }), 201

@bp.route("/<int:course_id>", methods=["PUT"])
@jwt_required()
@role_required("admin")
def update_course(course_id):
    course = Course.query.get_or_404(course_id)
    data = request.form.to_dict()

    course.title = data.get("title", course.title)
    course.description = data.get("description", course.description)
    course.long_description = data.get("long_description", course.long_description)
    course.price = data.get("price", course.price)
    course.is_published = data.get("is_published", course.is_published)

    # Handle image upload (images still stored locally or can be moved to S3)
    image_file = request.files.get("image")
    if image_file and allowed_file(image_file.filename, ALLOWED_IMG_EXT):
        filename = secure_filename(image_file.filename)
        image_path = os.path.join(UPLOAD_IMAGE_FOLDER, filename)
        image_file.save(image_path)
        course.image = f"/static/uploads/images/{filename}"
        
        # Alternative: Upload to S3
        # result = upload_to_s3(image_file, folder='images')
        # if result['success']:
        #     course.image = result['file_url']

    db.session.commit()

    return jsonify({
        "message": "Course updated successfully",
        "course": {
            "id": course.id,
            "title": course.title,
            "description": course.description,
            "price": course.price,
            "is_published": course.is_published
        }
    }), 200

@bp.route("/<int:course_id>", methods=["DELETE"])
@jwt_required()
@role_required("admin")
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    # Delete all associated videos from S3
    for section in course.sections:
        for lesson in section.lessons:
            if lesson.s3_video_key:
                delete_from_s3(lesson.s3_video_key)
            if lesson.s3_document_key:
                delete_from_s3(lesson.s3_document_key)
    
    db.session.delete(course)
    db.session.commit()

    return jsonify({"message": "Course deleted successfully"}), 200

@bp.route("/<int:course_id>/sections", methods=["POST"])
@jwt_required()
@role_required("admin")
def create_section(course_id):
    course = Course.query.get_or_404(course_id)
    data = request.get_json()

    if not data or not data.get("name"):
        return jsonify({"error": "Section name is required"}), 400

    new_section = Section(
        name=data.get("name"),
        slug=slugify(data.get("name")),
        description=data.get("description", ""),
        course=course
    )
    db.session.add(new_section)
    db.session.commit()

    return jsonify({
        "message": "Section created successfully",
        "section": {
            "id": new_section.id,
            "name": new_section.name,
            "slug": new_section.slug,
            "description": new_section.description
        }
    }), 201

@bp.route("/<int:course_id>/sections/<int:section_id>", methods=["PUT"])
@jwt_required()
@role_required("admin")
def update_section(course_id, section_id):
    section = Section.query.get_or_404(section_id)

    if section.course_id != course_id:
        return jsonify({"error": "Section does not belong to this course"}), 400

    data = request.get_json()
    section.name = data.get("name", section.name)
    section.description = data.get("description", section.description)
    section.slug = slugify(section.name)

    db.session.commit()

    return jsonify({
        "message": "Section updated successfully",
        "section": {
            "id": section.id,
            "name": section.name,
            "slug": section.slug,
            "description": section.description
        }
    }), 200

@bp.route("/<int:course_id>/sections/<int:section_id>", methods=["DELETE"])
@jwt_required()
@role_required("admin")
def delete_section(course_id, section_id):
    section = Section.query.get_or_404(section_id)

    if section.course_id != course_id:
        return jsonify({"error": "Section does not belong to this course"}), 400
    
    # Delete all videos from S3 before deleting section
    for lesson in section.lessons:
        if lesson.s3_video_key:
            delete_from_s3(lesson.s3_video_key)
        if lesson.s3_document_key:
            delete_from_s3(lesson.s3_document_key)

    db.session.delete(section)
    db.session.commit()

    return jsonify({"message": "Section deleted successfully"}), 200

@bp.route("/<int:course_id>/sections/<int:section_id>/lessons", methods=["POST"])
@jwt_required()
@role_required("admin")
def create_lesson(course_id, section_id):
    """
    Create a new lesson with S3 video upload support
    """
    section = Section.query.get_or_404(section_id)

    if section.course_id != course_id:
        return jsonify({"error": "Section does not belong to this course"}), 400

    data = request.form.to_dict()
    title = data.get("title")

    if not title:
        return jsonify({"error": "Lesson title is required"}), 400

    # Create lesson
    new_lesson = Lesson(
        title=title,
        slug=slugify(title),
        notes=data.get("notes", ""),
        reference_link=data.get("reference_link", ""),
        section=section
    )

    # Handle video upload to S3
    video_file = request.files.get("video")
    if video_file and allowed_file(video_file.filename, ALLOWED_VIDEO_EXT):
        # Save to temporary file for metadata extraction
        temp_path = os.path.join(TEMP_VIDEO_FOLDER, f"temp_{uuid.uuid4()}_{secure_filename(video_file.filename)}")
        video_file.save(temp_path)
        
        try:
            # Get video duration
            duration = get_video_metadata(temp_path)
            if duration:
                new_lesson.duration = duration
            
            # Upload to S3
            video_file.seek(0)  # Reset file pointer
            result = upload_to_s3(video_file, folder='videos')
            
            if result['success']:
                new_lesson.s3_video_key = result['file_key']
                new_lesson.video_url = result['file_url']
                
                # Get file size from S3
                size = get_s3_file_size(result['file_key'])
                if size:
                    new_lesson.size = size
            else:
                return jsonify({"error": f"Failed to upload video: {result['error']}"}), 500
        
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # Handle document upload to S3
    doc_file = request.files.get("document")
    if doc_file and allowed_file(doc_file.filename, ALLOWED_DOC_EXT):
        result = upload_to_s3(doc_file, folder='docs')
        
        if result['success']:
            new_lesson.s3_document_key = result['file_key']
            new_lesson.document_url = result['file_url']
        else:
            return jsonify({"error": f"Failed to upload document: {result['error']}"}), 500

    db.session.add(new_lesson)
    db.session.commit()

    return jsonify({
        "message": "Lesson created successfully",
        "lesson": {
            "id": new_lesson.id,
            "title": new_lesson.title,
            "slug": new_lesson.slug,
            "video_url": new_lesson.video_url,
            "document_url": new_lesson.document_url,
            "duration": format_duration(new_lesson.duration),
            "size": format_size(new_lesson.size),
            "notes": new_lesson.notes,
            "reference_link": new_lesson.reference_link
        }
    }), 201

@bp.route("/lessons/<int:lesson_id>", methods=["PUT"])
@jwt_required()
@role_required("admin")
def update_lesson(lesson_id):
    """
    Update lesson with S3 support
    """
    lesson = Lesson.query.get_or_404(lesson_id)
    data = request.form.to_dict()

    lesson.title = data.get("title", lesson.title)
    lesson.slug = slugify(lesson.title)
    lesson.notes = data.get("notes", lesson.notes)
    lesson.reference_link = data.get("reference_link", lesson.reference_link)

    # Handle video update
    video_file = request.files.get("video")
    if video_file and allowed_file(video_file.filename, ALLOWED_VIDEO_EXT):
        # Delete old video from S3 if exists
        if lesson.s3_video_key:
            delete_from_s3(lesson.s3_video_key)
        
        # Save to temp file for metadata
        temp_path = os.path.join(TEMP_VIDEO_FOLDER, f"temp_{uuid.uuid4()}_{secure_filename(video_file.filename)}")
        video_file.save(temp_path)
        
        try:
            # Get duration
            duration = get_video_metadata(temp_path)
            if duration:
                lesson.duration = duration
            
            # Upload to S3
            video_file.seek(0)
            result = upload_to_s3(video_file, folder='videos')
            
            if result['success']:
                lesson.s3_video_key = result['file_key']
                lesson.video_url = result['file_url']
                
                # Get size
                size = get_s3_file_size(result['file_key'])
                if size:
                    lesson.size = size
            else:
                return jsonify({"error": f"Failed to upload video: {result['error']}"}), 500
        
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # Handle document update
    doc_file = request.files.get("document")
    if doc_file and allowed_file(doc_file.filename, ALLOWED_DOC_EXT):
        # Delete old document from S3
        if lesson.s3_document_key:
            delete_from_s3(lesson.s3_document_key)
        
        result = upload_to_s3(doc_file, folder='docs')
        
        if result['success']:
            lesson.s3_document_key = result['file_key']
            lesson.document_url = result['file_url']
        else:
            return jsonify({"error": f"Failed to upload document: {result['error']}"}), 500

    db.session.commit()

    return jsonify({
        "message": "Lesson updated successfully",
        "lesson": {
            "id": lesson.id,
            "title": lesson.title,
            "video_url": lesson.video_url,
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
    Returns full details of a specific lesson with presigned URL for video access
    """
    lesson = Lesson.query.get_or_404(lesson_id)
    user_id = get_jwt_identity()

    # Check if user has access (is enrolled and paid)
    has_access = False
    if user_id:
        enrollment = Enrollment.query.filter_by(
            user_id=user_id,
            course_id=lesson.section.course_id,
            status="active"
        ).first()

        if enrollment:
            payment = (
                Payment.query.join(
                    Enrollment, Enrollment.payment_reference == Payment.reference
                )
                .filter(
                    Payment.user_id == user_id,
                    Payment.status == "successful",
                    Enrollment.course_id == lesson.section.course_id
                )
                .first()
            )
            if payment:
                has_access = True

    # Build lesson response
    lesson_data = {
        "id": lesson.id,
        "title": lesson.title,
        "slug": lesson.slug,
        "notes": lesson.notes,
        "reference_link": lesson.reference_link,
        "created_at": lesson.created_at.isoformat(),
        "section": {
            "id": lesson.section.id,
            "name": lesson.section.name,
            "course_id": lesson.section.course_id
        } if lesson.section else None,
        "quizzes": []
    }

    # Only provide video URL if user has access
    if has_access:
        # Generate presigned URL for secure video access (expires in 2 hours)
        if lesson.s3_video_key:
            presigned_url = generate_presigned_url(lesson.s3_video_key, expiration=7200)
            lesson_data["video_url"] = presigned_url
        else:
            lesson_data["video_url"] = lesson.video_url
        
        # Same for documents
        if lesson.s3_document_key:
            presigned_url = generate_presigned_url(lesson.s3_document_key, expiration=7200)
            lesson_data["document_url"] = presigned_url
        else:
            lesson_data["document_url"] = lesson.document_url
    else:
        lesson_data["video_url"] = None
        lesson_data["document_url"] = None
        lesson_data["access_denied"] = "Please enroll and complete payment to access this content"

    # Include quizzes
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

@bp.route("/lessons/<int:lesson_id>/document", methods=["GET"])
@jwt_required(optional=True)
def download_lesson_document(lesson_id):
    """
    Download document with presigned URL
    """
    lesson = Lesson.query.get(lesson_id)

    if not lesson:
        return jsonify({"error": "Lesson not found"}), 404

    if not lesson.document_url:
        return jsonify({"message": "No document available"}), 200
    
    user_id = get_jwt_identity()
    
    # Check access
    has_access = False
    if user_id:
        enrollment = Enrollment.query.filter_by(
            user_id=user_id,
            course_id=lesson.section.course_id,
            status="active"
        ).first()

        if enrollment:
            payment = (
                Payment.query.join(
                    Enrollment, Enrollment.payment_reference == Payment.reference
                )
                .filter(
                    Payment.user_id == user_id,
                    Payment.status == "successful",
                    Enrollment.course_id == lesson.section.course_id
                )
                .first()
            )
            if payment:
                has_access = True
    
    if not has_access:
        return jsonify({"error": "Access denied. Please enroll and complete payment."}), 403
    
    # Generate presigned URL
    if lesson.s3_document_key:
        presigned_url = generate_presigned_url(lesson.s3_document_key, expiration=3600)
        if presigned_url:
            return jsonify({
                "download_url": presigned_url,
                "expires_in": 3600
            }), 200
        else:
            return jsonify({"error": "Failed to generate download link"}), 500
    
    # Fallback to local file
    filename = os.path.basename(lesson.document_url)
    directory = os.path.join(current_app.root_path, '..', 'static', 'uploads', 'docs')
    directory = os.path.abspath(directory)
    
    if not os.path.exists(os.path.join(directory, filename)):
        return jsonify({"error": "File not found"}), 404
    
    try:
        return send_from_directory(directory, filename, as_attachment=True)
    except Exception as e:
        return jsonify({"error": f"Error sending file: {str(e)}"}), 500