import boto3
from botocore.exceptions import ClientError
from botocore import exceptions as botocore
from botocore.response import StreamingBody

# Always use LocalStack endpoint and region
LOCALSTACK_ENDPOINT = 'http://localhost:4566'
LOCALSTACK_REGION = 'us-east-1'

import os
import zipfile
import json
from datetime import datetime
import time
from pathlib import Path
from tqdm import tqdm
from colorama import Fore, Style

import pandas as pd


def assert_user_authenticated():
    sts = boto3.client("sts", endpoint_url=LOCALSTACK_ENDPOINT, region_name=LOCALSTACK_REGION)
    assert sts.get_caller_identity(), "unable to authenticate"

    uid = sts.get_caller_identity()["Account"]
    secret = boto3.session.Session(endpoint_url=LOCALSTACK_ENDPOINT, region_name=LOCALSTACK_REGION).get_credentials().secret_key  # type: ignore
    access = boto3.session.Session(endpoint_url=LOCALSTACK_ENDPOINT, region_name=LOCALSTACK_REGION).get_credentials().access_key  # type: ignore
    session = boto3.session.Session(endpoint_url=LOCALSTACK_ENDPOINT, region_name=LOCALSTACK_REGION).get_credentials().token  # type: ignore
    region = boto3.session.Session(endpoint_url=LOCALSTACK_ENDPOINT, region_name=LOCALSTACK_REGION).region_name  # type: ignore
    assert uid and secret and access and session, "credentials must be set"
    assert region == "us-east-1", "region must be set to us-east-1"
    # print(f"credentials:\n\tacc id: {uid}\n\tsecret: {secret}\n\taccess: {access}\n\tsession: {session}\n\tnregion: {region}\n")

    try:
        ec2 = boto3.client("ec2", endpoint_url=LOCALSTACK_ENDPOINT, region_name=LOCALSTACK_REGION)
        _ = ec2.describe_instances()
    except ClientError as e:
        print(f"{Fore.RED}ec2 instance not accessible - start lab, update credentials{Style.RESET_ALL}")
        exit(1)


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)


class S3Client:
    c = boto3.client("s3", endpoint_url=LOCALSTACK_ENDPOINT, region_name=LOCALSTACK_REGION)

    @staticmethod
    def bucket_exists(bucket_name: str) -> bool:
        response = S3Client.c.list_buckets()
        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2

        for bucket in response["Buckets"]:
            if bucket["Name"] == bucket_name:
                return True
        return False

    @staticmethod
    def list_buckets() -> None:
        print(f"{Fore.GREEN}listing bucket content{Style.RESET_ALL}")

        response = S3Client.c.list_buckets()
        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2

        if len(response["Buckets"]) == 0:
            print("no buckets")
            return
        for bucket in response["Buckets"]:
            print(bucket["Name"])
            response = S3Client.c.list_objects_v2(Bucket=bucket["Name"])
            if response["KeyCount"] > 0:
                for obj in response["Contents"]:
                    print(f"\t{obj['Key']}")
            else:
                print("\tempty")

    @staticmethod
    def delete_bucket(bucket_name: str) -> None:
        print(f"{Fore.GREEN}deleting bucket {bucket_name}{Style.RESET_ALL}")
        assert S3Client.bucket_exists(bucket_name)

        response = S3Client.c.list_objects_v2(Bucket=bucket_name)
        if response["KeyCount"] > 0:
            S3Client.c.delete_objects(Bucket=bucket_name, Delete={"Objects": [{"Key": obj["Key"]} for obj in response["Contents"]]})
        S3Client.c.delete_bucket(Bucket=bucket_name)

        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2
        assert not S3Client.bucket_exists(bucket_name)

    @staticmethod
    def create_bucket(bucket_name: str) -> None:
        print(f"{Fore.GREEN}creating bucket {bucket_name}{Style.RESET_ALL}")

        if S3Client.bucket_exists(bucket_name):
            print(f"bucket {bucket_name} already exists, deleting first")
            S3Client.delete_bucket(bucket_name)
            print(f"deleted existing bucket - back to creating")

        response = S3Client.c.create_bucket(Bucket=bucket_name)
        print(json.dumps(response, indent=2))

        assert S3Client.bucket_exists(bucket_name)

    @staticmethod
    def add_invoke_permission(lambda_arn: str, bucket_name: str) -> None:
        print(f"{Fore.GREEN}adding invoke permission for {bucket_name} to {lambda_arn}{Style.RESET_ALL}")

        statement_id = f"{bucket_name}-invoke-permission"

        try:
            policy = LambdaClient.c.get_policy(FunctionName=lambda_arn)
            policy_dict = json.loads(policy["Policy"])
            for statement in policy_dict["Statement"]:
                if statement["Sid"] == statement_id:
                    # If the permission exists, remove it
                    LambdaClient.c.remove_permission(FunctionName=lambda_arn, StatementId=statement_id)
                    break
        except LambdaClient.c.exceptions.ResourceNotFoundException:
            pass

        response = LambdaClient.c.add_permission(
            FunctionName=lambda_arn, StatementId=statement_id, Action="lambda:InvokeFunction", Principal="s3.amazonaws.com", SourceArn=f"arn:aws:s3:::{bucket_name}"
        )

        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2
        print(f"{Fore.GREEN}Invoke permission added for {bucket_name} to {lambda_arn}{Style.RESET_ALL}")
        # Print the resulting policy for debugging
        policy = LambdaClient.c.get_policy(FunctionName=lambda_arn)
        print(json.dumps(json.loads(policy["Policy"]), indent=2))

    @staticmethod
    def upload_file(bucket_name: str, file_path: Path) -> None:
        print(f"{Fore.GREEN}uploading file {file_path} to bucket {bucket_name}{Style.RESET_ALL}")
        assert S3Client.bucket_exists(bucket_name)
        assert file_path.exists()

        S3Client.c.upload_file(str(file_path), bucket_name, file_path.name)

    @staticmethod
    def upload_folder(bucket_name: str, folder_path: Path, s3_directory: str = "") -> None:
        print(f"{Fore.GREEN}uploading folder {folder_path} to bucket {bucket_name}{Style.RESET_ALL}")
        assert S3Client.bucket_exists(bucket_name)

        for file_path in tqdm(folder_path.rglob("*")):
            if file_path.is_file():
                relative_path = file_path.relative_to(folder_path)
                key = f"{s3_directory}/{relative_path}" if s3_directory else str(relative_path)

                S3Client.c.upload_file(str(file_path), bucket_name, key)

    @staticmethod
    def set_bucket_notification(bucket_name: str, lambda_function_arn: str) -> None:
        print(f"{Fore.GREEN}setting bucket notification for {bucket_name}{Style.RESET_ALL}")
        assert S3Client.bucket_exists(bucket_name)

        response = S3Client.c.put_bucket_notification_configuration(
            Bucket=bucket_name,
            NotificationConfiguration={
                "LambdaFunctionConfigurations": [
                    {
                        "LambdaFunctionArn": lambda_function_arn,
                        "Events": ["s3:ObjectCreated:*"],
                        "Filter": {
                            "Key": {
                                "FilterRules": [
                                    {"Name": "suffix", "Value": ".jpg"},
                                ]
                            }
                        },
                    },
                ]
            },
        )

        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2

    @staticmethod
    def get_bucket_notification(bucket_name: str) -> None:
        response = S3Client.c.get_bucket_notification_configuration(Bucket=bucket_name)
        print(json.dumps(response, indent=2))


class DynamoDBClient:
    c = boto3.client("dynamodb", endpoint_url=LOCALSTACK_ENDPOINT, region_name=LOCALSTACK_REGION)

    @staticmethod
    def table_exists(table_name: str) -> bool:
        response = DynamoDBClient.c.list_tables()
        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2

        for table in response["TableNames"]:
            if table == table_name:
                return True
        return False

    @staticmethod
    def list_tables() -> None:
        print(f"{Fore.GREEN}listing tables{Style.RESET_ALL}")

        response = DynamoDBClient.c.list_tables()
        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2

        if len(response["TableNames"]) == 0:
            print("no tables")
            return
        for table in response["TableNames"]:
            print(table)
            response = DynamoDBClient.c.scan(TableName=table)
            print(json.dumps(response, indent=2))

    @staticmethod
    def delete_table(table_name: str) -> None:
        print(f"{Fore.GREEN}deleting table {table_name}{Style.RESET_ALL}")
        assert DynamoDBClient.table_exists(table_name)

        # wait for users to stop using table
        while True:
            try:
                response = DynamoDBClient.c.delete_table(TableName=table_name)
                break
            except botocore.ClientError:
                pass
        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2
        print(json.dumps(response, cls=DateTimeEncoder, indent=2))

        # wait for table to be deleted
        max_wait = 5
        for _ in range(max_wait):
            if not DynamoDBClient.table_exists(table_name):
                break
            time.sleep(1)
        assert not DynamoDBClient.table_exists(table_name)

    @staticmethod
    def create_table(table_name: str, partition_key: str = "timestamp", sort_key: str = None) -> None:
        print(f"{Fore.GREEN}creating table {table_name}{Style.RESET_ALL}")

        if DynamoDBClient.table_exists(table_name):
            print(f"table {table_name} already exists, deleting first")
            DynamoDBClient.delete_table(table_name)
            print(f"deleted existing table - back to creating")

        # Build KeySchema and AttributeDefinitions
        key_schema = [
            {"AttributeName": partition_key, "KeyType": "HASH"}
        ]
        attribute_definitions = [
            {"AttributeName": partition_key, "AttributeType": "S"}
        ]
        if sort_key:
            key_schema.append({"AttributeName": sort_key, "KeyType": "RANGE"})
            attribute_definitions.append({"AttributeName": sort_key, "AttributeType": "S"})

        args = {
            "KeySchema": key_schema,
            "AttributeDefinitions": attribute_definitions,
            "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        }
        response = DynamoDBClient.c.create_table(TableName=table_name, **args)
        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2

        # wait for creation to finish
        while True:
            response = DynamoDBClient.c.describe_table(TableName=table_name)
            if response["Table"]["TableStatus"] == "ACTIVE":
                break
            time.sleep(1)
        print(json.dumps(response, cls=DateTimeEncoder, indent=2))
        assert DynamoDBClient.table_exists(table_name)

    def download_table(self, table_name: str, file_path: Path, transfer_times: list = None) -> None:
        print(f"{Fore.GREEN}downloading table {table_name} to {file_path}{Style.RESET_ALL}")
        assert self.table_exists(table_name)

        all_data = []
        response = self.c.scan(TableName=table_name)
        all_data.extend(response["Items"])

        while "LastEvaluatedKey" in response:
            response = self.c.scan(TableName=table_name, ExclusiveStartKey=response["LastEvaluatedKey"])
            all_data.extend(response["Items"])

        extracted_data = []
        for item in all_data:
            s3_event_time = item.get("s3_eventTime", {}).get("S", "")
            yolo_detection = item.get("yolo_detection", {}).get("M", {})
            timestamp = item.get("timestamp", {}).get("S", "")

            inference_time = yolo_detection.get("inference_time", {}).get("N", "")
            input_image = yolo_detection.get("input_image", {}).get("S", "")

            extracted_data.append({"s3_eventTime": s3_event_time, "inference_time": inference_time, "input_image": input_image, "timestamp": timestamp})

        df = pd.DataFrame(extracted_data)
        if transfer_times:
            df["transfer_time"] = transfer_times
        df.to_csv(file_path, index=False)
        print(f"Data exported to {file_path}")


class LambdaClient:
    c = boto3.client("lambda", endpoint_url=LOCALSTACK_ENDPOINT, region_name=LOCALSTACK_REGION)
    iam = boto3.client("iam", endpoint_url=LOCALSTACK_ENDPOINT, region_name=LOCALSTACK_REGION)

    @staticmethod
    def layer_exists(lambda_name: str) -> bool:
        try:
            response = LambdaClient.c.list_layers()
            layers = response.get("Layers", [])
            if not layers:
                return False
            for function in layers:
                if lambda_name == function.get("LayerName"):
                    return True
            return False
        except Exception:
            return False

    @staticmethod
    def lambda_exists(lambda_name: str) -> bool:
        existing_functions = LambdaClient.c.list_functions()["Functions"]
        for function in existing_functions:
            if lambda_name == function["FunctionName"]:
                return True
        return False

    @staticmethod
    def list_lambdas():
        print(f"{Fore.GREEN}listing lambda functions{Style.RESET_ALL}")

        response = LambdaClient.c.list_functions()
        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2

        for function in response["Functions"]:
            print(f"\t{function['FunctionName']}")

    @staticmethod
    def delete_lambda(lambda_name: str, file_path: Path) -> None:
        print(f"{Fore.GREEN}deleting lambda function {lambda_name}{Style.RESET_ALL}")
        assert LambdaClient.lambda_exists(lambda_name)
        assert file_path.exists()

        response = LambdaClient.c.delete_function(FunctionName=lambda_name)
        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2

        def delete_zip(file_path):
            zip_file_path = file_path.with_suffix(".zip")
            assert zip_file_path.exists(), f"zip file {zip_file_path} does not exist"
            zip_file_path.unlink()
            print(f"deleted lambda zip")

        delete_zip(file_path)

        assert not LambdaClient.lambda_exists(lambda_name)
        assert not file_path.with_suffix(".zip").exists()

    @staticmethod
    def __remove_permission(lambda_function_name: str, statement_id: str):
        try:
            policy = LambdaClient.c.get_policy(FunctionName=lambda_function_name)
            policy_dict = json.loads(policy["Policy"])
            for statement in policy_dict["Statement"]:
                if statement["Sid"] == statement_id:
                    response = LambdaClient.c.remove_permission(FunctionName=lambda_function_name, StatementId=statement_id)

                    if response["ResponseMetadata"]["HTTPStatusCode"] == 204:
                        print("Permission removed successfully.")
                    else:
                        print("Failed to remove permission.")
                    break
        except LambdaClient.c.exceptions.ResourceNotFoundException:
            print("No policy with the given statement ID exists.")

    @staticmethod
    def __add_invoke_permission(lambda_function_name: str, bucket_name: str):

        LambdaClient.__remove_permission(lambda_function_name, f"{bucket_name}-invoke-permission")

        response = LambdaClient.c.add_permission(
            FunctionName=lambda_function_name, StatementId=f"{bucket_name}-invoke-permission", Action="lambda:InvokeFunction", Principal="s3.amazonaws.com", SourceArn=f"arn:aws:s3:::{bucket_name}"
        )

        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2

    @staticmethod
    def create_lambda(lambda_name: str, bucket_name: str, layer_name: str, file_path: Path) -> str:
        print(f"{Fore.GREEN}creating lambda function {lambda_name}{Style.RESET_ALL}")
        assert file_path.exists()
        assert file_path.suffix == ".py"
        assert file_path.stat().st_size > 0

        if LambdaClient.lambda_exists(lambda_name):
            print(f"lambda function {lambda_name} already exists, deleting first")
            LambdaClient.delete_lambda(lambda_name, file_path)
            print(f"deleted existing lambda function - back to creating")

        def zip_file(file_path: Path) -> Path:
            import shutil
            zip_file_path = file_path.with_suffix(".zip")
            temp_file = file_path.parent / "lambda_function.py"
            # Copy the source file to lambda_function.py
            shutil.copy(file_path, temp_file)
            if zip_file_path.exists():
                zip_file_path.unlink()
                print(f"deleted existing lambda zip")
            with zipfile.ZipFile(zip_file_path, "w") as z:
                z.write(temp_file, "lambda_function.py")
            os.chmod(temp_file, 0o777)
            os.chmod(zip_file_path, 0o777)
            temp_file.unlink()  # Clean up temp file
            print(f"created lambda zip with lambda_function.py")
            return zip_file_path

        zip_file_path = zip_file(file_path)

        with open(zip_file_path, "rb") as f:
            accountid = boto3.client("sts", endpoint_url=LOCALSTACK_ENDPOINT, region_name=LOCALSTACK_REGION).get_caller_identity()["Account"]
            role = "LabRole"
            response = LambdaClient.c.create_function(
                FunctionName=lambda_name,
                Runtime="python3.10",
                Role=f"arn:aws:iam::{accountid}:role/{role}",
                Handler="lambda_function.lambda_handler",
                Code={"ZipFile": f.read()},
                Layers=[layer_name],
                Timeout=900,
                MemorySize=1024,
            )
        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2
        print(json.dumps(response, indent=2))

        assert LambdaClient.lambda_exists(lambda_name)

        LambdaClient.__add_invoke_permission(lambda_name, bucket_name)

        return response["FunctionArn"]

    @staticmethod
    def delete_layer(layer_name: str) -> None:
        print(f"{Fore.GREEN}deleting lambda layer {layer_name}{Style.RESET_ALL}")
        assert LambdaClient.layer_exists(layer_name)

        response = LambdaClient.c.list_layer_versions(LayerName=layer_name)
        for version in response["LayerVersions"]:
            response = LambdaClient.c.delete_layer_version(LayerName=layer_name, VersionNumber=version["Version"])
            assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2
        assert not LambdaClient.layer_exists(layer_name)

    @staticmethod
    def publish_layer(layer_name: str, bucket_name: str, file_name: str) -> str:
        print(f"{Fore.GREEN}publishing lambda layer {layer_name}{Style.RESET_ALL}")

        if LambdaClient.layer_exists(layer_name):
            print(f"layer function {layer_name} already exists, deleting first")
            LambdaClient.delete_layer(layer_name)
            print(f"deleted existing layer function - back to creating")

        response = LambdaClient.c.publish_layer_version(
            LayerName=layer_name,
            Content={"S3Bucket": bucket_name, "S3Key": file_name},
            CompatibleRuntimes=["python3.10"],
        )
        assert response["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2
        print(json.dumps(response, indent=2))

        assert LambdaClient.layer_exists(layer_name)
        return response["LayerVersionArn"]

    @staticmethod
    def invoke_lambda(lambda_name: str, payload: dict) -> None:
        print(f"{Fore.GREEN}invoking lambda function {lambda_name}{Style.RESET_ALL}")
        assert LambdaClient.lambda_exists(lambda_name)

        def wait_until_ready(lambda_name):
            while True:
                try:
                    response = LambdaClient.c.get_function(FunctionName=lambda_name)
                    if response["Configuration"]["State"] == "Active":
                        break
                    print(f"waiting for lambda function {lambda_name} to be ready")
                except botocore.ClientError:
                    pass

        wait_until_ready(lambda_name)

        response = LambdaClient.c.invoke(FunctionName=lambda_name, Payload=json.dumps(payload))

        decoded_response = json.loads(response["Payload"].read().decode("utf-8"))
        print(json.dumps(decoded_response, indent=2))

    @staticmethod
    def create_minimal_lambda(lambda_name: str):
        # Create a minimal lambda_function.py
        import tempfile
        import shutil
        minimal_code = '''def lambda_handler(event, context):\n    return {\"statusCode\": 200, \"body\": \"Hello from minimal Lambda!\"}\n'''
        with tempfile.TemporaryDirectory() as tmpdir:
            handler_path = Path(tmpdir) / "lambda_function.py"
            with open(handler_path, "w") as f:
                f.write(minimal_code)
            zip_path = Path(tmpdir) / "lambda_function.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                z.write(handler_path, "lambda_function.py")
            accountid = boto3.client("sts", endpoint_url=LOCALSTACK_ENDPOINT, region_name=LOCALSTACK_REGION).get_caller_identity()["Account"]
            role = "LabRole"
            with open(zip_path, "rb") as f:
                response = LambdaClient.c.create_function(
                    FunctionName=lambda_name,
                    Runtime="python3.10",
                    Role=f"arn:aws:iam::{accountid}:role/{role}",
                    Handler="lambda_function.lambda_handler",
                    Code={"ZipFile": f.read()},
                    Timeout=30,
                    MemorySize=128,
                )
            print(f"Minimal Lambda {lambda_name} created.")
            return response


if __name__ == "__main__":
    assert_user_authenticated()

    table_name = "wolke-sieben-table-paul"
    download_results = True

    bucket_name = "wolke-sieben-bucket-paul"
    data_path = Path.cwd() / "data" / "input_folder"

    layer_name = "wolke-sieben-layer"
    layer_path = Path.cwd() / "src" / "aws" / "packages.zip"

    lambda_name = "wolke-sieben-lambda"
    lambda_path = Path.cwd() / "src" / "aws" / "lambda_function.py"

    yolo_tiny_configs = Path.cwd() / "yolo_tiny_configs"

    # Create services
    DynamoDBClient.create_table(table_name)
    S3Client.create_bucket(bucket_name)

    # Upload dependencies to S3
    S3Client.upload_file(bucket_name, layer_path)
    layer_arn_name = LambdaClient.publish_layer(layer_name, bucket_name, layer_path.name)
    lambda_arn_name = LambdaClient.create_lambda(lambda_name, bucket_name, layer_arn_name, lambda_path)

    # Upload Model Configs
    S3Client.upload_folder(bucket_name, yolo_tiny_configs, yolo_tiny_configs.name)

    # Hooking up Lambda to S3
    S3Client.add_invoke_permission(lambda_arn_name, bucket_name)
    S3Client.set_bucket_notification(bucket_name, lambda_arn_name)
    S3Client.get_bucket_notification(bucket_name)

    # Invoke lambda with s3 event for each file in the data folder
    transfer_time = []
    for file in data_path.rglob("*"):
        start_time = time.time()
        S3Client.upload_file(bucket_name, file)
        transfer_time.append(time.time() - start_time)

    # Download data from dynamodb
    if download_results:
        time.sleep(40)  # wait until DynamoDB is populated
        dynamodb_client = DynamoDBClient()
        dynamodb_client.download_table(table_name, Path("aws_results.csv"), transfer_times=transfer_time)

    # Show results in dynamodb
    # DynamoDBClient.list_tables() # doesn't work because it's async, results can be seen in the AWS console

    # Do not delete resources, they are part of the submission
    """
    DynamoDBClient.delete_table(table_name)
    S3Client.delete_bucket(bucket_name)
    LambdaClient.delete_lambda(lambda_name, lambda_path)
    """