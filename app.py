import streamlit as st
import requests
import json
import asyncio
import websockets
import pandas as pd
import time
import cv2
import numpy as np
from PIL import Image, ImageDraw
from datetime import datetime
import logging

# Fallback logger if project libs are not available
try:
    from libs.shared.logging.logger import get_logger
    log = get_logger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger(__name__)

# --- Page Config ---
st.set_page_config(
    page_title="Pipeline OpenCV Dashboard",
    page_icon="🛡️",
    layout="wide"
)

# --- Session State ---
if 'token' not in st.session_state:
    st.session_state.token = None
if 'camera_id' not in st.session_state:
    st.session_state.camera_id = "cam01"
if 'latest_detections' not in st.session_state:
    st.session_state.latest_detections = []
if 'latest_action' not in st.session_state:
    st.session_state.latest_action = None

def draw_boxes(image_bytes, detections, action=None):
    """Overlays bounding boxes and action status on the image."""
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Draw bounding boxes
        for det in detections:
            bbox = det.get("bbox", [0, 0, 0, 0])
            label = det.get("label", "person")
            conf = det.get("confidence", 0.0)
            
            x, y, w, h = map(int, bbox)
            color = (0, 255, 0) if label == "person" else (255, 255, 0)
            cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
            cv2.putText(img, f"{label} {conf:.2f}", (x, y - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Draw action alert if shoplifting
        if action and action.get("label") == "shoplifting":
            cv2.rectangle(img, (0, 0), (img.shape[1], 50), (255, 0, 0), -1)
            cv2.putText(img, "WARNING: SHOPLIFTING DETECTED", (50, 35),
                        cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), 2)
        
        return img
    except Exception as e:
        return None

# --- Sidebar: Connection & Configuration ---
with st.sidebar:
    st.header("⚙️ System Control")
    host = st.text_input("Backend Host", value="localhost")
    port = st.number_input("Signaling Port", value=9001)
    
    st.divider()
    
    # Fetch dynamic cameras from Redis
    try:
        cam_resp = requests.get(f"http://{host}:{port}/api/cameras/")
        if cam_resp.status_code == 200:
            available_cameras = cam_resp.json()
            cam_list = list(available_cameras.keys()) if available_cameras else ["cam01"]
        else:
            cam_list = ["cam01"]
    except:
        cam_list = ["cam01"]
        
    st.session_state.camera_id = st.selectbox("Select Camera", cam_list)

# --- Main Dashboard ---
st.title("🛡️ Pipeline OpenCV Command Center")

tabs = st.tabs(["📊 Live Monitor", "🎮 Camera Config", "📜 Event History", "🏥 System Health", "🖥️ System Logs"])

# ─── TAB 1: Live Monitor ──────────────────────────────────────────────────────
with tabs[0]:
    col_v, col_d = st.columns([2, 1])
    
    with col_v:
        st.subheader(f"🎥 Visual Feed: {st.session_state.camera_id}")
        if st.session_state.latest_action and st.session_state.latest_action.get("label") == "shoplifting":
            st.error(f"‼️ ALERT: Shoplifting Detected ({st.session_state.latest_action.get('confidence', 0):.2f})")
            
        placeholder_img = st.empty()
        enable_stream = st.toggle("Enable WebSocket Stream", value=True)
        
        async def run_visualizer():
            video_uri = f"ws://{host}:{port}/ws/camera/{st.session_state.camera_id}"
            pred_uri = f"ws://{host}:{port}/ws/predictions"
            
            try:
                # Use a single connection for predictions to avoid multiple listeners
                async with websockets.connect(video_uri) as video_ws, \
                           websockets.connect(pred_uri) as pred_ws:
                           
                    video_task = asyncio.create_task(video_ws.recv())
                    pred_task = asyncio.create_task(pred_ws.recv())
                    
                    while True:
                        done, _ = await asyncio.wait(
                            [video_task, pred_task],
                            return_when=asyncio.FIRST_COMPLETED,
                            timeout=0.1
                        )
                        
                        for task in done:
                            try:
                                msg = await task
                                if task == video_task:
                                    if isinstance(msg, bytes):
                                        processed_img = draw_boxes(
                                            msg, 
                                            st.session_state.latest_detections,
                                            st.session_state.latest_action
                                        )
                                        if processed_img is not None:
                                            placeholder_img.image(processed_img, width="stretch")
                                        else:
                                            placeholder_img.image(msg, width="stretch")
                                    video_task = asyncio.create_task(video_ws.recv())
                                elif task == pred_task:
                                    if msg:
                                        data = json.loads(msg)
                                        if data.get("camera_id") == st.session_state.camera_id:
                                            st.session_state.latest_detections = data.get("detections", [])
                                            st.session_state.latest_action = data.get("action")
                                    pred_task = asyncio.create_task(pred_ws.recv())
                            except Exception as e:
                                log.error(f"Error in task processing: {e}")
                                # Recreate tasks on error
                                if task == video_task:
                                    video_task = asyncio.create_task(video_ws.recv())
                                elif task == pred_task:
                                    pred_task = asyncio.create_task(pred_ws.recv())
            except Exception as e:
                st.error(f"Stream error: {e}")

    with col_d:
        st.subheader("📡 Active Detections")
        st.dataframe(pd.DataFrame(st.session_state.latest_detections), use_container_width=True)
        
        if st.session_state.latest_action:
            st.write("Current Action Status:")
            st.json(st.session_state.latest_action)

    if enable_stream:
        # Consolidation wrapper for multiple tabs
        try:
            asyncio.run(run_visualizer())
        except Exception:
            pass

# ─── TAB 2: Camera Config ─────────────────────────────────────────────────────
with tabs[1]:
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader(f"⚙️ Tuning: {st.session_state.camera_id}")
        try:
            cfg_resp = requests.get(f"http://{host}:{port}/api/config/{st.session_state.camera_id}")
            if cfg_resp.status_code == 200:
                c = cfg_resp.json()
                with st.form("config_form"):
                    enabled = st.checkbox("Service Enabled", value=c.get("enabled", True))
                    conf = st.slider("Confidence Threshold", 0.1, 1.0, float(c.get("confidence_threshold", 0.5)))
                    iou = st.slider("IOU Match Threshold", 0.1, 1.0, float(c.get("iou_threshold", 0.5)))
                    dist = st.number_input("Hand distance (px)", value=int(c.get("hand_dist_px", 80)))
                    
                    if st.form_submit_button("Save Changes"):
                        payload = {
                            "enabled": enabled,
                            "confidence_threshold": conf,
                            "iou_threshold": iou,
                            "hand_dist_px": dist,
                            "roi": c.get("roi")
                        }
                        requests.put(f"http://{host}:{port}/api/config/{st.session_state.camera_id}", json=payload)
                        st.success("Config updated!")
            else:
                st.warning("No config found for this camera.")
        except Exception as e:
            st.error(f"Error connecting to API: {e}")

    with col2:
        st.subheader("➕ Add New Camera")
        with st.form("add_cam_form"):
            new_id = st.text_input("Camera ID", value="cam02")
            new_src = st.text_input("Source (index or RTSP)", value="0")
            if st.form_submit_button("Provision Camera"):
                resp = requests.post(f"http://{host}:{port}/api/cameras/", json={"id": new_id, "source": new_src})
                if resp.status_code == 200:
                    st.success(f"Camera {new_id} added! MediaBridge will auto-discover.")
                    st.rerun()
                else:
                    st.error("Failed to add camera")

# ─── TAB 3: Event History ──────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("📜 Detection Audit Log")
    if st.button("Refresh History"):
        try:
            hist_resp = requests.get(f"http://{host}:{port}/api/events?limit=100")
            if hist_resp.status_code == 200:
                events = hist_resp.json()
                if events:
                    st.table(pd.DataFrame(events))
                else:
                    st.info("No events found in database.")
        except:
             st.error("Connection failed")

# ─── TAB 4: System Health ──────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("🏥 Service Heartbeats")
    if st.button("Check Vital Signs"):
        try:
            health_resp = requests.get(f"http://{host}:{port}/api/health")
            if health_resp.status_code == 200:
                st.json(health_resp.json())
        except:
             st.error("Connection failed")

# ─── TAB 5: System Logs ────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("🚦 Real-time System Logs")
    log_placeholder = st.empty()
    if 'sys_logs' not in st.session_state:
        st.session_state.sys_logs = []

    async def watch_logs():
        uri = f"ws://{host}:{port}/ws/logs"
        try:
            async with websockets.connect(uri) as ws:
                while True:
                    msg = await ws.recv()
                    st.session_state.sys_logs.append(msg)
                    if len(st.session_state.sys_logs) > 50:
                        st.session_state.sys_logs.pop(0)
                    
                    with log_placeholder.container():
                        for l in reversed(st.session_state.sys_logs):
                            try:
                                j = json.loads(l)
                                color = "red" if j.get("level") == "ERROR" else "green" if j.get("level") == "INFO" else "white"
                                st.markdown(f"**{j.get('ts')}** | :{color}[{j.get('level')}] | **{j.get('logger')}** | {j.get('msg')}")
                            except:
                                st.text(l)
        except:
            pass

    if st.toggle("Start Log Stream", value=True):
        asyncio.run(watch_logs())

st.divider()
st.caption("Pipeline OpenCV | Unified Interface v0.5.0")
