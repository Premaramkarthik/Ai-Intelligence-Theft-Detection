import redis
import json
import time
import os
import paho.mqtt.client as mqtt
from datetime import datetime

# Load settings — adjust if Docker ports are mapped differently
REDIS_HOST = "localhost"
REDIS_PORT = 6379 
REDIS_PASS = "karthikS9"

MQTT_HOST = "localhost"
MQTT_PORT = 1883

def get_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASS, decode_responses=True)

def on_message(client, userdata, message):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n🔔 [{ts}] MQTT Alert Topic: {message.topic}")
    try:
        data = json.loads(message.payload.decode())
        print(json.dumps(data, indent=2))
    except:
        print(f"Payload: {message.payload.decode()}")

def run_dashboard():
    r = get_redis()
    
    # MQTT Setup (using modern API to avoid DeprecationWarning)
    # CallbackAPIVersion.VERSION2 for newer paho-mqtt
    try:
        from paho.mqtt.enums import CallbackAPIVersion
        client = mqtt.Client(CallbackAPIVersion.VERSION2)
    except ImportError:
        client = mqtt.Client() # Fallback for older versions

    client.on_message = on_message
    
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.subscribe("alerts/#")
        client.loop_start()
        
        print(f"� Data Inspector Started (Redis: {REDIS_PORT}, MQTT: {MQTT_PORT})")
        print("Press Ctrl+C to exit.\n")

        last_frames_count = 0
        
        while True:
            # Clear line / move cursor could be complex, let's keep it simple with scrolling or static updates
            sources = r.hgetall("camera_sources")
            frames_count = r.llen("frames")
            
            # Check for latest frame pointer
            cam01_ptr = r.get("frame_ptr:cam01")
            
            # Simple terminal "UI"
            ts = datetime.now().strftime("%H:%M:%S")
            diff = frames_count - last_frames_count
            trend = "📈" if diff > 0 else "📉" if diff < 0 else "➖"
            
            print(f"\033[H\033[J") # Clear screen
            print(f"--- � Live Data Pipeline Dashboard [{ts}] ---")
            print(f"📸 Active Cameras: {sources}")
            print(f"📍 Latest Pointer (cam01): {cam01_ptr}")
            print(f"🎞️ Frames in Queue: {frames_count} {trend} ({diff:+} last sec)")
            
            if frames_count > 0:
                recent = r.lindex("frames", 0)
                try:
                    meta = json.loads(recent)
                    print(f"� Latest Metadata: Slot={meta.get('slot_id')} Trace={meta.get('trace_id')}")
                except:
                    print(f"🕒 Latest Metadata: {recent}")

            print("\n--- 📡 MQTT Alerts (Listening...) ---")
            print("Note: Alerts only appear here when a detection occurs.")
            
            last_frames_count = frames_count
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    run_dashboard()
