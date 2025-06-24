import boto3
import json
import os
import zipfile
from pathlib import Path
from datetime import datetime
import time

# Import the AWS client classes from the existing aws.py
from aws import S3Client, DynamoDBClient, LambdaClient

class ReviewAnalysisDeployer:
    def __init__(self):
        self.s3_client = S3Client()
        self.dynamodb_client = DynamoDBClient()
        self.lambda_client = LambdaClient()
        
        # Configuration
        self.config_bucket = "review-analysis-config"
        self.reviews_bucket = "review-analysis-reviews"
        self.processed_bucket = "review-analysis-processed"
        self.profanity_bucket = "review-analysis-profanity"
        self.sentiment_bucket = "review-analysis-sentiment"
        
        self.reviews_table = "review-analysis-reviews"
        self.users_table = "review-analysis-users"
        
        self.preprocessing_lambda = "review-preprocessing"
        self.profanity_check_lambda = "review-profanity-check"
        self.sentiment_analysis_lambda = "review-sentiment-analysis"
        
        self.preprocessing_layer = "review-preprocessing-layer"
        self.profanity_layer = "review-profanity-layer"
        self.sentiment_layer = "review-sentiment-layer"
    
    def create_config_bucket_and_parameters(self):
        """Create configuration bucket and upload parameters"""
        print("Creating configuration bucket and parameters...")
        
        # Create config bucket
        self.s3_client.create_bucket(self.config_bucket)
        
        # Upload parameters
        parameters = {
            'reviews_bucket': self.reviews_bucket,
            'processed_bucket': self.processed_bucket,
            'profanity_bucket': self.profanity_bucket,
            'sentiment_bucket': self.sentiment_bucket,
            'reviews_table': self.reviews_table,
            'users_table': self.users_table
        }
        
        for param_name, param_value in parameters.items():
            self.s3_client.c.put_object(
                Bucket=self.config_bucket,
                Key=f'parameters/{param_name}.txt',
                Body=param_value,
                ContentType='text/plain'
            )
            print(f"Uploaded parameter: {param_name} = {param_value}")
    
    def create_s3_buckets(self):
        """Create all required S3 buckets"""
        print("Creating S3 buckets...")
        
        buckets = [
            self.reviews_bucket,
            self.processed_bucket,
            self.profanity_bucket,
            self.sentiment_bucket
        ]
        
        for bucket in buckets:
            self.s3_client.create_bucket(bucket)
    
    def create_dynamodb_tables(self):
        """Create DynamoDB tables"""
        print("Creating DynamoDB tables...")
        
        # Reviews table
        self.dynamodb_client.create_table(
            table_name=self.reviews_table,
            partition_key='review_id',
            sort_key=None
        )
        
        # Users table
        self.dynamodb_client.create_table(
            table_name=self.users_table,
            partition_key='reviewerID',
            sort_key=None
        )
        
        # Wait for tables to be active
        print("Waiting for DynamoDB tables to be active...")
        time.sleep(10)
    
    def create_lambda_layers(self):
        """Create Lambda layers with required dependencies"""
        print("Creating Lambda layers...")
        
        # Create preprocessing layer (NLTK)
        self.create_nltk_layer()
        
        # Create sentiment layer (TextBlob)
        self.create_textblob_layer()
        
        # Create profanity layer (basic dependencies)
        self.create_basic_layer()
    
    def create_nltk_layer(self):
        """Create NLTK layer for preprocessing"""
        print("Creating NLTK layer...")
        
        # Create layer directory
        layer_dir = Path("/tmp/nltk_layer")
        layer_dir.mkdir(exist_ok=True)
        python_dir = layer_dir / "python"
        python_dir.mkdir(exist_ok=True)
        
        # Install NLTK in the layer directory
        os.system(f"python3 -m pip install nltk -t {python_dir}")
        
        # Download NLTK data
        import nltk
        nltk_data_dir = python_dir / "nltk_data"
        nltk.download('punkt', download_dir=str(nltk_data_dir))
        nltk.download('stopwords', download_dir=str(nltk_data_dir))
        nltk.download('wordnet', download_dir=str(nltk_data_dir))
        
        # Create zip file
        zip_path = Path("/tmp/nltk_layer.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in python_dir.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(layer_dir)
                    zipf.write(file_path, arcname)
        
        # Upload and publish layer
        self.s3_client.upload_file(self.config_bucket, zip_path)
        self.lambda_client.publish_layer(
            layer_name=self.preprocessing_layer,
            bucket_name=self.config_bucket,
            file_name=zip_path.name
        )
    
    def create_textblob_layer(self):
        """Create TextBlob layer for sentiment analysis"""
        print("Creating TextBlob layer...")
        
        # Create layer directory
        layer_dir = Path("/tmp/textblob_layer")
        layer_dir.mkdir(exist_ok=True)
        python_dir = layer_dir / "python"
        python_dir.mkdir(exist_ok=True)
        
        # Install TextBlob in the layer directory
        os.system(f"python3 -m pip install textblob -t {python_dir}")
        
        # Create zip file
        zip_path = Path("/tmp/textblob_layer.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in python_dir.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(layer_dir)
                    zipf.write(file_path, arcname)
        
        # Upload and publish layer
        self.s3_client.upload_file(self.config_bucket, zip_path)
        self.lambda_client.publish_layer(
            layer_name=self.sentiment_layer,
            bucket_name=self.config_bucket,
            file_name=zip_path.name
        )
    
    def create_basic_layer(self):
        """Create basic layer for profanity check"""
        print("Creating basic layer...")
        
        # Create layer directory
        layer_dir = Path("/tmp/basic_layer")
        layer_dir.mkdir(exist_ok=True)
        python_dir = layer_dir / "python"
        python_dir.mkdir(exist_ok=True)
        
        # Install basic dependencies
        os.system(f"python3 -m pip install boto3 -t {python_dir}")
        
        # Create zip file
        zip_path = Path("/tmp/basic_layer.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in python_dir.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(layer_dir)
                    zipf.write(file_path, arcname)
        
        # Upload and publish layer
        self.s3_client.upload_file(self.config_bucket, zip_path)
        self.lambda_client.publish_layer(
            layer_name=self.profanity_layer,
            bucket_name=self.config_bucket,
            file_name=zip_path.name
        )
    
    def create_lambda_functions(self):
        """Create Lambda functions"""
        print("Creating Lambda functions...")
        
        # Create preprocessing function
        self.lambda_client.create_lambda(
            lambda_name=self.preprocessing_lambda,
            bucket_name=self.config_bucket,
            layer_name=self.preprocessing_layer,
            file_path=Path("preprocessing_lambda.py")
        )
        
        # Create profanity check function
        self.lambda_client.create_lambda(
            lambda_name=self.profanity_check_lambda,
            bucket_name=self.config_bucket,
            layer_name=self.profanity_layer,
            file_path=Path("profanity_check_lambda.py")
        )
        
        # Create sentiment analysis function
        self.lambda_client.create_lambda(
            lambda_name=self.sentiment_analysis_lambda,
            bucket_name=self.config_bucket,
            layer_name=self.sentiment_layer,
            file_path=Path("sentiment_analysis_lambda.py")
        )
    
    def setup_s3_triggers(self):
        """Setup S3 bucket triggers for Lambda functions"""
        print("Setting up S3 triggers...")
        
        # Get Lambda ARNs
        preprocessing_arn = f"arn:aws:lambda:us-east-1:{boto3.client('sts').get_caller_identity()['Account']}:function:{self.preprocessing_lambda}"
        profanity_arn = f"arn:aws:lambda:us-east-1:{boto3.client('sts').get_caller_identity()['Account']}:function:{self.profanity_check_lambda}"
        sentiment_arn = f"arn:aws:lambda:us-east-1:{boto3.client('sts').get_caller_identity()['Account']}:function:{self.sentiment_analysis_lambda}"
        
        # Add permissions
        self.s3_client.add_invoke_permission(preprocessing_arn, self.reviews_bucket)
        self.s3_client.add_invoke_permission(profanity_arn, self.processed_bucket)
        self.s3_client.add_invoke_permission(sentiment_arn, self.profanity_bucket)
        
        # Setup bucket notifications
        self.s3_client.set_bucket_notification(self.reviews_bucket, preprocessing_arn)
        self.s3_client.set_bucket_notification(self.processed_bucket, profanity_arn)
        self.s3_client.set_bucket_notification(self.profanity_bucket, sentiment_arn)
    
    def deploy(self):
        """Deploy the complete review analysis system"""
        print("Starting deployment of Review Analysis System...")
        
        try:
            # Create configuration
            self.create_config_bucket_and_parameters()
            
            # Create S3 buckets
            self.create_s3_buckets()
            
            # Create DynamoDB tables
            self.create_dynamodb_tables()
            
            # Create Lambda layers
            self.create_lambda_layers()
            
            # Create Lambda functions
            self.create_lambda_functions()
            
            # Setup triggers
            self.setup_s3_triggers()
            
            print("Deployment completed successfully!")
            print("\nSystem Configuration:")
            print(f"Reviews Bucket: {self.reviews_bucket}")
            print(f"Processed Bucket: {self.processed_bucket}")
            print(f"Profanity Bucket: {self.profanity_bucket}")
            print(f"Sentiment Bucket: {self.sentiment_bucket}")
            print(f"Reviews Table: {self.reviews_table}")
            print(f"Users Table: {self.users_table}")
            print(f"Preprocessing Lambda: {self.preprocessing_lambda}")
            print(f"Profanity Check Lambda: {self.profanity_check_lambda}")
            print(f"Sentiment Analysis Lambda: {self.sentiment_analysis_lambda}")
            
        except Exception as e:
            print(f"Deployment failed: {str(e)}")
            raise

def main():
    """Main function to run deployment"""
    deployer = ReviewAnalysisDeployer()
    deployer.deploy()

if __name__ == "__main__":
    main() 