# Complete Instructions: Processing Full Dataset with Serverless Review Analysis System

## 🎯 Overview
This guide provides step-by-step instructions to process the complete `reviews_devset.json` dataset (142k+ reviews, 55MB) using our fully functional serverless AWS Lambda pipeline running on LocalStack.

## 📋 Prerequisites
- macOS/Linux system with Docker installed
- Python 3.9+
- Git repository cloned: `https://github.com/julienco44/aws-review-analysis.git`

## 🚀 Step-by-Step Instructions

### Step 1: Clone and Setup Repository
```bash
# Clone the repository
git clone https://github.com/julienco44/aws-review-analysis.git
cd aws-review-analysis

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Start LocalStack with Proper Docker Configuration
```bash
# Start LocalStack with Docker-in-Docker support (CRITICAL for Lambda functions)
docker run -it --rm --name localstack \
  -p 4566:4566 -p 4510-4559:4510-4559 \
  -e DEBUG=1 \
  -e LAMBDA_EXECUTOR=docker \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  -v /var/run/docker.sock:/var/run/docker.sock \
  localstack/localstack
```

**Important**: Keep this terminal running. LocalStack must stay active throughout the entire process.

### Step 3: Set AWS Credentials (New Terminal)
Open a new terminal and set up AWS credentials for LocalStack:
```bash
# Navigate to project directory
cd /path/to/aws-review-analysis
source .venv/bin/activate

# Set LocalStack AWS credentials
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
```

### Step 4: Deploy the Serverless Infrastructure
```bash
# Deploy all Lambda functions, S3 buckets, DynamoDB tables, and SSM parameters
cd src/aws
python deploy_review_analysis.py
```

**Expected Output**: You should see successful creation of:
- ✅ 5 S3 buckets (config, reviews, processed, profanity, sentiment)
- ✅ 2 DynamoDB tables (reviews, users)  
- ✅ 3 Lambda layers with dependencies
- ✅ 6 SSM parameters
- ✅ 3 Lambda functions (preprocessing, profanity-check, sentiment-analysis) in **Active** state

### Step 5: Verify System Functionality
```bash
# Run comprehensive integration tests
python test_real_lambda_chain.py
```

**Expected Output**:
```
✅ All individual function tests: PASSED
✅ All chain tests: PASSED  
✅ All real data tests: PASSED
✅ Pipeline processing: SUCCESSFUL
```

### Step 6: Process the Full Dataset

#### Option A: Process Entire Dataset (142k+ reviews, ~8-12 hours)
```bash
# Process all 142k+ reviews with default settings
python process_full_dataset.py
```

#### Option B: Process Smaller Batch for Testing
```bash
# Process first 100 reviews (recommended for initial testing)
python process_full_dataset.py --max_reviews 100

# Process first 1000 reviews (~20 minutes)
python process_full_dataset.py --max_reviews 1000

# Process with custom batch size and workers
python process_full_dataset.py --max_reviews 5000 --batch_size 20 --max_workers 5
```

#### Configuration Options
```bash
# Available parameters:
--max_reviews     # Number of reviews to process (default: all ~142k)
--batch_size      # Reviews per batch (default: 10) 
--max_workers     # Parallel workers (default: 3)
--start_index     # Starting review index (default: 0)
```

### Step 7: Monitor Progress
The script provides real-time progress monitoring:
```
Processing batch 1/50 (reviews 0-9)...
✅ Batch 1 completed: 10/10 successful (0 errors)
Progress: 10/100 reviews (10.0%) | ETA: 0:01:23
Average processing time: 0.42s per review
```

### Step 8: Review Results
After completion, check the results:
```bash
# View summary statistics
cat assignment_results.json | python -m json.tool

# Key metrics will include:
# - Total reviews processed
# - Sentiment analysis breakdown (positive/negative/neutral)
# - Profanity detection statistics  
# - User banning statistics
# - Processing performance metrics
```

## 📊 Expected Performance

| Dataset Size | Estimated Time | Reviews/Minute |
|-------------|---------------|----------------|
| 100 reviews | ~2 minutes    | ~50           |
| 1,000 reviews | ~20 minutes | ~50           |
| 10,000 reviews | ~3 hours    | ~55           |
| 142,000 reviews | ~8-12 hours | ~200-300      |

## 🔧 System Architecture

The system implements a 3-stage serverless pipeline:

1. **Preprocessing Lambda**: Text cleaning, tokenization, stopword removal
2. **Profanity Check Lambda**: Content filtering, user tracking, auto-banning
3. **Sentiment Analysis Lambda**: TextBlob-based sentiment classification

## 📁 Key Files

- `deploy_review_analysis.py` - Infrastructure deployment
- `process_full_dataset.py` - Main dataset processing script
- `test_real_lambda_chain.py` - Comprehensive testing
- `preprocessing_lambda.py` - Text preprocessing function
- `profanity_check_lambda.py` - Profanity detection function  
- `sentiment_analysis_lambda.py` - Sentiment analysis function
- `assignment_results.json` - Final processing results

## 🐛 Troubleshooting

### Common Issues:

**1. Lambda Functions Show "Failed" State**
```bash
# Restart LocalStack with proper Docker configuration
docker stop localstack
# Use the Docker command from Step 2
```

**2. "Docker not available" Error**
- Ensure Docker Desktop is running
- Verify the `-v /var/run/docker.sock:/var/run/docker.sock` volume mount

**3. AWS Credentials Error**
```bash
# Reset credentials
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
```

**4. Processing Hangs or Fails**
```bash
# Check LocalStack logs for errors
docker logs localstack

# Restart deployment if needed
python deploy_review_analysis.py
```

## ✅ Success Indicators

- All Lambda functions show **Active** state
- Integration tests pass 100%
- Real-time progress updates during processing
- `assignment_results.json` generated with comprehensive statistics
- No Docker/LocalStack connection errors

## 🎓 Assignment Completion

Upon successful completion, you will have:
- ✅ Fully functional event-driven serverless architecture
- ✅ Complete processing of customer review dataset
- ✅ Comprehensive analytics: sentiment analysis, profanity detection, user management
- ✅ Detailed performance metrics and statistics
- ✅ Ready-to-submit Assignment 3 deliverables

The system successfully demonstrates all Assignment 3 requirements: event-driven serverless application, multiple Lambda functions, S3/DynamoDB integration, automated testing, and comprehensive dataset processing. 