import subprocess
import threading
import time
import cv2
from PIL import Image
from source_base import ImageSource


def list_webcams() -> list[tuple[int, str]]:
    """
    Returns a list of (index, name) for all available webcams.
    Name is resolved via PowerShell on Windows; falls back to 'Camera <index>'.
    """
    names = _get_camera_names_windows()
    cameras = []
    idx = 0
    while True:
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            break
        name = names[idx] if idx < len(names) else f"Camera {idx}"
        cameras.append((idx, name))
        cap.release()
        idx += 1
        if idx > 9:
            break
    return cameras


def _get_camera_names_windows() -> list[str]:
    """Query PnP camera device names via PowerShell."""
    try:
        cmd = [
            "powershell", "-NoProfile", "-Command",
            "Get-PnpDevice -Class Camera -Status OK | "
            "Sort-Object InstanceId | "
            "Select-Object -ExpandProperty FriendlyName"
        ]
        out = subprocess.check_output(cmd, timeout=5, stderr=subprocess.DEVNULL, text=True)
        return [line.strip() for line in out.strip().splitlines() if line.strip()]
    except Exception:
        return []


def _resolve_webcam_index(webcam_id: str) -> int:
    """
    Resolve a WEBCAM_ID string to an OpenCV camera index.
    - If it's a plain integer string (e.g. "0"), use it directly.
    - Otherwise, treat it as a device name substring and search for a match.
    """
    if webcam_id.lstrip("-").isdigit():
        return int(webcam_id)

    # Name-based lookup
    names = _get_camera_names_windows()
    needle = webcam_id.lower()
    for i, name in enumerate(names):
        if needle in name.lower():
            print(f"Matched webcam name '{name}' at index {i}")
            return i

    # Brute-force: try indices until we find one that opens
    print(f"No exact name match for '{webcam_id}', scanning available cameras...")
    cameras = list_webcams()
    if cameras:
        for i, name in cameras:
            print(f"  [{i}] {name}")
        print(f"Defaulting to index 0. Set WEBCAM_ID=<index> to choose a specific camera.")
        return 0

    raise RuntimeError(f"No webcam found matching '{webcam_id}'")


class WebcamSource(ImageSource):
    """Captures frames from a local USB/built-in webcam via OpenCV."""

    def __init__(self, webcam_id: str = "0"):
        self.webcam_id = webcam_id
        self._index: int = 0
        self._cap: cv2.VideoCapture | None = None
        self._latest_frame = None
        self._frame_lock = threading.Lock()
        self._capture_thread: threading.Thread | None = None
        self._stop_capture = False

    def connect(self):
        self._index = _resolve_webcam_index(self.webcam_id)
        print(f"Opening webcam index {self._index} (id='{self.webcam_id}')...")
        self._cap = cv2.VideoCapture(self._index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            raise RuntimeError(f"Failed to open webcam at index {self._index}")

        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Warm up
        for _ in range(5):
            self._cap.grab()

        self._stop_capture = False
        self._capture_thread = threading.Thread(target=self._continuous_capture, daemon=True)
        self._capture_thread.start()
        print("Webcam ready.")

    def _continuous_capture(self):
        while not self._stop_capture and self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if ret and frame is not None:
                with self._frame_lock:
                    self._latest_frame = frame
            time.sleep(0.03)  # ~30 FPS

    def get_image(self) -> Image.Image:
        if not self._cap or not self._cap.isOpened():
            raise RuntimeError("Webcam not connected")

        with self._frame_lock:
            frame = self._latest_frame.copy() if self._latest_frame is not None else None

        if frame is None:
            # Fallback: direct read
            ret, frame = self._cap.read()
            if not ret or frame is None:
                raise RuntimeError("Failed to capture frame from webcam")

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(frame_rgb)

    def disconnect(self):
        self._stop_capture = True
        if self._capture_thread:
            self._capture_thread.join(timeout=2)
        if self._cap:
            self._cap.release()
            self._cap = None
        with self._frame_lock:
            self._latest_frame = None
        print("Webcam disconnected.")
