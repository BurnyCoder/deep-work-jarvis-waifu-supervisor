"""Screenshot and webcam capture for productivity monitoring."""

import os
import threading
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import cv2
import mss
from PIL import Image, ImageDraw, ImageFont

from config import CAPTURE_INTERVAL_SECONDS, CAPTURES_BEFORE_ANALYSIS
from state import app_state, Mode


class Monitor:
    def __init__(self, results_dir: str = "results"):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._results_dir = Path(results_dir)
        self._results_dir.mkdir(exist_ok=True)
        self._captures: list[Image.Image] = []
        self._on_analysis_ready: Optional[callable] = None

    def set_on_analysis_ready(self, callback: callable):
        """Set callback for when captures are ready for AI analysis."""
        self._on_analysis_ready = callback

    def start(self):
        """Start the monitoring background thread."""
        if self._running:
            return

        self._running = True
        self._captures = []
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the monitoring background thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None

    def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            if app_state.mode == Mode.ON:
                try:
                    combined = self._capture_all()
                    if combined:
                        self._captures.append(combined)

                        # Save individual capture
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        save_path = self._results_dir / f"capture_{timestamp}.png"
                        combined.save(save_path)

                        # Check if we have enough captures for analysis
                        if len(self._captures) >= CAPTURES_BEFORE_ANALYSIS:
                            if self._on_analysis_ready:
                                # Create a grid of captures for analysis
                                grid = self._create_capture_grid(self._captures)
                                self._on_analysis_ready(grid)
                            self._captures = []

                except Exception as e:
                    print(f"Monitor error: {e}")

            time.sleep(CAPTURE_INTERVAL_SECONDS)

    def _capture_all(self) -> Optional[Image.Image]:
        """Capture all monitors and webcam, combine into single image."""
        images = []
        labels = []

        # Capture all monitors
        with mss.mss() as sct:
            # monitors[0] is all monitors combined, but we want individual
            for i, mon in enumerate(sct.monitors[1:], 1):
                screenshot = sct.grab(mon)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                # Resize to reasonable size to reduce API costs
                img.thumbnail((800, 600), Image.Resampling.LANCZOS)
                images.append(img)
                labels.append(f"Monitor {i}")

        # Capture webcam
        webcam_img = self._capture_webcam()
        if webcam_img:
            webcam_img.thumbnail((400, 300), Image.Resampling.LANCZOS)
            images.append(webcam_img)
            labels.append("Webcam")

        if not images:
            return None

        # Combine images horizontally with labels
        return self._stitch_images(images, labels)

    def _capture_webcam(self) -> Optional[Image.Image]:
        """Capture a single frame from the webcam."""
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return None

            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                return None

            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return Image.fromarray(frame_rgb)

        except Exception as e:
            print(f"Webcam capture error: {e}")
            return None

    def _stitch_images(self, images: list[Image.Image], labels: list[str]) -> Image.Image:
        """Stitch images horizontally with labels."""
        if not images:
            return None

        # Add labels to images
        labeled_images = []
        for img, label in zip(images, labels):
            labeled = self._add_label(img, label)
            labeled_images.append(labeled)

        # Calculate total dimensions
        total_width = sum(img.width for img in labeled_images)
        max_height = max(img.height for img in labeled_images)

        # Create combined image
        combined = Image.new("RGB", (total_width, max_height), color=(30, 30, 30))

        # Paste images
        x_offset = 0
        for img in labeled_images:
            # Center vertically
            y_offset = (max_height - img.height) // 2
            combined.paste(img, (x_offset, y_offset))
            x_offset += img.width

        return combined

    def _add_label(self, img: Image.Image, label: str) -> Image.Image:
        """Add a label to the top of an image."""
        label_height = 30
        new_img = Image.new("RGB", (img.width, img.height + label_height), color=(50, 50, 50))
        new_img.paste(img, (0, label_height))

        draw = ImageDraw.Draw(new_img)
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except OSError:
            font = ImageFont.load_default()

        # Center the label
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        x = (img.width - text_width) // 2
        draw.text((x, 5), label, fill=(255, 255, 255), font=font)

        return new_img

    def _create_capture_grid(self, captures: list[Image.Image]) -> Image.Image:
        """Create a grid image from multiple captures."""
        if not captures:
            return None

        # Resize all to same size
        target_width = 600
        target_height = 400
        resized = []
        for cap in captures:
            resized_cap = cap.copy()
            resized_cap.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
            resized.append(resized_cap)

        # Create grid (e.g., 5 images in a row or 2 rows)
        cols = min(3, len(resized))
        rows = (len(resized) + cols - 1) // cols

        grid_width = cols * target_width
        grid_height = rows * target_height
        grid = Image.new("RGB", (grid_width, grid_height), color=(20, 20, 20))

        for i, img in enumerate(resized):
            row = i // cols
            col = i % cols
            x = col * target_width + (target_width - img.width) // 2
            y = row * target_height + (target_height - img.height) // 2
            grid.paste(img, (x, y))

        # Save grid for debugging
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        grid.save(self._results_dir / f"grid_{timestamp}.png")

        return grid

    def capture_once(self) -> Optional[Image.Image]:
        """Capture once immediately (non-continuous). Returns combined image."""
        return self._capture_all()


# Global monitor instance
monitor = Monitor()
