#!/usr/bin/env python3
"""
Process Full Dataset Through Serverless Pipeline
This script processes the entire reviews_devset.json through the Lambda functions
and generates comprehensive analysis results.
"""

import json
import boto3
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure for LocalStack
os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

class FullDatasetProcessor:
    def __init__(self):
        self.common_config = {
            'endpoint_url': 'http://localhost:4566',
            'aws_access_key_id': 'test',
            'aws_secret_access_key': 'test',
            'region_name': 'us-east-1'
        }
        
        self.lambda_client = boto3.client('lambda', **self.common_config)
        
        # Statistics tracking
        self.stats = {
            'total_reviews': 0,
            'processed_reviews': 0,
            'failed_reviews': 0,
            'sentiment_counts': {'positive': 0, 'negative': 0, 'neutral': 0},
            'profanity_reviews': 0,
            'banned_users': 0,
            'user_profanity_counts': {},
            'processing_times': [],
            'errors': []
        }
        
        print("🚀 Full Dataset Processor Initialized")
    
    def load_dataset(self, file_path="Data/reviews_devset.json", max_reviews=None):
        """Load reviews from the dataset file"""
        print(f"📂 Loading dataset from {file_path}...")
        
        reviews = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if max_reviews and i >= max_reviews:
                        break
                    
                    try:
                        review = json.loads(line.strip())
                        reviews.append(review)
                    except json.JSONDecodeError as e:
                        print(f"⚠️  Error parsing line {i+1}: {e}")
                        continue
            
            print(f"✅ Loaded {len(reviews)} reviews from dataset")
            self.stats['total_reviews'] = len(reviews)
            return reviews
            
        except FileNotFoundError:
            print(f"❌ Dataset file not found: {file_path}")
            return []
        except Exception as e:
            print(f"❌ Error loading dataset: {e}")
            return []
    
    def process_single_review(self, review, review_index):
        """Process a single review through the complete pipeline"""
        start_time = time.time()
        
        try:
            # Step 1: Preprocessing
            preprocessing_payload = {
                "Records": [{
                    "s3": {
                        "bucket": {"name": "review-analysis-reviews"},
                        "object": {"key": f"batch/review_{review_index}.json"}
                    }
                }],
                "review_data": review
            }
            
            preprocessing_response = self.lambda_client.invoke(
                FunctionName='review-preprocessing',
                Payload=json.dumps(preprocessing_payload)
            )
            
            if preprocessing_response['StatusCode'] != 200:
                raise Exception(f"Preprocessing failed with status {preprocessing_response['StatusCode']}")
            
            preprocessing_result = json.loads(preprocessing_response['Payload'].read())
            
            # Step 2: Profanity Check
            profanity_payload = {
                "Records": [{
                    "s3": {
                        "bucket": {"name": "review-analysis-processed"},
                        "object": {"key": f"batch/processed_{review_index}.json"}
                    }
                }],
                "processed_data": {
                    "review_id": f"review_{review_index}",
                    "preprocessing_result": preprocessing_result,
                    "original_review": review
                }
            }
            
            profanity_response = self.lambda_client.invoke(
                FunctionName='review-profanity-check',
                Payload=json.dumps(profanity_payload)
            )
            
            if profanity_response['StatusCode'] != 200:
                raise Exception(f"Profanity check failed with status {profanity_response['StatusCode']}")
            
            profanity_result = json.loads(profanity_response['Payload'].read())
            
            # Step 3: Sentiment Analysis
            sentiment_payload = {
                "Records": [{
                    "s3": {
                        "bucket": {"name": "review-analysis-profanity"},
                        "object": {"key": f"batch/profanity_{review_index}.json"}
                    }
                }],
                "profanity_data": {
                    "review_id": f"review_{review_index}",
                    "preprocessing_result": preprocessing_result,
                    "profanity_result": profanity_result,
                    "original_review": review
                }
            }
            
            sentiment_response = self.lambda_client.invoke(
                FunctionName='review-sentiment-analysis',
                Payload=json.dumps(sentiment_payload)
            )
            
            if sentiment_response['StatusCode'] != 200:
                raise Exception(f"Sentiment analysis failed with status {sentiment_response['StatusCode']}")
            
            sentiment_result = json.loads(sentiment_response['Payload'].read())
            
            # Update statistics
            processing_time = time.time() - start_time
            self.update_statistics(preprocessing_result, profanity_result, sentiment_result, processing_time)
            
            return {
                'review_index': review_index,
                'success': True,
                'processing_time': processing_time
            }
            
        except Exception as e:
            self.stats['failed_reviews'] += 1
            self.stats['errors'].append(f"Review {review_index}: {str(e)}")
            
            return {
                'review_index': review_index,
                'success': False,
                'error': str(e),
                'processing_time': time.time() - start_time
            }
    
    def update_statistics(self, preprocessing_result, profanity_result, sentiment_result, processing_time):
        """Update processing statistics"""
        self.stats['processed_reviews'] += 1
        self.stats['processing_times'].append(processing_time)
        
        # Sentiment statistics
        if sentiment_result.get('body'):
            sentiment = sentiment_result['body'].get('sentiment', 'neutral')
            self.stats['sentiment_counts'][sentiment] = self.stats['sentiment_counts'].get(sentiment, 0) + 1
        
        # Profanity statistics
        if profanity_result.get('body', {}).get('has_profanity'):
            self.stats['profanity_reviews'] += 1
        
        # User profanity tracking
        if profanity_result.get('body', {}).get('user_update'):
            user_update = profanity_result['body']['user_update']
            reviewer_id = user_update.get('reviewer_id')
            profanity_count = user_update.get('new_profanity_count', 0)
            is_banned = user_update.get('is_banned', False)
            
            if reviewer_id:
                self.stats['user_profanity_counts'][reviewer_id] = profanity_count
                if is_banned:
                    self.stats['banned_users'] += 1
    
    def process_dataset_batch(self, reviews, batch_size=20, max_workers=5):
        """Process dataset in batches with threading"""
        print(f"🔄 Processing {len(reviews)} reviews in batches of {batch_size}...")
        print(f"🧵 Using {max_workers} parallel workers")
        
        results = []
        
        # Process in batches
        for batch_start in range(0, len(reviews), batch_size):
            batch_end = min(batch_start + batch_size, len(reviews))
            batch_reviews = reviews[batch_start:batch_end]
            
            print(f"\n📦 Processing batch {batch_start//batch_size + 1}: reviews {batch_start} to {batch_end-1}")
            
            # Use ThreadPoolExecutor for parallel processing
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks for this batch
                future_to_index = {
                    executor.submit(self.process_single_review, review, batch_start + i): batch_start + i
                    for i, review in enumerate(batch_reviews)
                }
                
                # Collect results as they complete
                batch_results = []
                for future in as_completed(future_to_index):
                    result = future.result()
                    batch_results.append(result)
                    
                    # Print progress
                    if result['success']:
                        print(f"   ✅ Review {result['review_index']} processed in {result['processing_time']:.2f}s")
                    else:
                        print(f"   ❌ Review {result['review_index']} failed")
                
                results.extend(batch_results)
            
            # Print batch statistics
            successful = len([r for r in batch_results if r['success']])
            failed = len([r for r in batch_results if not r['success']])
            avg_time = sum(r['processing_time'] for r in batch_results) / len(batch_results)
            
            print(f"   📊 Batch {batch_start//batch_size + 1} complete: {successful} success, {failed} failed, avg {avg_time:.2f}s")
        
        return results
    
    def generate_results_summary(self):
        """Generate comprehensive results summary"""
        print("\n" + "="*80)
        print("📊 COMPREHENSIVE ANALYSIS RESULTS")
        print("="*80)
        
        print(f"\n📈 PROCESSING STATISTICS:")
        print(f"   • Total Reviews: {self.stats['total_reviews']:,}")
        print(f"   • Successfully Processed: {self.stats['processed_reviews']:,}")
        print(f"   • Failed: {self.stats['failed_reviews']:,}")
        if self.stats['total_reviews'] > 0:
            print(f"   • Success Rate: {(self.stats['processed_reviews']/self.stats['total_reviews']*100):.1f}%")
        
        if self.stats['processing_times']:
            avg_time = sum(self.stats['processing_times']) / len(self.stats['processing_times'])
            total_time = sum(self.stats['processing_times'])
            print(f"   • Average Processing Time: {avg_time:.2f}s per review")
            print(f"   • Total Processing Time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
        
        print(f"\n💭 SENTIMENT ANALYSIS:")
        for sentiment, count in self.stats['sentiment_counts'].items():
            percentage = (count / self.stats['processed_reviews'] * 100) if self.stats['processed_reviews'] > 0 else 0
            print(f"   • {sentiment.title()}: {count:,} ({percentage:.1f}%)")
        
        print(f"\n🚫 PROFANITY ANALYSIS:")
        profanity_rate = (self.stats['profanity_reviews'] / self.stats['processed_reviews'] * 100) if self.stats['processed_reviews'] > 0 else 0
        print(f"   • Reviews with Profanity: {self.stats['profanity_reviews']:,} ({profanity_rate:.1f}%)")
        print(f"   • Users with Profanity: {len(self.stats['user_profanity_counts']):,}")
        print(f"   • Banned Users: {self.stats['banned_users']:,}")
        
        if self.stats['user_profanity_counts']:
            max_profanity = max(self.stats['user_profanity_counts'].values())
            print(f"   • Highest User Profanity Count: {max_profanity}")
        
        # Save detailed results to file
        self.save_results_to_file()
    
    def save_results_to_file(self):
        """Save detailed results to JSON file"""
        results_file = "assignment_results.json"
        
        final_results = {
            "processing_summary": {
                "total_reviews": self.stats['total_reviews'],
                "processed_reviews": self.stats['processed_reviews'],
                "failed_reviews": self.stats['failed_reviews'],
                "success_rate": (self.stats['processed_reviews']/self.stats['total_reviews']*100) if self.stats['total_reviews'] > 0 else 0
            },
            "sentiment_analysis": {
                "counts": self.stats['sentiment_counts'],
                "percentages": {
                    sentiment: (count / self.stats['processed_reviews'] * 100) if self.stats['processed_reviews'] > 0 else 0
                    for sentiment, count in self.stats['sentiment_counts'].items()
                }
            },
            "profanity_analysis": {
                "reviews_with_profanity": self.stats['profanity_reviews'],
                "profanity_rate_percent": (self.stats['profanity_reviews'] / self.stats['processed_reviews'] * 100) if self.stats['processed_reviews'] > 0 else 0,
                "users_with_profanity": len(self.stats['user_profanity_counts']),
                "banned_users": self.stats['banned_users']
            },
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            with open(results_file, 'w') as f:
                json.dump(final_results, f, indent=2)
            print(f"\n💾 Detailed results saved to: {results_file}")
        except Exception as e:
            print(f"\n❌ Error saving results file: {e}")
    
    def run_full_analysis(self, max_reviews=None, batch_size=20, max_workers=5):
        """Run complete analysis of the dataset"""
        print("🚀 STARTING FULL DATASET ANALYSIS")
        print("="*80)
        
        start_time = time.time()
        
        # Load dataset
        reviews = self.load_dataset(max_reviews=max_reviews)
        if not reviews:
            print("❌ No reviews to process. Exiting.")
            return
        
        # Process all reviews
        results = self.process_dataset_batch(reviews, batch_size=batch_size, max_workers=max_workers)
        
        # Generate summary
        total_time = time.time() - start_time
        print(f"\n⏱️  Total Analysis Time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
        
        self.generate_results_summary()
        
        print("\n🎉 FULL DATASET ANALYSIS COMPLETE!")
        print("="*80)

def main():
    """Main function to run full dataset analysis"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Process full reviews dataset through serverless pipeline')
    parser.add_argument('--max-reviews', type=int, help='Maximum number of reviews to process (default: all)')
    parser.add_argument('--batch-size', type=int, default=20, help='Batch size for processing (default: 20)')
    parser.add_argument('--max-workers', type=int, default=5, help='Maximum parallel workers (default: 5)')
    
    args = parser.parse_args()
    
    processor = FullDatasetProcessor()
    processor.run_full_analysis(
        max_reviews=args.max_reviews,
        batch_size=args.batch_size,
        max_workers=args.max_workers
    )

if __name__ == "__main__":
    main()
