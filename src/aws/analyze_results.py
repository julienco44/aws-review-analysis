import boto3
import json
from datetime import datetime
from collections import defaultdict

class ReviewAnalysisResults:
    def __init__(self):
        self.dynamodb = boto3.client('dynamodb')
        self.s3 = boto3.client('s3')
        
        # Configuration
        self.reviews_table = "review-analysis-reviews"
        self.users_table = "review-analysis-users"
        self.sentiment_bucket = "review-analysis-sentiment"
    
    def get_all_reviews(self):
        """Get all processed reviews from DynamoDB"""
        reviews = []
        
        try:
            # Scan the reviews table
            response = self.dynamodb.scan(TableName=self.reviews_table)
            
            while True:
                for item in response.get('Items', []):
                    reviews.append(item)
                
                # Check if there are more items
                if 'LastEvaluatedKey' in response:
                    response = self.dynamodb.scan(
                        TableName=self.reviews_table,
                        ExclusiveStartKey=response['LastEvaluatedKey']
                    )
                else:
                    break
                    
        except Exception as e:
            print(f"Error scanning reviews table: {e}")
        
        return reviews
    
    def get_all_users(self):
        """Get all users from DynamoDB"""
        users = []
        
        try:
            # Scan the users table
            response = self.dynamodb.scan(TableName=self.users_table)
            
            while True:
                for item in response.get('Items', []):
                    users.append(item)
                
                # Check if there are more items
                if 'LastEvaluatedKey' in response:
                    response = self.dynamodb.scan(
                        TableName=self.users_table,
                        ExclusiveStartKey=response['LastEvaluatedKey']
                    )
                else:
                    break
                    
        except Exception as e:
            print(f"Error scanning users table: {e}")
        
        return users
    
    def analyze_sentiment_distribution(self, reviews):
        """Analyze sentiment distribution"""
        sentiment_counts = defaultdict(int)
        
        for review in reviews:
            if 'sentiment' in review:
                sentiment = review['sentiment']['S']
                sentiment_counts[sentiment] += 1
        
        return dict(sentiment_counts)
    
    def analyze_profanity_distribution(self, reviews):
        """Analyze profanity distribution"""
        profanity_count = 0
        total_reviews = len(reviews)
        
        for review in reviews:
            if 'has_profanity' in review and review['has_profanity']['BOOL']:
                profanity_count += 1
        
        return {
            'total_reviews': total_reviews,
            'profanity_reviews': profanity_count,
            'clean_reviews': total_reviews - profanity_count,
            'profanity_percentage': (profanity_count / total_reviews * 100) if total_reviews > 0 else 0
        }
    
    def analyze_banned_users(self, users):
        """Analyze banned users"""
        banned_users = []
        total_users = len(users)
        
        for user in users:
            if 'is_banned' in user and user['is_banned']['BOOL']:
                banned_users.append({
                    'reviewerID': user['reviewerID']['S'],
                    'reviewerName': user.get('reviewerName', {}).get('S', 'Unknown'),
                    'profanity_count': int(user.get('profanity_count', {}).get('N', 0)),
                    'created_at': user.get('created_at', {}).get('S', 'Unknown'),
                    'last_updated': user.get('last_updated', {}).get('S', 'Unknown')
                })
        
        return {
            'total_users': total_users,
            'banned_users': banned_users,
            'banned_count': len(banned_users),
            'banned_percentage': (len(banned_users) / total_users * 100) if total_users > 0 else 0
        }
    
    def analyze_review_details(self, reviews):
        """Analyze detailed review information"""
        review_details = []
        
        for review in reviews:
            detail = {
                'review_id': review['review_id']['S'],
                'reviewerID': review['reviewerID']['S'],
                'asin': review['asin']['S'],
                'sentiment': review.get('sentiment', {}).get('S', 'unknown'),
                'has_profanity': review.get('has_profanity', {}).get('BOOL', False),
                'profanity_words': [word['S'] for word in review.get('profanity_words_found', {}).get('L', [])],
                'sentiment_polarity': float(review.get('sentiment_polarity', {}).get('N', 0)),
                'processing_status': review.get('processing_status', {}).get('S', 'unknown'),
                'processing_timestamp': review.get('processing_timestamp', {}).get('S', 'unknown')
            }
            review_details.append(detail)
        
        return review_details
    
    def generate_report(self):
        """Generate comprehensive analysis report"""
        print("Generating Review Analysis Report...")
        print("=" * 50)
        
        # Get data
        reviews = self.get_all_reviews()
        users = self.get_all_users()
        
        print(f"Found {len(reviews)} reviews and {len(users)} users")
        
        # Analyze data
        sentiment_dist = self.analyze_sentiment_distribution(reviews)
        profanity_dist = self.analyze_profanity_distribution(reviews)
        banned_users_info = self.analyze_banned_users(users)
        review_details = self.analyze_review_details(reviews)
        
        # Create report
        report = {
            'analysis_timestamp': datetime.now().isoformat(),
            'summary': {
                'total_reviews': len(reviews),
                'total_users': len(users),
                'positive_reviews': sentiment_dist.get('positive', 0),
                'negative_reviews': sentiment_dist.get('negative', 0),
                'neutral_reviews': sentiment_dist.get('neutral', 0),
                'profanity_reviews': profanity_dist['profanity_reviews'],
                'banned_users': banned_users_info['banned_count']
            },
            'sentiment_analysis': sentiment_dist,
            'profanity_analysis': profanity_dist,
            'user_analysis': banned_users_info,
            'review_details': review_details
        }
        
        # Print summary
        print("\nREVIEW ANALYSIS SUMMARY")
        print("=" * 50)
        print(f"Total Reviews Processed: {len(reviews)}")
        print(f"Total Users: {len(users)}")
        print("\nSentiment Distribution:")
        print(f"  Positive: {sentiment_dist.get('positive', 0)}")
        print(f"  Negative: {sentiment_dist.get('negative', 0)}")
        print(f"  Neutral: {sentiment_dist.get('neutral', 0)}")
        print(f"\nProfanity Analysis:")
        print(f"  Reviews with Profanity: {profanity_dist['profanity_reviews']}")
        print(f"  Clean Reviews: {profanity_dist['clean_reviews']}")
        print(f"  Profanity Percentage: {profanity_dist['profanity_percentage']:.2f}%")
        print(f"\nUser Analysis:")
        print(f"  Banned Users: {banned_users_info['banned_count']}")
        print(f"  Banned Percentage: {banned_users_info['banned_percentage']:.2f}%")
        
        if banned_users_info['banned_users']:
            print(f"\nBanned Users Details:")
            for user in banned_users_info['banned_users']:
                print(f"  - {user['reviewerName']} ({user['reviewerID']}): {user['profanity_count']} profane reviews")
        
        # Save report
        report_file = f"review_analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\nDetailed report saved to: {report_file}")
        
        return report
    
    def compare_with_devset(self, devset_file):
        """Compare results with the original devset"""
        print(f"\nComparing with devset: {devset_file}")
        print("=" * 50)
        
        try:
            with open(devset_file, 'r') as f:
                devset_reviews = json.load(f)
            
            print(f"Devset contains {len(devset_reviews)} reviews")
            
            # Analyze devset sentiment (using simple rule-based approach)
            devset_sentiment = defaultdict(int)
            devset_profanity = 0
            
            for review in devset_reviews:
                # Simple sentiment analysis based on rating
                rating = review.get('overall', 3)
                if rating >= 4:
                    devset_sentiment['positive'] += 1
                elif rating <= 2:
                    devset_sentiment['negative'] += 1
                else:
                    devset_sentiment['neutral'] += 1
                
                # Simple profanity check
                text = (review.get('reviewText', '') + ' ' + review.get('summary', '')).lower()
                profanity_words = ['shit', 'fuck', 'crap', 'damn', 'hell', 'piss', 'dick', 'cock', 'pussy', 'bastard', 'motherfucker', 'fucker', 'bullshit', 'garbage', 'trash']
                if any(word in text for word in profanity_words):
                    devset_profanity += 1
            
            print("\nDEVSET ANALYSIS:")
            print(f"Positive Reviews: {devset_sentiment['positive']}")
            print(f"Negative Reviews: {devset_sentiment['negative']}")
            print(f"Neutral Reviews: {devset_sentiment['neutral']}")
            print(f"Reviews with Profanity: {devset_profanity}")
            
            # Get processed results
            reviews = self.get_all_reviews()
            sentiment_dist = self.analyze_sentiment_distribution(reviews)
            profanity_dist = self.analyze_profanity_distribution(reviews)
            
            print("\nPROCESSED RESULTS:")
            print(f"Positive Reviews: {sentiment_dist.get('positive', 0)}")
            print(f"Negative Reviews: {sentiment_dist.get('negative', 0)}")
            print(f"Neutral Reviews: {sentiment_dist.get('neutral', 0)}")
            print(f"Reviews with Profanity: {profanity_dist['profanity_reviews']}")
            
        except Exception as e:
            print(f"Error comparing with devset: {e}")

def main():
    """Main function to run analysis"""
    analyzer = ReviewAnalysisResults()
    report = analyzer.generate_report()
    
    # Compare with devset if available
    devset_file = "../../Data/reviews_devset.json"
    try:
        analyzer.compare_with_devset(devset_file)
    except FileNotFoundError:
        print(f"Devset file not found: {devset_file}")

if __name__ == "__main__":
    main() 