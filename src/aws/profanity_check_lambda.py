import boto3
import json
import os
from datetime import datetime

# Initialize AWS clients
s3 = boto3.client('s3')
dynamodb = boto3.client('dynamodb')
ssm = boto3.client('ssm')

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

# Common profanity words list (basic set for demonstration)
PROFANITY_WORDS = {
    'damn', 'hell', 'crap', 'shit', 'fuck', 'fucking', 'fucked', 'bitch', 'bastard',
    'asshole', 'ass', 'piss', 'suck', 'sucks', 'sucked', 'stupid', 'idiot', 'moron',
    'dumb', 'hate', 'terrible', 'awful', 'horrible', 'disgusting', 'pathetic',
    'worthless', 'useless', 'garbage', 'trash', 'piece of shit', 'bullshit'
}

def check_profanity(text):
    """
    Check if text contains profanity words
    Returns tuple: (has_profanity, profanity_words_found)
    """
    if not text or not isinstance(text, str):
        return False, []
    
    text_lower = text.lower()
    found_profanity = []
    
    for word in PROFANITY_WORDS:
        if word in text_lower:
            found_profanity.append(word)
    
    return len(found_profanity) > 0, found_profanity

def check_profanity_in_tokens(tokens):
    """
    Check profanity in tokenized text
    Returns tuple: (has_profanity, profanity_words_found)
    """
    if not tokens:
        return False, []
    
    found_profanity = []
    
    for token in tokens:
        if isinstance(token, str) and token.lower() in PROFANITY_WORDS:
            found_profanity.append(token.lower())
    
    return len(found_profanity) > 0, found_profanity

def lambda_handler(event, context):
    """
    Lambda function to check for profanity in preprocessed review data
    Handles both S3 event triggers and direct data passing
    """
    print(f"Profanity Check Lambda invoked with event: {json.dumps(event)}")
    
    try:
        # Get configuration parameters
        profanity_bucket = get_parameter('profanity_bucket')
        users_table = get_parameter('users_table')
        
        # Extract processed data - handle both S3 events and direct data
        processed_data = None
        
        if "processed_data" in event:
            # Direct data passing (for LocalStack compatibility)
            processed_data = event["processed_data"]
            print("Processing direct profanity check data")
            
        elif "Records" in event and len(event["Records"]) > 0:
            # S3 event processing
            s3_event = event["Records"][0]["s3"]
            bucket_name = s3_event["bucket"]["name"]
            object_key = s3_event["object"]["key"]
            
            # Download the processed data from S3
            response = s3.get_object(Bucket=bucket_name, Key=object_key)
            processed_data = json.loads(response['Body'].read().decode('utf-8'))
            print(f"Processing S3 event from {bucket_name}/{object_key}")
            
        else:
            raise ValueError("No valid processed data or S3 records found in event")
        
        if not processed_data:
            raise ValueError("Failed to extract processed data from event")
        
        # Extract preprocessing results
        preprocessing_result = processed_data.get('preprocessing_result', {})
        if isinstance(preprocessing_result, dict) and 'body' in preprocessing_result:
            preprocessing_body = preprocessing_result['body']
        else:
            preprocessing_body = preprocessing_result
        
        review_text_data = preprocessing_body.get('reviewText', {})
        summary_data = preprocessing_body.get('summary', {})
        
        # Check profanity in reviewText
        review_text_original = review_text_data.get('original', '')
        review_text_tokens = review_text_data.get('preprocessed', [])
        review_text_cleaned = review_text_data.get('cleaned', '')
        
        # Check profanity in summary
        summary_original = summary_data.get('original', '')
        summary_tokens = summary_data.get('preprocessed', [])
        summary_cleaned = summary_data.get('cleaned', '')
        
        # Check profanity in all text fields
        review_has_profanity, review_profanity_words = check_profanity(review_text_original)
        review_tokens_has_profanity, review_tokens_profanity = check_profanity_in_tokens(review_text_tokens)
        
        summary_has_profanity, summary_profanity_words = check_profanity(summary_original)
        summary_tokens_has_profanity, summary_tokens_profanity = check_profanity_in_tokens(summary_tokens)
        
        # Overall profanity check (requirement: check reviewText, summary, and overall fields)
        overall_rating = processed_data.get('original_review', {}).get('overall', 0)
        
        # Combine all profanity findings
        all_profanity_words = list(set(
            review_profanity_words + review_tokens_profanity + 
            summary_profanity_words + summary_tokens_profanity
        ))
        
        has_any_profanity = (
            review_has_profanity or review_tokens_has_profanity or
            summary_has_profanity or summary_tokens_has_profanity
        )
        
        # Check if low rating indicates negative sentiment (could be considered "rude")
        low_rating_negative = overall_rating <= 2.0
        
        # Create profanity check result
        profanity_result = {
            'has_profanity': has_any_profanity,
            'profanity_words': all_profanity_words,
            'profanity_count': len(all_profanity_words),
            'review_text_profanity': {
                'has_profanity': review_has_profanity or review_tokens_has_profanity,
                'words': list(set(review_profanity_words + review_tokens_profanity))
            },
            'summary_profanity': {
                'has_profanity': summary_has_profanity or summary_tokens_has_profanity,
                'words': list(set(summary_profanity_words + summary_tokens_profanity))
            },
            'overall_rating': overall_rating,
            'low_rating_negative': low_rating_negative,
            'clean_review': not has_any_profanity,
            'processing_metadata': {
                'timestamp': datetime.now().isoformat(),
                'lambda_function': context.function_name if context else 'unknown',
                'checked_fields': ['reviewText', 'summary', 'overall']
            }
        }
        
        # Update user profanity count if profanity found
        reviewer_id = processed_data.get('original_review', {}).get('reviewerID')
        if has_any_profanity and reviewer_id:
            try:
                # Get current user data
                user_response = dynamodb.get_item(
                    TableName=users_table,
                    Key={'reviewerID': {'S': reviewer_id}}
                )
                
                current_count = 0
                if 'Item' in user_response:
                    current_count = int(user_response['Item'].get('profanity_count', {}).get('N', '0'))
                
                new_count = current_count + 1
                is_banned = new_count > 3  # Ban after more than 3 profane reviews
                
                # Update user record
                dynamodb.put_item(
                    TableName=users_table,
                    Item={
                        'reviewerID': {'S': reviewer_id},
                        'profanity_count': {'N': str(new_count)},
                        'is_banned': {'BOOL': is_banned},
                        'last_violation': {'S': datetime.now().isoformat()},
                        'last_profanity_words': {'SS': all_profanity_words if all_profanity_words else ['none']}
                    }
                )
                
                profanity_result['user_update'] = {
                    'reviewer_id': reviewer_id,
                    'new_profanity_count': new_count,
                    'is_banned': is_banned
                }
                
                if is_banned:
                    print(f"User {reviewer_id} banned for profanity (count: {new_count})")
                    
            except Exception as e:
                print(f"Error updating user profanity count: {e}")
                profanity_result['user_update_error'] = str(e)
        
        print(f"Profanity check completed - Has profanity: {has_any_profanity}, Words found: {len(all_profanity_words)}")
        
        return {
            'statusCode': 200,
            'body': profanity_result
        }
        
    except Exception as e:
        error_msg = f"Error in profanity check lambda: {str(e)}"
        print(error_msg)
        return {
            'statusCode': 500,
            'body': {
                'error': 'Internal server error',
                'message': str(e)
            }
        } 