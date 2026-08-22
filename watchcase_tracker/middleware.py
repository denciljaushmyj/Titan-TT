import time
import logging

logger = logging.getLogger(__name__)

class RequestTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()

        response = self.get_response(request)

        elapsed = (time.perf_counter() - start) * 1000

        print(f"[TIMING] {request.method} {request.path} : {elapsed:.2f} ms")

        return response