import json
import os
import neoapi
import numpy as np
from PIL import Image
from source_base import ImageSource

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Megapixel to resolution mapping (width x height)
MEGA_PIXEL_RESOLUTIONS = {
    1: (1280, 800),
    2: (1920, 1080),
    3: (2048, 1536),
    5: (2592, 1944),
    6: (2976, 2000),
    8: (3840, 2160),
    12: (4000, 3000),
    20: (5472, 3648),
}


def load_config():
    """Load Baumer camera configuration from config.json."""
    with open(CONFIG_PATH, "r") as f:
        return json.load(f).get("baumer", {})


class BaumerSource(ImageSource):
    def __init__(self):
        self.camera = None
        self.config = load_config()

    def connect(self):
        print("Connecting to Baumer camera...")

        infolist = neoapi.CamInfoList.Get()  # Get the info list
        infolist.Refresh()  # Refresh the list to reflect the current status
        model = ""
        for info in infolist:
            model = info.GetModelName()
            print(
                info.GetModelName(), info.IsConnectable(), sep=" :: "
            )  # print a list of all connected cameras with its connection status

        self.camera = neoapi.Cam()
        self.camera.Connect(model)

        print("Camera connected?  ", self.camera.IsConnected())

        if self.camera.IsConnected():
            self._apply_config()

        # Read model and serial (your SDK returns them as simple attributes)
        try:
            model = self.camera.f.DeviceModelName.GetCurrent()
            serial = self.camera.f.DeviceSerialNumber.GetCurrent()
        except:
            model = "UnknownModel"
            serial = "UnknownSerial"

        print(f"Connected to: {model} ({serial})")

    def _apply_config(self):
        """Apply settings from config.json to the connected camera."""
        img_fmt = self.config.get("image_format", {})
        brightness = self.config.get("brightness", {})

        # Override resolution if mega_pixels is set in config.json
        mega_pixels = self.config.get("mega_pixels")
        if mega_pixels:
            mp = int(mega_pixels)
            if mp in MEGA_PIXEL_RESOLUTIONS:
                width, height = MEGA_PIXEL_RESOLUTIONS[mp]
                img_fmt["width"] = width
                img_fmt["height"] = height
                print(f"Resolution set to {width}x{height} ({mp} MP)")
            else:
                available = sorted(MEGA_PIXEL_RESOLUTIONS.keys())
                print(f"Warning: {mp} MP not supported. Available: {available}")

        try:
            # Image format / ROI
            if "width" in img_fmt:
                self.camera.f.Width.Set(img_fmt["width"])
            if "height" in img_fmt:
                self.camera.f.Height.Set(img_fmt["height"])
            if "x_offset" in img_fmt:
                self.camera.f.OffsetX.Set(img_fmt["x_offset"])
            if "y_offset" in img_fmt:
                self.camera.f.OffsetY.Set(img_fmt["y_offset"])

            # Brightness / Exposure
            if "exposure_time" in brightness:
                self.camera.f.ExposureTime.Set(brightness["exposure_time"])
            if "gain" in brightness:
                self.camera.f.Gain.Set(brightness["gain"])
            if "target_brightness" in brightness:
                self.camera.f.TargetBrightness.Set(brightness["target_brightness"])

            print("Config applied from config.json")
        except Exception as e:
            print(f"Warning: Could not apply some config settings: {e}")

    def get_image(self) -> Image.Image:
        if not self.camera or not self.camera.IsConnected():
            raise Exception("Baumer camera not connected")

        # Start acquisition (same flow as your working script)
        self.camera.f.AcquisitionStart.Execute()

        img = self.camera.GetImage()  # 1s timeout

        self.camera.f.AcquisitionStop.Execute()

        if img.IsEmpty():
            return None

        # Convert to RGB8 so Pillow always works
        rgb_img = img.Convert("RGB8")

        img_array = rgb_img.GetNPArray()

        # Pillow image
        return Image.fromarray(img_array, mode="RGB")

    def disconnect(self):
        if self.camera and self.camera.IsConnected():
            print("Disconnecting Baumer camera...")
            self.camera.Disconnect()
