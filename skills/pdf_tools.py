# -*- coding: utf-8 -*-
"""PDF inspection, text extraction, page extraction, merging and rendering."""
import os
from talaria.providers.base import ToolSpec
try:
    import fitz
except Exception:
    fitz = None

_WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workspace"))
_MAX = 12000

def _path(p):
    p = str(p or "").strip()
    return p if os.path.isabs(p) else os.path.join(_WORKSPACE, p)

def _check(p):
    if fitz is None: return "Error: PyMuPDF is not installed in the sandbox."
    if not p: return "Error: empty path"
    if not os.path.isfile(p): return f"Error: file not found: {p}"
    return ""

def pdf_info(path=""):
    p = _path(path); err = _check(p)
    if err: return err
    try:
        with fitz.open(p) as doc:
            return "\n".join([f"Pages: {len(doc)}", f"Metadata: {doc.metadata}",
                *[f"- page {i+1}: {page.rect.width:.0f}x{page.rect.height:.0f} pt" for i, page in enumerate(doc)][:20]])
    except Exception as e: return f"Error: could not open PDF ({type(e).__name__}: {e})"

def pdf_text(path="", page_start=1, page_end=0):
    p = _path(path); err = _check(p)
    if err: return err
    try:
        with fitz.open(p) as doc:
            start = max(1, int(page_start)); end = int(page_end) or len(doc)
            if start > end or start > len(doc): return "Error: invalid page range"
            out = []
            for n in range(start-1, min(end, len(doc))):
                out.append(f"--- Page {n+1} ---\n{doc[n].get_text()}")
            result = "\n".join(out).strip()
            return (result or "(no text layer; PDF may be scanned)")[:_MAX]
    except Exception as e: return f"Error: text extraction failed ({type(e).__name__}: {e})"

def pdf_extract_pages(path="", output_path="", page_start=1, page_end=0):
    src, dst = _path(path), _path(output_path); err = _check(src)
    if err: return err
    if not output_path: return "Error: output_path is required"
    try:
        with fitz.open(src) as doc:
            start, end = max(1, int(page_start)), int(page_end) or len(doc)
            if start > end or start > len(doc): return "Error: invalid page range"
            out = fitz.open(); out.insert_pdf(doc, from_page=start-1, to_page=min(end, len(doc))-1)
            os.makedirs(os.path.dirname(dst), exist_ok=True); out.save(dst); out.close()
            return f"Saved: {output_path} ({end-start+1} pages)"
    except Exception as e: return f"Error: page extraction failed ({type(e).__name__}: {e})"

def pdf_merge(paths="", output_path=""):
    if fitz is None: return "Error: PyMuPDF is not installed in the sandbox."
    items = paths if isinstance(paths, list) else [x.strip() for x in str(paths or "").split(",") if x.strip()]
    if not items or not output_path: return "Error: paths and output_path are required"
    try:
        out = fitz.open()
        for item in items:
            p = _path(item)
            if not os.path.isfile(p): out.close(); return f"Error: file not found: {item}"
            with fitz.open(p) as doc: out.insert_pdf(doc)
        dst = _path(output_path); os.makedirs(os.path.dirname(dst), exist_ok=True); out.save(dst); pages = len(out); out.close()
        return f"Saved: {output_path} ({pages} pages)"
    except Exception as e: return f"Error: merge failed ({type(e).__name__}: {e})"

def pdf_render(path="", output_dir="", page_start=1, page_end=0, dpi=150):
    p = _path(path); err = _check(p)
    if err: return err
    if not output_dir: return "Error: output_dir is required"
    try:
        with fitz.open(p) as doc:
            start, end = max(1, int(page_start)), int(page_end) or len(doc); scale = max(36, min(int(dpi), 600)) / 72
            if start > end or start > len(doc): return "Error: invalid page range"
            dst = _path(output_dir); os.makedirs(dst, exist_ok=True); files=[]
            for n in range(start-1, min(end, len(doc))):
                pix = doc[n].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                fn = os.path.join(dst, f"page_{n+1}.png"); pix.save(fn); files.append(fn)
            return "Rendered:\n" + "\n".join(files)
    except Exception as e: return f"Error: rendering failed ({type(e).__name__}: {e})"

TOOLS = [
 ToolSpec(name="pdf_info", description="Show PDF page count, metadata and page dimensions.", input_schema={"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}, handler=pdf_info),
 ToolSpec(name="pdf_text", description="Extract text from a PDF, optionally by page range.", input_schema={"type":"object","properties":{"path":{"type":"string"},"page_start":{"type":"integer"},"page_end":{"type":"integer"}},"required":["path"]}, handler=pdf_text),
 ToolSpec(name="pdf_extract_pages", description="Save a selected page range as a new PDF.", input_schema={"type":"object","properties":{"path":{"type":"string"},"output_path":{"type":"string"},"page_start":{"type":"integer"},"page_end":{"type":"integer"}},"required":["path","output_path"]}, handler=pdf_extract_pages),
 ToolSpec(name="pdf_merge", description="Merge multiple PDFs into one. paths may be a list or comma-separated string.", input_schema={"type":"object","properties":{"paths":{"description":"PDF paths","oneOf":[{"type":"array","items":{"type":"string"}},{"type":"string"}]},"output_path":{"type":"string"}},"required":["paths","output_path"]}, handler=pdf_merge),
 ToolSpec(name="pdf_render", description="Render PDF pages to PNG images for OCR or inspection.", input_schema={"type":"object","properties":{"path":{"type":"string"},"output_dir":{"type":"string"},"page_start":{"type":"integer"},"page_end":{"type":"integer"},"dpi":{"type":"integer"}},"required":["path","output_dir"]}, handler=pdf_render),
]
