"""
macOS Vision Framework OCR implementation.
Ultra-fast native OCR using Apple's Vision framework.
"""

from typing import List, Optional, Tuple
from PIL import Image
from ...schemas.ocr_result import OCRResult


class MacOSVisionOCR:
    """
    Native macOS OCR using Vision framework.
    Extremely fast, leverages Neural Engine on Apple Silicon.
    """

    def __init__(self):
        """
        Initialize macOS Vision OCR.
        """
        self.vision_available = False
        self._initialize_vision()

    def _initialize_vision(self):
        """
        Initialize Apple Vision framework.
        """
        try:
            import Vision
            import Quartz
            from Foundation import NSData, NSURL

            self.Vision = Vision
            self.Quartz = Quartz
            self.NSData = NSData
            self.NSURL = NSURL
            self.vision_available = True
        except ImportError:
            self.vision_available = False

    def is_available(self) -> bool:
        """
        Check if Vision framework is available.

        Returns:
            True if Vision framework is available
        """
        return self.vision_available

    def recognize_text(
        self,
        image: Image.Image,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> List[OCRResult]:
        """
        Recognize text in image using Vision framework.

        Args:
            image: PIL Image to process
            region: Optional region to crop (x, y, width, height)

        Returns:
            List of OCRResult objects with text, bounding boxes, and confidence
        """
        if not self.vision_available:
            return []

        if region:
            x, y, w, h = region
            image = image.crop((x, y, x + w, y + h))
            offset_x, offset_y = x, y
        else:
            offset_x, offset_y = 0, 0

        try:
            if image.mode != "RGB":
                image = image.convert("RGB")

            img_width, img_height = image.size
            img_bytes = image.tobytes()

            cg_image = self._create_cgimage(image, img_bytes, img_width, img_height)
            if not cg_image:
                return []

            request = self.Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(
                self.Vision.VNRequestTextRecognitionLevelAccurate
            )
            request.setUsesLanguageCorrection_(True)
            request.setAutomaticallyDetectsLanguage_(True)

            handler = (
                self.Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
                    cg_image, None
                )
            )

            error = None
            success, err = handler.performRequests_error_([request], error)
            if not success or err:
                return []

            results = []
            observations = request.results()

            if not observations:
                return []

            for observation in observations:
                text = str(observation.text())
                confidence = float(observation.confidence())

                bounding_box = observation.boundingBox()
                x_norm = float(bounding_box.origin.x)
                y_norm = float(bounding_box.origin.y)
                width_norm = float(bounding_box.size.width)
                height_norm = float(bounding_box.size.height)

                y_norm = 1.0 - y_norm - height_norm

                x = int(x_norm * img_width) + offset_x
                y = int(y_norm * img_height) + offset_y
                width = int(width_norm * img_width)
                height = int(height_norm * img_height)

                center_x = x + width // 2
                center_y = y + height // 2

                results.append(
                    OCRResult(
                        text=text,
                        bounds=(x, y, width, height),
                        center=(center_x, center_y),
                        confidence=confidence,
                    )
                )

            return results

        except Exception:
            return []

    def _create_cgimage(
        self, image: Image.Image, img_bytes: bytes, width: int, height: int
    ):
        """
        Create CGImage from PIL Image.

        Args:
            image: PIL Image
            img_bytes: Image bytes
            width: Image width
            height: Image height

        Returns:
            CGImage object or None
        """
        try:
            data_provider = self.Quartz.CGDataProviderCreateWithData(
                None, img_bytes, len(img_bytes), None
            )

            color_space = self.Quartz.CGColorSpaceCreateDeviceRGB()

            cg_image = self.Quartz.CGImageCreate(
                width,
                height,
                8,
                24,
                width * 3,
                color_space,
                self.Quartz.kCGBitmapByteOrderDefault,
                data_provider,
                None,
                False,
                self.Quartz.kCGRenderingIntentDefault,
            )

            return cg_image

        except Exception:
            return None
