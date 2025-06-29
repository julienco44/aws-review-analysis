# Assignment 3 - Event-Driven Serverless Review Analysis

## 📋 Assignment Requirements Implementation

This project implements a **complete event-driven serverless application** that meets all Assignment 3 requirements:

✅ **Three Lambda Functions**: preprocessing, profanity-check, sentiment-analysis  
✅ **Event-Driven Architecture**: S3 → Lambda → S3 → Lambda chain  
✅ **Real Lambda Function Invocations**: Uses AWS API calls (not simulations)  
✅ **SSM Parameter Store**: For configuration management  
✅ **DynamoDB**: For data storage and user banning logic  
✅ **Integration Tests**: Automated testing of all functionality  
✅ **Dataset Processing**: Processes reviews_devset.json with results generation  

---

## 📁 Essential Project Files

### **Core Lambda Functions**
- `src/aws/preprocessing_lambda.py` - Text preprocessing (tokenization, stop words, lemmatization)
- `src/aws/profanity_check_lambda.py` - Bad word detection and user tracking
- `src/aws/sentiment_analysis_lambda.py` - Sentiment analysis and final results

### **Infrastructure & Deployment**
- `src/aws/deploy_review_analysis.py` - Complete AWS infrastructure deployment
- `src/aws/real_serverless_pipeline.py` - Main event-driven pipeline
- `src/aws/upload_reviews.py` - Upload reviews to trigger the pipeline
- `src/aws/test_real_lambda_chain.py` - Test individual Lambda functions

### **Testing**
- `src/tests/test_review_analysis.py` - Comprehensive integration tests

### **Data & Configuration**
- `Data/reviews_devset.json` - Dataset for processing
- `requirements.txt` - Python dependencies

---

## 🚀 Quick Start

### 1. Setup Environment
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start LocalStack
docker run --rm -it -p 4566:4566 -p 4571:4571 localstack/localstack
```

### 2. Deploy Infrastructure
```bash
cd src/aws
python deploy_review_analysis.py
```

### 3. Process Reviews
```bash
# Upload and process reviews with real serverless architecture
python real_serverless_pipeline.py
```

### 4. Run Tests
```bash
cd ../tests
python -m pytest test_review_analysis.py -v
```

---

## 📊 Results

The pipeline processes the complete dataset and generates:
- **Sentiment Analysis**: Positive/Negative/Neutral review counts
- **Profanity Analysis**: Reviews containing bad words
- **User Banning**: Users with >3 profane reviews marked as banned
- **Results File**: `assignment_results.json` with all analysis data

---

## 🏗️ Architecture

```
Review Upload → S3 → Preprocessing Lambda → S3 → Profanity Check Lambda → S3 → Sentiment Analysis Lambda → Results
                                     ↓                            ↓                               ↓
                                DynamoDB ←―――――――――――――――――――――――― DynamoDB ←――――――――――――――――― DynamoDB
```

**Event-Driven Flow:**
1. Review uploaded to S3 bucket triggers preprocessing Lambda
2. Preprocessed data stored in S3 triggers profanity check Lambda  
3. Profanity results stored in S3 trigger sentiment analysis Lambda
4. All stages update DynamoDB for user tracking and banning logic

This implementation uses **real AWS Lambda function invocations** via the AWS API to ensure authentic serverless behavior as required by the assignment.

