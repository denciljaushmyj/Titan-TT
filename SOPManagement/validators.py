"""
SOP Management Validators — pure input validation.

Rule: NO DB writes here, no querying beyond what's needed to validate
uniqueness/existence. Returns (is_valid, error_message) tuples so callers
in services.py can decide what to do, matching the Brass_QC/services
validators.py convention used elsewhere in this project.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

ALLOWED_SOP_EXT = '.pdf'
ALLOWED_SOP_MIME = 'application/pdf'
PDF_SIGNATURE = b'%PDF-'

# Dangerous intermediate extensions that must never appear in the filename
# stem, same denylist convention as ModelImageSerializer.
_DANGEROUS_EXT = frozenset({
    '.exe', '.php', '.sh', '.bat', '.cmd', '.ps1', '.js', '.py',
    '.rb', '.pl', '.asp', '.aspx', '.jsp', '.cgi', '.dll', '.so',
})


def get_sop_max_upload_size():
    return getattr(settings, 'SOP_FILE_MAX_UPLOAD_SIZE', 20 * 1024 * 1024)


def _detect_pdf_signature(value):
    """Read the first bytes of the uploaded file and confirm the PDF magic number."""
    try:
        value.seek(0)
        header = value.read(8)
    finally:
        value.seek(0)

    if not header:
        return False
    return header.startswith(PDF_SIGNATURE)


def validate_sop_file(value):
    """
    Validate an uploaded SOP file. Returns None on success, or an error
    string describing the first failure encountered.

    Layers (mirrors ModelImageSerializer.validate_master_image, adapted for
    PDF documents):
      1. Dangerous intermediate extension denylist.
      2. Final extension allowlist (.pdf only).
      3. Content-Type allowlist (application/pdf).
      4. Max upload size (settings.SOP_FILE_MAX_UPLOAD_SIZE).
      5. Magic-number (file signature) verification — the actual bytes
         must start with the PDF header, independent of extension/MIME.
    """
    import os

    name = value.name or ''
    stem = os.path.splitext(name)[0].lower()
    _, ext = os.path.splitext(name.lower())

    for dext in _DANGEROUS_EXT:
        if stem.endswith(dext) or f'{dext}.' in stem:
            return f'File "{name}" contains a disallowed intermediate extension.'

    if ext != ALLOWED_SOP_EXT:
        return 'Only PDF files are allowed for SOP documents.'

    content_type = getattr(value, 'content_type', '') or ''
    if content_type and content_type != ALLOWED_SOP_MIME:
        return f'File type "{content_type}" is not allowed. Only PDF files are accepted.'

    max_size = get_sop_max_upload_size()
    size = getattr(value, 'size', None)
    if size is not None and size > max_size:
        max_mb = max_size / (1024 * 1024)
        return f'File exceeds maximum allowed size of {max_mb:g} MB.'

    if size is not None and size == 0:
        return 'Uploaded file is empty.'

    if not _detect_pdf_signature(value):
        return 'File content does not match a valid PDF. The file may be corrupted or not a genuine PDF.'

    return None


def validate_sop_title(sop_title):
    if not sop_title or not sop_title.strip():
        return 'SOP title is required.'
    if len(sop_title) > 200:
        return 'SOP title cannot exceed 200 characters.'
    return None


def validate_sop_version(version):
    if not version or not version.strip():
        return 'Version is required.'
    if len(version) > 20:
        return 'Version cannot exceed 20 characters.'
    return None
