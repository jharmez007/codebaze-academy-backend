"""
Quick Test Script for AWS S3 Integration

This script helps you verify your S3 setup is working correctly.

Usage:
    python test_s3_connection.py
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_env_variables():
    """Test if all required environment variables are set"""
    print("\n" + "="*60)
    print("STEP 1: Checking Environment Variables")
    print("="*60)
    
    required_vars = [
        'AWS_ACCESS_KEY_ID',
        'AWS_SECRET_ACCESS_KEY',
        'AWS_REGION',
        'AWS_S3_BUCKET_NAME'
    ]
    
    all_set = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            if 'SECRET' in var or 'KEY' in var:
                display_value = value[:4] + '*' * (len(value) - 8) + value[-4:]
            else:
                display_value = value
            print(f"✅ {var}: {display_value}")
        else:
            print(f"❌ {var}: NOT SET")
            all_set = False
    
    if not all_set:
        print("\n⚠️  Some environment variables are missing!")
        print("Please check your .env file")
        return False
    
    print("\n✅ All environment variables are set correctly!")
    return True


def test_s3_connection():
    """Test connection to S3"""
    print("\n" + "="*60)
    print("STEP 2: Testing S3 Connection")
    print("="*60)
    
    try:
        import boto3
        from botocore.exceptions import ClientError
        
        # Create S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION')
        )
        
        bucket_name = os.getenv('AWS_S3_BUCKET_NAME')
        
        # Try to access the bucket
        response = s3_client.head_bucket(Bucket=bucket_name)
        print(f"✅ Successfully connected to bucket: {bucket_name}")
        print(f"   Region: {os.getenv('AWS_REGION')}")
        
        return True
        
    except ImportError:
        print("❌ boto3 is not installed")
        print("   Run: pip install boto3")
        return False
    
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            print(f"❌ Bucket '{bucket_name}' does not exist")
            print("   Please create the bucket in AWS Console")
        elif error_code == '403':
            print(f"❌ Access denied to bucket '{bucket_name}'")
            print("   Check your IAM user permissions")
        else:
            print(f"❌ Error: {e}")
        return False
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_bucket_permissions():
    """Test if we can write to the bucket"""
    print("\n" + "="*60)
    print("STEP 3: Testing Bucket Permissions")
    print("="*60)
    
    try:
        import boto3
        from botocore.exceptions import ClientError
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION')
        )
        
        bucket_name = os.getenv('AWS_S3_BUCKET_NAME')
        test_key = 'test/connection-test.txt'
        test_content = b'S3 connection test successful!'
        
        # Try to upload a test file
        print(f"📤 Uploading test file to: {test_key}")
        s3_client.put_object(
            Bucket=bucket_name,
            Key=test_key,
            Body=test_content,
            ContentType='text/plain'
        )
        print("✅ Upload successful!")
        
        # Try to read it back
        print(f"📥 Downloading test file...")
        response = s3_client.get_object(Bucket=bucket_name, Key=test_key)
        downloaded_content = response['Body'].read()
        
        if downloaded_content == test_content:
            print("✅ Download successful!")
        else:
            print("⚠️  Downloaded content doesn't match")
        
        # Clean up - delete test file
        print(f"🗑️  Cleaning up test file...")
        s3_client.delete_object(Bucket=bucket_name, Key=test_key)
        print("✅ Cleanup successful!")
        
        print("\n✅ All permissions are working correctly!")
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'AccessDenied':
            print("❌ Access denied - check IAM permissions")
            print("   Your IAM user needs: s3:PutObject, s3:GetObject, s3:DeleteObject")
        else:
            print(f"❌ Error: {e}")
        return False
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_presigned_url():
    """Test presigned URL generation"""
    print("\n" + "="*60)
    print("STEP 4: Testing Presigned URL Generation")
    print("="*60)
    
    try:
        import boto3
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION')
        )
        
        bucket_name = os.getenv('AWS_S3_BUCKET_NAME')
        test_key = 'test/presigned-url-test.txt'
        
        # Upload a test file first
        s3_client.put_object(
            Bucket=bucket_name,
            Key=test_key,
            Body=b'Testing presigned URLs',
            ContentType='text/plain'
        )
        
        # Generate presigned URL
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': test_key},
            ExpiresIn=3600
        )
        
        print("✅ Presigned URL generated successfully!")
        print(f"   URL: {url[:80]}...")
        print(f"   Expires in: 1 hour")
        
        # Clean up
        s3_client.delete_object(Bucket=bucket_name, Key=test_key)
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def print_summary(results):
    """Print test summary"""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    all_passed = all(results.values())
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print("="*60)
    
    if all_passed:
        print("\n🎉 SUCCESS! Your S3 integration is ready to use!")
        print("\nNext steps:")
        print("1. Update your Lesson model with s3_video_key and s3_document_key fields")
        print("2. Run database migration")
        print("3. Replace your courses.py with the updated version")
        print("4. Start uploading videos!")
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
        print("\nCommon solutions:")
        print("- Check your .env file has correct credentials")
        print("- Verify bucket exists in AWS Console")
        print("- Check IAM user has S3 permissions")
        print("- Ensure bucket is in the correct region")


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("AWS S3 INTEGRATION TEST")
    print("="*60)
    print("\nThis script will test your S3 setup step by step")
    
    results = {}
    
    # Test 1: Environment variables
    results['Environment Variables'] = test_env_variables()
    if not results['Environment Variables']:
        print("\n❌ Cannot proceed without environment variables")
        return
    
    # Test 2: S3 Connection
    results['S3 Connection'] = test_s3_connection()
    if not results['S3 Connection']:
        print("\n❌ Cannot proceed without S3 connection")
        return
    
    # Test 3: Bucket permissions
    results['Bucket Permissions'] = test_bucket_permissions()
    
    # Test 4: Presigned URLs
    results['Presigned URLs'] = test_presigned_url()
    
    # Print summary
    print_summary(results)


if __name__ == "__main__":
    main()