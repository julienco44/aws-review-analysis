import boto3
import json
import os
from pathlib import Path

def upload_reviews():
    """Upload reviews from the devset to S3 for testing"""
    
    # Initialize S3 client for LocalStack
    s3 = boto3.client('s3', endpoint_url='http://localhost:4566')
    
    # Configuration
    reviews_bucket = "review-analysis-reviews"
    devset_file = Path("../../Data/reviews_devset.json")
    
    try:
        # Check if bucket exists
        s3.head_bucket(Bucket=reviews_bucket)
        print(f"Found bucket: {reviews_bucket}")
    except Exception as e:
        print(f"Bucket {reviews_bucket} not found. Please run the deployment script first.")
        return
    
    # Load reviews from devset
    if not devset_file.exists():
        print(f"Devset file not found: {devset_file}")
        return
    
    with open(devset_file, 'r') as f:
        reviews = json.load(f)
    
    print(f"Loaded {len(reviews)} reviews from devset")
    
    # Upload each review individually
    for i, review in enumerate(reviews):
        review_key = f"review_{i+1:03d}_{review['reviewerID']}_{review['asin']}.json"
        
        try:
            s3.put_object(
                Bucket=reviews_bucket,
                Key=review_key,
                Body=json.dumps(review),
                ContentType='application/json'
            )
            print(f"Uploaded: {review_key}")
        except Exception as e:
            print(f"Error uploading {review_key}: {e}")
    
    print(f"\nSuccessfully uploaded {len(reviews)} reviews to {reviews_bucket}")
    print("The Lambda function chain should now process these reviews automatically.")

def upload_single_review(review_data, review_name="test_review"):
    """Upload a single review for testing"""
    
    s3 = boto3.client('s3', endpoint_url='http://localhost:4566')
    reviews_bucket = "review-analysis-reviews"
    
    try:
        s3.head_bucket(Bucket=reviews_bucket)
    except Exception as e:
        print(f"Bucket {reviews_bucket} not found. Please run the deployment script first.")
        return
    
    review_key = f"{review_name}_{review_data['reviewerID']}_{review_data['asin']}.json"
    
    try:
        s3.put_object(
            Bucket=reviews_bucket,
            Key=review_key,
            Body=json.dumps(review_data),
            ContentType='application/json'
        )
        print(f"Uploaded: {review_key}")
    except Exception as e:
        print(f"Error uploading {review_key}: {e}")

def main():
    """Main function"""
    print("Review Upload Script")
    print("=" * 30)
    
    # Upload all reviews from devset
    upload_reviews()
    
    # Example: Upload a single test review
    print("\n" + "=" * 30)
    print("Uploading additional test review...")
    
    test_review = {
        "reviewerID": "TEST_SINGLE_USER",
        "asin": "B000999999",
        "reviewerName": "Test Single User",
        "helpful": [1, 1],
        "reviewText": "This is a test review with some profanity. This product is shit and I hate it!",
        "overall": 1.0,
        "summary": "Terrible test product",
        "unixReviewTime": 1640995300,
        "reviewTime": "01 1, 2022"
    }
    
    upload_single_review(test_review, "single_test")

if __name__ == "__main__":
    main() 