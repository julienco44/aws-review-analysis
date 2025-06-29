# Event-Driven Serverless Review Analysis

This project implements a complete event-driven serverless application using AWS Lambda functions to analyze customer reviews. The system performs text preprocessing, profanity detection, sentiment analysis, and user management through a chain of Lambda functions triggered by S3 events.

### Core Requirements Implemented

- **Three Lambda Functions**: preprocessing → profanity-check → sentiment-analysis  
- **Event-Driven Architecture**: S3 triggers → Lambda chain execution  
- **Field Analysis**: Processes reviewText, summary, and overall rating fields  
- **SSM Parameter Store**: Centralized configuration management  
- **User Banning Logic**: Automatic banning after >3 profane reviews  
- **Integration Tests**: Comprehensive automated testing suite  
- **Real Serverless Execution**: Uses actual AWS Lambda function invocations  

---

## System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   S3 Upload     │───▶│  Preprocessing   │───▶│ Profanity Check  │───▶│ Sentiment Analysis│
│   (Raw Review)  │    │     Lambda       │    │     Lambda       │    │     Lambda       │
└─────────────────┘    └──────────────────┘    └──────────────────┘    └──────────────────┘
                                │                        │                        │
                                ▼                        ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ SSM Parameter   │    │  S3 Processed    │    │ S3 Profanity     │    │ S3 Sentiment     │
│     Store       │    │     Bucket       │    │    Results       │    │    Results       │
└─────────────────┘    └──────────────────┘    └──────────────────┘    └──────────────────┘
                                                        │                        │
                                                        ▼                        ▼
                                               ┌──────────────────┐    ┌──────────────────┐
                                               │    DynamoDB      │    │    DynamoDB      │
                                               │  Users Table     │    │  Reviews Table   │
                                               │ (Banning Logic)  │    │ (Final Results)  │
                                               └──────────────────┘    └──────────────────┘
```

### Event-Driven Flow

1. **Review Upload** → S3 `reviews` bucket
2. **S3 Event Trigger** → Preprocessing Lambda
3. **Processed Data** → S3 `processed` bucket → Profanity Check Lambda
4. **Profanity Results** → S3 `profanity` bucket → Sentiment Analysis Lambda
5. **Final Results** → S3 `sentiment` bucket + DynamoDB storage

---

## Project Structure

```
Assignment_3/
├── README.md                           # This file
├── requirements.txt                    # Python dependencies
├── assignment_results.json             # Final processing results
├── Data/
│   └── reviews_devset.json            # Dataset for analysis
├── src/
│   ├── aws/                           # Core serverless implementation
│   │   ├── deploy_review_analysis.py         # Infrastructure deployment
│   │   ├── preprocessing_lambda.py           # Lambda 1: Text preprocessing
│   │   ├── profanity_check_lambda.py         # Lambda 2: Profanity detection
│   │   ├── sentiment_analysis_lambda.py      # Lambda 3: Sentiment analysis
│   │   ├── process_full_dataset.py           # Main dataset processor
│   │   ├── real_serverless_pipeline.py       # Event-driven pipeline
│   │   ├── test_real_lambda_chain.py         # Lambda function tests
│   │   └── upload_reviews.py                 # Data upload utilities
│   └── tests/
│       └── test_review_analysis.py           # Integration tests
└── docs/
    ├── report.pdf                     # Assignment report (8 pages max)
    └── instructions.pdf               # Execution instructions
```

---

## Setup and Execution

### Prerequisites

- **Docker** installed and running
- **Python 3.9+** with pip
- **LocalStack** for AWS simulation
- **Git** for repository management

### 1. Environment Setup

```bash
# Clone the repository
git clone <repository-url>
cd Assignment_3

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Start LocalStack

```bash
# Start LocalStack with Docker support (CRITICAL for Lambda functions)
docker run -it --rm --name localstack \
  -p 4566:4566 -p 4510-4559:4510-4559 \
  -e DEBUG=1 \
  -e LAMBDA_EXECUTOR=docker \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  -v /var/run/docker.sock:/var/run/docker.sock \
  localstack/localstack
```

**Important:** Keep this terminal running throughout the entire process.

### 3. Configure AWS Credentials

In a new terminal:
```bash
# Set LocalStack credentials
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1

# Navigate to project
cd Assignment_3
source .venv/bin/activate
```

### 4. Deploy Infrastructure

```bash
cd src/aws
python deploy_review_analysis.py
```

### 5. Verify System

```bash
# Test individual Lambda functions
python test_real_lambda_chain.py
```

---

## Dataset Processing

### Full Dataset Processing

Process the complete reviews_devset.json dataset (78,000+ reviews):

```bash
# Process all reviews with optimal settings
python process_full_dataset.py --batch-size 50 --max-workers 10
```

### Comprehensive Analysis

Process a substantial portion of the dataset for thorough analysis:

```bash
# Process 10,000 reviews for comprehensive analysis
python process_full_dataset.py --max-reviews 10000 --batch-size 25 --max-workers 8

# Process 5,000 reviews with standard settings
python process_full_dataset.py --max-reviews 5000 --batch-size 20 --max-workers 5
```

### Processing Parameters

- `--max-reviews`: Number of reviews to process (omit for full dataset)
- `--batch-size`: Reviews processed per batch (default: 10)
- `--max-workers`: Parallel processing threads (default: 3)
- `--start-index`: Starting review index (default: 0)

---

## Assignment Results

After processing, the system generates `assignment_results.json` containing:

### Required Analysis Results
- **Sentiment Analysis**: Count of positive/neutral/negative reviews
- **Profanity Check**: Reviews that failed profanity screening
- **User Banning**: Users banned for >3 profane reviews

### Results Structure
```json
{
  "sentiment_analysis": {
    "positive_reviews": 425,
    "neutral_reviews": 45,
    "negative_reviews": 30,
    "sentiment_distribution": {
      "positive_percentage": 85.0,
      "neutral_percentage": 9.0,
      "negative_percentage": 6.0
    }
  },
  "profanity_analysis": {
    "reviews_with_profanity": 67,
    "reviews_without_profanity": 433,
    "profanity_rate_percentage": 13.4
  },
  "user_banning": {
    "total_banned_users": 5,
    "banned_user_ids": ["A1234567", "B2345678", "C3456789", "D4567890", "E5678901"]
  }
}
```

---

## Testing and Validation

### Run Integration Tests
```bash
cd src/tests
python test_review_analysis.py
```

### Test Individual Components
```bash
# Test preprocessing functionality
python -c "from preprocessing_lambda import preprocess_text; print(preprocess_text('This is amazing!'))"

# Test profanity detection
python -c "from profanity_check_lambda import check_profanity; print(check_profanity('This is terrible!'))"

# Test sentiment analysis
python -c "from sentiment_analysis_lambda import analyze_sentiment; print(analyze_sentiment('Great product!', 5))"
```

### Verify AWS Resources
```bash
# Check S3 buckets
aws --endpoint-url=http://localhost:4566 s3 ls

# Check DynamoDB tables
aws --endpoint-url=http://localhost:4566 dynamodb list-tables

# Check Lambda functions
aws --endpoint-url=http://localhost:4566 lambda list-functions
```

---

## Troubleshooting

### Common Issues

**Lambda Functions Show "Failed" State**
```bash
# Restart LocalStack with proper Docker configuration
docker stop localstack
# Use the Docker command from Step 2 above
```

**"Docker not available" Error**
- Ensure Docker Desktop is running
- Verify the volume mount: `-v /var/run/docker.sock:/var/run/docker.sock`

**Dataset File Not Found**
```bash
# Verify dataset location
ls -la Data/reviews_devset.json

# Or specify custom path
python process_full_dataset.py --dataset-path "/path/to/reviews_devset.json"
```

**Processing Hangs**
```bash
# Check LocalStack logs
docker logs localstack

# Restart infrastructure if needed
python deploy_review_analysis.py
```

**Memory/Performance Issues**
```bash
# Reduce batch size and workers
python process_full_dataset.py --batch-size 5 --max-workers 2
```

---

## Performance Considerations

| Reviews | Processing Time | Lambda Calls |
|---------|----------------|--------------|
| 1,000   | ~40 minutes    | 3,000        |
| 5,000   | ~3 hours       | 15,000       |
| 10,000  | ~6 hours       | 30,000       |
| Full Dataset | ~12-16 hours | 234,000+    |

---

## Assignment Compliance

This implementation satisfies all Assignment 3 requirements:

| Requirement | Implementation | Status |
|-------------|----------------|--------|
| 3 Lambda Functions | preprocessing, profanity-check, sentiment-analysis | Complete |
| S3 Event Triggers | S3 upload → Lambda chain execution | Complete |
| Field Analysis | reviewText, summary, overall rating | Complete |
| SSM Parameter Store | Centralized configuration | Complete |
| User Banning | >3 profane reviews = banned | Complete |
| Integration Tests | Comprehensive test suite | Complete |
| Event-Driven Architecture | Real serverless execution | Complete |

---

## Additional Resources

- **AWS Lambda Documentation**: https://docs.aws.amazon.com/lambda/
- **LocalStack Documentation**: https://docs.localstack.cloud/
- **Assignment Requirements**: See `Assignment_3_Instructions.md`
- **System Architecture**: Detailed in `report.pdf`

---

## Team Information

**Group ID**: [Your Group ID]  
**Team Members**: [Your Team Members]  
**Course**: Distributed and Information Centric Computing  
**Institution**: [Your Institution]  

---

## Submission Notes

This implementation demonstrates:
- **Real serverless architecture** with actual AWS Lambda invocations
- **Event-driven processing** with S3 → Lambda → S3 chains
- **Comprehensive analysis** of customer review sentiment and profanity
- **Production-ready code** with error handling and testing
- **Scalable design** capable of processing large datasets

The system successfully processes the `reviews_devset.json` dataset and generates all required analysis results as specified in Assignment 3 requirements.
