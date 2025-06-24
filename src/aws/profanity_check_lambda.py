import boto3
import json
import os
import re
from datetime import datetime

# Initialize AWS clients
s3 = boto3.client('s3')
dynamodb = boto3.client('dynamodb')

# Common profanity words list (this would typically be stored in S3 or SSM)
PROFANITY_WORDS = {
    'shit', 'fuck', 'ass', 'bitch', 'crap', 'damn', 'hell', 'piss', 'dick', 'cock',
    'pussy', 'bastard', 'motherfucker', 'fucker', 'bullshit', 'garbage', 'trash',
    'stupid', 'idiot', 'moron', 'dumb', 'useless', 'worthless', 'terrible', 'awful'
}

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

def check_profanity(text):
    """
    Check if text contains profanity words
    Returns: (has_profanity, profanity_words_found)
    """
    if not text or not isinstance(text, str):
        return False, []
    
    # Convert to lowercase for comparison
    text_lower = text.lower()
    
    # Find profanity words in the text
    found_profanity = []
    for word in PROFANITY_WORDS:
        if word in text_lower:
            found_profanity.append(word)
    
    return len(found_profanity) > 0, found_profanity

def lambda_handler(event, context):
    """
    Lambda function to check for profanity in processed reviews
    Triggered by S3 object creation in processed bucket
    """
    print(f"Profanity Check Lambda invoked with event: {json.dumps(event)}")
    
    try:
        # Get configuration parameters
        processed_bucket = get_parameter('processed_bucket')
        profanity_bucket = get_parameter('profanity_bucket')
        reviews_table = get_parameter('reviews_table')
        users_table = get_parameter('users_table')
        
        # Extract S3 event details
        if "Records" in event and len(event["Records"]) > 0:
            s3_event = event["Records"][0]["s3"]
            bucket_name = s3_event["bucket"]["name"]
            object_key = s3_event["object"]["key"]
            event_time = event["Records"][0]["eventTime"]
        else:
            raise ValueError("No S3 records found in event")
        
        # Download the processed review from S3
        response = s3.get_object(Bucket=bucket_name, Key=object_key)
        processed_review = json.loads(response['Body'].read().decode('utf-8'))
        
        # Check profanity in original text and summary
        review_text_profanity, review_text_bad_words = check_profanity(processed_review.get('original_reviewText', ''))
        summary_profanity, summary_bad_words = check_profanity(processed_review.get('original_summary', ''))
        
        # Combine all bad words found
        all_bad_words = list(set(review_text_bad_words + summary_bad_words))
        has_profanity = review_text_profanity or summary_profanity
        
        # Create profanity check result
        profanity_result = {
            'reviewerID': processed_review.get('reviewerID'),
            'asin': processed_review.get('asin'),
            'reviewerName': processed_review.get('reviewerName'),
            'has_profanity': has_profanity,
            'profanity_words_found': all_bad_words,
            'review_text_has_profanity': review_text_profanity,
            'summary_has_profanity': summary_profanity,
            'review_text_bad_words': review_text_bad_words,
            'summary_bad_words': summary_bad_words,
            'original_reviewText': processed_review.get('original_reviewText'),
            'original_summary': processed_review.get('original_summary'),
            'overall': processed_review.get('overall'),
            'unixReviewTime': processed_review.get('unixReviewTime'),
            'reviewTime': processed_review.get('reviewTime'),
            'processing_timestamp': processed_review.get('processing_timestamp'),
            'profanity_check_timestamp': datetime.now().isoformat(),
            's3_event_time': event_time,
            'processed_s3_key': object_key
        }
        
        # Upload profanity check result to profanity bucket
        profanity_key = f"profanity_check/{processed_review.get('reviewerID')}_{processed_review.get('asin')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        s3.put_object(
            Bucket=profanity_bucket,
            Key=profanity_key,
            Body=json.dumps(profanity_result),
            ContentType='application/json'
        )
        
        # Update DynamoDB review tracking
        dynamodb_item = {
            'review_id': {'S': f"{processed_review.get('reviewerID')}_{processed_review.get('asin')}"},
            'reviewerID': {'S': processed_review.get('reviewerID')},
            'asin': {'S': processed_review.get('asin')},
            'processing_status': {'S': 'profanity_checked'},
            'has_profanity': {'BOOL': has_profanity},
            'profanity_words_found': {'L': [{'S': word} for word in all_bad_words]},
            'profanity_s3_key': {'S': profanity_key},
            'processed_s3_key': {'S': object_key},
            'profanity_check_timestamp': {'S': profanity_result['profanity_check_timestamp']},
            's3_event_time': {'S': event_time},
            'lambda_function': {'S': context.function_name},
            'lambda_version': {'S': context.function_version}
        }
        
        dynamodb.put_item(
            TableName=reviews_table,
            Item=dynamodb_item
        )
        
        # Update user profanity count if profanity was found
        if has_profanity:
            try:
                # Get current user record
                user_response = dynamodb.get_item(
                    TableName=users_table,
                    Key={'reviewerID': {'S': processed_review.get('reviewerID')}}
                )
                
                if 'Item' in user_response:
                    # User exists, increment profanity count
                    current_count = user_response['Item'].get('profanity_count', {'N': '0'})
                    new_count = int(current_count['N']) + 1
                    is_banned = new_count > 3
                    
                    dynamodb.update_item(
                        TableName=users_table,
                        Key={'reviewerID': {'S': processed_review.get('reviewerID')}},
                        UpdateExpression='SET profanity_count = :count, is_banned = :banned, last_updated = :timestamp',
                        ExpressionAttributeValues={
                            ':count': {'N': str(new_count)},
                            ':banned': {'BOOL': is_banned},
                            ':timestamp': {'S': datetime.now().isoformat()}
                        }
                    )
                else:
                    # New user, create record
                    dynamodb.put_item(
                        TableName=users_table,
                        Item={
                            'reviewerID': {'S': processed_review.get('reviewerID')},
                            'reviewerName': {'S': processed_review.get('reviewerName', '')},
                            'profanity_count': {'N': '1'},
                            'is_banned': {'BOOL': False},
                            'created_at': {'S': datetime.now().isoformat()},
                            'last_updated': {'S': datetime.now().isoformat()}
                        }
                    )
            except Exception as e:
                print(f"Error updating user profanity count: {e}")
        
        print(f"Successfully completed profanity check: {profanity_key}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Profanity check completed successfully',
                'profanity_key': profanity_key,
                'has_profanity': has_profanity,
                'profanity_words_found': all_bad_words,
                'reviewerID': processed_review.get('reviewerID'),
                'asin': processed_review.get('asin')
            })
        }
        
    except Exception as e:
        print(f"Error in profanity check lambda: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        } 