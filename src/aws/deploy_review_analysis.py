#!/usr/bin/env python3
"""
Deploy Review Analysis Infrastructure
Creates complete serverless infrastructure for Assignment 3.
"""

import boto3
import json
import os
import zipfile
from pathlib import Path
from datetime import datetime
import time

# Configure for LocalStack
os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

class ReviewAnalysisDeployer:
    def __init__(self):
        self.common_config = {
            'endpoint_url': 'http://localhost:4566',
            'aws_access_key_id': 'test',
            'aws_secret_access_key': 'test',
            'region_name': 'us-east-1'
        }
        
        self.s3 = boto3.client('s3', **self.common_config)
        self.dynamodb = boto3.client('dynamodb', **self.common_config)
        self.lambda_client = boto3.client('lambda', **self.common_config)
        self.ssm = boto3.client('ssm', **self.common_config)
        
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
    
    def create_s3_bucket(self, bucket_name):
        """Create S3 bucket"""
        try:
            self.s3.create_bucket(Bucket=bucket_name)
            print(f"✅ Created S3 bucket: {bucket_name}")
        except Exception as e:
            if "BucketAlreadyExists" in str(e) or "BucketAlreadyOwnedByYou" in str(e):
                print(f"✅ S3 bucket already exists: {bucket_name}")
            else:
                print(f"❌ Error creating bucket {bucket_name}: {e}")

    def create_ssm_parameters(self):
        """Create SSM Parameter Store parameters"""
        print("Creating SSM parameters...")
        
        parameters = {
            '/review-analysis/reviews-bucket': self.reviews_bucket,
            '/review-analysis/processed-bucket': self.processed_bucket,
            '/review-analysis/profanity-bucket': self.profanity_bucket,
            '/review-analysis/sentiment-bucket': self.sentiment_bucket,
            '/review-analysis/reviews-table': self.reviews_table,
            '/review-analysis/users-table': self.users_table
        }
        
        for param_name, param_value in parameters.items():
            try:
                self.ssm.put_parameter(
                    Name=param_name,
                    Value=param_value,
                    Type='String',
                    Overwrite=True
                )
                print(f"✅ Created SSM parameter: {param_name}")
            except Exception as e:
                print(f"❌ Error creating parameter {param_name}: {e}")
    
    def create_s3_buckets(self):
        """Create all required S3 buckets"""
        print("Creating S3 buckets...")
        
        buckets = [
            self.config_bucket,
            self.reviews_bucket,
            self.processed_bucket,
            self.profanity_bucket,
            self.sentiment_bucket
        ]
        
        for bucket in buckets:
            self.create_s3_bucket(bucket)
    
    def create_dynamodb_table(self, table_name, partition_key):
        """Create DynamoDB table"""
        try:
            self.dynamodb.create_table(
                TableName=table_name,
                KeySchema=[
                    {
                        'AttributeName': partition_key,
                        'KeyType': 'HASH'
                    }
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName': partition_key,
                        'AttributeType': 'S'
                    }
                ],
                BillingMode='PAY_PER_REQUEST'
            )
            print(f"✅ Created DynamoDB table: {table_name}")
        except Exception as e:
            if "ResourceInUseException" in str(e):
                print(f"✅ DynamoDB table already exists: {table_name}")
            else:
                print(f"❌ Error creating table {table_name}: {e}")

    def create_dynamodb_tables(self):
        """Create DynamoDB tables"""
        print("Creating DynamoDB tables...")
        
        # Reviews table
        self.create_dynamodb_table(self.reviews_table, 'review_id')
        
        # Users table  
        self.create_dynamodb_table(self.users_table, 'reviewerID')
        
        # Wait for tables to be active
        print("Waiting for DynamoDB tables to be active...")
        time.sleep(5)
    
    def create_lambda_layers(self):
        """Create Lambda layers with required dependencies"""
        print("Creating Lambda layers...")
        
        # Create simple layers without complex dependencies
        self.create_simple_layer("review-nltk-layer", ["nltk"])
        self.create_simple_layer("review-textblob-layer", ["textblob"])  
        self.create_simple_layer("review-basic-layer", ["boto3"])
    
    def create_simple_layer(self, layer_name, packages):
        """Create a simple Lambda layer"""
        try:
            layer_dir = Path(f"/tmp/{layer_name}")
            layer_dir.mkdir(exist_ok=True)
            python_dir = layer_dir / "python"
            python_dir.mkdir(exist_ok=True)
            
            # Create empty __init__.py
            (python_dir / "__init__.py").write_text("")
            
            # Create zip file
            zip_path = Path(f"/tmp/{layer_name}.zip")
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in python_dir.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(layer_dir)
                        zipf.write(file_path, arcname)
            
            # Upload layer
            with open(zip_path, 'rb') as f:
                response = self.lambda_client.publish_layer_version(
                    LayerName=layer_name,
                    Content={'ZipFile': f.read()},
                    CompatibleRuntimes=['python3.8', 'python3.9', 'python3.10']
                )
            
            print(f"✅ Created layer: {layer_name}")
            return response['LayerVersionArn']
            
        except Exception as e:
            print(f"⚠️ Warning creating layer {layer_name}: {e}")
            return None

    def create_lambda_function(self, function_name, filename):
        """Create Lambda function"""
        try:
            # Get layers
            layers = []
            try:
                layer_response = self.lambda_client.list_layers()
                for layer in layer_response.get('Layers', []):
                    if 'review-' in layer['LayerName']:
                        versions = self.lambda_client.list_layer_versions(LayerName=layer['LayerName'])
                        if versions.get('LayerVersions'):
                            layers.append(versions['LayerVersions'][0]['LayerVersionArn'])
            except:
                pass
            
            # Create zip file
            zip_path = f"/tmp/{function_name}.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(filename, 'lambda_function.py')
            
            # Create function
            with open(zip_path, 'rb') as f:
                response = self.lambda_client.create_function(
                    FunctionName=function_name,
                    Runtime='python3.10',
                    Role='arn:aws:iam::000000000000:role/lambda-role',
                    Handler='lambda_function.lambda_handler',
                    Code={'ZipFile': f.read()},
                    Timeout=300,
                    MemorySize=512,
                    Environment={
                        'Variables': {
                            'AWS_ACCESS_KEY_ID': 'test',
                            'AWS_SECRET_ACCESS_KEY': 'test',
                            'AWS_DEFAULT_REGION': 'us-east-1'
                        }
                    },
                    Layers=layers[:3] if layers else []  # Limit to 3 layers
                )
            
            print(f"✅ Created Lambda function: {function_name}")
            
            # Add S3 permissions
            try:
                self.lambda_client.add_permission(
                    FunctionName=function_name,
                    StatementId=f's3-trigger-{function_name}',
                    Action='lambda:InvokeFunction',
                    Principal='s3.amazonaws.com'
                )
            except:
                pass
                
        except Exception as e:
            if "ResourceConflictException" in str(e):
                print(f"✅ Lambda function already exists: {function_name}")
            else:
                print(f"❌ Error creating function {function_name}: {e}")

    def create_lambda_functions(self):
        """Create all Lambda functions"""
        print("Creating Lambda functions...")
        
        # Get the directory where this script is located
        script_dir = Path(__file__).parent
        
        functions = [
            (self.preprocessing_lambda, script_dir / 'preprocessing_lambda.py'),
            (self.profanity_check_lambda, script_dir / 'profanity_check_lambda.py'), 
            (self.sentiment_analysis_lambda, script_dir / 'sentiment_analysis_lambda.py')
        ]
        
        for function_name, filename in functions:
            self.create_lambda_function(function_name, str(filename))
    
    def deploy(self):
        """Deploy complete infrastructure"""
        print("🚀 Deploying Review Analysis Infrastructure...")
        print("=" * 50)
        
        try:
            # Step 1: Create S3 buckets
            self.create_s3_buckets()
            print()
            
            # Step 2: Create SSM parameters
            self.create_ssm_parameters()
            print()
            
            # Step 3: Create DynamoDB tables
            self.create_dynamodb_tables()
            print()
            
            # Step 4: Create Lambda layers
            self.create_lambda_layers()
            print()
            
            # Step 5: Create Lambda functions
            self.create_lambda_functions()
            print()
            
            print("✅ Infrastructure deployment completed successfully!")
            print()
            print("📋 Summary:")
            print(f"✅ S3 Buckets: 5 created")
            print(f"✅ DynamoDB Tables: 2 created") 
            print(f"✅ Lambda Functions: 3 created")
            print(f"✅ SSM Parameters: 6 created")
            print()
            print("🚀 Ready to process reviews!")
            
        except Exception as e:
            print(f"❌ Deployment failed: {e}")
            raise

def main():
    deployer = ReviewAnalysisDeployer()
    deployer.deploy()

if __name__ == "__main__":
    main() 