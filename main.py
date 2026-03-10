import os
import io
import time
import threading
import requests
from PIL import Image
from dotenv import load_dotenv

# Import our modular sources
from source_rtsp import RTSPSource

# Load environment variables
load_dotenv()

# API and Auth
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
WORKSPACE_ID = os.getenv("WORKSPACE_ID")

# Form Fields
IMAGE_FIELD_NAME = os.getenv("IMAGE_FIELD_NAME", "image_file")
PRODUCT_NAME = os.getenv("PRODUCT_NAME")
SESSION_NAME = os.getenv("SESSION_NAME")
ARTICLE_NAME = os.getenv("ARTICLE_NAME")
NEXT_ARTICLE = os.getenv("NEXT_ARTICLE", "false")

# App Config
IMAGES_SAVE_PATH = os.getenv("IMAGES_SAVE_PATH", "./images")
SOURCE_TYPE = os.getenv("SOURCE_TYPE", "baumer").lower()  # 'baumer', 'rtsp', or 'webcam'
RTSP_URL = os.getenv("RTSP_URL")
WEBCAM_ID = os.getenv("WEBCAM_ID", "0")  # Index (0,1,2) or device name substring

# Modbus Button Config
MODBUS_TRIGGER = os.getenv("MODBUS_TRIGGER", "false").lower() == "true"
MODBUS_HOST = os.getenv("MODBUS_HOST", "192.168.7.120")
MODBUS_PORT = int(os.getenv("MODBUS_PORT", "502"))
MODBUS_ADDRESS = int(os.getenv("MODBUS_ADDRESS", "0"))
MODBUS_UNIT = int(os.getenv("MODBUS_UNIT", "1"))
MODBUS_USE_COIL = os.getenv("MODBUS_USE_COIL", "true").lower() == "true"
MODBUS_POLL_INTERVAL = float(os.getenv("MODBUS_POLL_INTERVAL", "0.1"))

def capture_and_process(source):
    try:
        print("Capturing image...")
        pil_img = source.get_image()
        
        if pil_img is None:
            print("Captured image is empty.")
            return

        # Prepare WebP data (High quality lossless)
        buffer = io.BytesIO()
        pil_img.save(buffer, format="WEBP", quality=100, lossless=True)
        image_data = buffer.getvalue()

        # Generate filename
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"capture_{timestamp}.webp"
        
        # Local Save
        os.makedirs(IMAGES_SAVE_PATH, exist_ok=True)
        local_path = os.path.join(IMAGES_SAVE_PATH, filename)
        with open(local_path, "wb") as f:
            f.write(image_data)
        print(f"Image saved locally: {local_path}")

        # API Upload
        if API_URL:
            print(f"Uploading to {API_URL}...")
            
            # Headers
            headers = {
                "x-api-key": API_KEY,
                "x-workspace-id": WORKSPACE_ID
            }
            
            # Form Data
            data = {
                "product_name": PRODUCT_NAME,
                "session_name": SESSION_NAME,
                "article_name": ARTICLE_NAME,
                "next_article": NEXT_ARTICLE
            }
            
            # Files
            files = {IMAGE_FIELD_NAME: (filename, image_data, "image/webp")}
            
            try:
                response = requests.post(
                    API_URL, 
                    headers=headers, 
                    data=data, 
                    files=files, 
                    timeout=30
                )
                print(f"API Response: {response.status_code}")
                if response.status_code >= 400:
                    print(f"Error Details: {response.text}")
                else:
                    # Optional: print some success info if the API returns JSON
                    try:
                        print(f"Success: {response.json()}")
                    except:
                        pass
            except Exception as e:
                print(f"API Upload failed: {e}")
        else:
            print("No API_URL, skipping upload.")

    except Exception as e:
        print(f"Processing error: {e}")

def main():
    source = None
    modbus_btn = None
    try:
        if SOURCE_TYPE == "rtsp":
            if not RTSP_URL:
                print("Error: RTSP_URL must be set when SOURCE_TYPE is 'rtsp'")
                return
            source = RTSPSource(RTSP_URL)
        elif SOURCE_TYPE == "webcam":
            from source_webcam import WebcamSource
            source = WebcamSource(WEBCAM_ID)
        else:
            from source_baumer import BaumerSource
            source = BaumerSource()

        source.connect()

        print(f"\nSource initialized: {SOURCE_TYPE.upper()}")

        # --- Modbus button trigger ---
        if MODBUS_TRIGGER:
            from modbus_button import ModbusButton

            capture_lock = threading.Lock()

            def on_button_press():
                with capture_lock:
                    print("\n[Modbus] Button pressed — capturing...")
                    start = time.time()
                    capture_and_process(source)
                    print(f"Cycle time: {time.time() - start:.2f}s")
                    print("Enter 'x' to exit: ", end="", flush=True)

            modbus_btn = ModbusButton(
                host=MODBUS_HOST,
                port=MODBUS_PORT,
                address=MODBUS_ADDRESS,
                unit=MODBUS_UNIT,
                use_coil=MODBUS_USE_COIL,
                poll_interval=MODBUS_POLL_INTERVAL,
            )
            modbus_btn.on_press = on_button_press
            modbus_btn.connect()
            modbus_btn.start()
            print(f"Modbus trigger active — waiting for button at {MODBUS_HOST}:{MODBUS_PORT} address #{MODBUS_ADDRESS}")
            print("Enter 'x' to exit: ", end="", flush=True)

            while True:
                cmd = input().strip().lower()
                if cmd == 'x':
                    break
                elif cmd == 'c':
                    on_button_press()
                else:
                    print("Enter 'x' to exit (or press the hardware button): ", end="", flush=True)
        # --- Manual keyboard trigger ---
        else:
            print("Ready.")
            while True:
                cmd = input("Enter 'c' to capture, 'x' to exit: ").strip().lower()
                if cmd == 'c':
                    capture_process_start = time.time()
                    capture_and_process(source)
                    print(f"Cycle time: {time.time() - capture_process_start:.2f}s")
                elif cmd == 'x':
                    break
                elif cmd == '':
                    continue
                else:
                    print(f"Unknown command: '{cmd}'")

    except Exception as e:
        print(f"Main Loop Error: {e}")
    finally:
        if modbus_btn:
            modbus_btn.stop()
        if source:
            source.disconnect()

if __name__ == "__main__":
    main()
