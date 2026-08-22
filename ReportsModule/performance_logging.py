import os
import time
from contextlib import contextmanager

from watchcase_tracker.performance_logging.logger import emit_perf_event
from watchcase_tracker.performance_logging.sanitizer import sanitize_metadata, truncate_value


DEFAULT_SLOW_REPORT_MS = 3000


def _duration_ms(start_time):
    return round((time.perf_counter() - start_time) * 1000, 3)


def _perf_enabled():
    try:
        from django.conf import settings

        return bool(getattr(settings, 'PERF_LOG_ENABLED', False))
    except Exception:
        return False


def _slow_report_threshold():
    try:
        return max(
            int(os.getenv('PERF_LOG_SLOW_REPORT_MS', str(DEFAULT_SLOW_REPORT_MS))),
            1,
        )
    except (TypeError, ValueError):
        return DEFAULT_SLOW_REPORT_MS


def _safe_filters(request):
    try:
        return sanitize_metadata(dict(getattr(request, 'GET', {}) or {}))
    except Exception:
        return {}


def _response_size(response):
    try:
        size = response.get('Content-Length')
        return int(size) if size not in (None, '') else None
    except Exception:
        return None


class ReportDiagnostics:
    def __init__(self, request, report_name, module_name, requested_format):
        self.request = request
        self.report_name = report_name or 'unknown'
        self.module_name = module_name or 'ReportsModule'
        self.requested_format = requested_format or 'unknown'
        self.started_at = time.perf_counter()
        self.query_duration_ms = 0.0
        self.generation_duration_ms = 0.0
        self.download_duration_ms = 0.0
        self.rows = 0
        self.output_size_bytes = None
        self.ended = False
        self.slow_threshold_ms = _slow_report_threshold()

    @classmethod
    def start(
        cls,
        request,
        report_name,
        module_name='ReportsModule',
        requested_format='xlsx',
    ):
        diagnostics = cls(request, report_name, module_name, requested_format)
        diagnostics.emit(
            'REPORT.START',
            'INFO',
            'Report generation started',
            {
                'report_name': diagnostics.report_name,
                'module': diagnostics.module_name,
                'requested_format': diagnostics.requested_format,
                'requested_filters': _safe_filters(request) if _perf_enabled() else {},
            },
        )
        return diagnostics

    def emit(self, event_type, level, message, metadata=None):
        try:
            if not _perf_enabled():
                return
            emit_perf_event(
                'REPORT',
                event_type,
                level,
                message,
                metadata=metadata or {},
                request=self.request,
            )
        except Exception:
            return

    def query_start(self, query_identifier):
        self.emit(
            'REPORT.QUERY.START',
            'INFO',
            'Report query phase started',
            {
                'report_name': self.report_name,
                'phase_identifier': query_identifier,
            },
        )

    def query_end(self, query_identifier, duration_ms, rows_returned=None):
        self.query_duration_ms += duration_ms or 0.0
        if rows_returned is not None:
            self.rows = rows_returned
        self.emit(
            'REPORT.QUERY.END',
            'INFO',
            'Report query phase completed',
            {
                'report_name': self.report_name,
                'phase_identifier': query_identifier,
                'duration_ms': duration_ms,
                'rows_returned': rows_returned,
            },
        )

    def workbook_created(self, duration_ms, workbook_info):
        self.generation_duration_ms += duration_ms or 0.0
        self.rows = workbook_info.get('row_count', self.rows)
        self.output_size_bytes = workbook_info.get('estimated_workbook_size')
        self.emit(
            'REPORT.WORKBOOK.CREATE',
            'INFO',
            'Report workbook created',
            workbook_info,
        )
        self.emit(
            'REPORT.EXCEL.CREATE',
            'INFO',
            'Report Excel file created',
            {
                'workbook_creation_time_ms': duration_ms,
                'worksheet_count': workbook_info.get('worksheet_count'),
                'sheet_names': workbook_info.get('sheet_names'),
                'row_count': workbook_info.get('row_count'),
                'column_count': workbook_info.get('column_count'),
                'estimated_workbook_size': workbook_info.get(
                    'estimated_workbook_size'
                ),
            },
        )

    def worksheet_created(self, sheet_info):
        self.emit(
            'REPORT.WORKSHEET.CREATE',
            'INFO',
            'Report worksheet created',
            sheet_info,
        )

    def file_write(self, write_callable, destination_type='memory'):
        start = time.perf_counter()
        content = write_callable()
        duration_ms = _duration_ms(start)
        try:
            size = len(content)
        except Exception:
            size = None
        self.output_size_bytes = size
        self.emit(
            'REPORT.FILE.WRITE',
            'INFO',
            'Report file prepared',
            {
                'write_duration_ms': duration_ms,
                'output_size_bytes': size,
                'destination_type': destination_type,
            },
        )
        return content

    def download_start(self):
        self._download_started_at = time.perf_counter()
        self.emit(
            'REPORT.DOWNLOAD.START',
            'INFO',
            'Report download started',
            {
                'report_name': self.report_name,
                'format': self.requested_format,
            },
        )

    def download_end(self, response):
        duration_ms = _duration_ms(
            getattr(self, '_download_started_at', time.perf_counter())
        )
        self.download_duration_ms += duration_ms
        self.emit(
            'REPORT.DOWNLOAD.END',
            'INFO',
            'Report download completed',
            {
                'report_name': self.report_name,
                'format': self.requested_format,
                'status_code': getattr(response, 'status_code', None),
                'duration_ms': duration_ms,
                'response_size_bytes': _response_size(response),
            },
        )

    def error(self, exc):
        self.emit(
            'REPORT.ERROR',
            'ERROR',
            'Report generation failed',
            {
                'report_name': self.report_name,
                'exception_class': exc.__class__.__name__,
                'exception_message': truncate_value(exc, max_chars=300),
                'duration_ms': _duration_ms(self.started_at),
            },
        )

    def end(self, status='completed'):
        if self.ended:
            return
        self.ended = True
        total_duration_ms = _duration_ms(self.started_at)
        if total_duration_ms >= self.slow_threshold_ms:
            self.emit(
                'REPORT.SLOW',
                'WARNING',
                'Report generation exceeded slow threshold',
                {
                    'duration_ms': total_duration_ms,
                    'slow_report_threshold_ms': self.slow_threshold_ms,
                    'report_name': self.report_name,
                    'module': self.module_name,
                    'format': self.requested_format,
                },
            )
        self.emit(
            'REPORT.END',
            'INFO',
            'Report generation ended',
            {
                'report_name': self.report_name,
                'module': self.module_name,
                'format': self.requested_format,
                'status': status,
                'total_duration_ms': total_duration_ms,
                'data_fetch_duration_ms': round(self.query_duration_ms, 3),
                'generation_duration_ms': round(self.generation_duration_ms, 3),
                'download_duration_ms': round(self.download_duration_ms, 3),
                'rows': self.rows,
                'estimated_file_size': self.output_size_bytes,
            },
        )


def _workbook_info(writer, output):
    workbook = getattr(writer, 'book', None)
    sheets = list(getattr(workbook, 'worksheets', []) or [])
    sheet_infos = []
    total_rows = 0
    max_columns = 0
    for sheet in sheets:
        max_row = getattr(sheet, 'max_row', 0) or 0
        max_column = getattr(sheet, 'max_column', 0) or 0
        data_rows = max(max_row - 1, 0)
        total_rows += data_rows
        max_columns = max(max_columns, max_column)
        sheet_infos.append(
            {
                'sheet_name': getattr(sheet, 'title', None),
                'row_count': data_rows,
                'column_count': max_column,
            }
        )
    try:
        estimated_size = output.tell()
    except Exception:
        estimated_size = None
    return {
        'worksheet_count': len(sheet_infos),
        'sheet_names': [sheet['sheet_name'] for sheet in sheet_infos],
        'row_count': total_rows,
        'column_count': max_columns,
        'estimated_workbook_size': estimated_size,
        'worksheets': sheet_infos,
    }


@contextmanager
def report_excel_generation(diagnostics, writer_factory, output, **writer_kwargs):
    writer = None
    start = time.perf_counter()
    diagnostics.query_start('report_generation')
    try:
        with writer_factory(output, **writer_kwargs) as writer:
            yield writer
    except Exception as exc:
        diagnostics.error(exc)
        diagnostics.end(status='error')
        raise
    else:
        duration_ms = _duration_ms(start)
        info = _workbook_info(writer, output)
        diagnostics.query_end(
            'report_generation',
            duration_ms,
            rows_returned=info.get('row_count'),
        )
        diagnostics.workbook_created(duration_ms, info)
        for sheet_info in info.get('worksheets', []):
            diagnostics.worksheet_created(sheet_info)
