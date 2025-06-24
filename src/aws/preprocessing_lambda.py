import boto3
import json
import os
import re
from datetime import datetime
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

try:
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('wordnet')

# Initialize NLTK components
lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('english'))

# Get parameters from SSM
ssm = boto3.client('ssm')
s3 = boto3.client('s3')
dynamodb = boto3.client('dynamodb')

def get_parameter(parameter_name):
    """Retrieve parameter from SSM Parameter Store"""
    try:
        response = s3.get_object(
            Bucket=os.environ.get('CONFIG_BUCKET', 'review-analysis-config'),
            Key=f'parameters/{parameter_name}.txt'
        )
        return response['Body'].read().decode('utf-8').strip()
    except Exception as e:
        print(f"Error getting parameter {parameter_name}: {e}")
        # Fallback to environment variables
        return os.environ.get(parameter_name.upper())

def preprocess_text(text):
    """
    Preprocess text by performing:
    1. Tokenization
    2. Stop word removal
    3. Lemmatization
    """
    if not text or not isinstance(text, str):
        return []
    
    # Convert to lowercase
    text = text.lower()
    
    # Remove special characters and numbers
    text = re.sub(r'[^a-zA-Z\s]', '', text)
    
    # Tokenize
    tokens = word_tokenize(text)
    
    # Remove stop words and lemmatize
    processed_tokens = []
    for token in tokens:
        if token not in stop_words and len(token) > 2:
            lemmatized = lemmatizer.lemmatize(token)
            processed_tokens.append(lemmatized)
    
    return processed_tokens

def lambda_handler(event, context):
    """
    Lambda function to preprocess review text and summary
    Triggered by S3 object creation events
    """
    print(f"Preprocessing Lambda invoked with event: {json.dumps(event)}")
    
    try:
        # Get configuration parameters
        reviews_bucket = get_parameter('reviews_bucket')
        processed_bucket = get_parameter('processed_bucket')
        reviews_table = get_parameter('reviews_table')
        
        # Extract S3 event details
        if "Records" in event and len(event["Records"]) > 0:
            s3_event = event["Records"][0]["s3"]
            bucket_name = s3_event["bucket"]["name"]
            object_key = s3_event["object"]["key"]
            event_time = event["Records"][0]["eventTime"]
        else:
            raise ValueError("No S3 records found in event")
        
        # Download the review file from S3
        response = s3.get_object(Bucket=bucket_name, Key=object_key)
        review_data = json.loads(response['Body'].read().decode('utf-8'))
        
        # Preprocess review text and summary
        processed_review_text = preprocess_text(review_data.get('reviewText', ''))
        processed_summary = preprocess_text(review_data.get('summary', ''))
        
        # Create processed review object
        processed_review = {
            'reviewerID': review_data.get('reviewerID'),
            'asin': review_data.get('asin'),
            'reviewerName': review_data.get('reviewerName'),
            'original_reviewText': review_data.get('reviewText'),
            'original_summary': review_data.get('summary'),
            'processed_reviewText': processed_review_text,
            'processed_summary': processed_summary,
            'overall': review_data.get('overall'),
            'unixReviewTime': review_data.get('unixReviewTime'),
            'reviewTime': review_data.get('reviewTime'),
            'processing_timestamp': datetime.now().isoformat(),
            's3_event_time': event_time,
            'original_s3_key': object_key
        }
        
        # Upload processed review to processed bucket
        processed_key = f"processed/{review_data.get('reviewerID')}_{review_data.get('asin')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        s3.put_object(
            Bucket=processed_bucket,
            Key=processed_key,
            Body=json.dumps(processed_review),
            ContentType='application/json'
        )
        
        # Store in DynamoDB for tracking
        dynamodb_item = {
            'review_id': {'S': f"{review_data.get('reviewerID')}_{review_data.get('asin')}"},
            'reviewerID': {'S': review_data.get('reviewerID')},
            'asin': {'S': review_data.get('asin')},
            'processing_status': {'S': 'preprocessed'},
            'processed_s3_key': {'S': processed_key},
            'original_s3_key': {'S': object_key},
            'processing_timestamp': {'S': processed_review['processing_timestamp']},
            's3_event_time': {'S': event_time},
            'lambda_function': {'S': context.function_name},
            'lambda_version': {'S': context.function_version}
        }
        
        dynamodb.put_item(
            TableName=reviews_table,
            Item=dynamodb_item
        )
        
        print(f"Successfully preprocessed review: {processed_key}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Review preprocessing completed successfully',
                'processed_key': processed_key,
                'reviewerID': review_data.get('reviewerID'),
                'asin': review_data.get('asin')
            })
        }
        
    except Exception as e:
        print(f"Error in preprocessing lambda: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        } 