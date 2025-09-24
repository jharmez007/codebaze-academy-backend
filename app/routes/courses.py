from flask import Blueprint, request, jsonify
from app.extensions import db
from werkzeug.utils import secure_filename
from app.models import Course, Lesson
from app.models.course import SubCategory
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth import role_required
import json
from moviepy import VideoFileClip
import os, uuid, re

UPLOAD_VIDEO_FOLDER = os.path.join("static", "uploads", "videos")
UPLOAD_DOC_FOLDER = os.path.join("static", "uploads", "docs")
# Make sure the folders exist
os.makedirs(UPLOAD_VIDEO_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_DOC_FOLDER, exist_ok=True)
ALLOWED_VIDEO_EXT = {"mp4", "mov", "avi", "mkv", "mp3"}
ALLOWED_DOC_EXT = {"pdf", "docx", "pptx"}

def allowed_file(filename, allowed_ext):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_ext

def get_video_metadata(path):
    try:
        clip = VideoFileClip(path)
        duration = int(clip.duration)  # in seconds
        clip.reader.close()
        clip.audio.reader.close_proc()
        size = os.path.getsize(path)  # in bytes
        return duration, size
    except Exception as e:
        print("Video analysis error:", e)
        return None, None
    
def slugify(text):
    text = re.sub(r'[^a-zA-Z0-9]+', '-', text)
    return text.strip('-').lower()

bp = Blueprint("courses", __name__)

# List all published courses
@bp.route("/", methods=["GET"])
def list_courses():
    courses = Course.query.filter_by(is_published=True).all()
    result = []
    for c in courses:
        result.append({
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "price": c.price,
            "created_at": c.created_at.isoformat()
        })
    return jsonify(result)

# Get details of a single course
@bp.route("/<int:course_id>", methods=["GET"])
@jwt_required(optional=True)  # allow public view
def get_course(course_id):
    course = Course.query.get_or_404(course_id)

    response = {
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "price": course.price,
        "is_published": course.is_published,
        "created_at": course.created_at.isoformat(),
        "subcategories": []
    }

    for sub in course.subcategories:
        sub_data = {"id": sub.id, "name": sub.name, "lessons": []}

        for lesson in sub.lessons:
            lesson_data = {"id": lesson.id, "title": lesson.title}
            sub_data["lessons"].append(lesson_data)

        response["subcategories"].append(sub_data)

    return jsonify(response)

# Create a course (admin only)
# @bp.route("/", methods=["POST"])
# @jwt_required()
# @role_required("admin")
# def create_course():
#     # Expect JSON metadata in `form` field
#     data = request.form.get("data")
#     if not data:
#         return jsonify({"error": "Missing course data"}), 400
    
#     try:
#         data = json.loads(data)
#     except:
#         # print("RAW DATA:", request.form.get("data"))
#         return jsonify({"error": "Invalid JSON format"}), 400

#     title = data.get("title")
#     description = data.get("description")
#     price = data.get("price")
#     subcategories_data = data.get("subcategories", [])
    

#     if not all([title, description, price]):
#         return jsonify({"error": "Missing fields"}), 400

#     course = Course(title=title, description=description, price=price, is_published=True)

#     # Build subcategories & lessons
#     for i, sub in enumerate(subcategories_data):
#         subcategory = SubCategory(name=sub["name"], course=course)

#         for j, lesson_data in enumerate(sub.get("lessons", [])):
#             # Handle file uploads
#             video_file = request.files.get(f"sub_{i}_lesson_{j}_video")
#             doc_file = request.files.get(f"sub_{i}_lesson_{j}_doc")

#             video_path, doc_path = None, None

#             if video_file and allowed_file(video_file.filename, ALLOWED_VIDEO_EXT):
#                 filename = secure_filename(video_file.filename)
#                 video_path = os.path.join(UPLOAD_VIDEO_FOLDER, filename)
#                 video_file.save(video_path)

#             if doc_file and allowed_file(doc_file.filename, ALLOWED_DOC_EXT):
#                 filename = secure_filename(doc_file.filename)
#                 doc_path = os.path.join(UPLOAD_DOC_FOLDER, filename)
#                 doc_file.save(doc_path)

#             lesson = Lesson(
#                 title=lesson_data["title"],
#                 notes=lesson_data.get("notes"),
#                 reference_link=lesson_data.get("references"),
#                 video_url=video_path,
#                 document_url=doc_path,
#                 course=course
#             )
#             subcategory.lessons.append(lesson)

#         course.subcategories.append(subcategory)

#     db.session.add(course)
#     db.session.commit()

#     return jsonify({"message": "Course created", "id": course.id}), 201

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
    price = data.get("price")
    subcategories_data = data.get("subcategories", [])

    if not all([title, description, price]):
        return jsonify({"error": "Missing fields"}), 400

    # Handle course image
    image_file = request.files.get("image")
    image_path = None
    if image_file and allowed_file(image_file.filename, ALLOWED_IMG_EXT):  # e.g. jpg/png
        filename = secure_filename(image_file.filename)
        image_path = os.path.join(UPLOAD_IMAGE_FOLDER, filename)
        image_file.save(image_path)

    # Create course with slug (published = False initially)
    course = Course(
        title=title,
        description=description,
        price=price,
        slug=slugify(title),
        image=image_path,
        is_published=False
    )

    # Build subcategories & lessons
    for i, sub in enumerate(subcategories_data):
        subcategory = SubCategory(
            name=sub["name"],
            slug=slugify(sub["name"]),
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

                # Analyze video
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
                course=course
            )
            subcategory.lessons.append(lesson)

        course.subcategories.append(subcategory)

    db.session.add(course)
    db.session.commit()

    return jsonify({
        "message": "Course created",
        "id": course.id,
        "slug": course.slug,
        "title": course.title,
        "image": course.image,
        "is_published": course.is_published,
        "subcategories": [
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
            } for sub in course.subcategories
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
    subcategory = SubCategory.query.get(subcategory_id)
    if not subcategory or subcategory.course_id != course_id:
        return jsonify({"error": "Invalid subcategory"}), 400

    # Handle file uploads
    video_file = request.files.get("video")
    doc_file = request.files.get("document")

    video_path, doc_path = None, None

    if video_file and allowed_file(video_file.filename, ALLOWED_VIDEO_EXT):
        filename = secure_filename(video_file.filename)
        video_path = os.path.join(UPLOAD_VIDEO_FOLDER, filename)
        video_file.save(video_path)

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
        course=course,
        subcategory=subcategory
    )

    db.session.add(lesson)
    db.session.commit()

    return jsonify({"message": "Lesson added", "lesson_id": lesson.id}), 201
# Update a course (admin only)
@bp.route("/<int:course_id>", methods=["PUT"])
@jwt_required()
@role_required("admin")
def update_course(course_id):
    course = Course.query.get_or_404(course_id)
    data = request.get_json()
    course.title = data.get("title", course.title)
    course.description = data.get("description", course.description)
    course.price = data.get("price", course.price)
    course.is_published = data.get("is_published", course.is_published)
    db.session.commit()
    return jsonify({"message": "Course updated"})

# Delete a course (admin only)
@bp.route("/<int:course_id>", methods=["DELETE"])
@jwt_required()
@role_required("admin")
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    return jsonify({"message": "Course deleted"})
