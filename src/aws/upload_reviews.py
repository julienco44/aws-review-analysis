#!/usr/bin/env python3
"""
Script to upload sample reviews to S3 bucket to trigger the Lambda processing chain
"""

import boto3
import json
import os
import sys
from botocore.exceptions import ClientError

# Configure for LocalStack
os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

def get_s3_client():
    """Get S3 client configured for LocalStack"""
    return boto3.client(
        's3',
        endpoint_url='http://localhost:4566',
        aws_access_key_id='test',
        aws_secret_access_key='test',
        region_name='us-east-1'
    )

def load_sample_reviews():
    """Load sample reviews from the devset"""
    try:
        reviews = []
        with open('../../Data/reviews_devset.json', 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    review = json.loads(line)
                    reviews.append(review)
        return reviews
    except FileNotFoundError:
        print("Error: ../../Data/reviews_devset.json not found")
        return []
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in reviews_devset.json: {e}")
        return []

def upload_reviews_to_s3(reviews, bucket_name='review-analysis-reviews', max_reviews=10):
    """Upload reviews to S3 bucket to trigger Lambda processing"""
    s3_client = get_s3_client()
    
    # Check if bucket exists
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except ClientError:
        print(f"Error: Bucket '{bucket_name}' does not exist")
        print("Please run the deployment script first to create the infrastructure")
        return False
    
    uploaded_count = 0
    failed_count = 0
    
    print(f"Uploading {min(len(reviews), max_reviews)} reviews to bucket '{bucket_name}'...")
    
    for i, review in enumerate(reviews[:max_reviews]):
        try:
            # Create a unique key for each review
            reviewer_id = review.get('reviewerID', f'reviewer_{i}')
            asin = review.get('asin', f'product_{i}')
            key = f"reviews/{reviewer_id}_{asin}_{i}.json"
            
            # Upload the review
            s3_client.put_object(
                Bucket=bucket_name,
                Key=key,
                Body=json.dumps(review),
                ContentType='application/json'
            )
            
            uploaded_count += 1
            print(f"Uploaded review {i+1}/{min(len(reviews), max_reviews)}: {key}")
            
        except Exception as e:
            failed_count += 1
            print(f"Failed to upload review {i+1}: {e}")
    
    print(f"\nUpload Summary:")
    print(f"  Successfully uploaded: {uploaded_count}")
    print(f"  Failed: {failed_count}")
    print(f"\nReviews uploaded to trigger Lambda processing chain.")
    
    return uploaded_count > 0

def main():
    """Main function"""
    print("AWS Review Analysis - Upload Reviews Script")
    print("=" * 50)
    
    # Parse command line arguments
    max_reviews = 10
    if len(sys.argv) > 1:
        try:
            max_reviews = int(sys.argv[1])
        except ValueError:
            print("Error: Invalid number of reviews specified")
            print("Usage: python upload_reviews.py [number_of_reviews]")
            sys.exit(1)
    
    # Load sample reviews
    print("Loading sample reviews...")
    reviews = load_sample_reviews()
    
    if not reviews:
        print("No reviews found to upload")
        sys.exit(1)
    
    print(f"Found {len(reviews)} reviews in dataset")
    
    # Upload reviews
    success = upload_reviews_to_s3(reviews, max_reviews=max_reviews)
    
    if success:
        print("\n✅ Reviews uploaded successfully!")
        print("Check the Lambda logs to see the processing chain in action.")
    else:
        print("\n❌ Failed to upload reviews")
        sys.exit(1)

if __name__ == "__main__":
    main() 