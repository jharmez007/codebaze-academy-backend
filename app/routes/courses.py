from flask import Blueprint, request, jsonify
from app.extensions import db
from werkzeug.utils import secure_filename
from app.models import Course, Lesson
from app.models.course import Section
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth import role_required
import json
from moviepy import VideoFileClip
import os, uuid, re

UPLOAD_VIDEO_FOLDER = os.path.join("static", "uploads", "videos")
UPLOAD_IMAGE_FOLDER = os.path.join("static", "uploads", "images")
UPLOAD_DOC_FOLDER = os.path.join("static", "uploads", "docs")
# Make sure the folders exist
os.makedirs(UPLOAD_VIDEO_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_DOC_FOLDER, exist_ok=True)
ALLOWED_VIDEO_EXT = {"mp4", "mov", "avi", "mkv", "mp3"}
ALLOWED_DOC_EXT = {"pdf", "docx", "pptx"}
ALLOWED_IMG_EXT = {"png", "jpg", "jpeg", "gif"}

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

# Get details of a single course
@bp.route("/<int:course_id>", methods=["GET"])
@jwt_required(optional=True)  # allow public view
def get_course(course_id):
    course = Course.query.get_or_404(course_id)

    response = {
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "long_description": course.long_description,
        "price": course.price,
        "is_published": course.is_published,
        "total_lessons": course.total_lessons,
        "created_at": course.created_at.isoformat(),
        "image": course.image,
        "sections": []
    }

    for sub in course.sections:
        sub_data = {"id": sub.id, "name": sub.name, "description": sub.description, "lessons": []}

        for lesson in sub.lessons:
            lesson_data = {"id": lesson.id, "title": lesson.title}
            sub_data["lessons"].append(lesson_data)

        response["sections"].append(sub_data)

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
#     sections_data = data.get("sections", [])
    

#     if not all([title, description, price]):
#         return jsonify({"error": "Missing fields"}), 400

#     course = Course(title=title, description=description, price=price, is_published=True)

#     # Build sections & lessons
#     for i, sub in enumerate(sections_data):
#         sections = SubCategory(name=sub["name"], course=course)

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
#             sections.lessons.append(lesson)

#         course.sections.append(sections)

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
                section=section   # ✅ link to Section, not Course
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
        sections=sections
    )

    db.session.add(lesson)
    db.session.commit()

    return jsonify({"message": "Lesson added", "lesson_id": lesson.id}), 201
# Update a course (admin only)
# @bp.route("/<int:course_id>", methods=["PUT"])
# @jwt_required()
# @role_required("admin")
# def update_course(course_id):
#     course = Course.query.get_or_404(course_id)

#     # Get form data (consistent with create_course)
#     raw_data = request.form.get("data")
#     if not raw_data:
#         return jsonify({"error": "Missing course data"}), 400

#     try:
#         data = json.loads(raw_data)
#     except:
#         return jsonify({"error": "Invalid JSON format"}), 400

#     # Update fields if provided
#     course.title = data.get("title", course.title)
#     course.description = data.get("description", course.description)
#     course.price = data.get("price", course.price)
#     # course.is_published = data.get("is_published", course.is_published)

#     # Handle new image if uploaded
#     image_file = request.files.get("image")
#     if image_file and allowed_file(image_file.filename, ALLOWED_IMG_EXT):
#         filename = secure_filename(image_file.filename)
#         image_path = os.path.join(UPLOAD_IMAGE_FOLDER, filename)
#         image_file.save(image_path)
#         course.image = image_path  # update image path

#     db.session.commit()

#     return jsonify({
#         "message": "Course updated",
#         "id": course.id,
#         "title": course.title,
#         "description": course.description,
#         "price": course.price,
#         "is_published": course.is_published,
#         "image": course.image
#     }), 200

# # Delete a course (admin only)
# @bp.route("/<int:course_id>", methods=["DELETE"])
# @jwt_required()
# @role_required("admin")
# def delete_course(course_id):
#     course = Course.query.get_or_404(course_id)
#     db.session.delete(course)
#     db.session.commit()
#     return jsonify({"message": "Course deleted"})

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

    # Update base fields
    course.title = data.get("title", course.title)
    course.description = data.get("description", course.description)
    course.price = data.get("price", course.price)
    course.long_description = data.get("long_description", course.long_description)

    # Handle new course image if uploaded
    image_file = request.files.get("image")
    if image_file and allowed_file(image_file.filename, ALLOWED_IMG_EXT):
        filename = secure_filename(image_file.filename)
        image_path = os.path.join(UPLOAD_IMAGE_FOLDER, filename)
        image_file.save(image_path)
        course.image = image_path

    # Handle sections & lessons
    sections_data = data.get("sections", [])
    for i, sub in enumerate(sections_data):
        section_id = sub.get("id")
        if section_id:
            section = Section.query.filter_by(id=section_id, course_id=course.id).first()
            if section:
                # update existing section
                section.name = sub.get("name", section.name)
                section.description = sub.get("description", section.description)
            else:
                continue
        else:
            # create new section
            section = Section(
                name=sub["name"],
                slug=slugify(sub["name"]),
                description=sub.get("description", ""),
                course=course
            )
            db.session.add(section)

        # Handle lessons
        for j, lesson_data in enumerate(sub.get("lessons", [])):
            lesson_id = lesson_data.get("id")
            if lesson_id:
                lesson = Lesson.query.filter_by(id=lesson_id, section_id=section.id).first()
                if lesson:
                    lesson.title = lesson_data.get("title", lesson.title)
                    lesson.notes = lesson_data.get("notes", lesson.notes)
                    lesson.reference_link = lesson_data.get("reference_link", lesson.reference_link)
                else:
                    continue
            else:
                # Create new lesson
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

    return jsonify({"message": "Course and related data updated"}), 200

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
