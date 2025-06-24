
import boto3
import datetime
import time
import numpy as np
import cv2
import os

from pathlib import Path

TABLE_NAME = "wolke-sieben-table"
BUCKET_NAME = "wolke-sieben-bucket-paul"  # Replace with your bucket name
S3_FOLDER = "yolo_tiny_configs"
LOCAL_TMP_FOLDER = "/tmp/yolo_tiny_configs/"


class Boto3Client:
    def __init__(self):
        self.s3 = boto3.client("s3")

    def download_from_s3(self, bucket_name, s3_key, local_path):
        self.s3.download_file(bucket_name, s3_key, local_path)
        print(f"Downloaded {s3_key} from bucket {bucket_name} to {local_path}")

    def download_all_files_in_folder(self, bucket_name, s3_folder, local_folder):
        paginator = self.s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket_name, Prefix=s3_folder)

        for page in pages:
            if "Contents" in page:
                for obj in page["Contents"]:
                    s3_key = obj["Key"]
                    relative_path = os.path.relpath(s3_key, s3_folder)
                    local_path = os.path.join(local_folder, relative_path)
                    local_dir = os.path.dirname(local_path)

                    if not os.path.exists(local_dir):
                        os.makedirs(local_dir)

                    if not os.path.exists(local_path):
                        self.download_from_s3(bucket_name, s3_key, local_path)


class ObjectDetection:
    def __init__(self):
        self.root = Path("/tmp")
        self.MODEL_CONFIG = self.root / "yolo_tiny_configs" / "yolov3-tiny.cfg"
        self.MODEL_WEIGHTS = self.root / "yolo_tiny_configs" / "yolov3-tiny.weights"
        self.COCO_NAMES = self.root / "yolo_tiny_configs" / "coco.names"

        self.net = cv2.dnn.readNet(str(self.MODEL_WEIGHTS), str(self.MODEL_CONFIG))

        # Check if CUDA is available and set the preferable backend and target
        # Note: could not get the openCV running on CUDA
        if cv2.cuda.getCudaEnabledDeviceCount() > 0:
            print("CUDA is available. Using GPU.")
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
        else:
            print("CUDA is not available. Using CPU.")
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_DEFAULT)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

        with open(self.COCO_NAMES, "r") as f:
            self.classes = [line.strip() for line in f.readlines()]

        self.output_layers = self.net.getUnconnectedOutLayersNames()

    def detect_objects(self, image_data, confidence_threshold=0.5, return_image=False):
        # Convert to a numpy array and decode to an image
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        height, width, _ = img.shape

        # Prepare the image for YOLO
        blob = cv2.dnn.blobFromImage(img, 0.00392, (416, 416), (0, 0, 0), True, crop=False)

        # Run the YOLO network
        self.net.setInput(blob)
        start_time = time.time()
        outs = self.net.forward(self.output_layers)
        end_time = time.time()
        inference_time = end_time - start_time

        class_ids = []
        confidences = []
        boxes = []

        # Extract the bounding boxes, confidences, and class IDs
        for out in outs:
            for detection in out:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]

                # filter out low confidence detections
                if confidence > confidence_threshold:
                    center_x = int(detection[0] * width)
                    center_y = int(detection[1] * height)
                    w = int(detection[2] * width)
                    h = int(detection[3] * height)

                    x = int(center_x - w / 2)
                    y = int(center_y - h / 2)

                    boxes.append([x, y, w, h])
                    confidences.append(float(confidence))
                    class_ids.append(class_id)

        indexes = cv2.dnn.NMSBoxes(boxes, confidences, confidence_threshold, 0.4)

        detected_objects = []
        if len(indexes) > 0:
            for i in indexes:
                label = str(self.classes[class_ids[i]])
                confidence = confidences[i]
                if confidence > confidence_threshold:
                    detected_objects.append({"label": label, "accuracy": confidence})

        return detected_objects, inference_time


def main(event, context) -> dict:
    print("Lambda Function invoked with event:", event)

    # Initialize Boto3 client
    boto3_client = Boto3Client()

    # Ensure the local directory exists, only download files if they don't exist, otherwise use the cached files
    if not os.path.exists(LOCAL_TMP_FOLDER):
        os.makedirs(LOCAL_TMP_FOLDER)

        # Download all files in the specified S3 folder to /tmp when the container is initialized
        boto3_client.download_all_files_in_folder(BUCKET_NAME, S3_FOLDER, LOCAL_TMP_FOLDER)

    # Extract S3 event details
    if "Records" in event and len(event["Records"]) > 0:
        event_time = event["Records"][0]["eventTime"]
        s3_event = event["Records"][0]["s3"]
        bucket_name = s3_event["bucket"]["name"]
        object_key = s3_event["object"]["key"]

    # Download the file from S3
    image_path = f"/tmp/{object_key}"
    boto3_client.download_from_s3(bucket_name, object_key, image_path)

    # Read the image file
    with open(image_path, "rb") as image_file:
        image_data = image_file.read()

    # Initialize ObjectDetection class
    obj_detect = ObjectDetection()
    detected_objects, inference_time = obj_detect.detect_objects(image_data, confidence_threshold=0.5)

    dynamodb_item = {
        "timestamp": {"S": datetime.datetime.now().isoformat()},
        "s3_eventTime": {"S": event_time},
        "context": {
            "M": {
                "function_name": {"S": context.function_name},
                "function_version": {"S": context.function_version},
                "memory_limit_in_mb": {"N": str(context.memory_limit_in_mb)},
                "time_remaining_in_millis": {"N": str(context.get_remaining_time_in_millis())},
                "aws_request_id": {"S": context.aws_request_id},
                "log_group_name": {"S": context.log_group_name},
            },
        },
        "yolo_detection": {
            "M": {
                "input_image": {"S": f"s3://{bucket_name}/{object_key}"},  # S3 URI
                "detected_objects": {"L": [{"M": {"label": {"S": obj["label"]}, "accuracy": {"N": str(obj["accuracy"])}}} for obj in detected_objects]},
                "inference_time": {"N": str(inference_time)},
            }
        },
    }

    print("DynamoDB PutItem Request: ", dynamodb_item)

    # Write output to DynamoDB
    dynamodb = boto3.client("dynamodb")
    res = dynamodb.put_item(
        TableName=TABLE_NAME,
        Item=dynamodb_item,
    )
    assert res["ResponseMetadata"]["HTTPStatusCode"] // 100 == 2, f"Failed to write to DynamoDB: {res}"