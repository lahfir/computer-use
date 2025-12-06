"""
OCR factory for selecting optimal OCR engine based on platform.
"""

import platform
from typing import Optional, List
from ...schemas.ocr_result import GPUInfo
from .ocr_protocol import OCREngine


def get_all_available_ocr_engines(use_gpu: Optional[bool] = None) -> List[OCREngine]:
    """
    Get all available OCR engines in priority order for fallback.

    Args:
        use_gpu: Whether to use GPU. If None, auto-detect.

    Returns:
        List of available OCR engines (Vision -> Paddle -> EasyOCR)
    """
    engines = []
    system = platform.system().lower()

    if system == "darwin":
        try:
            from .macos_vision_ocr import MacOSVisionOCR

            engine = MacOSVisionOCR()
            if engine.is_available():
                engines.append(engine)
        except Exception:
            pass

    try:
        from .paddleocr_engine import PaddleOCREngine

        engine = PaddleOCREngine(use_gpu=use_gpu)
        if engine.is_available():
            engines.append(engine)
    except Exception:
        pass

    try:
        from .easyocr_engine import EasyOCREngine

        engine = EasyOCREngine()
        if engine.is_available():
            engines.append(engine)
    except Exception:
        pass

    return engines


def create_ocr_engine(use_gpu: Optional[bool] = None) -> Optional[OCREngine]:
    """
    Create optimal OCR engine for current platform.

    Args:
        use_gpu: Whether to use GPU. If None, auto-detect.

    Returns:
        OCR engine instance with recognize_text method
    """
    from ...utils.ui import console, THEME, dashboard, VerbosityLevel

    system = platform.system().lower()

    if system == "darwin":
        from .macos_vision_ocr import MacOSVisionOCR

        engine = MacOSVisionOCR()
        if engine.is_available():
            if dashboard.verbosity == VerbosityLevel.VERBOSE:
                console.print(
                    f"[{THEME['success']}]Using Apple Vision Framework OCR[/]"
                )
            return engine

    from .paddleocr_engine import PaddleOCREngine

    engine = PaddleOCREngine(use_gpu=use_gpu)
    if engine.is_available():
        if dashboard.verbosity == VerbosityLevel.VERBOSE:
            gpu_status = "GPU" if engine.use_gpu else "CPU"
            console.print(f"[{THEME['success']}]Using PaddleOCR ({gpu_status})[/]")
        return engine

    from .easyocr_engine import EasyOCREngine

    engine = EasyOCREngine()
    if engine.is_available():
        if dashboard.verbosity == VerbosityLevel.VERBOSE:
            console.print(f"[{THEME['success']}]Using EasyOCR (fallback)[/]")
        return engine

    return None


def detect_gpu_availability() -> GPUInfo:
    """
    Detect GPU availability and type.

    Returns:
        GPUInfo object with GPU information
    """
    system = platform.system().lower()

    if system == "darwin":
        try:
            import subprocess

            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if "Apple" in result.stdout:
                return GPUInfo(
                    available=True,
                    type="Apple Silicon (Metal/MPS)",
                    device_count=1,
                )
        except Exception:
            pass
    else:
        try:
            import paddle

            if paddle.device.is_compiled_with_cuda():
                gpu_count = paddle.device.cuda.device_count()
                if gpu_count > 0:
                    return GPUInfo(
                        available=True,
                        type="CUDA",
                        device_count=gpu_count,
                    )
        except (ImportError, Exception):
            pass

    return GPUInfo(available=False, type=None, device_count=0)
