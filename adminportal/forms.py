import logging
import time as _time

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm

from .services import is_recaptcha_configured

logger = logging.getLogger(__name__)


try:
    from django_recaptcha.fields import ReCaptchaField
    from django_recaptcha.widgets import ReCaptchaV2Checkbox
except ImportError:  # pragma: no cover - keeps startup safe if dependency is absent.
    ReCaptchaField = None
    ReCaptchaV2Checkbox = None


class AdaptiveCaptchaAuthenticationForm(AuthenticationForm):
    """
    AuthenticationForm with an optional server-validated reCAPTCHA challenge.
    """

    captcha_unavailable_message = (
        'CAPTCHA verification is not configured. Please contact an administrator.'
    )

    def __init__(self, request=None, *args, require_captcha=False, **kwargs):
        # Perf instrumentation (LOGIN_POST_TIMING breakdown): the enclosing
        # TimedLoginView.post() only times the *total* get_form() call. These
        # sub-timers pinpoint whether the cost is Django's own AuthenticationForm
        # __init__ (field/widget setup) or the reCAPTCHA field construction.
        t0 = _time.time()
        self.require_captcha = bool(require_captcha and is_recaptcha_configured())
        super().__init__(request, *args, **kwargs)
        super_init_ms = (_time.time() - t0) * 1000

        if not self.require_captcha:
            if getattr(settings, 'ENABLE_LOGIN_LATENCY_LOGS', False):
                logger.warning(
                    'LOGIN_FORM_INIT_TIMING: super_init=%.2fms | captcha_field=skipped',
                    super_init_ms,
                )
            return

        t0 = _time.time()
        if ReCaptchaField is None or ReCaptchaV2Checkbox is None:
            self.fields['captcha'] = forms.CharField(
                required=False,
                widget=forms.HiddenInput,
            )
        else:
            self.fields['captcha'] = ReCaptchaField(
                label='',
                widget=ReCaptchaV2Checkbox(
                    attrs={
                        'data-theme': 'light',
                        'data-size': 'normal',
                    }
                ),
                error_messages={
                    'required': 'Please complete the CAPTCHA verification.',
                    'captcha_invalid': 'CAPTCHA verification failed. Please try again.',
                },
            )
        captcha_field_ms = (_time.time() - t0) * 1000

        if getattr(settings, 'ENABLE_LOGIN_LATENCY_LOGS', False):
            logger.warning(
                'LOGIN_FORM_INIT_TIMING: super_init=%.2fms | captcha_field=%.2fms',
                super_init_ms, captcha_field_ms,
            )

    def clean(self):
        if self.require_captcha and self.errors.get('captcha'):
            return self.cleaned_data
        return super().clean()

    def get_captcha_error_message(self):
        if not self.require_captcha:
            return None

        errors = self.errors.get('captcha')
        if errors:
            return errors[0]

        for error in self.non_field_errors():
            if 'CAPTCHA' in str(error):
                return str(error)
        return None
