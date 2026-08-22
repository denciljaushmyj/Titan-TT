import time


class BaseStageTimingMiddleware:
    stage_name = 'UNKNOWN'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()

        response = self.get_response(request)

        elapsed = time.perf_counter() - started

        perf = getattr(request, '_perf', None)
        if perf is not None:
            perf.record_stage(
                self.stage_name,
                elapsed,
            )

        return response


class SessionStageTimingMiddleware(BaseStageTimingMiddleware):
    stage_name = 'MW_SESSION_CHAIN'


class AuthenticationStageTimingMiddleware(BaseStageTimingMiddleware):
    stage_name = 'MW_AUTH_CHAIN'


class ModuleAccessStageTimingMiddleware(BaseStageTimingMiddleware):
    stage_name = 'MW_MODULE_ACCESS_CHAIN'


class LoginLatencyStageTimingMiddleware(BaseStageTimingMiddleware):
    stage_name = 'MW_LOGIN_LATENCY_CHAIN'


class ForbiddenRedirectStageTimingMiddleware(BaseStageTimingMiddleware):
    stage_name = 'MW_FORBIDDEN_REDIRECT_CHAIN'