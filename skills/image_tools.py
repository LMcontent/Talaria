# -*- coding: utf-8 -*-
"""Image metadata, conversion, preprocessing and OCR."""
import os, shutil
from talaria.providers.base import ToolSpec
try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except Exception:
    Image = ImageEnhance = ImageFilter = ImageOps = None
try:
    import pytesseract
except Exception:
    pytesseract = None
_WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workspace"))
_CANDIDATES = [r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"]

def _path(p):
    p = str(p or "").strip()
    return p if os.path.isabs(p) else os.path.join(_WORKSPACE, p)
def _tess():
    p = shutil.which("tesseract")
    if p: return p
    return next((x for x in _CANDIDATES if os.path.isfile(x)), "")
def image_info(path=""):
    if Image is None: return "Error: Pillow is not installed in the sandbox."
    p=_path(path)
    if not p: return "Error: empty path"
    if not os.path.isfile(p): return f"Error: file not found: {path}"
    try:
        with Image.open(p) as im:
            return f"Path: {path}\nFormat: {im.format}\nMode: {im.mode}\nSize: {im.width}x{im.height}\nFile size: {os.path.getsize(p)} bytes"
    except Exception as e: return f"Error: could not open image ({type(e).__name__}: {e})"
def image_convert(path="", output_path="", max_dimension=0):
    if Image is None: return "Error: Pillow is not installed in the sandbox."
    src,dst=_path(path),_path(output_path)
    if not src or not dst: return "Error: both path and output_path are required"
    if not os.path.isfile(src): return f"Error: file not found: {path}"
    try:
        with Image.open(src) as im:
            im = im.convert("RGB") if im.mode in ("P","RGBA") and dst.lower().endswith((".jpg",".jpeg")) else im
            m=int(max_dimension or 0)
            if m>0 and max(im.size)>m: im.thumbnail((m,m), Image.Resampling.LANCZOS)
            os.makedirs(os.path.dirname(dst), exist_ok=True); im.save(dst)
            return f"Saved: {output_path} ({im.width}x{im.height})"
    except Exception as e: return f"Error: conversion failed ({type(e).__name__}: {e})"
def image_ocr(path="", lang="eng", scale=2, contrast=1.0, threshold=0, rotate=0):
    """OCR an image. Optional preprocessing: scale, contrast, threshold (1-254), rotate degrees."""
    if Image is None or pytesseract is None: return "Error: Pillow/pytesseract is not installed in the sandbox."
    tess=_tess()
    if not tess: return "Tesseract-OCR не найден. Установите его: https://github.com/UB-Mannheim/tesseract/wiki"
    p=_path(path)
    if not p: return "Error: empty path"
    if not os.path.isfile(p): return f"Error: file not found: {path}"
    try:
        pytesseract.pytesseract.tesseract_cmd=tess
        with Image.open(p) as original:
            im=original.convert("L")
            s=max(1,min(int(scale or 1),5))
            if s != 1: im=im.resize((im.width*s, im.height*s), Image.Resampling.LANCZOS)
            c=float(contrast or 1.0)
            if c != 1.0: im=ImageEnhance.Contrast(im).enhance(max(.1,min(c,5)))
            if int(rotate or 0): im=im.rotate(int(rotate), expand=True, fillcolor="white")
            t=int(threshold or 0)
            if 1 <= t <= 254: im=im.point(lambda x: 255 if x >= t else 0)
            text=pytesseract.image_to_string(im, lang=str(lang or "eng"))
        return text.strip()[:8000] or "(no text detected)"
    except Exception as e: return f"Error: OCR failed ({type(e).__name__}: {e})"
TOOLS=[
 ToolSpec(name="image_info",description="Show metadata for an image file (format, size, mode, file size).",input_schema={"type":"object","properties":{"path":{"type":"string"}},"required":["path"]},handler=image_info),
 ToolSpec(name="image_convert",description="Convert an image and/or resize it with preserved aspect ratio.",input_schema={"type":"object","properties":{"path":{"type":"string"},"output_path":{"type":"string"},"max_dimension":{"type":"integer"}},"required":["path","output_path"]},handler=image_convert),
 ToolSpec(name="image_ocr",description="OCR an image with optional preprocessing: scale, contrast, threshold and rotation. Requires system Tesseract-OCR.",input_schema={"type":"object","properties":{"path":{"type":"string"},"lang":{"type":"string"},"scale":{"type":"integer"},"contrast":{"type":"number"},"threshold":{"type":"integer"},"rotate":{"type":"integer"}},"required":["path"]},handler=image_ocr),
] 
