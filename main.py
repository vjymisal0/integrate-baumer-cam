import os
import io
import time
import threading
import requests
from dotenv import load_dotenv

load_dotenv()

# --- API ---
API_URL        = os.getenv("API_URL")
API_KEY        = os.getenv("API_KEY")
WORKSPACE_ID   = os.getenv("WORKSPACE_ID")

# --- Form fields ---
IMAGE_FIELD_NAME = os.getenv("IMAGE_FIELD_NAME", "image_file")
PRODUCT_NAME     = os.getenv("PRODUCT_NAME")
SESSION_NAME     = os.getenv("SESSION_NAME")
ARTICLE_NAME     = os.getenv("ARTICLE_NAME")
NEXT_ARTICLE     = os.getenv("NEXT_ARTICLE", "false")

# --- Image source ---
IMAGES_SAVE_PATH = os.getenv("IMAGES_SAVE_PATH", "./images")
SOURCE_TYPE      = os.getenv("SOURCE_TYPE", "baumer").lower()  # baumer | rtsp | webcam
RTSP_URL         = os.getenv("RTSP_URL")
WEBCAM_ID        = os.getenv("WEBCAM_ID", "0")  # integer index or device name substring

# --- Modbus ---
MODBUS_TRIGGER        = os.getenv("MODBUS_TRIGGER", "false").lower() == "true"
MODBUS_HOST           = os.getenv("MODBUS_HOST", "192.168.7.120")
MODBUS_PORT           = int(os.getenv("MODBUS_PORT", "502"))
MODBUS_ADDRESS        = int(os.getenv("MODBUS_ADDRESS", "0"))
MODBUS_UNIT           = int(os.getenv("MODBUS_UNIT", "1"))
MODBUS_USE_COIL       = os.getenv("MODBUS_USE_COIL", "false").lower() == "true"
MODBUS_POLL_INTERVAL  = float(os.getenv("MODBUS_POLL_INTERVAL", "0.1"))
MODBUS_OUTPUT_ADDRESS = int(os.getenv("MODBUS_OUTPUT_ADDRESS", "0"))

# Inspection result → output coil index (Y0=NA, Y1=Pass, Y2=Fail)
RESULT_VALUES = {"NA": 0, "Pass": 1, "Fail": 2}


def capture_and_process(source, modbus_btn=None):
    try:
        print("Capturing image...")
        pil_img = source.get_image()

        if pil_img is None:
            print("Captured image is empty.")
            return

        buffer = io.BytesIO()
        pil_img.save(buffer, format="WEBP", quality=100, lossless=True)
        image_data = buffer.getvalue()

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename  = f"capture_{timestamp}.webp"

        os.makedirs(IMAGES_SAVE_PATH, exist_ok=True)
        local_path = os.path.join(IMAGES_SAVE_PATH, filename)
        with open(local_path, "wb") as f:
            f.write(image_data)
        print(f"Saved: {local_path}")

        if not API_URL:
            print("No API_URL configured, skipping upload.")
            return

        print(f"Uploading to API...")
        headers = {"x-api-key": API_KEY, "x-workspace-id": WORKSPACE_ID}
        data    = {
            "product_name": PRODUCT_NAME,
            "session_name": SESSION_NAME,
            "article_name": ARTICLE_NAME,
            "next_article": NEXT_ARTICLE,
        }
        files = {IMAGE_FIELD_NAME: (filename, image_data, "image/webp")}

        try:
            response = requests.post(API_URL, headers=headers, data=data, files=files, timeout=30)
            print(f"API Response: {response.status_code}")

            if response.status_code >= 400:
                print(f"Error: {response.text}")
                return

            body           = response.json()
            overall_result = body.get("overall_result", "NA")
            modbus_value   = RESULT_VALUES.get(overall_result, 0)
            print(f"Result: {overall_result}")

            if modbus_btn:
                modbus_btn.write_result(MODBUS_OUTPUT_ADDRESS, modbus_value)

        except Exception as e:
            print(f"API upload failed: {e}")

    except Exception as e:
        print(f"Capture error: {e}")


def _build_source():
    if SOURCE_TYPE == "rtsp":
        if not RTSP_URL:
            raise ValueError("RTSP_URL must be set when SOURCE_TYPE=rtsp")
        from source_rtsp import RTSPSource
        return RTSPSource(RTSP_URL)
    if SOURCE_TYPE == "webcam":
        from source_webcam import WebcamSource
        return WebcamSource(WEBCAM_ID)
    from source_baumer import BaumerSource
    return BaumerSource()


def main():
    source     = None
    modbus_btn = None

    try:
        source = _build_source()
        source.connect()
        print(f"\nSource: {SOURCE_TYPE.upper()}")

        if MODBUS_TRIGGER:
            from modbus_button import ModbusButton

            capture_lock = threading.Lock()

            def on_button_press():
                with capture_lock:
                    print("\n[Modbus] Button pressed — capturing...")
                    t = time.time()
                    capture_and_process(source, modbus_btn)
                    print(f"Cycle time: {time.time() - t:.2f}s")
                    print("Press button or type 'c' to capture, 'x' to exit: ", end="", flush=True)

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
            print(f"Modbus trigger active — {MODBUS_HOST}:{MODBUS_PORT} input #{MODBUS_ADDRESS}")
            print("Press button or type 'c' to capture, 'x' to exit: ", end="", flush=True)

            while True:
                cmd = input().strip().lower()
                if cmd == "x":
                    break
                elif cmd == "c":
                    t = time.time()
                    capture_and_process(source, modbus_btn)
                    print(f"Cycle time: {time.time() - t:.2f}s")
                elif cmd:
                    print("Press button or type 'c' to capture, 'x' to exit: ", end="", flush=True)

        else:
            print("Ready. Type 'c' to capture, 'x' to exit.")
            while True:
                cmd = input("> ").strip().lower()
                if cmd == "x":
                    break
                elif cmd == "c":
                    t = time.time()
                    capture_and_process(source, modbus_btn)
                    print(f"Cycle time: {time.time() - t:.2f}s")
                elif cmd:
                    print(f"Unknown command: '{cmd}'")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if modbus_btn:
            modbus_btn.stop()
        if source:
            source.disconnect()


if __name__ == "__main__":
    main()
