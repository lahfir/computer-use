"""
OpenCV template matching for visual element detection.
"""

from typing import List
from PIL import Image
import numpy as np
import cv2


class TemplateMatcher:
    """
    Template matching using OpenCV for finding visual elements.
    """

    def find_template(
        self, screenshot: Image.Image, template: Image.Image, threshold: float = 0.8
    ) -> List[dict]:
        """
        Find template matches in screenshot.

        Args:
            screenshot: Main image to search in
            template: Template image to find
            threshold: Match confidence threshold (0.0-1.0)

        Returns:
            List of matches with coordinates
        """
        screen_gray = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
        template_gray = cv2.cvtColor(np.array(template), cv2.COLOR_RGB2GRAY)

        result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)

        locations = np.where(result >= threshold)
        matches = []

        template_h, template_w = template_gray.shape

        for pt in zip(*locations[::-1]):
            x, y = pt
            center_x = x + template_w // 2
            center_y = y + template_h // 2

            confidence = float(result[y, x])

            matches.append(
                {
                    "bounds": (x, y, template_w, template_h),
                    "center": (center_x, center_y),
                    "confidence": confidence,
                    "detection_method": "cv",
                }
            )

        matches = self._remove_overlapping(matches)

        return matches

    def _remove_overlapping(self, matches: List[dict]) -> List[dict]:
        """
        Remove overlapping matches, keeping highest confidence.

        Args:
            matches: List of match dictionaries

        Returns:
            Filtered list without overlaps
        """
        if not matches:
            return []

        matches_sorted = sorted(matches, key=lambda m: m["confidence"], reverse=True)

        filtered = []

        for match in matches_sorted:
            x1, y1, w1, h1 = match["bounds"]

            is_overlapping = False
            for existing in filtered:
                x2, y2, w2, h2 = existing["bounds"]

                if self._boxes_overlap(x1, y1, w1, h1, x2, y2, w2, h2):
                    is_overlapping = True
                    break

            if not is_overlapping:
                filtered.append(match)

        return filtered

    def _boxes_overlap(
        self, x1: int, y1: int, w1: int, h1: int, x2: int, y2: int, w2: int, h2: int
    ) -> bool:
        """
        Check if two bounding boxes overlap.
        """
        return not (x1 + w1 < x2 or x2 + w2 < x1 or y1 + h1 < y2 or y2 + h2 < y1)

    def find_by_color(
        self, screenshot: Image.Image, color_range: tuple, min_area: int = 100
    ) -> List[dict]:
        """
        Find elements by color range.

        Args:
            screenshot: Image to search
            color_range: ((lower_h, lower_s, lower_v), (upper_h, upper_s, upper_v))
            min_area: Minimum area for detected elements

        Returns:
            List of detected elements
        """
        img_hsv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2HSV)

        lower, upper = color_range
        mask = cv2.inRange(img_hsv, np.array(lower), np.array(upper))

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        elements = []

        for contour in contours:
            area = cv2.contourArea(contour)

            if area >= min_area:
                x, y, w, h = cv2.boundingRect(contour)
                center_x = x + w // 2
                center_y = y + h // 2

                elements.append(
                    {
                        "bounds": (x, y, w, h),
                        "center": (center_x, center_y),
                        "confidence": min(1.0, area / (w * h)),
                        "detection_method": "cv",
                        "area": int(area),
                    }
                )

        return elements
