"""
Direct S3 Upload - Generate Presigned POST URLs

This allows the frontend to upload files DIRECTLY to S3,
bypassing your Flask server completely.

Add these routes to your courses.py
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app.utils.auth import role_required
import boto3
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
AWS_S3_BUCKET_NAME = os.getenv('AWS_S3_BUCKET_NAME')

bp = Blueprint("upload", __name__)

# ALLOWED file types
ALLOWED_VIDEO_TYPES = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska']
ALLOWED_DOC_TYPES = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']


@bp.route("/generate-upload-url", methods=["POST"])
@jwt_required()
@role_required("admin")
def generate_upload_url():
    """
    Generate a presigned POST URL for direct S3 upload from browser.
    
    Request body:
    {
        "filename": "my-video.mp4",
        "filetype": "video/mp4",
        "folder": "videos"  // optional, defaults to "videos"
    }
    
    Returns:
    {
        "upload_url": "https://bucket.s3.amazonaws.com/",
        "fields": {
            "key": "videos/abc123.mp4",
            "AWSAccessKeyId": "...",
            "policy": "...",
            "signature": "..."
        },
        "file_key": "videos/abc123.mp4",
        "file_url": "https://bucket.s3.amazonaws.com/videos/abc123.mp4"
    }
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
    
    # Create S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )
    
    # Generate presigned POST URL
    # This allows the browser to upload directly to S3
    try:
        presigned_post = s3_client.generate_presigned_post(
            Bucket=AWS_S3_BUCKET_NAME,
            Key=file_key,
            Fields={
                'Content-Type': filetype,
                'Cache-Control': 'max-age=31536000',
            },
            Conditions=[
                {'Content-Type': filetype},
                ['content-length-range', 0, 10737418240],  # Max 10GB
            ],
            ExpiresIn=3600  # URL expires in 1 hour
        )
        
        # Generate the final file URL
        file_url = f"https://{AWS_S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{file_key}"
        
        return jsonify({
            'upload_url': presigned_post['url'],
            'fields': presigned_post['fields'],
            'file_key': file_key,
            'file_url': file_url
        }), 200
    
    except Exception as e:
        print(f"Error generating presigned POST: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/confirm-upload", methods=["POST"])
@jwt_required()
@role_required("admin")
def confirm_upload():
    """
    After frontend uploads to S3, call this to save the video metadata.
    
    Request body:
    {
        "lesson_id": 123,
        "file_key": "videos/abc123.mp4",
        "file_url": "https://bucket.s3.amazonaws.com/videos/abc123.mp4",
        "file_type": "video",  // "video" or "document"
        "duration": 125.5,  // optional, can be calculated in frontend
        "size": 52428800  // optional, file size in bytes
    }
    """
    from app.models import Lesson
    from app.extensions import db
    
    data = request.get_json()
    
    if not data or not data.get('lesson_id') or not data.get('file_key'):
        return jsonify({"error": "lesson_id and file_key are required"}), 400
    
    lesson_id = data.get('lesson_id')
    file_key = data.get('file_key')
    file_url = data.get('file_url')
    file_type = data.get('file_type', 'video')
    duration = data.get('duration')
    size = data.get('size')
    
    # Get lesson
    lesson = Lesson.query.get(lesson_id)
    if not lesson:
        return jsonify({"error": "Lesson not found"}), 404
    
    # Update lesson with S3 info
    if file_type == 'video':
        lesson.s3_video_key = file_key
        lesson.video_url = file_url
        if duration:
            lesson.duration = duration
        if size:
            lesson.size = size
    elif file_type == 'document':
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
            "s3_document_key": lesson.s3_document_key if file_type == 'document' else None
        }
    }), 200