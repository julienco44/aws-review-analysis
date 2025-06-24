# Review Analysis System - Assignment 3

A serverless application for automated review analysis using AWS Lambda, S3, and DynamoDB on LocalStack.

## Features
- Text preprocessing (tokenization, stop words, lemmatization)
- Profanity detection and user banning
- Sentiment analysis using TextBlob
- Event-driven processing chain

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start LocalStack
localstack start

# Deploy system
cd src/aws
python deploy_review_analysis.py

# Upload test data
python upload_reviews.py

# Run tests
cd ../tests
python test_review_analysis.py

# Generate report
cd ../aws
python analyze_results.py
```

## Architecture
- **3 Lambda Functions**: Preprocessing → Profanity Check → Sentiment Analysis
- **5 S3 Buckets**: Reviews, Processed, Profanity, Sentiment, Config
- **2 DynamoDB Tables**: Reviews tracking, User management
- **Event-Driven**: S3 triggers chain the functions

## Expected Results
- Positive reviews: ~6-7
- Negative reviews: ~2-3  
- Reviews with profanity: ~3-4
- Banned users: 1

See `instructions.md` for detailed setup and troubleshooting. 