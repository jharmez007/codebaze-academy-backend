"""
AWS S3 Helper Utilities
Handles file uploads, downloads, and presigned URL generation for S3
"""

import boto3
import os
import uuid
from botocore.exceptions import ClientError
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# AWS Configuration
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-2')
AWS_S3_BUCKET_NAME = os.getenv('AWS_S3_BUCKET_NAME')

# Optional CloudFront domain for faster delivery
AWS_CLOUDFRONT_DOMAIN = os.getenv('AWS_CLOUDFRONT_DOMAIN', None)


class S3Helper:
    """Helper class for S3 operations"""
    
    def __init__(self):
        """Initialize S3 client"""
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
        self.bucket_name = AWS_S3_BUCKET_NAME
        self.cloudfront_domain = AWS_CLOUDFRONT_DOMAIN
    
    def upload_file(self, file_obj, folder='videos', filename=None):
        """
        Upload a file to S3
        
        Args:
            file_obj: File object from Flask request.files
            folder: Folder path in S3 (e.g., 'videos', 'images', 'docs')
            filename: Optional custom filename. If None, generates unique filename
        
        Returns:
            dict: {
                'success': bool,
                'file_key': str,  # S3 object key
                'file_url': str,  # Full S3 URL or CloudFront URL
                'error': str      # Error message if failed
            }
        """
        try:
            # Generate unique filename if not provided
            if filename is None:
                original_filename = secure_filename(file_obj.filename)
                file_extension = original_filename.rsplit('.', 1)[1].lower()
                filename = f"{uuid.uuid4()}.{file_extension}"
            else:
                filename = secure_filename(filename)
            
            # Create S3 key (path in bucket)
            file_key = f"{folder}/{filename}"
            
            # Determine content type based on file extension
            content_type = self._get_content_type(filename)
            
            # Upload to S3
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                file_key,
                ExtraArgs={
                    'ContentType': content_type,
                    'CacheControl': 'max-age=31536000',  # Cache for 1 year
                }
            )
            
            # Generate URL
            if self.cloudfront_domain:
                file_url = f"https://{self.cloudfront_domain}/{file_key}"
            else:
                file_url = f"https://{self.bucket_name}.s3.{AWS_REGION}.amazonaws.com/{file_key}"
            
            return {
                'success': True,
                'file_key': file_key,
                'file_url': file_url,
                'error': None
            }
        
        except ClientError as e:
            print(f"S3 upload error: {str(e)}")
            return {
                'success': False,
                'file_key': None,
                'file_url': None,
                'error': str(e)
            }
        except Exception as e:
            print(f"Unexpected error during upload: {str(e)}")
            return {
                'success': False,
                'file_key': None,
                'file_url': None,
                'error': str(e)
            }
    
    def generate_presigned_url(self, file_key, expiration=3600):
        """
        Generate a presigned URL for secure file access
        Users can access the file using this URL for a limited time
        
        Args:
            file_key: S3 object key (e.g., 'videos/abc123.mp4')
            expiration: URL expiration time in seconds (default: 1 hour)
        
        Returns:
            str: Presigned URL or None if error
        """
        try:
            # If using CloudFront, generate CloudFront signed URL
            # For simplicity, we'll use S3 presigned URLs
            # You can implement CloudFront signed URLs for production
            
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': file_key
                },
                ExpiresIn=expiration
            )
            return url
        
        except ClientError as e:
            print(f"Error generating presigned URL: {str(e)}")
            return None
    
    def delete_file(self, file_key):
        """
        Delete a file from S3
        
        Args:
            file_key: S3 object key to delete
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=file_key
            )
            return True
        
        except ClientError as e:
            print(f"Error deleting file: {str(e)}")
            return False
    
    def get_file_size(self, file_key):
        """
        Get the size of a file in S3
        
        Args:
            file_key: S3 object key
        
        Returns:
            int: File size in bytes, or None if error
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=file_key
            )
            return response['ContentLength']
        
        except ClientError as e:
            print(f"Error getting file size: {str(e)}")
            return None
    
    def file_exists(self, file_key):
        """
        Check if a file exists in S3
        
        Args:
            file_key: S3 object key
        
        Returns:
            bool: True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=file_key
            )
            return True
        except ClientError:
            return False
    
    def _get_content_type(self, filename):
        """
        Determine content type based on file extension
        
        Args:
            filename: Name of the file
        
        Returns:
            str: MIME type
        """
        extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        content_types = {
            # Videos
            'mp4': 'video/mp4',
            'mov': 'video/quicktime',
            'avi': 'video/x-msvideo',
            'mkv': 'video/x-matroska',
            'webm': 'video/webm',
            'mp3': 'audio/mpeg',
            
            # Documents
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            
            # Images
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp',
        }
        
        return content_types.get(extension, 'application/octet-stream')


# Create a singleton instance
s3_helper = S3Helper()


# Convenience functions for direct import
def upload_to_s3(file_obj, folder='videos', filename=None):
    """Upload a file to S3"""
    return s3_helper.upload_file(file_obj, folder, filename)


def generate_presigned_url(file_key, expiration=3600):
    """Generate presigned URL for file access"""
    return s3_helper.generate_presigned_url(file_key, expiration)


def delete_from_s3(file_key):
    """Delete a file from S3"""
    return s3_helper.delete_file(file_key)


def get_s3_file_size(file_key):
    """Get file size from S3"""
    return s3_helper.get_file_size(file_key)


def s3_file_exists(file_key):
    """Check if file exists in S3"""
    return s3_helper.file_exists(file_key)