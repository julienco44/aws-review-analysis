import boto3
import json
import os
import re
from datetime import datetime
from textblob import TextBlob

# Initialize AWS clients
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

def analyze_sentiment(text):
    """
    Analyze sentiment of text using TextBlob
    Returns: (sentiment_score, sentiment_label)
    """
    if not text or not isinstance(text, str):
        return 0.0, 'neutral'
    
    # Create TextBlob object
    blob = TextBlob(text)
    
    # Get polarity score (-1 to 1)
    polarity = blob.sentiment.polarity
    
    # Convert to sentiment label
    if polarity > 0.1:
        sentiment_label = 'positive'
    elif polarity < -0.1:
        sentiment_label = 'negative'
    else:
        sentiment_label = 'neutral'
    
    return polarity, sentiment_label

def analyze_overall_sentiment(review_text, summary, overall_rating):
    """
    Analyze overall sentiment considering text, summary, and rating
    """
    # Analyze text and summary sentiment
    text_polarity, text_sentiment = analyze_sentiment(review_text)
    summary_polarity, summary_sentiment = analyze_sentiment(summary)
    
    # Convert overall rating to sentiment (1-2: negative, 3: neutral, 4-5: positive)
    if overall_rating <= 2:
        rating_sentiment = 'negative'
        rating_polarity = -0.5
    elif overall_rating == 3:
        rating_sentiment = 'neutral'
        rating_polarity = 0.0
    else:
        rating_sentiment = 'positive'
        rating_polarity = 0.5
    
    # Calculate weighted average polarity
    # Give more weight to text, then summary, then rating
    weighted_polarity = (text_polarity * 0.5 + summary_polarity * 0.3 + rating_polarity * 0.2)
    
    # Determine final sentiment
    if weighted_polarity > 0.1:
        final_sentiment = 'positive'
    elif weighted_polarity < -0.1:
        final_sentiment = 'negative'
    else:
        final_sentiment = 'neutral'
    
    return {
        'text_polarity': text_polarity,
        'text_sentiment': text_sentiment,
        'summary_polarity': summary_polarity,
        'summary_sentiment': summary_sentiment,
        'rating_sentiment': rating_sentiment,
        'rating_polarity': rating_polarity,
        'weighted_polarity': weighted_polarity,
        'final_sentiment': final_sentiment
    }

def lambda_handler(event, context):
    """
    Lambda function to perform sentiment analysis on reviews
    Triggered by S3 object creation in profanity bucket
    """
    print(f"Sentiment Analysis Lambda invoked with event: {json.dumps(event)}")
    
    try:
        # Get configuration parameters
        profanity_bucket = get_parameter('profanity_bucket')
        sentiment_bucket = get_parameter('sentiment_bucket')
        reviews_table = get_parameter('reviews_table')
        
        # Extract S3 event details
        if "Records" in event and len(event["Records"]) > 0:
            s3_event = event["Records"][0]["s3"]
            bucket_name = s3_event["bucket"]["name"]
            object_key = s3_event["object"]["key"]
            event_time = event["Records"][0]["eventTime"]
        else:
            raise ValueError("No S3 records found in event")
        
        # Download the profanity check result from S3
        response = s3.get_object(Bucket=bucket_name, Key=object_key)
        profanity_result = json.loads(response['Body'].read().decode('utf-8'))
        
        # Perform sentiment analysis
        sentiment_analysis = analyze_overall_sentiment(
            profanity_result.get('original_reviewText', ''),
            profanity_result.get('original_summary', ''),
            profanity_result.get('overall', 3.0)
        )
        
        # Create sentiment analysis result
        sentiment_result = {
            'reviewerID': profanity_result.get('reviewerID'),
            'asin': profanity_result.get('asin'),
            'reviewerName': profanity_result.get('reviewerName'),
            'original_reviewText': profanity_result.get('original_reviewText'),
            'original_summary': profanity_result.get('original_summary'),
            'overall': profanity_result.get('overall'),
            'unixReviewTime': profanity_result.get('unixReviewTime'),
            'reviewTime': profanity_result.get('reviewTime'),
            'has_profanity': profanity_result.get('has_profanity'),
            'profanity_words_found': profanity_result.get('profanity_words_found'),
            'sentiment_analysis': sentiment_analysis,
            'processing_timestamp': profanity_result.get('processing_timestamp'),
            'profanity_check_timestamp': profanity_result.get('profanity_check_timestamp'),
            'sentiment_analysis_timestamp': datetime.now().isoformat(),
            's3_event_time': event_time,
            'profanity_s3_key': object_key
        }
        
        # Upload sentiment analysis result to sentiment bucket
        sentiment_key = f"sentiment_analysis/{profanity_result.get('reviewerID')}_{profanity_result.get('asin')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        s3.put_object(
            Bucket=sentiment_bucket,
            Key=sentiment_key,
            Body=json.dumps(sentiment_result),
            ContentType='application/json'
        )
        
        # Update DynamoDB review tracking
        dynamodb_item = {
            'review_id': {'S': f"{profanity_result.get('reviewerID')}_{profanity_result.get('asin')}"},
            'reviewerID': {'S': profanity_result.get('reviewerID')},
            'asin': {'S': profanity_result.get('asin')},
            'processing_status': {'S': 'sentiment_analyzed'},
            'has_profanity': {'BOOL': profanity_result.get('has_profanity', False)},
            'profanity_words_found': {'L': [{'S': word} for word in profanity_result.get('profanity_words_found', [])]},
            'sentiment': {'S': sentiment_analysis['final_sentiment']},
            'sentiment_polarity': {'N': str(sentiment_analysis['weighted_polarity'])},
            'sentiment_s3_key': {'S': sentiment_key},
            'profanity_s3_key': {'S': object_key},
            'sentiment_analysis_timestamp': {'S': sentiment_result['sentiment_analysis_timestamp']},
            's3_event_time': {'S': event_time},
            'lambda_function': {'S': context.function_name},
            'lambda_version': {'S': context.function_version}
        }
        
        dynamodb.put_item(
            TableName=reviews_table,
            Item=dynamodb_item
        )
        
        print(f"Successfully completed sentiment analysis: {sentiment_key}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Sentiment analysis completed successfully',
                'sentiment_key': sentiment_key,
                'sentiment': sentiment_analysis['final_sentiment'],
                'sentiment_polarity': sentiment_analysis['weighted_polarity'],
                'reviewerID': profanity_result.get('reviewerID'),
                'asin': profanity_result.get('asin')
            })
        }
        
    except Exception as e:
        print(f"Error in sentiment analysis lambda: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        } 