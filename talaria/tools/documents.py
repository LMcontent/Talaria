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


def edit_document(
    workspace_dir: str, path: str, old_text: str = "", new_text: str = "", replace_all: str = "false"
) -> str:
    """Replace old_text with new_text inside an existing workspace file,
    without the caller resending the whole file — the point being to
    avoid both the token cost and the "accidentally dropped a chunk of
    the file while retyping it" risk that comes with write_document for
    anything beyond a small file. old_text must match the file's
    current content exactly (including whitespace) and, unless
    replace_all, occur exactly once — ambiguous or missing matches are
    refused rather than guessed at."""
    try:
        full_path = resolve_path(workspace_dir, path)
    except WorkspaceError as e:
        return f"Error: {e}"

    if not os.path.isfile(full_path):
        return f"Error: file not found: {path}"
    if not old_text:
        return "Error: 'old_text' must be non-empty (use write_document to create a new file)."
    all_occurrences = str(replace_all).strip().lower() in ("1", "true", "yes", "on")

    with open(full_path, encoding="utf-8") as f:
        content = f.read()

    count = content.count(old_text)
    if count == 0:
        return f"Error: old_text not found in {path} (it must match exactly, including whitespace)."
    if count > 1 and not all_occurrences:
        return (
            f"Error: old_text occurs {count} times in {path} - make it unique with more "
            "surrounding context, or pass replace_all=true to replace every occurrence."
        )

    new_content = content.replace(old_text, new_text) if all_occurrences else content.replace(old_text, new_text, 1)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    times = f"{count} occurrences" if all_occurrences and count > 1 else "1 occurrence"
    return f"Replaced {times} in {path} ({len(new_content)} chars now)."


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
            name="edit_document",
            description=(
                "Replace one exact occurrence of old_text with new_text in an existing "
                "workspace file, without resending the whole file - prefer this over "
                "write_document for anything beyond a small file or a full rewrite. "
                "old_text must match the file's current content exactly (whitespace "
                "included) and occur exactly once unless replace_all is set."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the workspace."},
                    "old_text": {"type": "string", "description": "Exact text to find (must be unique unless replace_all)."},
                    "new_text": {"type": "string", "description": "Text to replace it with (empty string deletes old_text)."},
                    "replace_all": {"type": "string", "description": "'true' to replace every occurrence instead of requiring exactly one (default 'false')."},
                },
                "required": ["path", "old_text", "new_text"],
            },
            handler=lambda path, old_text="", new_text="", replace_all="false": edit_document(
                workspace_dir, path, old_text, new_text, replace_all
            ),
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
