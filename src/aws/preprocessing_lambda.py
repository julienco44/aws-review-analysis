import boto3
import json
import os
import re
from datetime import datetime

# Try to import NLTK components, fallback to basic preprocessing if not available
try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.stem import WordNetLemmatizer
    from nltk.tokenize import word_tokenize
    
    # Initialize NLTK components (NLTK data should be in a Lambda layer)
    lemmatizer = WordNetLemmatizer()
    
    # Use basic English stopwords if NLTK is not fully available
    try:
        stop_words = set(stopwords.words('english'))
    except:
        # Fallback stopwords list
        stop_words = {
            'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours',
            'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 'hers',
            'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves',
            'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are',
            'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does',
            'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until',
            'while', 'of', 'at', 'by', 'for', 'with', 'through', 'during', 'before', 'after',
            'above', 'below', 'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again',
            'further', 'then', 'once'
        }
    
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False
    # Fallback stopwords if NLTK is not available
    stop_words = {
        'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours',
        'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 'hers',
        'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves',
        'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are',
        'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does',
        'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until',
        'while', 'of', 'at', 'by', 'for', 'with', 'through', 'during', 'before', 'after',
        'above', 'below', 'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again',
        'further', 'then', 'once'
    }

# Get parameters from SSM
ssm = boto3.client('ssm')
s3 = boto3.client('s3')
dynamodb = boto3.client('dynamodb')

def get_parameter(parameter_name):
    """Retrieve parameter from SSM Parameter Store with fallback"""
    try:
        response = ssm.get_parameter(Name=parameter_name)
        return response['Parameter']['Value']
    except Exception as e:
        print(f"SSM parameter {parameter_name} not found, using default: {e}")
        # Fallback values
        defaults = {
            'reviews_bucket': 'review-analysis-reviews',
            'processed_bucket': 'review-analysis-processed',
            'profanity_bucket': 'review-analysis-profanity',
            'sentiment_bucket': 'review-analysis-sentiment',
            'reviews_table': 'review-analysis-reviews',
            'users_table': 'review-analysis-users'
        }
        return defaults.get(parameter_name, f'review-analysis-{parameter_name}')

def preprocess_text(text):
    """
    Preprocess text by performing:
    1. Tokenization
    2. Stop word removal
    3. Lemmatization (if NLTK is available)
    """
    if not text or not isinstance(text, str):
        return []
    
    # Convert to lowercase
    text = text.lower()
    
    # Remove special characters and numbers
    text = re.sub(r'[^a-zA-Z\s]', '', text)
    
    # Tokenize
    if NLTK_AVAILABLE:
        try:
            tokens = word_tokenize(text)
        except:
            # Fallback to simple split
            tokens = text.split()
    else:
        # Simple tokenization by splitting on whitespace
        tokens = text.split()
    
    # Remove stop words and lemmatize
    processed_tokens = []
    for token in tokens:
        if token not in stop_words and len(token) > 2:
            if NLTK_AVAILABLE:
                try:
                    lemmatized = lemmatizer.lemmatize(token)
                    processed_tokens.append(lemmatized)
                except:
                    # Fallback to original token
                    processed_tokens.append(token)
            else:
                # No lemmatization available
                processed_tokens.append(token)
    
    return processed_tokens

def lambda_handler(event, context):
    """
    Lambda function to preprocess review text and summary
    Handles both S3 event triggers and direct data passing
    """
    print(f"Preprocessing Lambda invoked with event: {json.dumps(event)}")
    
    try:
        # Get configuration parameters
        reviews_bucket = get_parameter('reviews_bucket')
        processed_bucket = get_parameter('processed_bucket')
        reviews_table = get_parameter('reviews_table')
        
        # Extract review data - handle both S3 events and direct data
        review_data = None
        object_key = None
        event_time = datetime.now().isoformat()
        
        if "review_data" in event:
            # Direct data passing (for LocalStack compatibility)
            review_data = event["review_data"]
            object_key = f"direct/{review_data.get('reviewerID', 'unknown')}_{int(datetime.now().timestamp())}.json"
            print("Processing direct review data")
            
        elif "Records" in event and len(event["Records"]) > 0:
            # S3 event processing
            s3_event = event["Records"][0]["s3"]
            bucket_name = s3_event["bucket"]["name"]
            object_key = s3_event["object"]["key"]
            event_time = event["Records"][0].get("eventTime", datetime.now().isoformat())
            
            # Download the review file from S3
            response = s3.get_object(Bucket=bucket_name, Key=object_key)
            review_data = json.loads(response['Body'].read().decode('utf-8'))
            print(f"Processing S3 event from {bucket_name}/{object_key}")
            
        else:
            raise ValueError("No valid review data or S3 records found in event")
        
        if not review_data:
            raise ValueError("Failed to extract review data from event")
        
        # Preprocess review text and summary
        review_text = review_data.get('reviewText', '')
        summary_text = review_data.get('summary', '')
        
        processed_review_text = preprocess_text(review_text)
        processed_summary = preprocess_text(summary_text)
        
        # Create cleaned text versions
        cleaned_review_text = ' '.join(processed_review_text)
        cleaned_summary = ' '.join(processed_summary)
        
        # Create processing result
        processing_result = {
            'reviewText': {
                'original': review_text,
                'preprocessed': processed_review_text,
                'cleaned': cleaned_review_text
            },
            'summary': {
                'original': summary_text,
                'preprocessed': processed_summary,
                'cleaned': cleaned_summary
            },
            'overall_rating': review_data.get('overall'),
            'processing_metadata': {
                'timestamp': datetime.now().isoformat(),
                'nltk_available': NLTK_AVAILABLE,
                'event_time': event_time,
                'lambda_function': context.function_name if context else 'unknown',
                'original_s3_key': object_key
            }
        }
        
        print(f"Successfully preprocessed review - reviewText tokens: {len(processed_review_text)}, summary tokens: {len(processed_summary)}")
        
        return {
            'statusCode': 200,
            'body': processing_result
        }
        
    except Exception as e:
        error_msg = f"Error in preprocessing lambda: {str(e)}"
        print(error_msg)
        return {
            'statusCode': 500,
            'body': {
                'error': 'Internal server error',
                'message': str(e)
            }
        } 