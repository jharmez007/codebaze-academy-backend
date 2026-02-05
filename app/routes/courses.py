from flask import Blueprint, request, jsonify, send_from_directory, current_app
from app.extensions import db
from werkzeug.utils import secure_filename
from app.models import Course, Lesson, Enrollment
from app.models.user import Payment, User
from app.models.course import Section
from app.models.lesson import Quiz
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth import role_required
from app.helpers.currency import detect_currency, convert_ngn_to_usd
import json
from moviepy import VideoFileClip
import os, uuid, re
import tempfile
import boto3
from dotenv import load_dotenv

load_dotenv()

# Import S3 helper functions - YES, YOU STILL NEED THESE!
from app.utils.s3_helper import (
    generate_presigned_url,  # For video playback
    delete_from_s3,          # For deleting old videos
    get_s3_file_size,        # For getting file metadata
    s3_file_exists           # For checking if file exists
)

# AWS Configuration for direct upload
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
AWS_S3_BUCKET_NAME = os.getenv('AWS_S3_BUCKET_NAME')

# Keep local folders for images only
UPLOAD_IMAGE_FOLDER = os.path.join("static", "uploads", "images")
os.makedirs(UPLOAD_IMAGE_FOLDER, exist_ok=True)

ALLOWED_VIDEO_TYPES = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska']
ALLOWED_DOC_TYPES = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
ALLOWED_IMG_EXT = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename, allowed_ext):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_ext
    
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

@bp.route("/generate-upload-url", methods=["POST"])
@jwt_required()
@role_required("admin")
def generate_upload_url():
    """
    Generate presigned PUT URL for direct browser upload to S3
    FIXED: Includes ContentDisposition header for video streaming
    Frontend should upload using fetch() with PUT method
    """
    data = request.get_json()
    
    if not data or not data.get('filename') or not data.get('filetype'):
        return jsonify({"error": "filename and filetype are required"}), 400
    
    filename = data.get('filename')
    filetype = data.get('filetype')
    folder = data.get('folder', 'videos')
    
    # Validate file type
    if folder == 'videos' and filetype not in ALLOWED_VIDEO_TYPES:
        return jsonify({"error": f"Invalid video type. Allowed: {ALLOWED_VIDEO_TYPES}"}), 400
    
    if folder == 'docs' and filetype not in ALLOWED_DOC_TYPES:
        return jsonify({"error": f"Invalid document type. Allowed: {ALLOWED_DOC_TYPES}"}), 400
    
    # Generate unique filename
    file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'mp4'
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    file_key = f"{folder}/{unique_filename}"
    
    # Create S3 client with proper configuration
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
        config=boto3.session.Config(
            signature_version='s3v4',
            s3={'addressing_style': 'virtual'}
        )
    )
    
    try:
        # Set ContentDisposition based on file type
        if folder == 'videos':
            content_disposition = 'inline'  # Stream videos
        else:
            content_disposition = f'attachment; filename="{secure_filename(filename)}"'  # Download docs
        
        # Generate presigned PUT URL with proper headers for streaming
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': AWS_S3_BUCKET_NAME,
                'Key': file_key,
                'ContentType': filetype,
                'ContentDisposition': content_disposition,
                'CacheControl': 'max-age=31536000'
            },
            ExpiresIn=3600,  # URL expires in 1 hour
            HttpMethod='PUT'
        )
        
        # Generate the final file URL
        file_url = f"https://{AWS_S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{file_key}"
        
        print(f"✅ Generated presigned URL for: {filename}")
        print(f"📂 File key: {file_key}")
        print(f"🌐 Region: {AWS_REGION}")
        
        return jsonify({
            'upload_url': presigned_url,
            'file_key': file_key,
            'file_url': file_url,
            'content_type': filetype,
            'content_disposition': content_disposition,
            'method': 'PUT'
        }), 200
    
    except Exception as e:
        print(f"❌ Error generating presigned PUT URL: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# Alternative: Direct backend upload (if presigned URLs keep failing)
@bp.route("/upload-to-s3-backend", methods=["POST"])
@jwt_required()
@role_required("admin")
def upload_to_s3_backend():
    """
    Upload file through backend to S3 (FALLBACK option)
    Use this if direct upload fails or for small files
    Includes proper headers for video streaming
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    lesson_id = request.form.get('lesson_id')
    file_type = request.form.get('file_type', 'video')
    
    if not lesson_id:
        return jsonify({"error": "lesson_id is required"}), 400
    
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    # Get lesson
    lesson = Lesson.query.get(lesson_id)
    if not lesson:
        return jsonify({"error": "Lesson not found"}), 404
    
    # Validate file type
    content_type = file.content_type
    if file_type == 'video' and content_type not in ALLOWED_VIDEO_TYPES:
        return jsonify({"error": f"Invalid video type. Allowed: {ALLOWED_VIDEO_TYPES}"}), 400
    
    if file_type == 'document' and content_type not in ALLOWED_DOC_TYPES:
        return jsonify({"error": f"Invalid document type. Allowed: {ALLOWED_DOC_TYPES}"}), 400
    
    # Generate unique filename
    file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'mp4'
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    folder = 'videos' if file_type == 'video' else 'docs'
    file_key = f"{folder}/{unique_filename}"
    
    # Create S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )
    
    try:
        print(f"📤 Uploading {file.filename} to S3...")
        print(f"📂 Destination: {file_key}")
        
        # Get file size first
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        print(f"📦 File size: {format_size(file_size)}")
        
        # Prepare upload parameters with proper headers
        extra_args = {
            'ContentType': content_type,
            'CacheControl': 'max-age=31536000',
            'Metadata': {
                'original-filename': secure_filename(file.filename)
            }
        }
        
        # Set ContentDisposition for streaming vs download
        if file_type == 'video':
            extra_args['ContentDisposition'] = 'inline'  # Videos stream in browser
            print("🎬 Setting ContentDisposition to 'inline' for video streaming")
        else:
            extra_args['ContentDisposition'] = f'attachment; filename="{secure_filename(file.filename)}"'
            print("📄 Setting ContentDisposition to 'attachment' for document download")
        
        # Upload to S3
        s3_client.upload_fileobj(
            file,
            AWS_S3_BUCKET_NAME,
            file_key,
            ExtraArgs=extra_args
        )
        
        print(f"✅ Upload successful!")
        
        # Generate file URL
        file_url = f"https://{AWS_S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{file_key}"
        
        # Update lesson in database
        if file_type == 'video':
            # Delete old video if exists
            if lesson.s3_video_key:
                print(f"🗑️ Deleting old video: {lesson.s3_video_key}")
                delete_from_s3(lesson.s3_video_key)
            
            lesson.s3_video_key = file_key
            lesson.video_url = file_url
            lesson.size = file_size
            
        elif file_type == 'document':
            # Delete old document if exists
            if lesson.s3_document_key:
                print(f"🗑️ Deleting old document: {lesson.s3_document_key}")
                delete_from_s3(lesson.s3_document_key)
            
            lesson.s3_document_key = file_key
            lesson.document_url = file_url
        
        db.session.commit()
        print(f"💾 Database updated for lesson #{lesson.id}")
        
        return jsonify({
            "message": "File uploaded successfully",
            "lesson": {
                "id": lesson.id,
                "title": lesson.title,
                "video_url": lesson.video_url if file_type == 'video' else None,
                "document_url": lesson.document_url if file_type == 'document' else None,
                "s3_video_key": lesson.s3_video_key if file_type == 'video' else None,
                "s3_document_key": lesson.s3_document_key if file_type == 'document' else None,
                "size": format_size(lesson.size) if file_type == 'video' and lesson.size else None
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error uploading to S3: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    

@bp.route("/confirm-upload", methods=["POST"])
@jwt_required()
@role_required("admin")
def confirm_upload():

    data = request.get_json()
    
    if not data or not data.get('lesson_id') or not data.get('file_key'):
        return jsonify({"error": "lesson_id and file_key are required"}), 400
    
    lesson_id = data.get('lesson_id')
    file_key = data.get('file_key')
    file_url = data.get('file_url')
    file_type = data.get('file_type', 'video')
    duration = data.get('duration')  # Optional - from frontend
    size = data.get('size')  # Optional - will auto-fetch if not provided
    
    # Get lesson
    lesson = Lesson.query.get(lesson_id)
    if not lesson:
        return jsonify({"error": "Lesson not found"}), 404
    
    # Create S3 client for metadata retrieval
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )
    
    # Auto-fetch file size from S3 if not provided
    if not size:
        try:
            response = s3_client.head_object(Bucket=AWS_S3_BUCKET_NAME, Key=file_key)
            size = response['ContentLength']
        except Exception as e:
            size = None
    
    # Update lesson with S3 info
    if file_type == 'video':
        # Delete old video if exists
        if lesson.s3_video_key and lesson.s3_video_key != file_key:
            print(f"🗑️ Deleting old video: {lesson.s3_video_key}")
            delete_from_s3(lesson.s3_video_key)
        
        lesson.s3_video_key = file_key
        lesson.video_url = file_url
        
        # Update duration if provided
        if duration:
            lesson.duration = duration
        
        # Update size (either from frontend or auto-fetched from S3)
        if size:
            lesson.size = size
            
    elif file_type == 'document':
        # Delete old document if exists
        if lesson.s3_document_key and lesson.s3_document_key != file_key:
            delete_from_s3(lesson.s3_document_key)
        
        lesson.s3_document_key = file_key
        lesson.document_url = file_url
    
    db.session.commit()
    
    return jsonify({
        "message": "Upload confirmed successfully",
        "lesson": {
            "id": lesson.id,
            "title": lesson.title,
            "video_url": lesson.video_url if file_type == 'video' else None,
            "document_url": lesson.document_url if file_type == 'document' else None,
            "s3_video_key": lesson.s3_video_key if file_type == 'video' else None,
            "s3_document_key": lesson.s3_document_key if file_type == 'document' else None,
            "duration": format_duration(lesson.duration) if lesson.duration else "00:00:00",
            "size": format_size(lesson.size) if lesson.size else "0 KB"
        }
    }), 200

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

@bp.route("/<int:course_id>/publish", methods=["PATCH"])
@jwt_required()
@role_required("admin")
def publish_course(course_id):
    """Toggle course publication status"""
    course = Course.query.get_or_404(course_id)
    data = request.get_json()
    
    # Toggle or set specific value
    if data and "is_published" in data:
        course.is_published = data.get("is_published")
    else:
        # Toggle if no data provided
        course.is_published = not course.is_published
    
    db.session.commit()
    
    return jsonify({
        "message": f"Course {'published' if course.is_published else 'unpublished'} successfully",
        "course": {
            "id": course.id,
            "title": course.title,
            "is_published": course.is_published
        }
    }), 200

@bp.route("/<int:course_id>", methods=["GET"])
@jwt_required(optional=True)
def get_course(course_id):
    course = Course.query.get_or_404(course_id)
    user_id = get_jwt_identity()
    user_currency = detect_currency()

    is_paid = False
    is_enrolled = False

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

    if user_currency == "USD":
        price = convert_ngn_to_usd(course.price)
    else:
        price = course.price

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
    course = Course.query.get_or_404(course_id)
    user_id = get_jwt_identity()

    is_admin = False
    has_access = False
    
    if user_id:
        user = User.query.get(user_id)
        if user and user.role == "admin":
            is_admin = True
            has_access = True  # Admins always have access
        else:
            # Check enrollment and payment for non-admin users
            enrollment = Enrollment.query.filter_by(
                user_id=user_id,
                course_id=course.id,
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
                        Enrollment.course_id == course.id
                    )
                    .first()
                )
                if payment:
                    has_access = True

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
        "has_access": has_access,  # ✅ Tell frontend if user has access
        "is_admin": is_admin,      # ✅ Tell frontend if user is admin
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
                "duration": format_duration(lesson.duration),
                "size": format_size(lesson.size),
                "created_at": lesson.created_at.isoformat(),
                "quizzes": []
            }

            # ✅ Only show video/document URLs if user has access (paid or admin)
            if has_access:
                if lesson.s3_video_key:
                    # Generate presigned URL for S3 videos
                    presigned_url = generate_presigned_url(lesson.s3_video_key, expiration=7200)
                    lesson_data["video_url"] = presigned_url
                else:
                    lesson_data["video_url"] = lesson.video_url
                
                if lesson.s3_document_key:
                    # Generate presigned URL for S3 documents
                    presigned_url = generate_presigned_url(lesson.s3_document_key, expiration=7200)
                    lesson_data["document_url"] = presigned_url
                else:
                    lesson_data["document_url"] = lesson.document_url
            else:
                # Free users see null URLs
                lesson_data["video_url"] = None
                lesson_data["document_url"] = None

            # ✅ Include quizzes
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

    image_file = request.files.get("image")
    if image_file and allowed_file(image_file.filename, ALLOWED_IMG_EXT):
        filename = secure_filename(image_file.filename)
        image_path = os.path.join(UPLOAD_IMAGE_FOLDER, filename)
        image_file.save(image_path)
        course.image = f"/static/uploads/images/{filename}"

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
    section = Section.query.get_or_404(section_id)

    if section.course_id != course_id:
        return jsonify({"error": "Section does not belong to this course"}), 400

    data = request.get_json()  # Changed from request.form to request.get_json()
    title = data.get("title")

    if not title:
        return jsonify({"error": "Lesson title is required"}), 400

    # Create lesson with just metadata
    new_lesson = Lesson(
        title=title,
        slug=slugify(title),
        notes=data.get("notes", ""),
        reference_link=data.get("reference_link", ""),
        section=section
    )

    db.session.add(new_lesson)
    db.session.commit()

    return jsonify({
        "message": "Lesson created successfully",
        "lesson": {
            "id": new_lesson.id,
            "title": new_lesson.title,
            "slug": new_lesson.slug,
            "notes": new_lesson.notes,
            "reference_link": new_lesson.reference_link
        }
    }), 201

# MODIFIED: Update lesson metadata only
@bp.route("/lessons/<int:lesson_id>", methods=["PUT"])
@jwt_required()
@role_required("admin")
def update_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)

    data = {}
    document_file = None

    # -------- HANDLE MULTIPART FORM --------
    if request.content_type and "multipart/form-data" in request.content_type:
        # If frontend sends JSON inside a "data" field
        raw_data = request.form.get("data")
        if raw_data:
            try:
                import json
                data = json.loads(raw_data)
            except Exception:
                return jsonify({"error": "Invalid JSON in form field 'data'"}), 400
        else:
            # fallback: normal form fields
            data = request.form.to_dict()

        document_file = request.files.get("document")

    # -------- HANDLE JSON BODY --------
    elif request.is_json:
        data = request.get_json() or {}

    else:
        return jsonify({"error": "Unsupported content type"}), 400

    # -------- UPDATE METADATA --------
    if "title" in data and data["title"]:
        lesson.title = data["title"].strip()
        lesson.slug = slugify(lesson.title)

    if "notes" in data:
        lesson.notes = (data.get("notes") or "").strip()

    if "reference_link" in data:
        ref = data.get("reference_link")
        links = []

        # If frontend sends real array
        if isinstance(ref, list):
            links = [str(link).strip() for link in ref if str(link).strip()]

        # If frontend sends JSON string array: '["a.com","b.com"]'
        elif isinstance(ref, str) and ref.strip().startswith("["):
            try:
                import json
                parsed = json.loads(ref)
                if isinstance(parsed, list):
                    links = [str(link).strip() for link in parsed if str(link).strip()]
            except Exception:
                links = []

        # If frontend sends single string
        elif isinstance(ref, str) and ref.strip():
            links = [ref.strip()]
    # -------- HANDLE DOCUMENT UPLOAD --------
    if document_file and document_file.filename:
        if document_file.content_type not in ALLOWED_DOC_TYPES:
            return jsonify({"error": f"Invalid document type. Allowed: {ALLOWED_DOC_TYPES}"}), 400

        file_extension = document_file.filename.rsplit('.', 1)[1].lower() if '.' in document_file.filename else 'pdf'
        file_key = f"docs/{uuid.uuid4()}.{file_extension}"

        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )

        try:
            s3_client.upload_fileobj(
                document_file,
                AWS_S3_BUCKET_NAME,
                file_key,
                ExtraArgs={
                    'ContentType': document_file.content_type,
                    'ContentDisposition': f'attachment; filename="{secure_filename(document_file.filename)}"',
                    'CacheControl': 'max-age=31536000'
                }
            )

            # Delete old doc if exists
            if lesson.s3_document_key:
                delete_from_s3(lesson.s3_document_key)

            lesson.s3_document_key = file_key
            lesson.document_url = f"https://{AWS_S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{file_key}"

        except Exception as e:
            return jsonify({"error": f"S3 upload failed: {str(e)}"}), 500

    # -------- SAVE CHANGES --------
    db.session.commit()

    lesson.reference_link = json.dumps(links)

    return jsonify({
        "message": "Lesson updated successfully",
        "lesson": {
            "id": lesson.id,
            "title": lesson.title,
            "slug": lesson.slug,
            "video_url": lesson.video_url,
            "document_url": lesson.document_url,
            "s3_document_key": lesson.s3_document_key,
            "duration": format_duration(lesson.duration) if lesson.duration else "00:00:00",
            "size": format_size(lesson.size) if lesson.size else "0 KB",
            "notes": lesson.notes,
            "reference_link": lesson.reference_link
        }
    }), 200

@bp.route("/lessons/<int:lesson_id>", methods=["GET"])
@jwt_required(optional=True)
def get_lesson_details(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    user_id = get_jwt_identity()

    # ✅ Check if user is admin
    is_admin = False
    has_access = False

    if user_id:
        from app.models.user import User
        user = User.query.get(user_id)
        if user and user.role == "admin":
            is_admin = True
            has_access = True  # Admins always have access
        else:
            # Check enrollment and payment for non-admin users
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

    lesson_data = {
        "id": lesson.id,
        "title": lesson.title,
        "slug": lesson.slug,
        "notes": lesson.notes,
        "reference_link": lesson.reference_link,
        "duration": format_duration(lesson.duration) if lesson.duration else "00:00:00",  # ✅ ADDED
        "size": format_size(lesson.size) if lesson.size else "0 KB",  # ✅ ADDED
        "created_at": lesson.created_at.isoformat(),
        "has_access": has_access,  # ✅ Tell frontend if user has access
        "is_admin": is_admin,      # ✅ Tell frontend if user is admin
        "section": {
            "id": lesson.section.id,
            "name": lesson.section.name,
            "course_id": lesson.section.course_id
        } if lesson.section else None,
        "quizzes": []
    }

    # ✅ Show video/document URLs if user has access (paid or admin)
    if has_access:
        if lesson.s3_video_key:
            presigned_url = generate_presigned_url(lesson.s3_video_key, expiration=7200)
            lesson_data["video_url"] = presigned_url
        else:
            lesson_data["video_url"] = lesson.video_url
        
        if lesson.s3_document_key:
            presigned_url = generate_presigned_url(lesson.s3_document_key, expiration=7200)
            lesson_data["document_url"] = presigned_url
        else:
            lesson_data["document_url"] = lesson.document_url
    else:
        lesson_data["video_url"] = None
        lesson_data["document_url"] = None
        # Only show access denied if user is logged in but not paid (and not admin)
        if user_id and not is_admin:
            lesson_data["access_denied"] = "Please enroll and complete payment to access this content"

    # ✅ Include quizzes
    if hasattr(lesson, "quizzes") and lesson.quizzes:
        for quiz in lesson.quizzes:
            lesson_data["quizzes"].append({
                "id": quiz.id,
                "question": quiz.question,
                "options": quiz.options,
                "correct_answer": quiz.correct_answer,
                "quiz_type": quiz.quiz_type,  # ✅ ADDED (was missing)
                "explanation": quiz.explanation
            })

    return jsonify(lesson_data), 200

@bp.route("/<int:course_id>/sections/<int:section_id>/lessons/<int:lesson_id>", methods=["DELETE"])
@jwt_required()
@role_required("admin")
def delete_lesson(course_id, section_id, lesson_id):

    lesson = Lesson.query.get_or_404(lesson_id)
    
    # Verify lesson belongs to the specified section and course
    if lesson.section_id != section_id:
        return jsonify({"error": "Lesson does not belong to this section"}), 400
    
    if lesson.section.course_id != course_id:
        return jsonify({"error": "Section does not belong to this course"}), 400
    
    # Delete S3 files if they exist
    if lesson.s3_video_key:
        delete_from_s3(lesson.s3_video_key)
    
    if lesson.s3_document_key:
        delete_from_s3(lesson.s3_document_key)
    
    # Delete the lesson from database
    lesson_title = lesson.title
    db.session.delete(lesson)
    db.session.commit()

    return jsonify({
        "message": "Lesson deleted successfully",
        "deleted_lesson": {
            "id": lesson_id,
            "title": lesson_title
        }
    }), 200

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

    valid_types = ["multiple_choice", "true_false", "free_text"]
    if quiz_type not in valid_types:
        return jsonify({"error": f"Invalid quiz type. Must be one of {valid_types}"}), 400

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
    quiz = Quiz.query.get_or_404(quiz_id)

    if quiz.lesson_id != lesson_id:
        return jsonify({"error": "Quiz does not belong to this lesson"}), 400

    db.session.delete(quiz)
    db.session.commit()

    return jsonify({"message": "Quiz deleted successfully"}), 200

@bp.route("/lessons/<int:lesson_id>/document", methods=["GET"])
@jwt_required(optional=True)
def download_lesson_document(lesson_id):
    lesson = Lesson.query.get(lesson_id)

    if not lesson:
        return jsonify({"error": "Lesson not found"}), 404

    if not lesson.document_url:
        return jsonify({"message": "No document available"}), 200
    
    user_id = get_jwt_identity()
    
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
    
    if lesson.s3_document_key:
        presigned_url = generate_presigned_url(lesson.s3_document_key, expiration=3600)
        if presigned_url:
            return jsonify({
                "download_url": presigned_url,
                "expires_in": 3600
            }), 200
        else:
            return jsonify({"error": "Failed to generate download link"}), 500
    
    filename = os.path.basename(lesson.document_url)
    directory = os.path.join(current_app.root_path, '..', 'static', 'uploads', 'docs')
    directory = os.path.abspath(directory)
    
    if not os.path.exists(os.path.join(directory, filename)):
        return jsonify({"error": "File not found"}), 404
    
    try:
        return send_from_directory(directory, filename, as_attachment=True)
    except Exception as e:
        return jsonify({"error": f"Error sending file: {str(e)}"}), 500