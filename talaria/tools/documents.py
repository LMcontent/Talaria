import os

from talaria.providers.base import ToolSpec
from talaria.tools.workspace import WorkspaceError, resolve_path

_MAX_CHARS = 8000


def _read_pdf(path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_docx(path: str) -> str:
    import docx

    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def read_document(workspace_dir: str, path: str) -> str:
    """Read a text/pdf/docx file from the workspace and return its text."""
    try:
        full_path = resolve_path(workspace_dir, path)
    except WorkspaceError as e:
        return f"Error: {e}"

    if not os.path.isfile(full_path):
        return f"Error: file not found: {path}"

    ext = os.path.splitext(full_path)[1].lower()
    try:
        if ext == ".pdf":
            text = _read_pdf(full_path)
        elif ext == ".docx":
            text = _read_docx(full_path)
        else:
            with open(full_path, encoding="utf-8", errors="replace") as f:
                text = f.read()
    except Exception as e:
        return f"Error: could not read {path} ({e})"

    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + f"... [truncated, {len(text)} chars total]"
    return text


def write_document(workspace_dir: str, path: str, content: str) -> str:
    """Write text content to a file inside the workspace."""
    try:
        full_path = resolve_path(workspace_dir, path)
    except WorkspaceError as e:
        return f"Error: {e}"

    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Wrote {len(content)} chars to {path}"


def list_files(workspace_dir: str, subdir: str = ".") -> str:
    """List files inside a workspace directory."""
    try:
        full_path = resolve_path(workspace_dir, subdir)
    except WorkspaceError as e:
        return f"Error: {e}"

    if not os.path.isdir(full_path):
        return f"Error: not a directory: {subdir}"

    entries = sorted(os.listdir(full_path))
    if not entries:
        return "(empty)"
    return "\n".join(entries)


def make_document_tools(workspace_dir: str) -> list[ToolSpec]:
    return [
        ToolSpec(
            name="read_document",
            description="Read a text, .pdf or .docx file from the workspace directory.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the workspace."}
                },
                "required": ["path"],
            },
            handler=lambda path: read_document(workspace_dir, path),
        ),
        ToolSpec(
            name="write_document",
            description="Write text content to a file in the workspace directory (creates or overwrites).",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the workspace."},
                    "content": {"type": "string", "description": "Text content to write."},
                },
                "required": ["path", "content"],
            },
            handler=lambda path, content: write_document(workspace_dir, path, content),
        ),
        ToolSpec(
            name="list_files",
            description="List files in a directory inside the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "subdir": {
                        "type": "string",
                        "description": "Subdirectory relative to the workspace (default '.').",
                    }
                },
                "required": [],
            },
            handler=lambda subdir=".": list_files(workspace_dir, subdir),
        ),
    ]
