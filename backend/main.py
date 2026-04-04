import os
import yaml
import mysql.connector as mc
import multiprocessing.shared_memory as shm
import multiprocessing
import cv2
from PIL import Image
import numpy as np
import signal
import sys
from datetime import datetime, timedelta, time
import time as time_module
import traceback
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
import glob
from kafka import KafkaProducer
import json
import tritonclient.grpc as triton
from shapely.geometry import Polygon
import math
import itertools
from torch.nn import functional as F
import torch
from threading import Lock
import struct
import threading
import time
from scipy.optimize import linear_sum_assignment
from collections import defaultdict
import psutil, os, time

process = psutil.Process(os.getpid())

lock = Lock()

from FaceBoxes.FaceBoxes_ONNX_v1 import FaceBoxes_ONNX
from transformers import AutoFeatureExtractor, AutoModelForImageClassification
from TDDFA_ONNX import TDDFA_ONNX
from wwwroot.scripts import camera_metrics
from wwwroot.scripts import people_tracker
from wwwroot.scripts import vespa_handler
from wwwroot.scripts import shm_handler
from wwwroot.scripts import peoplecount
from wwwroot.scripts import employee_identification
from wwwroot.scripts import demographics
from wwwroot.scripts import hairnet
from wwwroot.scripts import Parking_Status


# os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp"

# Frame specifications
frame_shape = (640, 640, 3)
frame_dtype = np.uint8
frame_size = np.prod(frame_shape)
flag_dtype = np.uint8  # 1 byte


id_counter = itertools.count(start=0)


def get_db_connection(db_config):
    return mc.connect(**db_config)


def get_domain(camera_name):
    return camera_name.split("_")[0][:-3]


def get_usecase_key(camera_name):
    return camera_name.split("_")[1][:-3]


def get_db_config_and_path(domain):
    domain_map = {
        "1": ("CCTV_db_config.yaml", "/home/fortune/AIVVAA-DATA/", "CCTV"),
        "2": ("REST_db_config.yaml", "/home/fortune/AIVVAA-DATA/", "REST"),
        "3": ("RETAIL_db_config.yaml", "/home/fortune/AIVVAA-DATA/", "RETAIL"),
    }

    if domain not in domain_map:
        return None, "Unknown", "Unknown"

    yaml_file_name, base_path, domain_name = domain_map[domain]
    with open(yaml_file_name, "r") as f:
        db_config = yaml.safe_load(f)

    return db_config, base_path, domain_name


def get_triton_client(url: str = "localhost:8001"):
    try:
        keepalive_options = grpcclient.KeepAliveOptions(
            keepalive_time_ms=2**31 - 1,
            keepalive_timeout_ms=20000,
            keepalive_permit_without_calls=True,
            http2_max_pings_without_data=2,
        )
        triton_client = grpcclient.InferenceServerClient(
            url=url, verbose=False, keepalive_options=keepalive_options
        )
    except Exception as e:
        print("Channel creation failed: " + str(e))
        sys.exit()
    return triton_client


def get_camera_hierarchy_from_json(comp_br):
    domain = get_domain(comp_br)
    db_config, base_path, domain_name = get_db_config_and_path(domain)
    base_json_dir = f"/home/fortune/AIVVAA-DATA/{domain_name}_config"
    camera_list = []
    comp_br_device_time_diff = {}

    try:
        json_file_path = os.path.join(base_json_dir, f"{comp_br}.json")
        if not os.path.exists(json_file_path):
            print(json_file_path)
            print(f"JSON file not found for domain: {domain}")
            raise Exception

        with open(json_file_path, "r") as f:
            data = json.load(f)

        # Extract time_diff and CompId, BrId
        device_data = data.get("device_data", {})
        comp_id = device_data.get("CompId")
        br_id = device_data.get("BrId")
        time_diff = device_data.get("time_diff")

        if comp_id is None or br_id is None or time_diff is None:
            print(f"Missing keys in JSON for domain: {domain}")
            raise Exception

        comp_br = f"{comp_id}_{br_id}"
        comp_br_device_time_diff[comp_br] = time_diff

        # Extract camera hierarchy list
        camera_hierarchy_data = data.get("camera_hierarchy_data", [])
        for hierarchy in camera_hierarchy_data:
            if hierarchy.startswith(comp_br):
                camera_list.append(hierarchy)

        return camera_list, comp_br_device_time_diff
    except Exception as e:
        print(f"Error reading JSON for camera hierarchy: {e}")
        return [], {}


def receive_frames(camera_name, camera_rtsp_link, shared_mem_name, shared_flag_name):
    while True:
        try:
            cap = cv2.VideoCapture(camera_rtsp_link, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            shared_mem = shm.SharedMemory(name=shared_mem_name)
            frame_array = np.ndarray(frame_shape, dtype=frame_dtype, buffer=shared_mem.buf)

            flag_mem = shm.SharedMemory(name=shared_flag_name)
            flag_array = np.ndarray((1,), dtype=flag_dtype, buffer=flag_mem.buf)
            while True:
                start_time = datetime.now()

                ret, frame = cap.read()
                if not ret:
                    flag_array[0] = 0
                    break

                if frame.shape[:2] != (640, 640):
                    frame = cv2.resize(frame, (640, 640))

                np.copyto(frame_array, frame)
                flag_array[0] = 1
                end_time = datetime.now()
                elapsed = end_time - start_time
                # print(f"[{camera_name}] Frame capture time: {elapsed.total_seconds():.3f} seconds")

        except Exception as e:
            print("Exception! -> main.py -> receive_frames ->", e)
            traceback.print_exc()
            time_module.sleep(0.5)
        finally:
            cap.release()


# ______________CAMERA METRICS_______________#
def handle_camera_tasks(camera_name, frame, start_time):
    """Wrapper function for process_camera_tasks"""
    try:
        camera_out_dict = camera_metrics.camera_metrics_process_frame(
            camera_name, frame, start_time
        )
        return camera_out_dict
    except Exception as e:
        traceback.print_exc()
        print(f"Error processing camera tasks: {e}")


def get_or_create_json_file(camera_name):
    """Returns the path of a JSON file. Creates an empty file if it does not exist."""
    compid, brid, deviceid, camera_id = camera_name.split("_")
    domain = get_domain(camera_name)
    db_config, base_path, domain_name = get_db_config_and_path(domain)
    folder = f"/home/fortune/AIVVAA-DATA/{domain_name}_Json_Files/{compid}/{brid}"
    filename = f"{camera_name}.json"
    file_path = os.path.join(folder, filename)

    # Ensure the folder exists
    os.makedirs(folder, exist_ok=True)

    # Check if the JSON file exists
    if not os.path.exists(file_path):
        open(file_path, "w").close()  # Create an empty JSON file
        # print(f"Created new JSON file: {file_path}")
    else:
        pass
        # print(f"JSON file already exists: {file_path}")

    return file_path  # Return the path of the JSON file


def run_shell_command(command):
    """
    Runs a shell command and returns the output, error, and exit code.

    Parameters:
        command (str): The shell command to run.

    Returns:
        tuple: (output, error, exit_code)
    """
    result = subprocess.run(command, shell=True, capture_output=True, text=True)


def save_live_images(camera_name, frame, BASE_DESTINATION_PATH, domain_name):

    # location = '/home/fortune/tmp/AIVVAA-DATA/'
    comp_id, br_id, dev_id, cam_id = camera_name.split("_")
    # print("CHECK camera_name",camera_name)

    # domain = get_domain(camera_name)
    # db_config, base_path, domain_name = get_db_config_and_path(domain)

    # Set the full directory path
    directory_path = f"{BASE_DESTINATION_PATH}{domain_name}_Aivvaa_Images/{comp_id}/{br_id}"

    # Check if the folder exists, if not, create it
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)  # Create directory if it doesn't exist

    # If the frame is None, load a default image
    if frame is None:
        frame = cv2.imread(f"{BASE_DESTINATION_PATH}/default/no_feed_image.jpg")

    # Resize the frame to desired size
    frame = cv2.resize(frame, (1920, 1080))

    # Save the image in the appropriate folder
    cv2.imwrite(f"{directory_path}/{camera_name}.jpg", frame)
    # if comp_id == "2001":
    #     print("CompId ",comp_id, f"/home/fortune/tmp/AIVVAA-DATA/{domain_name}_Aivvaa_Images/{comp_id}/{br_id}/{camera_name}.jpg", f"/home/fortune/tmp/AIVVAA-DATA/{domain_name}_Aivvaa_Images/{comp_id}/{br_id}")
    #     edge_device_image = f"scp -P 2223 /home/fortune/tmp/AIVVAA-DATA/{domain_name}_Aivvaa_Images/{comp_id}/{br_id}/{camera_name}.jpg fortune@192.168.0.199:/home/fortune/tmp/AIVVAA-DATA/{domain_name}_Aivvaa_Images/{comp_id}/{br_id}"
    #     run_shell_command(edge_device_image)

    #  if comp_id == "2002":   # Has to be Un comment and run main and test for Potblack Data
    #     print("CompId ",comp_id, f"/home/fortune/tmp/AIVVAA-DATA/{domain_name}_Aivvaa_Images/{comp_id}/{br_id}/{camera_name}.jpg", f"/home/fortune/tmp/AIVVAA-DATA/{domain_name}_Aivvaa_Images/{comp_id}/{br_id}")
    #     edge_device_image = f"scp -P 2225 /home/fortune/tmp/AIVVAA-DATA/{domain_name}_Aivvaa_Images/{comp_id}/{br_id}/{camera_name}.jpg ri2@192.168.0.199:/home/fortune/tmp/AIVVAA-DATA/{domain_name}_Aivvaa_Images/{comp_id}/{br_id}"
    #     run_shell_command(edge_device_image)  ## Upto here
    ## TODO Sent to remote location


# ___________________________________________#
# ____________BLUEPRINT TRACKING_____________#


def prepare_batch_input(img):
    # print(type(img), img.shape)
    img = Image.fromarray(img)
    img = np.array(img.resize((640, 640), Image.BILINEAR))
    img = img.transpose(2, 0, 1)  # Change shape from (H, W, C) to (C, H, W)
    img = np.expand_dims(img, axis=0)  # Add batch dimension
    img = img.astype(np.float32) / 255.0  # Normalize to FP32
    return img


def get_birds_eye_view(source_points, destination_points, output_size):
    """
    Transforms the input frame into a bird's-eye view.

    :param frame: Input image from the camera feed.
    :param source_points: Four points from the original image (top-down view reference).
    :param destination_points: Four points representing the bird's-eye view coordinates.
    :param output_size: Tuple representing the size of the output bird's-eye view image (width, height).
    :return: Transformed bird's-eye view image.
    """
    # Compute the perspective transformation matrix
    matrix, _ = cv2.findHomography(np.float32(source_points), np.float32(destination_points))

    # Apply the perspective warp to get the bird's-eye view
    return matrix


def retrieve_blueprints(camera_names, comp_br, domain_name, BASE_DESTINATION_PATH):

    blueprint_paths = []
    final_path = []
    comp_id = comp_br.split("_")[0]
    br_id = comp_br.split("_")[1]

    for camera in camera_names:
        camera_path = camera + ".png"
        blueprint_path_folder = (
            f"{BASE_DESTINATION_PATH}{domain_name}_Aivvaa_Blueprint_Images/{comp_id}/{br_id}"
        )
        bp_path = os.path.join(blueprint_path_folder, camera_path)
        # print("bp_path ", bp_path)
        if os.path.exists(bp_path):
            # cam_bp_path[camera] = camera_path
            blueprint_paths.append(camera_path)
            final_path.append(bp_path)

    return blueprint_paths, final_path


def process_blueprint_tracking(data):

    (
        collected_frames,
        collected_images_for_masks,
        pose_result,
        seg_result_0,
        seg_result_1,
        blueprint_polygons,
        video_polygons,
        all_matrices,
        camera_names,
        angles,
    ) = data
    print(
        len(collected_frames),
        len(collected_images_for_masks),
        pose_result.shape,
        seg_result_0.shape,
        seg_result_1.shape,
        len(blueprint_polygons.keys()),
        len(video_polygons.keys()),
        len(all_matrices.keys()),
        len(camera_names),
        len(angles),
    )
    try:
        if data is None:  # Sentinel to terminate the process
            return
            # collected_frames, pose_result, seg_result_0, seg_result_1, blueprint_polygons, video_polygons, all_matrices, camera_names
        feet_tensor_list = people_tracker.run_parallel_videos(
            collected_frames,
            collected_images_for_masks,
            pose_result,
            seg_result_0,
            seg_result_1,
            blueprint_polygons,
            video_polygons,
            all_matrices,
            camera_names,
            angles,
        )
    except Exception as e:
        print("Blueprint Tracking failed : ", e)
        traceback.print_exc()

    return feet_tensor_list


def run_pose(triton_client, model_input):
    pose_response = triton_client.infer(model_name="yolo11l_pose", inputs=[model_input])
    return pose_response.as_numpy("output0")


def run_seg(triton_client, model_input):
    seg_response = triton_client.infer(model_name="yoloe11l_seg", inputs=[model_input])
    return (seg_response.as_numpy("output0"), seg_response.as_numpy("output1"))


def run_osnet(triton_client, model_input):
    osnet_response = triton_client.infer(model_name="osnet_ain", inputs=[model_input])
    return osnet_response.as_numpy("features")


# ___________________________________________#
# _______________PEOPLE COUNT________________#


def resize_coords(coord, original_size=(640, 640), new_size=(1920, 1080)):
    """Resizing the coords being pulled from database

    Args:
        coords (tuple): x and y coords for each point
        original_size (tuple): coords drawn on (1920, 1080) image.
        new_size (tuple): Resizing coords to required size of blueprint (640, 640).

    Returns:
        list: resized, int value of x, y
    """
    x, y = coord
    orig_w, orig_h = original_size
    new_w, new_h = new_size

    # Compute scaling factors
    scale_x = new_w / orig_w
    scale_y = new_h / orig_h

    # Scale each coordinate
    new_coords = [int(x * scale_x), int(y * scale_y)]

    return new_coords


# def get_section_and_table_details(comp_br, base_json_dir="configs"):
def get_section_and_table_details(data, comp_br):
    """
    Load section & table details for a given comp_br (e.g. "2001_99001")
    from a JSON file (<base_json_dir>/<domain>.json) instead of querying the DB.
    """
    section_and_table_dict = {}

    # # Derive domain (e.g. "2001") from comp_br via your existing helper
    # domain = get_domain(comp_br)
    # json_path = os.path.join(base_json_dir, f"{domain}.json")

    # if not os.path.exists(json_path):
    #     print(f"JSON file not found: {json_path}")
    #     return {}

    # with open(json_path, "r") as f:
    #     data = json.load(f)

    # Navigate into the JSON
    all_sections = data.get("section_table_data", {}).get(comp_br, {})

    for key_str, sec in all_sections.items():
        # Convert key "(31, 201)" → tuple (31, 201)
        try:
            section_id, camera_id = map(int, key_str.strip("()").split(","))
        except Exception:
            continue

        # Copy the loaded dict directly
        section_and_table_dict[(section_id, camera_id)] = {
            "CompId": sec["CompId"],
            "BrId": sec["BrId"],
            "DeviceId": sec["DeviceId"],
            "camera_section_id": sec["camera_section_id"],
            "camera_id": sec["camera_id"],
            "section_name": sec["section_name"],
            "section_coordinates": sec["section_coordinates"],
            "section_capacity": sec["section_capacity"],
            "section_status": sec["section_status"],
            "section_blueprint_flag": sec["section_blueprint_flag"],
            "tables": [
                {
                    "camera_table_id": t["camera_table_id"],
                    "table_name": t["table_name"],
                    "table_coordinates": t["table_coordinates"],
                    "table_status": t["table_status"],
                    "table_blueprint_flag": t["table_blueprint_flag"],
                }
                for t in sec.get("tables", [])
            ],
        }

    return section_and_table_dict


# ___________________________________________#
# _________EMPLOYEE IDENTIFICATION____________#

manager = multiprocessing.Manager()
gallery_features = manager.dict()  # Use defaultdict to automatically initialize lists
cache_gallery_features = manager.dict()


def create_galleries(gallery_folders_path, active_employees, comp_br):

    print("CREATING GALLERIES")
    global gallery_features, cache_gallery_features

    comp_br = comp_br.replace("/", "_")
    if comp_br not in gallery_features.keys():
        gallery_features[comp_br] = manager.dict()
        cache_gallery_features[comp_br] = manager.dict()

    try:
        gallery_folders = os.listdir(gallery_folders_path)
        # print("HERE0 ", gallery_folders)
        # print("HERE1 ", active_employees)

        for gallery_folder in gallery_folders:
            # print("CHECK0 ", type(gallery_folder))
            # print("CHECK1", type(active_employees[0]))
            if int(gallery_folder) in active_employees:
                print(f"Current folder being added {gallery_folder}")
                if gallery_folder not in gallery_features[comp_br].keys():
                    gallery_features[comp_br][gallery_folder] = manager.list()
                    cache_gallery_features[comp_br][gallery_folder] = manager.list()
                # Create dataset and dataloader for the gallery set of employees
                gallery_dataset_path = os.path.join(gallery_folders_path, gallery_folder)
                if not os.path.exists(gallery_dataset_path):
                    print(f"Processed folder does not contain employee {gallery_folder}")
                    pass
                extensions = ".json"
                json_files = [
                    f for f in os.listdir(gallery_dataset_path) if f.lower().endswith(extensions)
                ]

                # Process each image
                # print("PATH HERE ", gallery_dataset_path)
                for file in json_files:
                    json_reference_encoding_path = os.path.join(gallery_dataset_path, file)
                    with open(json_reference_encoding_path, "r") as f:
                        data = json.load(f)
                        # print("data ", data)

                    gallery_features[comp_br][gallery_folder].append(data)
                    # print("ENCODING ADDED TO DICTIONARY")

        for gallery_folder, features in gallery_features[comp_br].items():
            print("FOLDER PARSED", gallery_folder)
            cache_gallery_features[comp_br][gallery_folder] = features[:2]
    except Exception as e:
        print(f"Error creating gallery features for {comp_br} {gallery_folder} {e}")
        traceback.print_exc()


# ___________________________________________#
# ____________YOLOe Functions______________#


def iou(box1, box2):
    """
    Compute Intersection over Union (IoU) between two bounding boxes.

    Args:
        box1 (tuple): (x1, y1, x2, y2) for the first box.
        box2 (tuple): (x1, y1, x2, y2) for the second box.

    Returns:
        float: IoU value.
    """
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_area = max(0, x2 - x1) * max(0, y2 - y1)
    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])

    union_area = box1_area + box2_area - inter_area
    return inter_area / union_area if union_area > 0 else 0


def postprocess_yoloe_hairnet(output0, conf_thresh=0.3, iou_thresh=0.3):
    """
    Extract high-confidence hairnet detections across batch.
    Returns: List of detections as (bbox_xyxy, score) tuples across all frames
    """
    all_detections = []
    # print("CHECK SHAPE", output0.shape)
    for i in range(output0.shape[0]):
        detections = output0[i].T  # shape (8400, 38)
        boxes = detections[:, 0:4]

        cls_conf = detections[:, 5]
        keep = cls_conf > conf_thresh
        if not np.any(keep):
            continue

        boxes = boxes[keep]
        scores = cls_conf[keep]

        # Convert from [cx, cy, w, h] → [x1, y1, x2, y2]
        cx, cy, w, h = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        x1, y1 = cx - w / 2, cy - h / 2
        x2, y2 = cx + w / 2, cy + h / 2
        boxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)

        # Convert to format [x, y, w, h] for
        boxes_xywh = []
        for b in boxes_xyxy:
            x, y, x2, y2 = b
            boxes_xywh.append([int(x), int(y), int(x2 - x), int(y2 - y)])

        # Run NMS
        nms_indices = cv2.dnn.NMSBoxes(
            boxes_xywh, scores.tolist(), score_threshold=conf_thresh, nms_threshold=iou_thresh
        )

        if isinstance(nms_indices, np.ndarray):
            nms_indices = nms_indices.flatten()
        elif nms_indices is None or len(nms_indices) == 0:
            continue

        for idx in nms_indices:
            bbox = boxes_xyxy[idx].astype(int)
            # print("CHECK SCORE",scores[idx])
            all_detections.append(bbox)
            # print("CHECK ALL DETCTION", len(all_detections))

    return all_detections


def infer_yoloe_hairnet(emp_list, seg_result_0, iou_threshold=0.25):
    """
    Match each person in emp_list to any hairnet detection across all frames using IoU.
    Args:
        emp_list: list of tuples like (person_id, person_bbox) — overall detections
        seg_result_0: output of model of shape (B, 38, 8400)

    Returns:
        list of (person_id, "Hairnet"/"No_Detection")
    """
    detections_per_image = postprocess_yoloe_hairnet(seg_result_0)
    # print("CHECK RESULT1", detections_per_image)

    matched_results = []
    for person_id, person_bbox in emp_list:
        label = 1
        person_id = "V" + str(person_id)
        shm_list_name = f"{person_id}_list"
        shm_list = shm.ShareableList(name=shm_list_name)
        for det_bbox in detections_per_image:
            iou_val = iou(det_bbox, person_bbox)
            if iou_val >= iou_threshold:
                shm_list[23] = 0
                shm_list[22] = 0
                label = 0
                break
        if label == 1:
            if shm_list[23] < 11:
                shm_list[23] += 1
            else:
                shm_list[22] = 1
    # print("CHECK RESULT2", matched_results)
    return


# _________________________________________________________________#
# ________________________PARKING_________________________________#


def parking_camera_details(camera_type_data, section_table_data):

    parking_camera_dict = {}

    for cam_key, labels in camera_type_data.items():
        for label in labels:
            if "PARKING" in label.upper():
                # if cam_key not in camera_hierarchy:
                #     camera_hierarchy.append(cam_key)
                if cam_key not in parking_camera_dict:
                    cam_id = cam_key.split("_")[3]
                    parking_camera_dict[cam_id] = cam_key

    parking_sections = {}

    for (section_id, camera_id), section in section_table_data.items():
        # Check if camera_id (as string) is in parking_camera_dict
        if str(camera_id) in parking_camera_dict:
            section_name = section.get("section_name", "")
            if "PARKING" in section_name.upper():
                entry = {
                    "section_id": section["camera_section_id"],
                    "parking_area": section["section_name"],
                    "coords": section["section_coordinates"],
                    "total_spaces": section["section_capacity"],
                }
                cam_key = parking_camera_dict[str(camera_id)]
                # Append entry to list under the correct cam_key
                if cam_key not in parking_sections:
                    parking_sections[cam_key] = []
                parking_sections[cam_key].append(entry)
    return parking_sections


def xywh2xyxy(boxes):
    """Convert (x, y, w, h) → (x1, y1, x2, y2)"""
    x, y, w, h = boxes.T
    x1, y1 = x - (w / 2), y - (h / 2)
    x2, y2 = x + (w / 2), y + (h / 2)
    return np.stack([x1, y1, x2, y2], axis=1)


def vehicle_detections(seg_result_0, conf_threshold=0.1, score_threshold=0.3, iou_threshold=0.3):
    """
    Extracts Car (2), Motorcycle (3), Bus (5), Truck (6) detections from YOLOE11L segmentation output.
    seg_result_0: np.ndarray, shape (B, 42, 8400)
    """
    print("seg_result_0 shape:", seg_result_0.shape)

    # Model's global class index mapping
    # Assuming YOLO class order: 0=person, 1=hairnet, 2=Car, 3=Motorcycle, 4=Bus, 5=Truck
    vehicle_class_global = {2: "Car", 3: "Motorcycle", 5: "Bus", 6: "Truck"}

    batch_detections = []

    for b in range(seg_result_0.shape[0]):  # loop over batch
        preds = seg_result_0[b]  # (42, 8400)
        preds = preds.T  # (8400, 42)

        # Class columns for Car, Motorcycle, Bus, Truck in *global* model output
        vehicle_cols = [6, 7, 8, 9]

        # Extract only vehicle scores
        class_scores = preds[:, vehicle_cols]  # (8400, 4)

        # Get best vehicle score for each prediction
        scores = np.max(class_scores, axis=1)  # (8400,)

        # Confidence filtering
        mask = scores > conf_threshold
        preds = preds[mask]
        class_scores = class_scores[mask]
        scores = scores[mask]

        if len(preds) == 0:
            batch_detections.append([])
            continue

        # Bounding boxes
        boxes = preds[:, :4]
        boxes = xywh2xyxy(boxes).astype(int)

        # Map back to actual *global* class indices
        best_class_offsets = np.argmax(class_scores, axis=1)  # 0–3
        class_ids = [list(vehicle_class_global.keys())[o] for o in best_class_offsets]

        # Apply NMS
        indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), score_threshold, iou_threshold)

        detections = []
        if hasattr(indices, "flatten"):
            indices = indices.flatten()

        for i in indices:
            cid = class_ids[i]
            detections.append(
                {
                    "class_name": vehicle_class_global[cid],
                    "class_index": int(cid),
                    "confidence": float(scores[i]),
                    "bbox": boxes[i].tolist(),
                }
            )

        batch_detections.append(detections)

    return batch_detections

    return batch_detections


def parking_status_data(data):
    camera_name, start_time, seg_result_0, parking_sections, parking_frames = data
    # print("CHECK_P3")
    detections = vehicle_detections(seg_result_0)
    print("CHECK_P4 ", detections)
    try:
        if data is None:
            return
        for parking_section in parking_sections:
            Parking_Status.process_frame_parking(
                camera_name, detections, parking_section, parking_frames
            )

    except Exception as e:
        print("Parking Area failed : ", e)
        traceback.print_exc()


# ______________________________________________________________________________________________#


def process_face_tasks(
    face, tddfa, gallery_features, cache_gallery_features, active_emp_code_ids, domain_name
):
    try:
        print("FACE VALUE ", face)
        if face:
            print("Starting process_employee_identification_tasks")
            employee_identification.emp_identification(
                face,
                tddfa,
                gallery_features,
                cache_gallery_features,
                active_emp_code_ids,
                domain_name,
            )
        else:
            print("Shared memory does not contain an image for IDENTIFICATION.")

    except Exception as e:
        print(f"Error processing background people tasks: {e}")
        traceback.print_exc()


def process_demographics_task(
    person_id, age_model, age_feature_extractor, gender_model, gender_feature_extractor
):
    try:
        demographics.predicting_age_and_gender(
            person_id, age_model, age_feature_extractor, gender_model, gender_feature_extractor
        )
    except Exception as e:
        print(f"Error processing demographics task: {e}")
        traceback.print_exc()


def process_uniform_batch(batch, triton_client, time_zone_timenow):

    uniform_batch = []
    uniform_tracks = []
    uniform_image = []

    for person in batch:
        uniform_img = person[1]
        person_id = person[0]
        shm_list_name = f"{person_id}_list"
        shm_list = shm.ShareableList(name=shm_list_name)
        if shm_list[5] == 1:
            if shm_list[45] < 11:
                uniform_image.append(uniform_img)
                # Convert to float16 and normalize
                img_inputs = uniform_img.astype(np.float16) / 255.0

                # Change shape from HWC -> CHW
                img_input = np.transpose(img_inputs, (2, 0, 1))
                # Add batch dimension
                img_input = np.expand_dims(img_input, axis=0)
                uniform_batch.append(img_input)
                uniform_tracks.append(person[0])
            elif shm_list[45] > 300:
                shm_list[45] = 0
        else:
            if shm_list[45] > 1800:
                uniform_image.append(uniform_img)
                # Convert to float16 and normalize
                img_inputs = uniform_img.astype(np.float16) / 255.0

                # Change shape from HWC -> CHW
                img_input = np.transpose(img_inputs, (2, 0, 1))
                # Add batch dimension
                img_input = np.expand_dims(img_input, axis=0)
                uniform_batch.append(img_input)
                uniform_tracks.append(person[0])
                shm_list[45] = 0
        shm_list[45] += 1

    if len(uniform_batch) == 0:
        return
    uniform_batch_images = np.concatenate(uniform_batch, axis=0)

    # -------- Run inference (pose + seg in parallel) --------
    model_input = triton.InferInput("images", uniform_batch_images.shape, "FP16")
    model_input.set_data_from_numpy(uniform_batch_images)

    # Prepare Triton input
    uniform_response = triton_client.infer(model_name="uniform", inputs=[model_input])
    output0, output1 = uniform_response.as_numpy("output0"), uniform_response.as_numpy("output1")

    for idx, batch in enumerate(output0):
        # for i in enumerate(output0):
        # Remove batch dimension
        # det_output = batch[0]  # shape (38, 8400)

        # Column 4 is index 3 (0-based)
        col4_values = batch[4]  # shape (8400,)

        # Find maximum
        max_value = np.max(col4_values)

        person_id = uniform_tracks[idx]
        shm_list_name = f"{person_id}_list"
        shm_list = shm.ShareableList(name=shm_list_name)
        img = uniform_image[idx]

        # Check threshold
        if max_value >= 0.5:
            shm_list[5] = 0
            shm_list[45] = 0
        else:
            shm_list[5] = 1


# ______________________________________________________________________________________#


def pad_to_640(img):
    h, w, c = img.shape
    scale = min(640 / w, 640 / h)
    new_w, new_h = int(w * scale), int(h * scale)

    # Resize while preserving aspect ratio
    resized = cv2.resize(img, (new_w, new_h))

    # Create black canvas
    canvas = np.zeros((640, 640, 3), dtype=np.uint8)

    # Compute top-left corner for centering
    x_offset = (640 - new_w) // 2
    y_offset = (640 - new_h) // 2

    # Paste the resized image onto the canvas
    canvas[y_offset : y_offset + new_h, x_offset : x_offset + new_w] = resized

    return canvas, scale, x_offset, y_offset  # return offsets to reverse box scaling later


def show_active_threads():
    print(f"Active threads ({threading.active_count()}):")
    for t in threading.enumerate():
        print(f" - {t.name} (daemon: {t.daemon})")


def extract_person_id(match_id):
    return match_id.split("_")[0]  # '6_left' -> '6'


def compute_score(total, foreg, parts, dist, w_total=0.75, w_dist=0.25, w_parts=0.1, w_foreg=0.05):
    return (w_total * total) + (w_dist * (dist / 100))


def main():

    # show_active_threads()  # initial

    shared_memory_objects = {}
    shared_memory_flags = {}
    shared_metrics_objects = {}
    processes_receiving = []
    producer = KafkaProducer(
        bootstrap_servers=["124.123.40.165:9090"],
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    device_id = "10.0.0.2"
    for path in glob.glob("/dev/shm/*"):
        name = os.path.basename(path)
        try:
            shm_obj = shm.SharedMemory(name=name)
            shm_obj.close()
            shm_obj.unlink()
            # print(f" Cleaned: {name}")
        except Exception as e:
            pass

    vespa_handler.delete_recent_documents(0)

    try:
        domain_list = ["2001"]

        camera_queues = {}
        camera_hierarchies, time_diff_map = get_camera_hierarchy_from_json("2001_99001")

        for camera in camera_hierarchies:
            channel = camera.split("_")[-1]
            if camera.startswith("1001"):
                rtsp = f"rtsp://admin:1234567a@192.168.0.154/Streaming/Channels/{channel}"
            else:
                rtsp = f"rtsp://192.168.0.198:8554/{camera}"
            print(rtsp)
            camera_queues[camera] = rtsp
        print(camera_queues)
        # Create shared memory
        for cam in camera_queues:
            shared_memory_objects[cam] = shm.SharedMemory(name=cam, create=True, size=frame_size)
            # Camera metrics index nomenclature (Flag, start     time, end time, duration)
            shared_metrics_objects[cam] = shm.ShareableList(
                [False, " " * 8, " " * 8, 0] * 4, name=f"{cam}_camera_metrics"
            )
            shared_memory_flags[f"{cam}_flag"] = shm.SharedMemory(
                name=f"{cam}_flag", create=True, size=1
            )
        # Start receiving processes
        for camera_name, rtsp_link in camera_queues.items():
            p = multiprocessing.Process(
                target=receive_frames,
                args=(camera_name, rtsp_link, camera_name, f"{camera_name}_flag"),
            )
            p.start()
            processes_receiving.append(p)

        frame_arrays = {
            cam: np.ndarray(frame_shape, dtype=frame_dtype, buffer=shared_memory_objects[cam].buf)
            for cam in camera_queues.keys()
        }

        frame_flag = {
            cam: np.ndarray((1,), dtype=np.uint8, buffer=shared_memory_flags[f"{cam}_flag"].buf)
            for cam in camera_queues.keys()
        }

        # demographics model

        age_model_name = "NTQAI/pedestrian_age_recognition"

        # Load the pre-trained model and feature extractor for age
        age_model = AutoModelForImageClassification.from_pretrained(age_model_name)
        age_feature_extractor = AutoFeatureExtractor.from_pretrained(age_model_name)

        # Gender
        gender_model_name = "rizvandwiki/gender-classification"

        # Load the pre-trained model and feature extractor
        gender_model = AutoModelForImageClassification.from_pretrained(gender_model_name)
        gender_feature_extractor = AutoFeatureExtractor.from_pretrained(gender_model_name)

        process_camera_metrics = []
        process_facial_identification = []

        def _remove_future(future):
            try:
                process_facial_identification.remove(future)
            except ValueError:
                pass  # already removed

        process_demographics = []
        process_hairnet = []
        process_parking = []

        domain = get_domain(list(frame_flag.keys())[0])
        usecase_key = get_usecase_key(list(frame_flag.keys())[0])
        db_config, BASE_DESTINATION_PATH, domain_name = get_db_config_and_path(domain)

        temp_hierarchy = list(frame_flag.keys())[0].split("_")
        comp_br = temp_hierarchy[0] + "_" + temp_hierarchy[1]
        comp_br_timenow = time_diff_map[comp_br]

        # Model details
        # triton_client = get_triton_client("localhost:8001")
        triton_client = triton.InferenceServerClient(
            url="localhost:8001"
        )  # Replace with Triton server's IP

        # TODO: extrat comp_br from JSON file
        # TODO: Remove all hardcoded values
        print("HERE", BASE_DESTINATION_PATH)
        json_file_path = f"{BASE_DESTINATION_PATH}{domain_name}_config/{comp_br}.json"
        # print("HERE0", json_file_path)
        with open(json_file_path, "r") as file:
            data = json.load(file)

        # print("JSON FILE data ", data)
        employee_data = data.get("employee_data", {})

        blueprint_paths, bp_path = retrieve_blueprints(
            camera_queues.keys(), comp_br, domain_name, BASE_DESTINATION_PATH
        )

        all_video_coords = data.get("video_coords", {})
        all_blueprint_coords = data.get("blueprint_coords", {})

        video_coords = list(all_video_coords.values())
        blueprint_coords = list(all_blueprint_coords.values())

        # TODO: Create blueprint polygons here
        all_matrices = {
            cam_name: get_birds_eye_view(
                all_video_coords[cam_name], all_blueprint_coords[cam_name], (640, 640)
            )
            for cam_name in camera_queues.keys()
        }

        blueprint_polygons = {
            cam_name: Polygon(all_blueprint_coords[cam_name]) for cam_name in camera_queues.keys()
        }

        video_polygons = {
            cam_name: Polygon(all_video_coords[cam_name]) for cam_name in camera_queues.keys()
        }

        # print("all_blueprint_coords\n", all_blueprint_coords)
        # print("blueprint_polygons\n", blueprint_polygons)
        # print("\nvideo_polygons\n", video_polygons)

        # TODO: Extarct sections_tables from Json
        sections_tables = get_section_and_table_details(data, comp_br)

        camera_type_data = data.get("camera_type_data", {})
        parking_sections = parking_camera_details(camera_type_data, sections_tables)
        last_parking = 0
        print("\n parking_sections ", parking_sections)

        blueprint_section_coords = {}

        for cam, coords in all_blueprint_coords.items():
            blueprint_section_coords[cam] = [resize_coords(coord) for coord in coords]

        blueprint_section_polygons = {
            cam_name: Polygon(blueprint_section_coords[cam_name])
            for cam_name in camera_queues.keys()
        }

        device_time_diff = data["device_data"]["time_diff"]

        # print("HERE1", blueprint_paths)
        # print("HERE2", bp_path)
        # print("HERE3", all_video_coords)
        # print("HERE4", all_blueprint_coords)
        # print("HERE5", device_time_diff)

        domain_list = []
        for cam_name in camera_queues.keys():
            comp_br_dest = cam_name.split("_")[0] + "/" + cam_name.split("_")[1]
            # if comp_br_dest not in domain_list:
            if comp_br_dest not in domain_list:
                domain_list.append(comp_br_dest)
                active_emp_code_ids = employee_data[comp_br_dest]
                active_emp_ids = [emp["Employee_Id"] for emp in active_emp_code_ids]
                # active_emp_ids = ["2002"]
                print(f"Active employees {active_emp_ids} for {comp_br_dest}")
                if not active_emp_ids:
                    print(f"No active employees for {comp_br_dest}")
                    pass
                gallery_folders_path = f"/home/fortune/AIVVAA-DATA/{domain_name}_Object_Images_Processed/{comp_br_dest}"
                # print("gallery_folders_path ", gallery_folders_path)
                if not os.path.exists(gallery_folders_path):
                    print(f"Processed folder does not exist for {comp_br_dest}")
                    pass
                else:
                    process = multiprocessing.Process(
                        target=create_galleries,
                        args=(
                            gallery_folders_path,
                            active_emp_ids,
                            comp_br_dest,
                        ),
                    )  # TODO: temp folder and gallery folder to be sent
                    process.start()
                    try:
                        process.join()
                    except KeyboardInterrupt:
                        process.terminate()
                        process.join()
                    print(f"Gallery COMPLETE for {comp_br_dest}")

        for key in cache_gallery_features.keys():
            print(key, cache_gallery_features[key].keys())
            print(
                [
                    len(cache_gallery_features[key][ids])
                    for ids in cache_gallery_features[key].keys()
                ]
            )
        for key in gallery_features.keys():
            print(key, gallery_features[key].keys())
            print([len(gallery_features[key][ids]) for ids in gallery_features[key].keys()])
        print("GALLERY CODE FINISHED\n")

        active_emp_code_ids = [(emp["Emp_id"], emp["Employee_Id"]) for emp in active_emp_code_ids]
        print("\n active_emp_code_ids ", active_emp_code_ids, "\n")

        # load config
        cfg = yaml.load(open("configs/mb1_120x120.yml"), Loader=yaml.SafeLoader)

        face_boxes = FaceBoxes_ONNX(triton_client)
        tddfa = TDDFA_ONNX(triton_client, **cfg)
        angles = [30, 30, 30, 30, 30, 30, 30]
        temp_people_count = 0
        # Main loop or idle wait

        executor_camera = ThreadPoolExecutor(max_workers=5)
        executor_infer = ThreadPoolExecutor(max_workers=2)
        executor_misc = ThreadPoolExecutor(max_workers=8)

        while True:
            people_count_results = []
            start_time = datetime.now()
            try:
                time_zone_timenow = start_time + timedelta(seconds=comp_br_timenow)
                date_str = time_zone_timenow.strftime("%Y-%m-%d")
                time_str = time_zone_timenow.strftime("%H:%M:%S")

                # ✅ Recreate flag_arrays each iteration (fresh views)
                flag_arrays = {
                    cam + "_flag": np.ndarray(
                        (1,), dtype=flag_dtype, buffer=shared_memory_flags[f"{cam}_flag"].buf
                    )
                    for cam in camera_queues.keys()
                }
                # -------- Camera processing --------
                process_camera_metrics = []  # reset each loop
                for camera_name, frame in frame_arrays.items():
                    json_file_path = get_or_create_json_file(camera_name)

                    if flag_arrays[camera_name + "_flag"][0] == 1:
                        frame = frame
                    else:
                        frame = None

                    save_live_images(camera_name, frame, BASE_DESTINATION_PATH, domain_name)

                    if usecase_key in ["10", "99", "11"]:
                        future = executor_camera.submit(
                            handle_camera_tasks, camera_name, frame, time_zone_timenow
                        )
                        process_camera_metrics.append(future)

                # Collect results safely
                results = []
                for future in as_completed(process_camera_metrics):
                    try:
                        results.append(future.result())
                    except Exception as e:
                        results.append({"status": "error", "error": str(e)})
                camera_metrics_results = [r for r in results if r not in (None, [None, None])]

            except Exception:
                logging.exception("ERROR inside main while loop")
            camera_metrics_results = [item for item in results if item != [None, None]]
            # -------- Frame batching --------
            collected_frames, collected_images_for_masks, parking_frames = [], [], {}
            last_parking = getattr(main, "last_parking", 0)
            working_cameras = []
            for camera_name, frame in frame_arrays.items():
                camera_metrics_shm = shm.ShareableList(name=f"{camera_name}_camera_metrics")

                if camera_name.startswith(comp_br):
                    if frame_flag[camera_name][0] == 1 and not (
                        camera_metrics_shm[12] or camera_metrics_shm[8]
                    ):
                        if camera_name in parking_sections:
                            now = time_module.time()
                            if (now - last_parking) >= 60:
                                processed_frame = prepare_batch_input(frame)
                                collected_frames.append(processed_frame)
                                collected_images_for_masks.append(frame)
                                parking_frames[camera_name] = frame
                                working_cameras.append(camera_name)
                                main.last_parking = now
                                continue
                            else:
                                continue
                        processed_frame = prepare_batch_input(frame)
                        collected_frames.append(processed_frame)
                        collected_images_for_masks.append(frame)
                        working_cameras.append(camera_name)
            if len(collected_frames) == 0:
                logging.debug("All cameras not sending viable frames")
            else:
                batch_images = np.concatenate(collected_frames, axis=0)

                # -------- Run inference (pose + seg in parallel) --------
                model_input = triton.InferInput("images", batch_images.shape, "FP32")
                model_input.set_data_from_numpy(batch_images)

                pose_future = executor_infer.submit(run_pose, triton_client, model_input)
                seg_future = executor_infer.submit(run_seg, triton_client, model_input)

                pose_result = pose_future.result()
                seg_result_0, seg_result_1 = seg_future.result()

                feet_tensor_list = process_blueprint_tracking(
                    (
                        collected_frames,
                        collected_images_for_masks,
                        pose_result,
                        seg_result_0,
                        seg_result_1,
                        blueprint_polygons,
                        video_polygons,
                        all_matrices,
                        working_cameras,
                        angles,
                    )
                )
                all_features = []
                vespa_inputs = []
                # print(f"Inference POST processing complete in: {total_end_time - total_start_time:.3f} seconds ")
                print("\n\n______________________OUTPUT from people_tracker", len(feet_tensor_list))
                num_workers = len(feet_tensor_list) // 2
                # print("----------------------num_workers ", num_workers)
                # print("----------------------len(feet_tensor_list) ", len(feet_tensor_list))
                if num_workers != 0:
                    with ThreadPoolExecutor(max_workers=num_workers) as executor:
                        for i in range(num_workers):
                            # print(feet_tensor_list[2*i][1].shape, feet_tensor_list[(2*i)+1][1].shape)
                            # new_center_point, batched_tensor, visibility_vector, person_id_suffix, temp_cropped_full_img, cropped_full_img
                            np_tensor_1 = feet_tensor_list[2 * i][1].detach().cpu().numpy()
                            np_tensor_2 = feet_tensor_list[(2 * i) + 1][1].detach().cpu().numpy()
                            batch_images = np.concatenate([np_tensor_1, np_tensor_2], axis=0)
                            model_input = triton.InferInput("input", batch_images.shape, "FP32")
                            model_input.set_data_from_numpy(batch_images)
                            osnet_future = executor.submit(run_osnet, triton_client, model_input)
                            all_features.append(
                                [
                                    feet_tensor_list[2 * i][0],
                                    osnet_future,
                                    feet_tensor_list[2 * i][2],
                                    feet_tensor_list[2 * i][3],
                                    feet_tensor_list[2 * i][4],
                                    feet_tensor_list[2 * i][6],
                                    0,
                                ]
                            )
                            all_features.append(
                                [
                                    feet_tensor_list[(2 * i) + 1][0],
                                    osnet_future,
                                    feet_tensor_list[(2 * i) + 1][2],
                                    feet_tensor_list[(2 * i) + 1][3],
                                    feet_tensor_list[(2 * i) + 1][4],
                                    feet_tensor_list[(2 * i) + 1][6],
                                    1,
                                ]
                            )
                if len(feet_tensor_list) % 2 == 1:
                    # print(feet_tensor_list[-1][1].shape)
                    np_tensor = feet_tensor_list[-1][1].detach().cpu().numpy()
                    model_input = triton.InferInput("input", np_tensor.shape, "FP32")
                    # print(batch_images.shape)
                    model_input.set_data_from_numpy(np_tensor)
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        osnet_future = executor.submit(run_osnet, triton_client, model_input)
                    all_features.append(
                        [
                            feet_tensor_list[-1][0],
                            osnet_future,
                            feet_tensor_list[-1][2],
                            feet_tensor_list[-1][3],
                            feet_tensor_list[-1][4],
                            feet_tensor_list[-1][6],
                            0,
                        ]
                    )
                for feature in all_features:
                    feet_points = feature[0]
                    tensors = feature[1].result()
                    visibility_vector = feature[2]
                    suffix = feature[3]
                    cropped_image = feature[4]
                    org_bbox = feature[5]
                    idx = feature[6] * 4
                    tensors = torch.tensor(tensors[idx : idx + 4], dtype=torch.float32)
                    vespa_inputs.append(
                        [feet_points, tensors, visibility_vector, suffix, cropped_image, org_bbox]
                    )
                    # print("Vespa input obtained line 585 ", tensors.shape, feet_points, suffix, visibility_vector)
                if len(vespa_inputs) > 0:
                    print("------------------ Length of vespa inputs", len(vespa_inputs))
                    all_people_data = vespa_handler.match_all_features_parallel(vespa_inputs)
                    people_matched = []
                    final_matched = []
                    score_graph = defaultdict(lambda: defaultdict(lambda: float("10000")))
                    for source_idx, (source_info, matches) in enumerate(all_people_data):
                        feet_point, tensors, vis, suffix, cropped_image, v_org_bbox = source_info
                        if len(matches) == 0:
                            current_id = vespa_handler.add_to_vespa(source_info)
                            shm_handler.create_vespa_shared_memory(
                                str(current_id) + "_" + suffix,
                                cropped_image,
                                comp_br,
                                date_str,
                                domain_name,
                                time_str,
                                feet_point,
                            )
                            final_matched.append((current_id, v_org_bbox))
                            print("NO MATCHES FOUND ADDING ID ", current_id)
                        else:
                            people_matched.append((source_idx, v_org_bbox))
                            for match in matches:
                                match_id, total, foreg, parts, dist = match
                                target_id = extract_person_id(match_id)
                                score = compute_score(total, foreg, parts, dist)
                                # Only keep the best score if multiple views exist (e.g., 6_left, 6_front)
                                if source_idx not in score_graph:
                                    if target_id not in score_graph[source_idx]:
                                        score_graph[source_idx][target_id] = float("10000")
                                if score < score_graph[source_idx][target_id]:
                                    score_graph[source_idx][target_id] = score
                    left_nodes = list(score_graph.keys())
                    right_nodes = sorted(
                        {key for scores in score_graph.values() for key in scores.keys()}
                    )
                    print(right_nodes)

                    # Step 2: Create cost matrix
                    cost_matrix = np.full(
                        (len(left_nodes), len(right_nodes)), fill_value=0
                    )  # np.inf
                    for i, l in enumerate(left_nodes):
                        for j, r in enumerate(right_nodes):
                            if r in score_graph[l]:
                                score = score_graph[l][r]
                                cost_matrix[i, j] = -score  # negate to convert to minimization
                    print(cost_matrix)
                    # Step 3: Apply Hungarian algorithm
                    try:
                        row_ind, col_ind = linear_sum_assignment(cost_matrix)
                    except:
                        print("No feasible assignments, skipping Hungarian step")
                        row_ind, col_ind = np.array([]), np.array([])

                    # Step 4: Extract matches and actual (positive) scores
                    matches = {}
                    scores = []

                    for i, j in zip(row_ind, col_ind):
                        left = left_nodes[i]
                        right = right_nodes[j]
                        score = score_graph[left].get(right, None)
                        if score is not None:
                            matches[left] = right
                            scores.append(score)

                    print("MATCHES ", matches)
                    print("SCORE ", scores)
                    # print("all_people_data ", all_people_data[0])
                    # print("all_people_data ", len(all_people_data))
                    # print(matches)
                    # print(people_matched)

                    for people_id, v_org_bbox in people_matched:
                        source_info, _ = all_people_data[people_id]
                        feet_point, tensors, vis, suffix, cropped_image, v_org_bbox = source_info
                        if people_id in matches:
                            # print("MATCH FOUND")
                            final_matched.append((matches[people_id], v_org_bbox))
                            vespa_handler.update_vespa(source_info, matches[people_id], True)
                            shm_handler.create_vespa_shared_memory(
                                matches[people_id] + "_" + suffix,
                                cropped_image,
                                comp_br,
                                date_str,
                                domain_name,
                                time_str,
                                feet_point,
                            )
                            # print("shm updated for ", matches[people_id])
                        else:
                            current_id = vespa_handler.add_to_vespa(source_info)
                            final_matched.append((current_id, v_org_bbox))
                            shm_handler.create_vespa_shared_memory(
                                str(current_id) + "_" + suffix,
                                cropped_image,
                                comp_br,
                                date_str,
                                domain_name,
                                time_str,
                                feet_point,
                            )
                            # print("shm created new for ", current_id)

                    # for index, vespa_index in matches:
                    #     print(index, vespa_index)
                    #     print(all_people_data[index])
                    # if i do all_people_data[0] i get first person
                    # 1) is person in match list
                    # 2) if not, add to vespa
                    # 3) if matched, update vespa (id is the value)

                    # people_matched =
                    # print("people_matched ", people_matched)

                    # # TODO: SHM TO BE CREATED/PROCESSED HERE
                    # if num_workers == 0:
                    #     num_workers = 1
                    # else:
                    #     num_workers = num_workers*2

                    #         with ThreadPoolExecutor(max_workers=num_workers) as executor:
                    #             # TODO: Not parallelized properly
                    #             for i, (doc_id, id_match, matched_existing, score, cropped_image, feet_point, prospects) in enumerate(results):
                    #                 if matched_existing:
                    #                     people_matched.append(doc_id.split("_")[0])
                    #                     shm_feature = executor.submit(shm_handler.create_vespa_shared_memory, doc_id, cropped_image, comp_br, date_str, domain_name, time_str, feet_point)
                    #                     shm_feature.result()
                    #                 else:
                    #                     people_not_matched.append([doc_id, matched_existing, id_match, score, cropped_image, feet_point, prospects])
                    #         with ThreadPoolExecutor(max_workers=num_workers) as executor:
                    #                 # Create a mapping of Future to input data (people)
                    #                 futures = {
                    #                     executor.submit(process_person, people, people_matched, vespa_handler, new_visitors): people
                    #                     for people in people_not_matched
                    #                 }
                    #         with ThreadPoolExecutor(max_workers=num_workers) as executor:
                    #             for future in as_completed(futures):
                    #                 people = futures[future]  # Retrieve the corresponding input data
                    #                 try:
                    #                     doc_id = future.result()
                    #                     shm_feature = executor.submit(shm_handler.create_vespa_shared_memory, doc_id, people[4], comp_br, date_str, domain_name, time_str, people[-2])
                    #                     print(f"[Result {i}] Vespa ID: {doc_id}, ",
                    #                         f"Matched Existing: {matched_existing}, ",
                    #                         f"Exact ID Match: {id_match}, ",
                    #                         f"Score: {score}, ",
                    #                         f"Cropped Image Shape: {cropped_image.shape}, ",
                    #                         f"Feet Point: {feet_point}")
                    #                     shm_feature.result()
                    #                 except Exception as e:
                    #                     print(f"Thread raised exception for people={people}: {e}")

                    faces_for_identification = []
                    comp_id = comp_br.split("_")[0]
                    br_id = comp_br.split("_")[1]
                    print("Final Matched")
                    print(final_matched)
                    emp_list = []
                    emp_img_list = []
                    cust_list = []
                    for person_id, v_org_bbox in final_matched:
                        person_id = "V" + str(person_id)
                        shm_list = shm.ShareableList(name=f"{person_id}_list")

                        # print("\npeople_id ", person_id)
                        if shm_list[3] == "EMP":
                            emp_list.append((person_id, v_org_bbox))
                            shared_mem = shm.SharedMemory(name=person_id, create=False)
                            image_height, image_width = struct.unpack_from("ii", shared_mem.buf, 0)
                            shared_array = np.ndarray(
                                (640, 640, 3), dtype=np.uint8, buffer=shared_mem.buf, offset=8
                            )
                            emp_image = shared_array[:image_height, :image_width].copy()
                            emp_padded_img, scale, x_offset, y_offset = pad_to_640(emp_image)
                            emp_img_list.append((person_id, emp_padded_img))
                            shared_mem.close()
                            continue
                        elif shm_list[3] == "CUST":
                            cust_list.append((person_id, v_org_bbox))
                            continue

                        if shm_list[43] == "front":
                            # print("\npeople_id ", person_id)
                            shared_mem = shm.SharedMemory(name=person_id, create=False)
                            image_height, image_width = struct.unpack_from("ii", shared_mem.buf, 0)
                            shared_array = np.ndarray(
                                (640, 640, 3), dtype=np.uint8, buffer=shared_mem.buf, offset=8
                            )
                            image = shared_array[:image_height, :image_width].copy()
                            padded_img, scale, x_offset, y_offset = pad_to_640(image)
                            cv2.imwrite(
                                f"/home/fortune/AIVVAA-DATA/REST_Aivvaa_Visitor_Images/{comp_id}/{br_id}/{person_id}_{temp_people_count}.jpg",
                                padded_img,
                            )
                            # print("Line1035 main ", padded_img.shape)
                            temp_people_count += 1
                            faces_for_identification.append((person_id, padded_img))
                            shared_mem.close()

                    max_batch_size = 8
                    process_facial_identification = []

                    # Split faces into batches of 8
                    batches = [
                        faces_for_identification[i : i + max_batch_size]
                        for i in range(0, len(faces_for_identification), max_batch_size)
                    ]

                    def _remove_future(future):
                        try:
                            process_facial_identification.remove(future)
                        except ValueError:
                            pass

                    num_batches = len(batches)

                    # Use ThreadPoolExecutor to process multiple batches in parallel (optional)
                    if num_batches > 0:
                        with ThreadPoolExecutor(max_workers=num_batches) as executor:
                            for batch in batches:
                                triton_face_boxes = face_boxes(batch)
                                for face in triton_face_boxes:
                                    future = executor.submit(
                                        process_face_tasks,  # a function that handles a batch of faces
                                        face,
                                        tddfa,
                                        gallery_features[comp_br],
                                        cache_gallery_features[comp_br],
                                        active_emp_code_ids,
                                        domain_name,
                                    )
                                    future.add_done_callback(_remove_future)
                                    process_facial_identification.append(future)

                    print("LENGTH Employees", len(emp_img_list))

                    if len(emp_img_list) > 0:
                        max_batch_size_uniform = 8
                        process_uniform = []

                        # Split faces into batches of 8
                        uniform_batches = [
                            emp_img_list[i : i + max_batch_size_uniform]
                            for i in range(0, len(emp_img_list), max_batch_size)
                        ]
                        for batch in uniform_batches:
                            process_uniform_batch(batch, triton_client, time_zone_timenow)

                        #     triton_face_boxes = face_boxes(batch)
                        # for person_id, v_org_bbox in emp_list:

                    # CUSTOMER USECASES
                    # if len(final_matched) > 0:
                    #     try:
                    #         #TODO:Iterate through cust_list and create threads for each usecase by accessing the shm_list and shared memory for ther person once
                    #         with ThreadPoolExecutor(max_workers= len(final_matched)) as executor:
                    #             for person_id, v_org_bbox in final_matched:
                    #                 demographics_futures = executor.submit(process_demographics_task, person_id, age_model, age_feature_extractor, gender_model, gender_feature_extractor)
                    #                 process_demographics.append(demographics_futures)
                    #     except Exception as e:
                    #         print("DEMOGRAPHICS ERROR")
                    #         traceback.print_exc()

                    # EMPLOYEE USECASES
                    # TODO: Change final_matched to emp_list
                    if len(final_matched) > 0:
                        try:
                            # HAIRNET
                            infer_yoloe_hairnet(final_matched, seg_result_0)

                        except Exception as e:
                            print("Employee usecases ERROR")
                            traceback.print_exc()
                    if len(final_matched) != 0:
                        with ThreadPoolExecutor(max_workers=len(final_matched)) as executor:
                            futures = [
                                executor.submit(
                                    peoplecount.process_people_count,
                                    people_id,
                                    sections_tables,
                                    blueprint_section_polygons,
                                )
                                for people_id, _ in final_matched
                            ]
                            for future in as_completed(futures):
                                try:
                                    people_count_results.extend(future.result())
                                except Exception as e:
                                    print(f"peoplecount thread raised exception: {e}")

                    # TODO: Uncomment to return the file paths
                    # facial_done, _ = wait(process_facial_identification, timeout=0, return_when=FIRST_COMPLETED)

                    # for future in facial_done:
                    #     try:
                    #         result = future.result()
                    #         print("RESULT from face identification", result)
                    #         # process_face_id_result(result)
                    #     except Exception as e:
                    #         print("Error in collecting results from face_identification ", e)
                    #         traceback.print_exc()
                    #     process_facial_identification.remove(future)

                else:
                    print("NO VESPA INPUTS TO PROCESS")

                    # objects

                    # if len(collected_frames)==len(camera_hierarchies):
                    #     # print("CHECK_P1")
                    #     if len(process_parking) < 10:
                    #         # print("CHECK_P2")
                    #         parking_dict  = parking_sections.keys()
                    #         print("parking_dict ", parking_dict)
                    #         for camera_name in parking_dict:
                    #             parking_dict1  = parking_sections.get(camera_name)
                    #             print("CHECK parking_dict1",parking_dict1)
                    #             parking_process = multiprocessing.Process(target=parking_status_data, args=((camera_name, start_time, seg_result_0, parking_dict1, parking_frames),))
                    #             process_parking.append(parking_process)
                    #             parking_process.start()
                print("FACIAL LIST ", process_facial_identification)

                print("Sending payload out")
                payload = {
                    "device_id": device_id,
                    "domain_name": "REST",
                    "camera_metrics": camera_metrics_results,
                    "people_count": people_count_results,
                }

                print("PAYLOAD", payload)

                producer.send("camera-metadata", value=payload)
                producer.flush()
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                duration_check = max(0, 0.5 - duration)
                print(duration, "Final Duration in Seconds\n\n")

                # time.sleep(5)
                # show_active_threads()  # after threads run

                time_module.sleep(duration_check)

    except Exception as e:
        traceback.print_exc()
        print("Exception! -> main.py -> main -> ", e)


if __name__ == "__main__":
    main()
