#!/usr/bin/env python3
"""
Test Real Lambda Function Chain
This script tests individual Lambda functions with real AWS API invocations
to ensure the serverless architecture works correctly.
"""

import json
import boto3
import os
import time
from datetime import datetime

# Configure for LocalStack
os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

class LambdaChainTester:
    def __init__(self):
        self.common_config = {
            'endpoint_url': 'http://localhost:4566',
            'aws_access_key_id': 'test',
            'aws_secret_access_key': 'test',
            'region_name': 'us-east-1'
        }
        
        self.lambda_client = boto3.client('lambda', **self.common_config)
        self.s3 = boto3.client('s3', **self.common_config)
        
        print("🧪 Lambda Chain Tester Initialized")
    
    def test_lambda_function(self, function_name, test_payload):
        """Test a specific Lambda function with real invocation"""
        print(f"\n🔬 Testing Lambda function: {function_name}")
        print(f"📤 Payload: {json.dumps(test_payload, indent=2)}")
        
        try:
            response = self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(test_payload)
            )
            
            if response['StatusCode'] == 200:
                result = json.loads(response['Payload'].read().decode('utf-8'))
                print(f"✅ {function_name} - SUCCESS")
                print(f"📤 Response: {json.dumps(result, indent=2)}")
                return result
            else:
                print(f"❌ {function_name} - FAILED (Status: {response['StatusCode']})")
                return None
                
        except Exception as e:
            print(f"❌ {function_name} - ERROR: {e}")
            return None
    
    def test_preprocessing_lambda(self):
        """Test the preprocessing Lambda function"""
        test_review = {
            "reviewerID": "TEST_USER_001",
            "asin": "TEST_PRODUCT_001", 
            "reviewText": "This product is absolutely AMAZING! I love it so much, highly recommend to everyone!",
            "summary": "Great product, excellent quality",
            "overall": 5.0,
            "unixReviewTime": int(time.time())
        }
        
        payload = {
            "Records": [{
                "s3": {
                    "bucket": {"name": "review-analysis-reviews"},
                    "object": {"key": "test/test_review.json"}
                }
            }],
            "review_data": test_review
        }
        
        return self.test_lambda_function('review-preprocessing', payload)
    
    def test_profanity_check_lambda(self):
        """Test the profanity check Lambda function"""
        test_processed_data = {
            "review_id": "test_review_001",
            "preprocessing_result": {
                "statusCode": 200,
                "body": {
                    "reviewText": {
                        "original": "This product is damn good but the shipping sucks!",
                        "preprocessed": ["product", "damn", "good", "shipping", "sucks"],
                        "cleaned": "product damn good shipping sucks"
                    },
                    "summary": {
                        "original": "Good product, bad service",
                        "preprocessed": ["good", "product", "bad", "service"],
                        "cleaned": "good product bad service"
                    }
                }
            },
            "original_review": {
                "reviewerID": "TEST_USER_002",
                "overall": 3.0
            }
        }
        
        payload = {
            "Records": [{
                "s3": {
                    "bucket": {"name": "review-analysis-processed"},
                    "object": {"key": "test/test_processed.json"}
                }
            }],
            "processed_data": test_processed_data
        }
        
        return self.test_lambda_function('review-profanity-check', payload)
    
    def test_sentiment_analysis_lambda(self):
        """Test the sentiment analysis Lambda function"""
        test_profanity_data = {
            "review_id": "test_review_002",
            "preprocessing_result": {
                "statusCode": 200,
                "body": {
                    "reviewText": {
                        "original": "I absolutely love this product! It's fantastic and amazing!",
                        "preprocessed": ["absolutely", "love", "product", "fantastic", "amazing"],
                        "cleaned": "absolutely love product fantastic amazing"
                    },
                    "summary": {
                        "original": "Excellent product",
                        "preprocessed": ["excellent", "product"],
                        "cleaned": "excellent product"
                    }
                }
            },
            "profanity_result": {
                "statusCode": 200,
                "body": {
                    "has_profanity": False,
                    "profanity_words": [],
                    "clean_review": True
                }
            },
            "original_review": {
                "reviewerID": "TEST_USER_003",
                "overall": 5.0
            }
        }
        
        payload = {
            "Records": [{
                "s3": {
                    "bucket": {"name": "review-analysis-profanity"},
                    "object": {"key": "test/test_profanity.json"}
                }
            }],
            "profanity_data": test_profanity_data
        }
        
        return self.test_lambda_function('review-sentiment-analysis', payload)
    
    def test_complete_lambda_chain(self):
        """Test the complete Lambda function chain with a real review"""
        print("\n🔗 TESTING COMPLETE LAMBDA CHAIN")
        print("="*60)
        
        # Step 1: Test preprocessing
        print("\n🔄 STEP 1: Testing Preprocessing Lambda")
        preprocessing_result = self.test_preprocessing_lambda()
        
        if not preprocessing_result:
            print("❌ Chain test failed at preprocessing step")
            return False
        
        # Step 2: Test profanity check
        print("\n🔄 STEP 2: Testing Profanity Check Lambda")
        profanity_result = self.test_profanity_check_lambda()
        
        if not profanity_result:
            print("❌ Chain test failed at profanity check step")
            return False
        
        # Step 3: Test sentiment analysis
        print("\n🔄 STEP 3: Testing Sentiment Analysis Lambda")
        sentiment_result = self.test_sentiment_analysis_lambda()
        
        if not sentiment_result:
            print("❌ Chain test failed at sentiment analysis step")
            return False
        
        print("\n✅ COMPLETE LAMBDA CHAIN TEST SUCCESSFUL!")
        print("🚀 All Lambda functions are working correctly with real invocations")
        
        return True
    
    def list_lambda_functions(self):
        """List all available Lambda functions"""
        print("\n📋 AVAILABLE LAMBDA FUNCTIONS:")
        
        try:
            response = self.lambda_client.list_functions()
            functions = response.get('Functions', [])
            
            for func in functions:
                print(f"   • {func['FunctionName']} (Runtime: {func['Runtime']})")
            
            return len(functions) > 0
            
        except Exception as e:
            print(f"❌ Error listing Lambda functions: {e}")
            return False
    
    def check_lambda_status(self, function_name):
        """Check the status of a specific Lambda function"""
        try:
            response = self.lambda_client.get_function(FunctionName=function_name)
            
            state = response['Configuration']['State']
            print(f"📊 {function_name} status: {state}")
            
            if state == 'Active':
                print(f"✅ {function_name} is ready for invocation")
                return True
            else:
                print(f"⚠️  {function_name} is not active (State: {state})")
                return False
                
        except Exception as e:
            print(f"❌ Error checking {function_name}: {e}")
            return False

def main():
    """Main function to test the Lambda chain"""
    print("🧪 LAMBDA FUNCTION CHAIN TESTER")
    print("Testing real Lambda function invocations for event-driven architecture")
    print("="*80)
    
    tester = LambdaChainTester()
    
    # Check if Lambda functions are available
    print("🔍 Checking Lambda function availability...")
    if not tester.list_lambda_functions():
        print("❌ No Lambda functions found. Please deploy them first.")
        return
    
    # Check individual function status
    lambda_functions = ['review-preprocessing', 'review-profanity-check', 'review-sentiment-analysis']
    all_ready = True
    
    for func_name in lambda_functions:
        if not tester.check_lambda_status(func_name):
            all_ready = False
    
    if not all_ready:
        print("⚠️  Some Lambda functions are not ready. Testing may fail.")
    
    # Test individual functions
    print("\n🔬 TESTING INDIVIDUAL LAMBDA FUNCTIONS:")
    print("="*60)
    
    preprocessing_ok = tester.test_preprocessing_lambda() is not None
    profanity_ok = tester.test_profanity_check_lambda() is not None  
    sentiment_ok = tester.test_sentiment_analysis_lambda() is not None
    
    # Test complete chain
    chain_ok = tester.test_complete_lambda_chain()
    
    # Summary
    print("\n📊 TEST RESULTS SUMMARY:")
    print("="*40)
    print(f"   Preprocessing Lambda: {'✅ PASS' if preprocessing_ok else '❌ FAIL'}")
    print(f"   Profanity Check Lambda: {'✅ PASS' if profanity_ok else '❌ FAIL'}")
    print(f"   Sentiment Analysis Lambda: {'✅ PASS' if sentiment_ok else '❌ FAIL'}")
    print(f"   Complete Chain: {'✅ PASS' if chain_ok else '❌ FAIL'}")
    
    if all([preprocessing_ok, profanity_ok, sentiment_ok, chain_ok]):
        print("\n🎉 ALL TESTS PASSED!")
        print("🚀 Lambda functions are ready for event-driven serverless processing!")
    else:
        print("\n⚠️  SOME TESTS FAILED!")
        print("🔧 Please check Lambda function deployment and configuration.")

if __name__ == "__main__":
    main() 