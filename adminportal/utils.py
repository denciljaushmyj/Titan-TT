import os
import logging
from bs4 import BeautifulSoup
import re
from .service_performance_logging import (
    duration_ms as service_duration_ms,
    emit_external_end,
    emit_external_error,
    emit_external_start,
    perf_counter as service_perf_counter,
)

logger = logging.getLogger(__name__)

# Generic safe message returned to clients — never expose raw exception text
SAFE_ERROR_MESSAGE = "Unable to process the request. Please verify the submitted data and try again."


def log_and_get_safe_error(context: str, exc: Exception) -> str:
    """
    Log the full exception server-side and return a generic safe message.
    Call this instead of returning str(exc) in any HTTP response.
    """
    logger.exception("%s: %s", context, exc)
    return SAFE_ERROR_MESSAGE

def extract_table_headings_from_html(file_path):
    """
    Extract table headings from an HTML file.
    Returns a list of heading texts found in <th> tags.
    """
    external_started = service_perf_counter()
    emit_external_start('Filesystem', target=file_path, operation='read_template_headings')
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        soup = BeautifulSoup(content, 'html.parser')
        
        # Find all table headers
        headings = []
        th_tags = soup.find_all('th')
        
        for th in th_tags:
            # Get text content and clean it
            text = th.get_text(strip=True)
            if text and text not in headings:  # Avoid duplicates
                headings.append(text)
        
        # If no <th> tags found, look for headers in first table row
        if not headings:
            tables = soup.find_all('table')
            for table in tables:
                first_row = table.find('tr')
                if first_row:
                    cells = first_row.find_all(['td', 'th'])
                    for cell in cells:
                        text = cell.get_text(strip=True)
                        if text and text not in headings:
                            headings.append(text)
                    break  # Only process first table
        
        emit_external_end(
            'Filesystem',
            duration=service_duration_ms(external_started),
            status='success',
            target=file_path,
            operation='read_template_headings',
            metadata={'heading_count': len(headings)},
        )
        return headings
        
    except FileNotFoundError:
        emit_external_error(
            'Filesystem',
            FileNotFoundError(),
            duration=service_duration_ms(external_started),
            target=file_path,
            operation='read_template_headings',
        )
        print(f"File not found: {file_path}")
        return []
    except Exception as e:
        emit_external_error(
            'Filesystem',
            e,
            duration=service_duration_ms(external_started),
            target=file_path,
            operation='read_template_headings',
        )
        logger.error(f"Error reading file {file_path}: {str(e)}", exc_info=True)
        return []

def get_template_files():
    """
    Get all HTML template files from the templates directory.
    Returns a list of relative file paths.
    """
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'templates')
    template_files = []
    external_started = service_perf_counter()
    emit_external_start('Filesystem', target=templates_dir, operation='scan_template_directory')
    
    try:
        for root, dirs, files in os.walk(templates_dir):
            for file in files:
                if file.endswith('.html'):
                    # Get relative path from templates directory
                    rel_path = os.path.relpath(os.path.join(root, file), templates_dir)
                    template_files.append(rel_path.replace('\\', '/'))  # Use forward slashes
        
        sorted_files = sorted(template_files)
        emit_external_end(
            'Filesystem',
            duration=service_duration_ms(external_started),
            status='success',
            target=templates_dir,
            operation='scan_template_directory',
            metadata={'file_count': len(sorted_files)},
        )
        return sorted_files
    except Exception as e:
        emit_external_error(
            'Filesystem',
            e,
            duration=service_duration_ms(external_started),
            target=templates_dir,
            operation='scan_template_directory',
        )
        logger.error(f"Error scanning template directory: {str(e)}", exc_info=True)
        return []

def validate_html_file(file_path):
    """
    Validate if an HTML file exists and is readable.
    Returns True if valid, False otherwise.
    """
    external_started = service_perf_counter()
    try:
        templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'templates')
        full_path = os.path.join(templates_dir, file_path)
        emit_external_start('Filesystem', target=full_path, operation='validate_html_file')
        
        if not os.path.exists(full_path):
            emit_external_end(
                'Filesystem',
                duration=service_duration_ms(external_started),
                status='missing',
                target=full_path,
                operation='validate_html_file',
            )
            return False
        
        # Try to read the file
        with open(full_path, 'r', encoding='utf-8') as f:
            f.read(100)  # Read first 100 chars to test
        
        emit_external_end(
            'Filesystem',
            duration=service_duration_ms(external_started),
            status='success',
            target=full_path,
            operation='validate_html_file',
        )
        return True
    except Exception as exc:
        emit_external_error(
            'Filesystem',
            exc,
            duration=service_duration_ms(external_started),
            target=file_path,
            operation='validate_html_file',
        )
        return False
