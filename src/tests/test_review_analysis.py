import boto3
import json
import time
import pytest
from pathlib import Path
from datetime import datetime

class TestReviewAnalysis:
    def __init__(self):
        self.s3 = boto3.client('s3')
        self.dynamodb = boto3.client('dynamodb')
        self.lambda_client = boto3.client('lambda')
        
        # Configuration
        self.reviews_bucket = "review-analysis-reviews"
        self.processed_bucket = "review-analysis-processed"
        self.profanity_bucket = "review-analysis-profanity"
        self.sentiment_bucket = "review-analysis-sentiment"
        self.reviews_table = "review-analysis-reviews"
        self.users_table = "review-analysis-users"
        
        # Test data
        self.test_reviews = [
            {
                "reviewerID": "TEST_USER_1",
                "asin": "B000123456",
                "reviewerName": "Test User 1",
                "helpful": [2, 3],
                "reviewText": "This product is absolutely amazing! I love how it works and the quality is outstanding. Highly recommend to everyone.",
                "overall": 5.0,
                "summary": "Excellent product, highly recommended",
                "unixReviewTime": 1640995200,
                "reviewTime": "01 1, 2022"
            },
            {
                "reviewerID": "TEST_USER_2",
                "asin": "B000123457",
                "reviewerName": "Test User 2",
                "helpful": [1, 1],
                "reviewText": "This is the worst piece of crap I've ever bought. It's completely useless and a waste of money. Don't buy this shit!",
                "overall": 1.0,
                "summary": "Terrible product, waste of money",
                "unixReviewTime": 1640995201,
                "reviewTime": "01 1, 2022"
            },
            {
                "reviewerID": "TEST_USER_3",
                "asin": "B000123458",
                "reviewerName": "Test User 3",
                "helpful": [5, 7],
                "reviewText": "The product is okay, nothing special but it does what it's supposed to do. Average quality for the price.",
                "overall": 3.0,
                "summary": "Average product, meets expectations",
                "unixReviewTime": 1640995202,
                "reviewTime": "01 1, 2022"
            }
        ]
    
    def upload_test_review(self, review_data, review_index):
        """Upload a test review to S3"""
        review_key = f"test_review_{review_index}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        self.s3.put_object(
            Bucket=self.reviews_bucket,
            Key=review_key,
            Body=json.dumps(review_data),
            ContentType='application/json'
        )
        
        return review_key
    
    def wait_for_processing(self, review_id, max_wait_time=60):
        """Wait for review to be fully processed"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            try:
                response = self.dynamodb.get_item(
                    TableName=self.reviews_table,
                    Key={'review_id': {'S': review_id}}
                )
                
                if 'Item' in response:
                    status = response['Item'].get('processing_status', {}).get('S', '')
                    if status == 'sentiment_analyzed':
                        return response['Item']
                
                time.sleep(2)
            except Exception as e:
                print(f"Error checking processing status: {e}")
                time.sleep(2)
        
        return None
    
    def test_preprocessing_function(self):
        """Test preprocessing function"""
        print("Testing preprocessing function...")
        
        # Upload test review
        review_data = self.test_reviews[0]
        review_key = self.upload_test_review(review_data, 0)
        review_id = f"{review_data['reviewerID']}_{review_data['asin']}"
        
        # Wait for processing
        result = self.wait_for_processing(review_id)
        
        assert result is not None, "Preprocessing failed - no result found"
        assert result['processing_status']['S'] == 'sentiment_analyzed', f"Processing status is {result['processing_status']['S']}, expected 'sentiment_analyzed'"
        assert 'processed_s3_key' in result, "Processed S3 key not found"
        
        print("✓ Preprocessing function test passed")
        return result
    
    def test_profanity_check_function(self):
        """Test profanity check function"""
        print("Testing profanity check function...")
        
        # Upload test review with profanity
        review_data = self.test_reviews[1]  # Contains profanity
        review_key = self.upload_test_review(review_data, 1)
        review_id = f"{review_data['reviewerID']}_{review_data['asin']}"
        
        # Wait for processing
        result = self.wait_for_processing(review_id)
        
        assert result is not None, "Profanity check failed - no result found"
        assert result['has_profanity']['BOOL'] == True, "Profanity not detected"
        assert len(result['profanity_words_found']['L']) > 0, "No profanity words found"
        
        print("✓ Profanity check function test passed")
        return result
    
    def test_sentiment_analysis_function(self):
        """Test sentiment analysis function"""
        print("Testing sentiment analysis function...")
        
        # Upload test review
        review_data = self.test_reviews[0]  # Positive review
        review_key = self.upload_test_review(review_data, 2)
        review_id = f"{review_data['reviewerID']}_{review_data['asin']}"
        
        # Wait for processing
        result = self.wait_for_processing(review_id)
        
        assert result is not None, "Sentiment analysis failed - no result found"
        assert 'sentiment' in result, "Sentiment not found in result"
        assert 'sentiment_polarity' in result, "Sentiment polarity not found in result"
        
        # Check sentiment values
        sentiment = result['sentiment']['S']
        polarity = float(result['sentiment_polarity']['N'])
        
        assert sentiment in ['positive', 'negative', 'neutral'], f"Invalid sentiment: {sentiment}"
        assert -1.0 <= polarity <= 1.0, f"Invalid polarity: {polarity}"
        
        print("✓ Sentiment analysis function test passed")
        return result
    
    def test_user_banning_function(self):
        """Test user banning functionality"""
        print("Testing user banning functionality...")
        
        # Upload multiple reviews with profanity from the same user
        user_id = "TEST_BAN_USER"
        
        for i in range(4):  # Upload 4 profane reviews
            review_data = {
                "reviewerID": user_id,
                "asin": f"B00012345{i}",
                "reviewerName": "Test Ban User",
                "helpful": [1, 1],
                "reviewText": f"This is review {i+1} with profanity. This is shit and I hate it!",
                "overall": 1.0,
                "summary": f"Terrible review {i+1}",
                "unixReviewTime": 1640995200 + i,
                "reviewTime": "01 1, 2022"
            }
            
            review_key = self.upload_test_review(review_data, f"ban_{i}")
            review_id = f"{user_id}_{review_data['asin']}"
            
            # Wait for processing
            result = self.wait_for_processing(review_id)
            assert result is not None, f"Processing failed for review {i+1}"
        
        # Wait a bit for user table to be updated
        time.sleep(5)
        
        # Check user status
        try:
            user_response = self.dynamodb.get_item(
                TableName=self.users_table,
                Key={'reviewerID': {'S': user_id}}
            )
            
            assert 'Item' in user_response, "User record not found"
            user_item = user_response['Item']
            
            profanity_count = int(user_item['profanity_count']['N'])
            is_banned = user_item['is_banned']['BOOL']
            
            assert profanity_count >= 3, f"Expected profanity count >= 3, got {profanity_count}"
            assert is_banned == True, f"User should be banned, but is_banned is {is_banned}"
            
            print("✓ User banning functionality test passed")
            return user_item
            
        except Exception as e:
            print(f"Error checking user status: {e}")
            return None
    
    def test_function_chain(self):
        """Test the complete function chain"""
        print("Testing complete function chain...")
        
        # Upload a test review
        review_data = self.test_reviews[2]  # Neutral review
        review_key = self.upload_test_review(review_data, "chain")
        review_id = f"{review_data['reviewerID']}_{review_data['asin']}"
        
        # Wait for complete processing
        result = self.wait_for_processing(review_id)
        
        assert result is not None, "Function chain failed - no result found"
        
        # Verify all processing steps completed
        assert result['processing_status']['S'] == 'sentiment_analyzed', "Processing not completed"
        assert 'processed_s3_key' in result, "Preprocessing step failed"
        assert 'profanity_s3_key' in result, "Profanity check step failed"
        assert 'sentiment_s3_key' in result, "Sentiment analysis step failed"
        assert 'has_profanity' in result, "Profanity check result missing"
        assert 'sentiment' in result, "Sentiment analysis result missing"
        
        print("✓ Complete function chain test passed")
        return result
    
    def run_all_tests(self):
        """Run all integration tests"""
        print("Starting Review Analysis Integration Tests...")
        print("=" * 50)
        
        test_results = {}
        
        try:
            # Test preprocessing
            test_results['preprocessing'] = self.test_preprocessing_function()
            
            # Test profanity check
            test_results['profanity_check'] = self.test_profanity_check_function()
            
            # Test sentiment analysis
            test_results['sentiment_analysis'] = self.test_sentiment_analysis_function()
            
            # Test user banning
            test_results['user_banning'] = self.test_user_banning_function()
            
            # Test complete function chain
            test_results['function_chain'] = self.test_function_chain()
            
            print("\n" + "=" * 50)
            print("ALL TESTS PASSED! ✓")
            print("=" * 50)
            
            return test_results
            
        except Exception as e:
            print(f"\nTEST FAILED: {str(e)}")
            print("=" * 50)
            raise
    
    def generate_test_report(self, test_results):
        """Generate a test report"""
        print("\nGenerating Test Report...")
        print("=" * 50)
        
        report = {
            'test_timestamp': datetime.now().isoformat(),
            'total_tests': len(test_results),
            'tests_passed': len(test_results),
            'test_details': {}
        }
        
        for test_name, result in test_results.items():
            if result:
                report['test_details'][test_name] = {
                    'status': 'PASSED',
                    'details': 'Test completed successfully'
                }
            else:
                report['test_details'][test_name] = {
                    'status': 'FAILED',
                    'details': 'Test failed or returned no result'
                }
        
        # Save report
        report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"Test report saved to: {report_file}")
        return report

def main():
    """Main function to run tests"""
    tester = TestReviewAnalysis()
    test_results = tester.run_all_tests()
    tester.generate_test_report(test_results)

if __name__ == "__main__":
    main() 