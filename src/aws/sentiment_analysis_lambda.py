import boto3
import json
import os
from datetime import datetime
import re

# Initialize AWS clients
s3 = boto3.client('s3')
dynamodb = boto3.client('dynamodb')
ssm = boto3.client('ssm')

# Try to import TextBlob for sentiment analysis
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
    print("TextBlob successfully imported")
except ImportError:
    TEXTBLOB_AVAILABLE = False
    print("TextBlob not available, using basic sentiment analysis")

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

# Basic sentiment word lists for fallback analysis
POSITIVE_WORDS = {
    'excellent', 'great', 'amazing', 'wonderful', 'fantastic', 'awesome', 'superb',
    'outstanding', 'brilliant', 'perfect', 'love', 'loved', 'loving', 'good', 'nice',
    'best', 'better', 'happy', 'pleased', 'satisfied', 'recommend', 'recommended',
    'quality', 'beautiful', 'impressive', 'remarkable', 'incredible', 'phenomenal',
    'exceptional', 'marvelous', 'splendid', 'terrific', 'fabulous', 'delightful'
}

NEGATIVE_WORDS = {
    'terrible', 'awful', 'horrible', 'bad', 'worst', 'hate', 'hated', 'hating',
    'disappointing', 'disappointed', 'poor', 'useless', 'worthless', 'garbage',
    'trash', 'disgusting', 'pathetic', 'annoying', 'frustrating', 'broken',
    'defective', 'cheap', 'overpriced', 'waste', 'regret', 'avoid', 'problems',
    'issues', 'failed', 'failure', 'nightmare', 'disaster', 'mess', 'sucks'
}

def analyze_sentiment_basic(text, rating=None):
    """
    Basic sentiment analysis using word lists and rating
    Returns: sentiment ('positive', 'negative', 'neutral') and confidence score
    """
    if not text or not isinstance(text, str):
        # Use rating-based sentiment if no text
        if rating is not None:
            if rating >= 4:
                return 'positive', 0.7
            elif rating <= 2:
                return 'negative', 0.7
            else:
                return 'neutral', 0.5
        return 'neutral', 0.0
    
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    
    positive_count = sum(1 for word in words if word in POSITIVE_WORDS)
    negative_count = sum(1 for word in words if word in NEGATIVE_WORDS)
    
    # Calculate sentiment based on word counts and rating
    total_sentiment_words = positive_count + negative_count
    
    if total_sentiment_words == 0:
        # No sentiment words found, use rating
        if rating is not None:
            if rating >= 4:
                return 'positive', 0.6
            elif rating <= 2:
                return 'negative', 0.6
            else:
                return 'neutral', 0.5
        return 'neutral', 0.0
    
    # Calculate sentiment score
    sentiment_score = (positive_count - negative_count) / total_sentiment_words
    confidence = min(total_sentiment_words / len(words), 1.0) if words else 0.0
    
    # Factor in rating if available
    if rating is not None:
        rating_sentiment = (rating - 3) / 2  # Scale rating to -1 to 1
        sentiment_score = (sentiment_score + rating_sentiment) / 2
        confidence = max(confidence, 0.5)
    
    # Determine final sentiment
    if sentiment_score > 0.1:
        return 'positive', confidence
    elif sentiment_score < -0.1:
        return 'negative', confidence
    else:
        return 'neutral', confidence

def analyze_sentiment_textblob(text):
    """
    Sentiment analysis using TextBlob
    Returns: sentiment ('positive', 'negative', 'neutral') and confidence score
    """
    try:
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        
        # Convert polarity to sentiment label
        if polarity > 0.1:
            return 'positive', abs(polarity)
        elif polarity < -0.1:
            return 'negative', abs(polarity)
        else:
            return 'neutral', 1 - abs(polarity)
            
    except Exception as e:
        print(f"TextBlob analysis failed: {e}")
        return 'neutral', 0.0

def analyze_sentiment(text, rating=None):
    """
    Perform sentiment analysis using available method
    """
    if TEXTBLOB_AVAILABLE:
        sentiment, confidence = analyze_sentiment_textblob(text)
        # If TextBlob gives low confidence, fall back to basic analysis
        if confidence < 0.3:
            basic_sentiment, basic_confidence = analyze_sentiment_basic(text, rating)
            return basic_sentiment, max(confidence, basic_confidence)
        return sentiment, confidence
    else:
        return analyze_sentiment_basic(text, rating)

def lambda_handler(event, context):
    """
    Lambda function to perform sentiment analysis on review data
    Handles both S3 event triggers and direct data passing
    """
    print(f"Sentiment Analysis Lambda invoked with event: {json.dumps(event)}")
    
    try:
        # Get configuration parameters
        sentiment_bucket = get_parameter('sentiment_bucket')
        reviews_table = get_parameter('reviews_table')
        
        # Extract profanity data - handle both S3 events and direct data
        profanity_data = None
        
        if "profanity_data" in event:
            # Direct data passing (for LocalStack compatibility)
            profanity_data = event["profanity_data"]
            print("Processing direct sentiment analysis data")
            
        elif "Records" in event and len(event["Records"]) > 0:
            # S3 event processing
            s3_event = event["Records"][0]["s3"]
            bucket_name = s3_event["bucket"]["name"]
            object_key = s3_event["object"]["key"]
            
            # Download the profanity data from S3
            response = s3.get_object(Bucket=bucket_name, Key=object_key)
            profanity_data = json.loads(response['Body'].read().decode('utf-8'))
            print(f"Processing S3 event from {bucket_name}/{object_key}")
            
        else:
            raise ValueError("No valid profanity data or S3 records found in event")
        
        if not profanity_data:
            raise ValueError("Failed to extract profanity data from event")
        
        # Extract preprocessing results
        preprocessing_result = profanity_data.get('preprocessing_result', {})
        if isinstance(preprocessing_result, dict) and 'body' in preprocessing_result:
            preprocessing_body = preprocessing_result['body']
        else:
            preprocessing_body = preprocessing_result
        
        # Extract profanity results
        profanity_result = profanity_data.get('profanity_result', {})
        if isinstance(profanity_result, dict) and 'body' in profanity_result:
            profanity_body = profanity_result['body']
        else:
            profanity_body = profanity_result
        
        # Get text data
        review_text_data = preprocessing_body.get('reviewText', {})
        summary_data = preprocessing_body.get('summary', {})
        
        review_text_original = review_text_data.get('original', '')
        review_text_cleaned = review_text_data.get('cleaned', '')
        summary_original = summary_data.get('original', '')
        summary_cleaned = summary_data.get('cleaned', '')
        
        # Get overall rating
        overall_rating = profanity_data.get('original_review', {}).get('overall', 3.0)
        
        # Perform sentiment analysis on different text fields
        # Requirement: analyze reviewText, summary, and overall fields
        
        # Analyze review text
        review_sentiment, review_confidence = analyze_sentiment(review_text_original, overall_rating)
        
        # Analyze summary
        summary_sentiment, summary_confidence = analyze_sentiment(summary_original, overall_rating)
        
        # Analyze cleaned text (preprocessed)
        cleaned_review_sentiment, cleaned_review_confidence = analyze_sentiment(review_text_cleaned, overall_rating)
        cleaned_summary_sentiment, cleaned_summary_confidence = analyze_sentiment(summary_cleaned, overall_rating)
        
        # Combined analysis - weight by confidence and content length
        review_weight = len(review_text_original) * review_confidence
        summary_weight = len(summary_original) * summary_confidence
        rating_weight = 0.3  # Give rating some weight
        
        total_weight = review_weight + summary_weight + rating_weight
        
        if total_weight > 0:
            # Weighted sentiment calculation
            sentiment_scores = {
                'positive': 0,
                'negative': 0, 
                'neutral': 0
            }
            
            # Add weighted votes
            sentiment_scores[review_sentiment] += review_weight
            sentiment_scores[summary_sentiment] += summary_weight
            
            # Add rating-based sentiment
            if overall_rating >= 4:
                sentiment_scores['positive'] += rating_weight
            elif overall_rating <= 2:
                sentiment_scores['negative'] += rating_weight
            else:
                sentiment_scores['neutral'] += rating_weight
            
            # Determine final sentiment
            final_sentiment = max(sentiment_scores, key=sentiment_scores.get)
            final_confidence = sentiment_scores[final_sentiment] / total_weight
        else:
            final_sentiment = 'neutral'
            final_confidence = 0.0
        
        # Check if review is clean (no profanity)
        is_clean_review = not profanity_body.get('has_profanity', False)
        
        # Create sentiment analysis result
        sentiment_result = {
            'sentiment': final_sentiment,
            'confidence': final_confidence,
            'detailed_analysis': {
                'review_text': {
                    'sentiment': review_sentiment,
                    'confidence': review_confidence,
                    'original_text': review_text_original[:100] + '...' if len(review_text_original) > 100 else review_text_original
                },
                'summary': {
                    'sentiment': summary_sentiment,
                    'confidence': summary_confidence,
                    'original_text': summary_original
                },
                'cleaned_review': {
                    'sentiment': cleaned_review_sentiment,
                    'confidence': cleaned_review_confidence
                },
                'cleaned_summary': {
                    'sentiment': cleaned_summary_sentiment,
                    'confidence': cleaned_summary_confidence
                }
            },
            'overall_rating': overall_rating,
            'rating_based_sentiment': 'positive' if overall_rating >= 4 else 'negative' if overall_rating <= 2 else 'neutral',
            'is_clean_review': is_clean_review,
            'has_profanity': profanity_body.get('has_profanity', False),
            'profanity_words': profanity_body.get('profanity_words', []),
            'analysis_method': 'textblob' if TEXTBLOB_AVAILABLE else 'basic_word_list',
            'processing_metadata': {
                'timestamp': datetime.now().isoformat(),
                'lambda_function': context.function_name if context else 'unknown',
                'analyzed_fields': ['reviewText', 'summary', 'overall']
            }
        }
        
        print(f"Sentiment analysis completed - Final sentiment: {final_sentiment} (confidence: {final_confidence:.2f})")
        
        return {
            'statusCode': 200,
            'body': sentiment_result
        }
        
    except Exception as e:
        error_msg = f"Error in sentiment analysis lambda: {str(e)}"
        print(error_msg)
        return {
            'statusCode': 500,
            'body': {
                'error': 'Internal server error',
                'message': str(e)
            }
        } 