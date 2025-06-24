# Review Analysis System - Setup and Execution Instructions

## Overview
This document provides step-by-step instructions for setting up and running the serverless review analysis system that performs preprocessing, profanity checking, and sentiment analysis on customer reviews.

## Prerequisites

### 1. Environment Setup
- Python 3.8 or higher
- LocalStack running locally
- AWS CLI configured for LocalStack
- Required Python packages (see requirements.txt)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. LocalStack Configuration
Ensure LocalStack is running with the following services enabled:
- S3
- DynamoDB
- Lambda
- IAM

Start LocalStack with:
```bash
localstack start
```

## System Architecture

The system consists of three Lambda functions in a chain:

1. **Preprocessing Lambda** (`preprocessing_lambda.py`)
   - Triggered by S3 object creation in reviews bucket
   - Performs text preprocessing (tokenization, stop word removal, lemmatization)
   - Outputs to processed bucket

2. **Profanity Check Lambda** (`profanity_check_lambda.py`)
   - Triggered by S3 object creation in processed bucket
   - Checks for profanity in review text and summary
   - Tracks user profanity count and bans users with >3 profane reviews
   - Outputs to profanity bucket

3. **Sentiment Analysis Lambda** (`sentiment_analysis_lambda.py`)
   - Triggered by S3 object creation in profanity bucket
   - Performs sentiment analysis using TextBlob
   - Considers text, summary, and rating for final sentiment
   - Outputs to sentiment bucket

## Deployment Instructions

### Step 1: Deploy the System
```bash
cd src/aws
python deploy_review_analysis.py
```

This script will:
- Create S3 buckets for reviews, processed data, profanity results, and sentiment results
- Create DynamoDB tables for tracking reviews and users
- Create Lambda layers with required dependencies (NLTK, TextBlob)
- Deploy Lambda functions
- Set up S3 triggers to chain the functions

### Step 2: Verify Deployment
Check that all resources were created successfully:
```bash
# List S3 buckets
aws --endpoint-url=http://localhost:4566 s3 ls

# List DynamoDB tables
aws --endpoint-url=http://localhost:4566 dynamodb list-tables

# List Lambda functions
aws --endpoint-url=http://localhost:4566 lambda list-functions
```

## Testing Instructions

### Step 1: Run Integration Tests
```bash
cd src/tests
python test_review_analysis.py
```

This will run comprehensive tests including:
- Preprocessing function test
- Profanity check function test
- Sentiment analysis function test
- User banning functionality test
- Complete function chain test

### Step 2: Test with Sample Data
Upload reviews to the reviews bucket:
```bash
# Upload individual review
aws --endpoint-url=http://localhost:4566 s3 cp ../../Data/reviews_devset.json s3://review-analysis-reviews/

# Or upload individual reviews from the devset
python -c "
import json
import boto3
s3 = boto3.client('s3', endpoint_url='http://localhost:4566')
with open('../../Data/reviews_devset.json', 'r') as f:
    reviews = json.load(f)
for i, review in enumerate(reviews):
    s3.put_object(
        Bucket='review-analysis-reviews',
        Key=f'review_{i}.json',
        Body=json.dumps(review),
        ContentType='application/json'
    )
"
```

### Step 3: Monitor Processing
Check the processing status in DynamoDB:
```bash
aws --endpoint-url=http://localhost:4566 dynamodb scan --table-name review-analysis-reviews
```

## Results Analysis

### Step 1: Generate Analysis Report
```bash
cd src/aws
python analyze_results.py
```

This will generate a comprehensive report including:
- Sentiment distribution (positive, negative, neutral)
- Profanity analysis
- Banned users list
- Detailed review information

### Step 2: View Results
The analysis script will output:
- Summary statistics
- Detailed JSON report
- Comparison with original devset

## Expected Results

Based on the provided `reviews_devset.json`:

### Sentiment Distribution
- Positive reviews: ~6-7 (high ratings with positive language)
- Negative reviews: ~2-3 (low ratings with negative language)
- Neutral reviews: ~1-2 (mixed or average ratings)

### Profanity Analysis
- Reviews with profanity: ~3-4 (containing words like "shit", "crap", "fuck")
- Clean reviews: ~6-7

### Banned Users
- Users with >3 profane reviews: 1 (John Doe with 3 profane reviews)

## Troubleshooting

### Common Issues

1. **LocalStack not running**
   - Ensure LocalStack is started: `localstack start`
   - Check endpoint URL: `http://localhost:4566`

2. **Lambda function errors**
   - Check Lambda logs: `aws --endpoint-url=http://localhost:4566 logs describe-log-groups`
   - Verify function permissions and triggers

3. **S3 trigger issues**
   - Check bucket notifications: `aws --endpoint-url=http://localhost:4566 s3api get-bucket-notification-configuration --bucket review-analysis-reviews`

4. **DynamoDB connection issues**
   - Verify table creation: `aws --endpoint-url=http://localhost:4566 dynamodb describe-table --table-name review-analysis-reviews`

### Debug Mode
Enable debug logging by setting environment variables:
```bash
export AWS_LOG_LEVEL=DEBUG
export LOCALSTACK_LOG_LEVEL=DEBUG
```

## Cleanup

To clean up all resources:
```bash
# Delete S3 buckets
aws --endpoint-url=http://localhost:4566 s3 rb s3://review-analysis-reviews --force
aws --endpoint-url=http://localhost:4566 s3 rb s3://review-analysis-processed --force
aws --endpoint-url=http://localhost:4566 s3 rb s3://review-analysis-profanity --force
aws --endpoint-url=http://localhost:4566 s3 rb s3://review-analysis-sentiment --force
aws --endpoint-url=http://localhost:4566 s3 rb s3://review-analysis-config --force

# Delete DynamoDB tables
aws --endpoint-url=http://localhost:4566 dynamodb delete-table --table-name review-analysis-reviews
aws --endpoint-url=http://localhost:4566 dynamodb delete-table --table-name review-analysis-users

# Delete Lambda functions
aws --endpoint-url=http://localhost:4566 lambda delete-function --function-name review-preprocessing
aws --endpoint-url=http://localhost:4566 lambda delete-function --function-name review-profanity-check
aws --endpoint-url=http://localhost:4566 lambda delete-function --function-name review-sentiment-analysis
```

## File Structure
```
Assignment_3/
├── Data/
│   └── reviews_devset.json          # Sample review data
├── src/
│   ├── aws/
│   │   ├── aws.py                   # AWS client utilities
│   │   ├── deploy_review_analysis.py # Deployment script
│   │   ├── preprocessing_lambda.py  # Preprocessing function
│   │   ├── profanity_check_lambda.py # Profanity check function
│   │   ├── sentiment_analysis_lambda.py # Sentiment analysis function
│   │   └── analyze_results.py       # Results analysis script
│   ├── tests/
│   │   └── test_review_analysis.py  # Integration tests
│   └── local/                       # Local testing utilities
├── requirements.txt                 # Python dependencies
└── instructions.md                 # This file
```

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review Lambda function logs
3. Verify LocalStack is running correctly
4. Ensure all dependencies are installed 