from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.response import Response
from modelmasterapp.models import *
from rest_framework import status
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone  # Added timezone import
from django.conf import settings
import json
import re
import logging
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from .forms import AdaptiveCaptchaAuthenticationForm
from .serializers import *
from .utils import extract_table_headings_from_html
from .decorators import require_admin, IsAdminPermission
import datetime
from InputScreening import *
from django.db import transaction

logger = logging.getLogger(__name__)
from django.db.models import Sum, Q
from django.db.models.functions import Cast
from django.db.models import IntegerField
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from adminportal.models import *
from .models import *
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import os
from django.contrib.auth.models import Group
from django.http import JsonResponse
from django.contrib.auth import authenticate, get_user_model, login
from django.views.decorators.csrf import csrf_exempt
import json
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.html import escape
from django.views.decorators.http import require_POST
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Module, UserModuleProvision
from Recovery_DP.models import *


def get_allowed_modules_for_user(user):
    """
    Get list of module names accessible by user.
    Optimized with caching per user for fast repeated calls.
    Cache key includes user ID to prevent cross-user data leakage.
    """
    from .services import get_user_allowed_module_names
    return get_user_allowed_module_names(user)


@method_decorator(login_required(login_url='login-api'), name='dispatch')
class ShortcutConfigurationAPIView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request, format=None):
        import time as _time
        from .services import get_active_shortcut_configurations
        t0 = _time.time()
        shortcuts = get_active_shortcut_configurations()
        elapsed_ms = (_time.time() - t0) * 1000
        logger.debug(
            'shortcuts API: %.2fms count=%d user=%s',
            elapsed_ms, len(shortcuts), request.user.username,
        )
        return Response({
            'success': True,
            'shortcuts': shortcuts,
        })



# -----------------------------------------------------------------------------
# TimedLoginView
# - Extends Django's auth LoginView with per-phase timing so we can see exactly
#   what part of the POST is slow (form validation vs authenticate vs session
#   save vs redirect).
# - Keeps login lightweight. Dashboard stats are loaded separately by the
#   dashboard API after /home/ is rendered, never during login POST.
# - Routed via watchcase_tracker/urls.py; settings.py is not modified here.
# -----------------------------------------------------------------------------
class TimedLoginView(__import__('django.contrib.auth.views', fromlist=['LoginView']).LoginView):
    template_name = 'login.html'
    authentication_form = AdaptiveCaptchaAuthenticationForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.conf import settings
        from .services import is_recaptcha_configured, should_require_login_captcha

        form = context.get('form')
        username = ''
        if form is not None and getattr(form, 'data', None):
            username = form.data.get('username', '').strip()
        elif self.request.method == 'POST':
            username = self.request.POST.get('username', '').strip()

        context['enable_microsoft_login'] = getattr(settings, 'ENABLE_MICROSOFT_LOGIN', False)
        if self.request.GET.get('otp_error') == 'expired':
            context['error'] = 'Verification code expired.'
        context['show_captcha'] = bool(
            getattr(form, 'require_captcha', False)
            or should_require_login_captcha(username)
        )
        context['captcha_configured'] = is_recaptcha_configured()
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        from .services import should_require_login_captcha

        username = ''
        data = kwargs.get('data')
        if data:
            username = data.get('username', '').strip()
        kwargs['require_captcha'] = should_require_login_captcha(username)
        return kwargs

    def _login_error_message(self, form, username):
        captcha_error = getattr(form, 'get_captcha_error_message', lambda: None)()
        if captcha_error:
            return captcha_error

        from .services import get_account_lock_message

        return (
            get_account_lock_message(username)
            or 'Invalid username or password. Please try again.'
        )


    def form_valid(self, form):
        # Let Django perform the normal login
        response = super().form_valid(form)

        # Skip OTP verification
        self.request.session["mfa_verified"] = True
        self.request.session.modified = True

        return response

    def _refresh_captcha_context_after_failed_login(self, response, username):
        from .services import is_recaptcha_configured, should_require_login_captcha

        if not hasattr(response, 'context_data'):
            return

        captcha_required = should_require_login_captcha(username)
        if captcha_required:
            response.context_data['form'] = self.get_form_class()(
                self.request,
                initial={'username': username},
                require_captcha=True,
            )
        response.context_data['show_captcha'] = captcha_required
        response.context_data['captcha_configured'] = is_recaptcha_configured()

    # Rate limiting (CWE-307): cap login POSTs per source IP regardless of
    # which username is being tried. block=False so we can return our own
    # friendly HTML error instead of django-ratelimit's default 403 page;
    # the actual 429 response is built below when request.limited is True.
    # This is in addition to, not a replacement for, the existing
    # AccountLockoutBackend (5 failed attempts -> account lock).
    @method_decorator(ratelimit(key='ip', rate='10/m', method='POST', block=False))
    def post(self, request, *args, **kwargs):
        from django.conf import settings
        import time as _time

        # request.limited is set by the ratelimit decorator above.
        if getattr(request, 'limited', False):
            security_logger = logging.getLogger('security.auth')
            security_logger.warning(
                'LOGIN_RATE_LIMITED: ip=%s path=%s',
                request.META.get('REMOTE_ADDR', 'unknown'),
                request.path,
            )
            message = 'Too many login attempts. Please wait a minute and try again.'
            if request.headers.get('Accept', '').find('application/json') != -1 or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': message}, status=429)
            response = self.render_to_response(self.get_context_data(form=self.get_form()))
            response.status_code = 429
            if hasattr(response, 'context_data'):
                response.context_data['error'] = message
            return response

        timers = {}
        t_start = _time.time()

        t0 = _time.time()
        form = self.get_form()
        timers['get_form'] = (_time.time() - t0) * 1000

        t0 = _time.time()
        is_valid = form.is_valid()  # runs authenticate() + password verify
        timers['form_is_valid'] = (_time.time() - t0) * 1000

        if is_valid:
            t0 = _time.time()
            response = self.form_valid(form)
            timers['form_valid_otp'] = (_time.time() - t0) * 1000
        else:
            response = self.form_invalid(form)
            timers['form_invalid'] = 0.0
            # Account lockout policy: surface a clear message via the template's
            # {{ error }} block (locked account vs. plain invalid credentials).
            username = request.POST.get('username', '').strip()
            if hasattr(response, 'context_data'):
                response.context_data['error'] = self._login_error_message(form, username)
            self._refresh_captcha_context_after_failed_login(response, username)

        total = (_time.time() - t_start) * 1000
        breakdown = ' | '.join(f'{k}={v:.2f}ms' for k, v in timers.items())
        if getattr(settings, 'ENABLE_LOGIN_LATENCY_LOGS', False):
            logger.warning('LOGIN_POST_TIMING: total=%.2fms | %s', total, breakdown)
        return response


def _email_otp_context(request, message=None, error=None):
    from .otp_service import get_resend_cooldown_remaining

    remaining = get_resend_cooldown_remaining(request)
    return {
        'error': error,
        'message': message,
        'resend_remaining_seconds': remaining,
        'resend_cooldown_active': remaining > 0,
    }


def verify_email_otp(request):
    from .otp_service import (
        clear_pending_otp_session,
        validate_pending_otp_session,
    )

    pending_user_id = request.session.get('pending_mfa_user_id')
    if not pending_user_id:
        return redirect('login')

    context = _email_otp_context(request)

    if request.method == 'POST':
        if getattr(settings, 'DEBUG', False):
            logger.info('OTP_VERIFY_FORM_POST: path=%s', request.path)
        raw_otp = request.POST.get('otp', '').strip()
        otp = ''.join(ch for ch in raw_otp if ch.isdigit())
        if getattr(settings, 'DEBUG', False) and otp:
            logger.info('OTP_SUBMITTED_DEBUG_SUFFIX: otp_last2=%s', otp[-2:])

        if not otp:
            context['error'] = 'Invalid verification code.'
            return render(request, 'two_step_auth/verify_email_otp.html', context)
        if len(otp) != 6:
            context['error'] = 'Invalid verification code.'
            return render(request, 'two_step_auth/verify_email_otp.html', context)

        is_valid, reason = validate_pending_otp_session(request, otp)

        if not is_valid:
            if reason == 'expired':
                return redirect('/accounts/login/?otp_error=expired')

            if reason == 'max_attempts':
                return redirect('login')

            context['error'] = 'Invalid verification code.'
            return render(request, 'two_step_auth/verify_email_otp.html', context)

        User = get_user_model()
        try:
            user = User.objects.get(pk=pending_user_id)
        except User.DoesNotExist:
            clear_pending_otp_session(request)
            logger.warning('MFA_LOGIN_FAILED_USER_MISSING: user_id=%s', pending_user_id)
            return redirect('login')

        next_url = request.session.get('pending_mfa_next_url') or '/home/'
        login(request, user)
        clear_pending_otp_session(request)
        request.session.pop('pending_mfa_next_url', None)
        request.session['mfa_verified'] = True
        request.session.modified = True
        logger.info(
            'MFA_LOGIN_SUCCESS: user_id=%s username=%s',
            getattr(user, 'id', None),
            getattr(user, 'username', 'unknown'),
        )

        if not url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            next_url = '/home/'

        return redirect(next_url)

    if getattr(settings, 'DEBUG', False):
        logger.info('OTP_VERIFY_FORM_RENDERED: path=%s', request.path)
    return render(request, 'two_step_auth/verify_email_otp.html', context)


@require_POST
def resend_email_otp(request):
    from .otp_service import (
        OTPResendCooldownError,
        clear_pending_otp_session,
        resend_pending_otp_session,
    )

    pending_user_id = request.session.get('pending_mfa_user_id')
    if not pending_user_id:
        return redirect('login')

    User = get_user_model()
    try:
        user = User.objects.get(pk=pending_user_id)
    except User.DoesNotExist:
        clear_pending_otp_session(request)
        logger.warning('OTP_RESEND_FAILED: user_id=%s reason=user_missing', pending_user_id)
        return redirect('login')

    context = _email_otp_context(request)

    try:
        resend_pending_otp_session(request, user)
    except OTPResendCooldownError:
        context = _email_otp_context(
            request,
            message='Please wait before requesting another code.',
        )
        return render(request, 'two_step_auth/verify_email_otp.html', context)
    except Exception:
        logger.exception(
            'OTP_RESEND_FAILED: user_id=%s username=%s',
            getattr(user, 'id', None),
            getattr(user, 'username', 'unknown'),
        )
        context = _email_otp_context(
            request,
            error='Unable to resend verification code. Please try again.',
        )
        return render(request, 'two_step_auth/verify_email_otp.html', context)

    messages.success(request, 'A new verification code has been sent.')
    return redirect('verify_email_otp')


@method_decorator(login_required(login_url='login'), name='dispatch')
class IndexView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'index.html'
 
    def get(self, request, format=None):
        from django.utils import timezone
        import time
        
        # Timing checkpoint 1: Start
        t1 = time.time()
        
        # Get allowed modules (optimized with values_list for minimal data transfer)
        allowed_modules = get_allowed_modules_for_user(request.user)
        
        t2 = time.time()
        if hasattr(request, 'timers'):
            request.timers['allowed_modules'] = f'{(t2-t1)*1000:.2f}ms'
        
        # Do not touch dashboard stats during page render.
        # The browser loads them separately from DashboardStatsAPIView after
        # /home/ is already visible, so slow cache/log/DB work cannot block TTFB.
        t3 = time.time()
        request._ttt_allowed_modules = allowed_modules
        dashboard_stats = []
        t4 = time.time()
        if hasattr(request, 'timers'):
            request.timers['dashboard_stats'] = f'{(t4-t3)*1000:.2f}ms'
        
        # Build context
        context = { 
            'user': request.user,
            'allowed_modules': allowed_modules,
            'dashboard_stats': dashboard_stats,
            'dashboard_stats_loading': True,
            'current_date': timezone.now().strftime('%d %b %Y'),
        }
        
        # Create response (DRF handles rendering)
        response = Response(context)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        
        t5 = time.time()
        if hasattr(request, 'timers'):
            request.timers['context_build'] = f'{(t5-t4)*1000:.2f}ms'
        
        return response


@method_decorator(login_required(login_url='login'), name='dispatch')
class DashboardStatsAPIView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request, format=None):
        from django.conf import settings
        from .services import (
            filter_dashboard_stats_for_modules,
            get_dashboard_cache_snapshot,
            refresh_dashboard_stats_async,
        )
        import time

        t1 = time.time()
        allowed_modules = get_allowed_modules_for_user(request.user)
        dashboard_stats, labels, missing_labels, cache_lookup_ms = get_dashboard_cache_snapshot(
            allowed_module_names=allowed_modules
        )
        dashboard_stats = filter_dashboard_stats_for_modules(dashboard_stats, allowed_modules)
        refresh_started = refresh_dashboard_stats_async(missing_labels) if missing_labels else False
        elapsed_ms = (time.time() - t1) * 1000
        if getattr(settings, 'ENABLE_DASHBOARD_LATENCY_LOGS', False):
            logger.warning(
                'DASHBOARD_STATS_API: user_id=%s modules=%s missing=%s refresh_started=%s lookup=%.2fms total=%.2fms',
                request.user.id,
                len(dashboard_stats),
                missing_labels,
                refresh_started,
                cache_lookup_ms,
                elapsed_ms,
            )

        response = Response({
            'success': True,
            'stats': dashboard_stats,
            'count': len(dashboard_stats),
            'labels': [stat.get('label') for stat in dashboard_stats if stat.get('label')],
            'refreshing': bool(missing_labels),
            'refresh_started': refresh_started,
            'missing_labels': missing_labels,
            'expected_labels': labels,
            'retry_after_ms': 1200 if missing_labels else 0,
        })
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        return response

    
@method_decorator(login_required(login_url='login-api'), name='dispatch')
class Visual_AidView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'ModelMaster/VisualAid.html'

    def get(self, request, batch_id=None, format=None):
        # Get parameters from URL or query string
        batch_id = batch_id or request.GET.get('batch_id')
        lot_id = request.GET.get('lot_id')
        plating_stk_no = request.GET.get('plating_stk_no')

        context = {
            'user': request.user,
        }

        # Import required models
        from modelmasterapp.models import ModelMasterCreation, LookLikeModel, ModelMaster, TotalStockModel

        batch_obj = None
        model_master_obj = None
        data_source = None  # Track whether data comes from ModelMasterCreation or ModelMaster

        # Handle lot_id parameter - NEW ADDITION
        if lot_id:
            print(f"🔍 Visual_AidView received lot_id: {lot_id}")
            
            # Find TotalStockModel by lot_id to get batch_id
            total_stock_obj = TotalStockModel.objects.filter(lot_id=lot_id).first()
            
            if total_stock_obj and hasattr(total_stock_obj, 'batch_id'):
                batch_id_obj = total_stock_obj.batch_id
                print(f"Found batch_id object from TotalStockModel: {batch_id_obj}")
                print(f"Type of batch_id object: {type(batch_id_obj)}")
                
                # Check if batch_id is a ForeignKey (ModelMasterCreation object) or string
                if hasattr(batch_id_obj, 'batch_id'):
                    # batch_id is a ForeignKey to ModelMasterCreation
                    batch_obj = batch_id_obj  # This IS the ModelMasterCreation object
                    print(f"batch_id is ForeignKey, using object directly: {batch_obj}")
                    model_master_obj = batch_obj.model_stock_no
                    data_source = "ModelMasterCreation"
                elif isinstance(batch_id_obj, str):
                    # batch_id is a string field
                    full_batch_id_str = str(batch_id_obj)
                    print(f"batch_id is string: {full_batch_id_str}")
                    
                    # Extract only the BATCH part after " - " if it exists
                    if " - " in full_batch_id_str:
                        batch_id = full_batch_id_str.split(" - ", 1)[1]
                        print(f"Extracted batch_id: {batch_id}")
                    else:
                        batch_id = full_batch_id_str
                        print(f"Using full batch_id as no separator found: {batch_id}")
                    
                    # Find ModelMasterCreation by batch_id string
                    batch_obj = ModelMasterCreation.objects.filter(batch_id=batch_id).first()
                    if batch_obj:
                        print(f"Found batch_obj by batch_id: {batch_obj}")
                        model_master_obj = batch_obj.model_stock_no
                        data_source = "ModelMasterCreation"
                    else:
                        print(f"No ModelMasterCreation found for batch_id: {batch_id}")
                else:
                    print(f"Unknown batch_id type: {type(batch_id_obj)}")
            else:
                print(f"No TotalStockModel found with lot_id: {lot_id} or no batch_id attribute")

        # Handle plating_stk_no parameter
        elif plating_stk_no:
            print(f"🔍 Visual_AidView received plating_stk_no: {plating_stk_no}")
            
            # First, try to find ModelMasterCreation through ModelMaster
            model_master_obj = ModelMaster.objects.filter(plating_stk_no=plating_stk_no).first()
            print(f"Found ModelMaster by plating_stk_no: {model_master_obj}")
            
            if model_master_obj:
                # Try to find corresponding ModelMasterCreation
                batch_obj = ModelMasterCreation.objects.filter(model_stock_no=model_master_obj).first()
                
                if batch_obj:
                    print(f"Found batch_obj by ModelMaster: {batch_obj}")
                    data_source = "ModelMasterCreation"
                else:
                    print(f"No ModelMasterCreation found, using ModelMaster data directly")
                    data_source = "ModelMaster"
            else:
                print(f"No ModelMaster found with plating_stk_no: {plating_stk_no}")
                
        # Handle batch_id parameter
        elif batch_id:
            print(f"🔍 Visual_AidView received batch_id: {batch_id}")
            batch_obj = ModelMasterCreation.objects.filter(batch_id=batch_id).first()
            if batch_obj:
                print(f"Found batch_obj by batch_id: {batch_obj}")
                model_master_obj = batch_obj.model_stock_no
                data_source = "ModelMasterCreation"

        # Populate context based on available data
        if batch_obj or model_master_obj:
            if data_source == "ModelMasterCreation" and batch_obj:
                # Use ModelMasterCreation data (preferred)
                stock_for_images = batch_obj.plating_stk_no or getattr(batch_obj.model_stock_no, 'plating_stk_no', '')
                hover_payload = _get_model_hover_payload(
                    request,
                    stock_for_images,
                    fallback_images=batch_obj.images.all(),
                )
                image_urls = [img['url'] for img in hover_payload.get('images', [])] if hover_payload else []
                
                context.update({
                    'batch_id': batch_obj.batch_id,
                    'lot_id': lot_id,  # Include lot_id in context if it was provided
                    'image_urls': image_urls,
                    'plating_stk_no': batch_obj.plating_stk_no,
                    'changes': batch_obj.changes,
                    'polish_finish': batch_obj.polish_finish,
                    'version': batch_obj.version.version_internal if batch_obj.version else None,
                    'data_source': 'ModelMasterCreation'
                })
                model_master_instance = batch_obj.model_stock_no
                
            elif data_source == "ModelMaster" and model_master_obj:
                # Use ModelMaster data directly
                hover_payload = _get_model_hover_payload(
                    request,
                    model_master_obj.plating_stk_no,
                    fallback_images=model_master_obj.images.all(),
                )
                image_urls = [img['url'] for img in hover_payload.get('images', [])] if hover_payload else []
                
                context.update({
                    'batch_id': None,
                    'lot_id': lot_id,  # Include lot_id in context if it was provided
                    'image_urls': image_urls,
                    'plating_stk_no': model_master_obj.plating_stk_no,
                    'changes': getattr(model_master_obj, 'changes', 'N/A'),  # May not exist in ModelMaster
                    'polish_finish': model_master_obj.polish_finish,
                    'version': model_master_obj.version,
                    'brand': model_master_obj.brand,
                    'gender': model_master_obj.gender,
                    'ep_bath_type': model_master_obj.ep_bath_type,
                    'data_source': 'ModelMaster'
                })
                model_master_instance = model_master_obj

            print(f"Using {data_source} as data source")
            print(f"Context plating_stk_no: {context.get('plating_stk_no')}")

            # Get related versions and similar models
            if model_master_instance:
                # Get all ModelMaster objects with same model_no for variants
                masters = ModelMaster.objects.filter(model_no=model_master_instance.model_no)
                version_list = [m.version for m in masters if m.version]
                version_labels = [str(v) for v in version_list]
                context['modelmaster_versions'] = version_labels

                # Find similar models through LookLikeModel
                look_like_obj = LookLikeModel.objects.filter(same_plating_stk_no=model_master_instance).first()
                print(f"LookLikeModel object: {look_like_obj}")

                if look_like_obj:
                    # Get all related ModelMaster objects
                    related_model_masters = look_like_obj.plating_stk_no.all()
                    same_model_list = []
                    
                    for related_master in related_model_masters:
                        # Check if this ModelMaster has a corresponding ModelMasterCreation
                        has_creation = ModelMasterCreation.objects.filter(
                            model_stock_no=related_master
                        ).exists()
                        
                        model_info = {
                            'plating_stk_no': related_master.plating_stk_no,
                            'model_master_id': related_master.id,
                            'has_creation': has_creation,
                            'has_model_master': True,  # Always true since we're iterating ModelMaster objects
                            'version': related_master.version,
                            'polish_finish': str(related_master.polish_finish) if related_master.polish_finish else None,
                        }
                        
                        same_model_list.append(model_info)
                    
                    context['same_model_list'] = same_model_list
                    print(f"Same model list with ModelMaster details: {same_model_list}")
                else:
                    context['same_model_list'] = []
            else:
                context['same_model_list'] = []
                context['modelmaster_versions'] = []
        else:
            # Handle error cases
            if lot_id:
                context['error'] = f"No data found for lot_id: {lot_id}"
            elif plating_stk_no:
                context['error'] = f"No ModelMaster found with plating_stk_no: {plating_stk_no}"
            elif batch_id:
                context['error'] = f"No ModelMasterCreation found for batch_id: {batch_id}"
            else:
                context['error'] = "Please provide either lot_id, batch_id, or plating_stk_no parameter"

        return Response(context)
    
_STOCK_NO_RE = re.compile(r'^[A-Z0-9/_-]{1,50}$', re.IGNORECASE)
_STOCK_NO_CANONICAL_RE = re.compile(r'(\d{4})([A-Z])([A-Z])([A-Z])(\d{2})', re.IGNORECASE)

_IMAGE_VIEW_LABELS = {
    'TV': 'Top View',
    'FV': 'Front View',
    'FSV': 'Front Side View',
    'IV': 'Isometric View',
    'RSV': 'Right Side View',
    'LSV': 'Left Side View',
    'BV': 'Bottom View',
}

_IMAGE_VIEW_ORDER = {
    'TV': 0,
    'FV': 1,
    'FSV': 2,
    'IV': 3,
    'RSV': 4,
    'LSV': 5,
    'BV': 6,
}


def _parse_stock_no(raw_stock_no):
    stock_no = (raw_stock_no or '').strip().upper()
    if not stock_no or not _STOCK_NO_RE.match(stock_no):
        return None

    match = _STOCK_NO_CANONICAL_RE.search(stock_no)
    if not match:
        return None

    model_no, polish_code, plating_code, bath_code, version_code = match.groups()
    canonical = ''.join(match.groups()).upper()
    return {
        'raw': stock_no,
        'canonical': canonical,
        'model_no': model_no,
        'polish_code': polish_code.upper(),
        'plating_code': plating_code.upper(),
        'bath_code': bath_code.upper(),
        'version_code': version_code,
        'image_key': f'{model_no}xx{bath_code.lower()}{version_code}',
    }


def _detect_image_view(image_name):
    base_name = os.path.splitext(os.path.basename(image_name or ''))[0].upper()
    for suffix in ('RSV', 'LSV', 'FSV', 'TV', 'FV', 'IV', 'BV'):
        if base_name.endswith(suffix) or base_name.endswith('_' + suffix):
            return suffix, _IMAGE_VIEW_LABELS[suffix]
    return 'VIEW', 'View'


def _sort_model_images(images):
    return sorted(
        [img for img in images if getattr(img, 'master_image', None)],
        key=lambda img: (
            _IMAGE_VIEW_ORDER.get(_detect_image_view(img.master_image.name)[0], 99),
            os.path.basename(img.master_image.name).lower(),
        ),
    )


def _get_images_for_stock(stock_parts, model_master=None, fallback_images=None):
    keyed_images = ModelImage.objects.filter(
        master_image__icontains=stock_parts['image_key']
    )
    if keyed_images.exists():
        return _sort_model_images(keyed_images)

    if model_master:
        model_images = model_master.images.all()
        if model_images.exists():
            return _sort_model_images(model_images)

    if fallback_images is not None:
        fallback_images = list(fallback_images)
        if fallback_images:
            return _sort_model_images(fallback_images)

    model_images = ModelImage.objects.filter(master_image__icontains=stock_parts['model_no'])
    return _sort_model_images(model_images)


def _build_image_payload(request, images):
    payload = []
    for img in images:
        try:
            image_url = request.build_absolute_uri(img.master_image.url)
        except Exception:
            continue
        view_code, view_label = _detect_image_view(img.master_image.name)
        payload.append({
            'id': img.id,
            'url': image_url,
            'view_code': view_code,
            'view': view_label,
        })
    return payload


def _get_model_hover_payload(request, raw_stock_no, fallback_images=None):
    stock_parts = _parse_stock_no(raw_stock_no)
    if not stock_parts:
        return None

    model_master = (
        ModelMaster.objects
        .prefetch_related('images')
        .filter(plating_stk_no__iexact=stock_parts['canonical'])
        .first()
    )
    if not model_master:
        model_master = (
            ModelMaster.objects
            .prefetch_related('images')
            .filter(model_no=stock_parts['model_no'])
            .first()
        )

    if not model_master:
        return {
            'found': False,
            'stock_no': stock_parts['canonical'],
            'images': [],
            'preview_image': '',
            'visual_aid_url': '/adminportal/dp_visualaid/?plating_stk_no=' + stock_parts['canonical'],
        }

    images_payload = _build_image_payload(
        request,
        _get_images_for_stock(stock_parts, model_master=model_master, fallback_images=fallback_images),
    )
    preview = images_payload[0] if images_payload else {}

    return {
        'found': True,
        'stock_no': stock_parts['canonical'],
        'raw_stock_no': stock_parts['raw'],
        'model_no': model_master.model_no or stock_parts['model_no'],
        'version': stock_parts['version_code'],
        'bath_type': stock_parts['bath_code'],
        'ep_bath_type': model_master.ep_bath_type or '',
        'images': images_payload,
        'preview_image': preview.get('url', ''),
        'preview_view': preview.get('view', ''),
        'visual_aid_url': '/adminportal/dp_visualaid/?plating_stk_no=' + stock_parts['canonical'],
    }


@method_decorator(login_required(login_url='login-api'), name='dispatch')
class ModelHoverPreviewAPIView(APIView):
    """
    GET /adminportal/api/model-hover-preview/<stock_no>/
    Returns image URLs and metadata for the model identified by stock_no.
    Used by the global ttt-stock-hover.js popup system.
    All image URLs are built with request.build_absolute_uri() for IIS
    production compatibility (no localhost hardcoding).
    """
    renderer_classes = [JSONRenderer]

    def get(self, request, stock_no=None, format=None):
        stock_no = stock_no or request.GET.get('stock_no', '')
        payload = _get_model_hover_payload(request, stock_no)
        if payload is None:
            return Response({'error': 'Invalid stock number'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_200_OK)


@method_decorator(login_required(login_url='login-api'), name='dispatch')
class Rec_Visual_AidView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'ModelMaster/VisualAid.html'

    def get(self, request, batch_id=None, format=None):
        # Get parameters from URL or query string
        batch_id = batch_id or request.GET.get('batch_id')
        plating_stk_no = request.GET.get('plating_stk_no')

        context = {
            'user': request.user,
        }


        batch_obj = None
        model_master_obj = None
        data_source = None  # Track whether data comes from ModelMasterCreation or ModelMaster

        # Handle plating_stk_no parameter
        if plating_stk_no:
            print(f"🔍 Visual_AidView received plating_stk_no: {plating_stk_no}")
            
            # First, try to find RecoveryMasterCreation through ModelMaster
            model_master_obj = ModelMaster.objects.filter(plating_stk_no=plating_stk_no).first()
            print(f"Found ModelMaster by plating_stk_no: {model_master_obj}")
            
            if model_master_obj:
                # Try to find corresponding RecoveryMasterCreation
                batch_obj = RecoveryMasterCreation.objects.filter(model_stock_no=model_master_obj).first()
                
                if batch_obj:
                    print(f"Found batch_obj by ModelMaster: {batch_obj}")
                    data_source = "RecoveryMasterCreation"
                else:
                    print(f"No RecoveryMasterCreation found, using ModelMaster data directly")
                    data_source = "ModelMaster"
            else:
                print(f"No ModelMaster found with plating_stk_no: {plating_stk_no}")
                
        # Handle batch_id parameter
        elif batch_id:
            print(f"🔍 Visual_AidView received batch_id: {batch_id}")
            batch_obj = RecoveryMasterCreation.objects.filter(batch_id=batch_id).first()
            if batch_obj:
                print(f"Found batch_obj by batch_id: {batch_obj}")
                model_master_obj = batch_obj.model_stock_no
                data_source = "RecoveryMasterCreation"

        # Populate context based on available data
        if batch_obj or model_master_obj:
            if data_source == "RecoveryMasterCreation" and batch_obj:
                # Use RecoveryMasterCreation data (preferred)
                images = batch_obj.images.all()
                image_urls = [img.master_image.url for img in images if img.master_image]
                
                context.update({
                    'batch_id': batch_obj.batch_id,
                    'image_urls': image_urls,
                    'plating_stk_no': batch_obj.plating_stk_no,
                    'changes': batch_obj.changes,
                    'polish_finish': batch_obj.polish_finish,
                    'version': batch_obj.version.version_internal if batch_obj.version else None,
                    'data_source': 'ModelMasterCreation'
                })
                model_master_instance = batch_obj.model_stock_no
                
            elif data_source == "ModelMaster" and model_master_obj:
                # Use ModelMaster data directly
                images = model_master_obj.images.all()
                image_urls = [img.master_image.url for img in images if img.master_image]
                
                context.update({
                    'batch_id': None,
                    'image_urls': image_urls,
                    'plating_stk_no': model_master_obj.plating_stk_no,
                    'changes': getattr(model_master_obj, 'changes', 'N/A'),  # May not exist in ModelMaster
                    'polish_finish': model_master_obj.polish_finish,
                    'version': model_master_obj.version,
                    'brand': model_master_obj.brand,
                    'gender': model_master_obj.gender,
                    'ep_bath_type': model_master_obj.ep_bath_type,
                    'data_source': 'ModelMaster'
                })
                model_master_instance = model_master_obj

            print(f"Using {data_source} as data source")
            print(f"Context plating_stk_no: {context.get('plating_stk_no')}")

            # Get related versions and similar models
            if model_master_instance:
                # Get all ModelMaster objects with same model_no for variants
                masters = ModelMaster.objects.filter(model_no=model_master_instance.model_no)
                version_list = [m.version for m in masters if m.version]
                version_labels = [str(v) for v in version_list]
                context['modelmaster_versions'] = version_labels

                # Find similar models through LookLikeModel
                look_like_obj = LookLikeModel.objects.filter(same_plating_stk_no=model_master_instance).first()
                print(f"LookLikeModel object: {look_like_obj}")

                if look_like_obj:
                    # Get all related ModelMaster objects
                    related_model_masters = look_like_obj.plating_stk_no.all()
                    same_model_list = []
                    
                    for related_master in related_model_masters:
                        # Check if this ModelMaster has a corresponding RecoveryMasterCreation
                        has_creation = RecoveryMasterCreation.objects.filter(
                            model_stock_no=related_master
                        ).exists()
                        
                        model_info = {
                            'plating_stk_no': related_master.plating_stk_no,
                            'model_master_id': related_master.id,
                            'has_creation': has_creation,
                            'has_model_master': True,  # Always true since we're iterating ModelMaster objects
                            'version': related_master.version,
                            'polish_finish': str(related_master.polish_finish) if related_master.polish_finish else None,
                        }
                        
                        same_model_list.append(model_info)
                    
                    context['same_model_list'] = same_model_list
                    print(f"Same model list with ModelMaster details: {same_model_list}")
                else:
                    context['same_model_list'] = []
            else:
                context['same_model_list'] = []
                context['modelmaster_versions'] = []
        else:
            # Handle error cases
            if plating_stk_no:
                context['error'] = f"No ModelMaster found with plating_stk_no: {plating_stk_no}"
            elif batch_id:
                context['error'] = f"No ModelMasterCreation found for batch_id: {batch_id}"
            else:
                context['error'] = "Please provide either batch_id or plating_stk_no parameter"

        return Response(context)

@method_decorator(login_required(login_url='login-api'), name='dispatch')
class Other_Visual_AidView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'ModelMaster/VisualAid.html'

    def get(self, request, batch_id=None, format=None):
        # Get parameters from URL or query string
        batch_id = batch_id or request.GET.get('batch_id')
        plating_stk_no = request.GET.get('plating_stk_no')
        model_no = request.GET.get('model_no')  # Add this new parameter

        context = {
            'user': request.user,
        }

        # Import required models
        from modelmasterapp.models import ModelMasterCreation, LookLikeModel, ModelMaster

        batch_obj = None
        model_master_obj = None
        data_source = None

        # Handle model_no parameter (NEW)
        if model_no:
            print(f"🔍 Visual_AidView received model_no: {model_no}")
            
            # Find ModelMaster by model_no (first match)
            model_master_obj = ModelMaster.objects.filter(model_no__startswith=model_no).first()
            print(f"Found ModelMaster by model_no: {model_master_obj}")
            
            if model_master_obj:
                # Try to find corresponding ModelMasterCreation
                batch_obj = ModelMasterCreation.objects.filter(model_stock_no=model_master_obj).first()
                
                if batch_obj:
                    print(f"Found batch_obj by ModelMaster: {batch_obj}")
                    data_source = "ModelMasterCreation"
                else:
                    print(f"No ModelMasterCreation found, using ModelMaster data directly")
                    data_source = "ModelMaster"
            else:
                print(f"No ModelMaster found with model_no: {model_no}")

        # Handle plating_stk_no parameter (EXISTING)
        elif plating_stk_no:
            print(f"🔍 Visual_AidView received plating_stk_no: {plating_stk_no}")
            
            # First, try to find ModelMasterCreation through ModelMaster
            model_master_obj = ModelMaster.objects.filter(plating_stk_no=plating_stk_no).first()
            print(f"Found ModelMaster by plating_stk_no: {model_master_obj}")
            
            if model_master_obj:
                # Try to find corresponding ModelMasterCreation
                batch_obj = ModelMasterCreation.objects.filter(model_stock_no=model_master_obj).first()
                
                if batch_obj:
                    print(f"Found batch_obj by ModelMaster: {batch_obj}")
                    data_source = "ModelMasterCreation"
                else:
                    print(f"No ModelMasterCreation found, using ModelMaster data directly")
                    data_source = "ModelMaster"
            else:
                print(f"No ModelMaster found with plating_stk_no: {plating_stk_no}")
                
        # Handle batch_id parameter (EXISTING)
        elif batch_id:
            print(f"🔍 Visual_AidView received batch_id: {batch_id}")
            batch_obj = ModelMasterCreation.objects.filter(batch_id=batch_id).first()
            if batch_obj:
                print(f"Found batch_obj by batch_id: {batch_obj}")
                model_master_obj = batch_obj.model_stock_no
                data_source = "ModelMasterCreation"

        # Populate context based on available data
        if batch_obj or model_master_obj:
            if data_source == "ModelMasterCreation" and batch_obj:
                # Use ModelMasterCreation data (preferred)
                images = batch_obj.images.all()
                image_urls = [img.master_image.url for img in images if img.master_image]
                
                context.update({
                    'batch_id': batch_obj.batch_id,
                    'image_urls': image_urls,
                    'plating_stk_no': batch_obj.plating_stk_no,
                    'changes': batch_obj.changes,
                    'polish_finish': batch_obj.polish_finish,
                    'version': batch_obj.version.version_internal if batch_obj.version else None,
                    'data_source': 'ModelMasterCreation'
                })
                model_master_instance = batch_obj.model_stock_no
                
            elif data_source == "ModelMaster" and model_master_obj:
                # Use ModelMaster data directly
                images = model_master_obj.images.all()
                image_urls = [img.master_image.url for img in images if img.master_image]
                
                context.update({
                    'batch_id': None,
                    'image_urls': image_urls,
                    'plating_stk_no': model_master_obj.plating_stk_no,
                    'changes': getattr(model_master_obj, 'changes', 'N/A'),  # May not exist in ModelMaster
                    'polish_finish': model_master_obj.polish_finish,
                    'version': model_master_obj.version,
                    'brand': model_master_obj.brand,
                    'gender': model_master_obj.gender,
                    'ep_bath_type': model_master_obj.ep_bath_type,
                    'data_source': 'ModelMaster'
                })
                model_master_instance = model_master_obj

            print(f"Using {data_source} as data source")
            print(f"Context plating_stk_no: {context.get('plating_stk_no')}")

            # Get related versions and similar models
            if model_master_instance:
                # Get all ModelMaster objects with same model_no for variants
                masters = ModelMaster.objects.filter(model_no=model_master_instance.model_no)
                version_list = [m.version for m in masters if m.version]
                version_labels = [str(v) for v in version_list]
                context['modelmaster_versions'] = version_labels

                # Find similar models through LookLikeModel
                look_like_obj = LookLikeModel.objects.filter(same_plating_stk_no=model_master_instance).first()
                print(f"LookLikeModel object: {look_like_obj}")

                if look_like_obj:
                    # Get all related ModelMaster objects
                    related_model_masters = look_like_obj.plating_stk_no.all()
                    same_model_list = []
                    
                    for related_master in related_model_masters:
                        # Check if this ModelMaster has a corresponding ModelMasterCreation
                        has_creation = ModelMasterCreation.objects.filter(
                            model_stock_no=related_master
                        ).exists()
                        
                        model_info = {
                            'plating_stk_no': related_master.plating_stk_no,
                            'model_master_id': related_master.id,
                            'has_creation': has_creation,
                            'has_model_master': True,  # Always true since we're iterating ModelMaster objects
                            'version': related_master.version,
                            'polish_finish': str(related_master.polish_finish) if related_master.polish_finish else None,
                        }
                        
                        same_model_list.append(model_info)
                    
                    context['same_model_list'] = same_model_list
                    print(f"Same model list with ModelMaster details: {same_model_list}")
                else:
                    context['same_model_list'] = []
            else:
                context['same_model_list'] = []
                context['modelmaster_versions'] = []
        else:
            # Handle error cases
            if plating_stk_no:
                context['error'] = f"No ModelMaster found with plating_stk_no: {plating_stk_no}"
            elif batch_id:
                context['error'] = f"No ModelMasterCreation found for batch_id: {batch_id}"
            else:
                context['error'] = "Please provide either batch_id or plating_stk_no parameter"

        return Response(context)



from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class DP_ViewmasterView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'ModelMaster/viewmasters.html'

    def get_paginated_data(self, queryset, page_param, items_per_page=10):
        """Helper method to paginate queryset"""
        paginator = Paginator(queryset, items_per_page)
        page = self.request.GET.get(page_param, 1)
        
        try:
            paginated_items = paginator.page(page)
        except PageNotAnInteger:
            paginated_items = paginator.page(1)
        except EmptyPage:
            paginated_items = paginator.page(paginator.num_pages)
        
        return paginated_items

    def get(self, request, format=None):
        # Check if this is an AJAX request for pagination
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return self.handle_ajax_pagination(request)
        
        # Fetch all data with pagination
        model_masters = self.get_paginated_data(ModelMaster.objects.all(), 'model_page')
        polish_finishes = self.get_paginated_data(PolishFinishType.objects.all(), 'polish_page')
        plating_colors = self.get_paginated_data(Plating_Color.objects.all(), 'plating_page')
        tray_types = self.get_paginated_data(TrayType.objects.all(), 'tray_page')
        locations = self.get_paginated_data(Location.objects.all(), 'vendor_page')
        model_images = self.get_paginated_data(ModelImage.objects.all(), 'images_page')
        tray_ids = self.get_paginated_data(TrayId.objects.all(), 'trayid_page')
        categories = self.get_paginated_data(Category.objects.all(), 'category_page')
        ip_rejections = self.get_paginated_data(IP_Rejection_Table.objects.all(), 'iprejection_page')
        nickel_rejections = self.get_paginated_data(Nickel_QC_Rejection_Table.objects.all(), 'nickelrejection_page')
        brassiqf_rejections = self.get_paginated_data(Brass_QC_Rejection_Table.objects.all(), 'brassiqf_page')

        context = {
            'model_masters': model_masters,
            'polish_finishes': polish_finishes,
            'plating_colors': plating_colors,
            'tray_types': tray_types,
            'locations': locations,
            'model_images': model_images,
            'tray_ids': tray_ids,
            'categories': categories,
            'ip_rejections': ip_rejections,
            'nickel_rejections': nickel_rejections,
            'brassiqf_rejections': brassiqf_rejections,
        }
        return Response(context)

    def handle_ajax_pagination(self, request):
        """Handle AJAX pagination requests"""
        tab_name = request.GET.get('tab')
        page = request.GET.get('page', 1)
        
        # Map tab names to models
        tab_mapping = {
            'model': ModelMaster.objects.all(),
            'polish': PolishFinishType.objects.all(),
            'plating': Plating_Color.objects.all(),
            'tray': TrayType.objects.all(),
            'vendor': Location.objects.all(),
            'images': ModelImage.objects.all(),
            'trayid': TrayId.objects.all(),
            'category': Category.objects.all(),
            'iprejection': IP_Rejection_Table.objects.all(),
            'nickelrejection': Nickel_QC_Rejection_Table.objects.all(),
            'brassiqf': Brass_QC_Rejection_Table.objects.all(),
        }
        
        if tab_name not in tab_mapping:
            return JsonResponse({'error': 'Invalid tab'}, status=400)
        
        queryset = tab_mapping[tab_name]
        
        # Paginate the data
        paginator = Paginator(queryset, 10)
        try:
            paginated_data = paginator.page(page)
        except PageNotAnInteger:
            paginated_data = paginator.page(1)
        except EmptyPage:
            paginated_data = paginator.page(paginator.num_pages)
        
        # Generate HTML for the specific tab
        html_data = self.generate_table_rows(tab_name, paginated_data)
        
        return JsonResponse({
            'html': html_data,
            'current_page': paginated_data.number,
            'total_pages': paginated_data.paginator.num_pages,
            'total_items': paginated_data.paginator.count,
            'has_previous': paginated_data.has_previous(),
            'has_next': paginated_data.has_next(),
            'previous_page': paginated_data.previous_page_number() if paginated_data.has_previous() else None,
            'next_page': paginated_data.next_page_number() if paginated_data.has_next() else None,
        })

    def generate_table_rows(self, tab_name, paginated_data):
        """Generate HTML table rows for specific tab data.

        Security: every user-entered value is passed through escape() so stored
        HTML (e.g. <script>, <img>) is displayed as plain text, never rendered.
        """
        html_rows = ""

        if tab_name == 'model':
            for i, obj in enumerate(paginated_data, start=paginated_data.start_index()):
                html_rows += f"""
                <tr>
                    <td><input type="checkbox" class="select-checkbox model-checkbox" name="selected_ids" value="{obj.id}"></td>
                    <td>{i}</td>
                    <td>{obj.date_time.strftime('%Y-%m-%d')}</td>
                    <td>{escape(obj.model_no)}</td>
                    <td>{escape(obj.plating_stk_no)}</td>
                    <td>{escape(obj.polish_finish.polish_finish) if obj.polish_finish else '-'}</td>
                    <td>{escape(obj.ep_bath_type)}</td>
                    <td>{escape(obj.version)}</td>
                    <td>{escape(obj.tray_type.tray_type) if obj.tray_type else '-'}</td>
                    <td>{escape(obj.tray_type.tray_capacity) if obj.tray_type else '-'}</td>
                </tr>
                """
        elif tab_name == 'polish':
            for i, obj in enumerate(paginated_data, start=paginated_data.start_index()):
                html_rows += f"""
                <tr>
                    <td><input type="checkbox" class="select-checkbox polish-checkbox" name="selected_ids" value="{obj.id}"></td>
                    <td>{i}</td>
                    <td>{obj.date_time.strftime('%Y-%m-%d')}</td>
                    <td>{escape(obj.polish_finish)}</td>
                    <td>{escape(obj.polish_internal)}</td>
                </tr>
                """
        elif tab_name == 'plating':
            for i, obj in enumerate(paginated_data, start=paginated_data.start_index()):
                html_rows += f"""
                <tr>
                    <td><input type="checkbox" class="select-checkbox plating-checkbox" name="selected_ids" value="{obj.id}"></td>
                    <td>{i}</td>
                    <td>{obj.date_time.strftime('%Y-%m-%d')}</td>
                    <td>{escape(obj.plating_color)}</td>
                    <td>{escape(obj.plating_color_internal)}</td>
                </tr>
                """
        elif tab_name == 'tray':
            for i, obj in enumerate(paginated_data, start=paginated_data.start_index()):
                html_rows += f"""
                <tr>
                    <td><input type="checkbox" class="select-checkbox tray-checkbox" name="selected_ids" value="{obj.id}"></td>
                    <td>{i}</td>
                    <td>{obj.date_time.strftime('%Y-%m-%d')}</td>
                    <td>{escape(obj.tray_type)}</td>
                    <td>{escape(obj.tray_capacity)}</td>
                </tr>
                """
        elif tab_name == 'vendor':
            for i, obj in enumerate(paginated_data, start=paginated_data.start_index()):
                html_rows += f"""
                <tr>
                    <td><input type="checkbox" class="select-checkbox vendor-checkbox" name="selected_ids" value="{obj.id}"></td>
                    <td>{i}</td>
                    <td>{obj.date_time.strftime('%Y-%m-%d')}</td>
                    <td>{escape(obj.location_name)}</td>
                </tr>
                """
        elif tab_name == 'images':
            for i, obj in enumerate(paginated_data, start=paginated_data.start_index()):
                image_name = escape(obj.master_image.name) if obj.master_image else '-'
                image_url = f'<a href="{escape(obj.master_image.url)}" target="_blank">{escape(obj.master_image.url)}</a>' if obj.master_image else '-'
                html_rows += f"""
                <tr>
                    <td><input type="checkbox" class="select-checkbox images-checkbox" name="selected_ids" value="{obj.id}"></td>
                    <td>{i}</td>
                    <td>{obj.date_time.strftime('%Y-%m-%d')}</td>
                    <td>{image_name}</td>
                    <td>{image_url}</td>
                </tr>
                """
        elif tab_name == 'trayid':
            for i, obj in enumerate(paginated_data, start=paginated_data.start_index()):
                html_rows += f"""
                <tr>
                    <td><input type="checkbox" class="select-checkbox trayid-checkbox" name="selected_ids" value="{obj.id}"></td>
                    <td>{i}</td>
                    <td>{obj.date.strftime('%Y-%m-%d')}</td>
                    <td>{escape(obj.tray_id)}</td>
                    <td>{escape(obj.tray_type)}</td>
                    <td>{escape(obj.tray_capacity)}</td>
                </tr>
                """
        elif tab_name == 'category':
            for i, obj in enumerate(paginated_data, start=paginated_data.start_index()):
                html_rows += f"""
                <tr>
                    <td><input type="checkbox" class="select-checkbox category-checkbox" name="selected_ids" value="{obj.id}"></td>
                    <td>{i}</td>
                    <td>{obj.date_time.strftime('%Y-%m-%d')}</td>
                    <td>{escape(obj.category_name)}</td>
                </tr>
                """
        elif tab_name == 'iprejection':
            for i, obj in enumerate(paginated_data, start=paginated_data.start_index()):
                html_rows += f"""
                <tr>
                    <td><input type="checkbox" class="select-checkbox iprejection-checkbox" name="selected_ids" value="{obj.id}"></td>
                    <td>{i}</td>
                    <td>{obj.date.strftime('%Y-%m-%d')}</td>
                    <td>{escape(obj.rejection_reason_id)}</td>
                    <td>{escape(obj.rejection_reason)}</td>
                </tr>
                """
        elif tab_name == 'brassiqf':
            for i, obj in enumerate(paginated_data, start=paginated_data.start_index()):
                html_rows += f"""
                <tr>
                    <td><input type="checkbox" class="select-checkbox brassiqf-checkbox" name="selected_ids" value="{obj.id}"></td>
                    <td>{i}</td>
                    <td>{obj.date_time.strftime('%Y-%m-%d')}</td>
                    <td>{escape(obj.rejection_reason_id)}</td>
                    <td>{escape(obj.rejection_reason)}</td>
                </tr>
                """
        elif tab_name == 'nickelrejection':
            for i, obj in enumerate(paginated_data, start=paginated_data.start_index()):
                html_rows += f"""
                <tr>
                    <td><input type="checkbox" class="select-checkbox nickelrejection-checkbox" name="selected_ids" value="{obj.id}"></td>
                    <td>{i}</td>
                    <td>{obj.date_time.strftime('%Y-%m-%d')}</td>
                    <td>{escape(obj.rejection_reason)}</td>
                </tr>
                """
        
        if not html_rows:
            # Return appropriate empty message based on tab
            col_count = {
                'model': 10, 'polish': 5, 'plating': 5, 'tray': 5, 'vendor': 4,
                'images': 5, 'trayid': 6, 'category': 4, 'iprejection': 6,
                'brassiqf': 5, 'nickelrejection': 4
            }
            html_rows = f'<tr><td colspan="{col_count.get(tab_name, 5)}">No records found.</td></tr>'
        
        return html_rows

    def post(self, request, format=None):
        """Handle deletion of selected items"""
        try:
            action = request.POST.get('action')
            if action != 'delete':
                return JsonResponse({'success': False, 'error': 'Invalid action'})

            tab_name = request.POST.get('tab_name')
            selected_ids = request.POST.getlist('selected_ids')

            if not selected_ids:
                return JsonResponse({'success': False, 'error': 'No items selected'})

            # Map tab names to models
            model_mapping = {
                'model': ModelMaster,
                'polish': PolishFinishType,
                'plating': Plating_Color,
                'tray': TrayType,
                'vendor': Location,
                'images': ModelImage,
                'trayid': TrayId,
                'category': Category,
                'iprejection': IP_Rejection_Table,  
                'brassiqf': Brass_QC_Rejection_Table,
                'nickelrejection': Nickel_QC_Rejection_Table,
            }

            if tab_name not in model_mapping:
                return JsonResponse({'success': False, 'error': 'Invalid tab name'})

            model_class = model_mapping[tab_name]
            
            # Delete selected items
            deleted_count = 0
            for item_id in selected_ids:
                try:
                    if tab_name == 'brassiqf':
                        # Delete from all Brass/IQF tables by rejection_reason_id
                        obj = get_object_or_404(Brass_QC_Rejection_Table, id=item_id)
                        reason_id = obj.rejection_reason_id
                        obj.delete()
                        Brass_QC_Rejection_Table.objects.filter(rejection_reason_id=reason_id).delete()  
                        Brass_Audit_Rejection_Table.objects.filter(rejection_reason_id=reason_id).delete()
                        IQF_Rejection_Table.objects.filter(rejection_reason_id=reason_id).delete()
                        deleted_count += 1
                    elif tab_name == 'nickelrejection':
                        # Delete from both Nickel tables by rejection_reason text
                        obj = get_object_or_404(Nickel_QC_Rejection_Table, id=item_id)
                        reason_text = obj.rejection_reason
                        obj.delete()
                        Nickel_Audit_Rejection_Table.objects.filter(rejection_reason=reason_text).delete()
                        deleted_count += 1
                    else:
                        item = get_object_or_404(model_class, id=item_id)
                        item.delete()
                        deleted_count += 1
                except Exception as e:
                    logger.error(f"Error deleting item {item_id}: {str(e)}", exc_info=True)
                    continue

            return JsonResponse({
                'success': True, 
                'deleted_count': deleted_count,
                'message': f'Successfully deleted {deleted_count} item(s)'
            })

        except Exception as e:
            return JsonResponse({
                'success': False, 
                'error': 'Unable to process the request. Please verify the submitted data and try again.'
            })

@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class DP_ModelmasterView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'ModelMaster/dp_modelmaster.html'

    def get(self, request, format=None):
        # Get all data for dropdowns and existing records
        context = {
            'polish_finishes': PolishFinishType.objects.all(),
            'plating_colors': Plating_Color.objects.all(),
            'tray_types': TrayType.objects.all(),
            'vendors': Vendor.objects.all(),
            'model_images': ModelImage.objects.all(),
            'model_masters': ModelMaster.objects.all(),
            'versions': Version.objects.all(),
            # Add categories for dropdown
            'categories': Category.objects.all(),
        }
        return Response(context)

    def post(self, request, format=None):
        # Handle Category form submission
        if 'category_name' in request.data:
            # Add current datetime to the request data
            data = request.data.copy()
            data['date_time'] = timezone.now()
            
            serializer = CategorySerializer(data=data)
            if serializer.is_valid():
                category = serializer.save()
                # Redirect to same page with category_name in query params
                from django.shortcuts import redirect
                return redirect(f"/adminportal/dp_modelmaster/?category_name={category.category_name}")
            else:
                # Re-render page with errors
                context = {
                    'polish_finishes': PolishFinishType.objects.all(),
                    'plating_colors': Plating_Color.objects.all(),
                    'tray_types': TrayType.objects.all(),
                    'vendors': Vendor.objects.all(),
                    'model_images': ModelImage.objects.all(),
                    'model_masters': ModelMaster.objects.all(),
                    'versions': Version.objects.all(),
                    'categories': Category.objects.all(),
                    'category_form_errors': serializer.errors,
                }
                return Response(context)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class PolishFinishAPIView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request):
        """Get all Polish Finish types"""
        polish_finishes = PolishFinishType.objects.all()
        serializer = PolishFinishTypeSerializer(polish_finishes, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        """Create new Polish Finish type"""
        try:
            # Add current datetime to the request data
            data = request.data.copy()
            data['date_time'] = timezone.now()
            
            serializer = PolishFinishTypeSerializer(data=data)
            if serializer.is_valid():
                polish_finish = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Polish finish created successfully!',
                    'data': PolishFinishTypeSerializer(polish_finish).data
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        """Update Polish Finish type"""
        try:
            polish_finish = get_object_or_404(PolishFinishType, pk=pk)
            serializer = PolishFinishTypeSerializer(polish_finish, data=request.data)
            if serializer.is_valid():
                updated_polish_finish = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Polish finish updated successfully!',
                    'data': PolishFinishTypeSerializer(updated_polish_finish).data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        """Delete Polish Finish type"""
        try:
            polish_finish = get_object_or_404(PolishFinishType, pk=pk)
            polish_finish.delete()
            return Response({
                'success': True,
                'message': 'Polish finish deleted successfully!'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class PlatingColorAPIView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request):
        """Get all Plating Colors"""
        plating_colors = Plating_Color.objects.all()
        serializer = PlatingColorSerializer(plating_colors, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        """Create new Plating Color"""
        try:
            # Add current datetime to the request data
            data = request.data.copy()
            data['date_time'] = timezone.now()
            
            serializer = PlatingColorSerializer(data=data)
            if serializer.is_valid():
                plating_color = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Plating color created successfully!',
                    'data': PlatingColorSerializer(plating_color).data
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        """Update Plating Color"""
        try:
            plating_color = get_object_or_404(Plating_Color, pk=pk)
            serializer = PlatingColorSerializer(plating_color, data=request.data)
            if serializer.is_valid():
                updated_plating_color = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Plating color updated successfully!',
                    'data': PlatingColorSerializer(updated_plating_color).data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        """Delete Plating Color"""
        try:
            plating_color = get_object_or_404(Plating_Color, pk=pk)
            plating_color.delete()
            return Response({
                'success': True,
                'message': 'Plating color deleted successfully!'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class TrayTypeAPIView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request):
        """Get all Tray Types"""
        tray_types = TrayType.objects.all()
        serializer = TrayTypeSerializer(tray_types, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        """Create new Tray Type"""
        try:
            # Add current datetime to the request data
            data = request.data.copy()
            data['date_time'] = timezone.now()
            
            serializer = TrayTypeSerializer(data=data)
            if serializer.is_valid():
                tray_type = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Tray type created successfully!',
                    'data': TrayTypeSerializer(tray_type).data
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        """Update Tray Type"""
        try:
            tray_type = get_object_or_404(TrayType, pk=pk)
            serializer = TrayTypeSerializer(tray_type, data=request.data)
            if serializer.is_valid():
                updated_tray_type = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Tray type updated successfully!',
                    'data': TrayTypeSerializer(updated_tray_type).data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        """Delete Tray Type"""
        try:
            tray_type = get_object_or_404(TrayType, pk=pk)
            tray_type.delete()
            return Response({
                'success': True,
                'message': 'Tray type deleted successfully!'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class ModelImageAPIView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request):
        """Get all Model Images"""
        model_images = ModelImage.objects.all()
        serializer = ModelImageSerializer(model_images, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    # Allowed image MIME types and extensions (Issue #24)
    _ALLOWED_IMAGE_MIME = frozenset({
        'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp',
    })
    _ALLOWED_IMAGE_EXT = frozenset({
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp',
    })
    # Dangerous intermediate extensions that must not appear anywhere in the filename
    _DANGEROUS_EXT = frozenset({
        '.exe', '.php', '.sh', '.bat', '.cmd', '.ps1', '.js', '.py',
        '.rb', '.pl', '.asp', '.aspx', '.jsp', '.cgi', '.dll', '.so',
    })

    @staticmethod
    def _validate_image_file(image):
        """Returns an error string, or None if the file is acceptable."""
        import os
        name = image.name or ''
        _, ext = os.path.splitext(name.lower())
        # Block dangerous intermediate extensions (e.g. sample.exe.png)
        stem = os.path.splitext(name)[0].lower()
        for dext in ModelImageAPIView._DANGEROUS_EXT:
            if stem.endswith(dext) or f'{dext}.' in stem:
                return f'File "{name}" contains a disallowed intermediate extension.'
        if ext not in ModelImageAPIView._ALLOWED_IMAGE_EXT:
            return f'File extension "{ext}" is not allowed. Allowed: jpg, jpeg, png, gif, webp, bmp.'
        content_type = getattr(image, 'content_type', '') or ''
        if content_type and content_type not in ModelImageAPIView._ALLOWED_IMAGE_MIME:
            return f'File type "{content_type}" is not allowed. Only image files are accepted.'
        return None

    def post(self, request):
        """Upload new Model Images"""
        try:
            # Handle multiple image uploads
            uploaded_images = []

            if 'images' in request.FILES:
                images = request.FILES.getlist('images')
                for image in images:
                    # --- File type validation (Issue #24) ---
                    err = self._validate_image_file(image)
                    if err:
                        return Response({
                            'success': False,
                            'message': err,
                        }, status=status.HTTP_400_BAD_REQUEST)

                    image_data = {
                        'master_image': image,
                        'date_time': timezone.now()
                    }
                    serializer = ModelImageSerializer(data=image_data)
                    if serializer.is_valid():
                        model_image = serializer.save()
                        uploaded_images.append(ModelImageSerializer(model_image).data)
                    else:
                        return Response({
                            'success': False,
                            'message': 'Invalid image file',
                            'errors': serializer.errors
                        }, status=status.HTTP_400_BAD_REQUEST)

                return Response({
                    'success': True,
                    'message': f'{len(uploaded_images)} image(s) uploaded successfully!',
                    'data': uploaded_images
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'No images provided'
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.exception('ModelImageAPIView.post upload error')
            return Response({
                'success': False,
                'message': 'An internal error occurred while uploading. Please contact the administrator.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        """Delete Model Image"""
        try:
            model_image = get_object_or_404(ModelImage, pk=pk)
            # Delete the actual file
            if model_image.master_image:
                model_image.master_image.delete()
            model_image.delete()
            return Response({
                'success': True,
                'message': 'Model image deleted successfully!'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class ModelMasterAPIView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request):
        """Get all Model Masters"""
        model_masters = ModelMaster.objects.all()
        serializer = ModelMasterSerializer(model_masters, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        """Create new Model Master"""
        try:
            # Add current datetime to the request data
            data = request.data.copy()
            data['date_time'] = timezone.now()
            
            serializer = ModelMasterSerializer(data=data)
            if serializer.is_valid():
                model_master = serializer.save()
                
                # Handle many-to-many relationship for images
                if 'images' in request.data:
                    image_ids = request.data.getlist('images') if hasattr(request.data, 'getlist') else request.data.get('images', [])
                    if image_ids:
                        model_master.images.set(image_ids)
                
                return Response({
                    'success': True,
                    'message': 'Model master created successfully!',
                    'data': ModelMasterSerializer(model_master).data
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        """Update Model Master"""
        try:
            model_master = get_object_or_404(ModelMaster, pk=pk)
            serializer = ModelMasterSerializer(model_master, data=request.data)
            if serializer.is_valid():
                updated_model_master = serializer.save()
                
                # Handle many-to-many relationship for images
                if 'images' in request.data:
                    image_ids = request.data.getlist('images') if hasattr(request.data, 'getlist') else request.data.get('images', [])
                    updated_model_master.images.set(image_ids)
                
                return Response({
                    'success': True,
                    'message': 'Model master updated successfully!',
                    'data': ModelMasterSerializer(updated_model_master).data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        """Delete Model Master"""
        try:
            model_master = get_object_or_404(ModelMaster, pk=pk)
            model_master.delete()
            return Response({
                'success': True,
                'message': 'Model master deleted successfully!'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class LocationAPIView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request):
        """Get all Locations"""
        locations = Location.objects.all()
        serializer = LocationSerializer(locations, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        """Create new Location"""
        try:
            # Add current datetime to the request data
            data = request.data.copy()
            data['date_time'] = timezone.now()
            
            serializer = LocationSerializer(data=data)
            if serializer.is_valid():
                location = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Location created successfully!',
                    'data': LocationSerializer(location).data
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        """Update Location"""
        try:
            location = get_object_or_404(Location, pk=pk)
            serializer = LocationSerializer(location, data=request.data)
            if serializer.is_valid():
                updated_location = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Location updated successfully!',
                    'data': LocationSerializer(updated_location).data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        """Delete Location"""
        try:
            location = get_object_or_404(Location, pk=pk)
            location.delete()
            return Response({
                'success': True,
                'message': 'Location deleted successfully!'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class TrayIdAPIView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request):
        """Get all Tray IDs"""
        tray_ids = TrayId.objects.all()
        serializer = TrayIdSerializer(tray_ids, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        """Create new Tray ID"""
        try:
            # Convert tray_type to pk if needed (from string to int)
            data = request.data.copy()
            data['date'] = timezone.now()  # Add datetime
            
            if isinstance(data.get('tray_type'), str) and data.get('tray_type').isdigit():
                data['tray_type'] = int(data['tray_type'])
            serializer = TrayIdSerializer(data=data)
            if serializer.is_valid():
                tray_id = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Tray ID created successfully!',
                    'data': TrayIdSerializer(tray_id).data
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        """Update Tray ID"""
        try:
            tray_id_obj = get_object_or_404(TrayId, pk=pk)
            data = request.data.copy()
            if isinstance(data.get('tray_type'), str) and data.get('tray_type').isdigit():
                data['tray_type'] = int(data['tray_type'])
            serializer = TrayIdSerializer(tray_id_obj, data=data)
            if serializer.is_valid():
                updated_tray_id = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Tray ID updated successfully!',
                    'data': TrayIdSerializer(updated_tray_id).data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ── Consolidated Tray Management API ─────────────────────────────────────────
TRAY_FORMAT_PATTERN = re.compile(r'^(JB-A|JR-A|JD-A|JL-A|NB-A|NR-A|ND-A|NL-A)\d{5}$')

@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class TrayManageAPIView(APIView):
    """
    Single consolidated API for all Tray ID management operations.
    POST /api/tray/manage/
    Actions: add, delete, delete_all, list
    """
    renderer_classes = [JSONRenderer]

    def post(self, request):
        action = request.data.get('action', '').strip().lower()
        tray_ids = request.data.get('tray_ids', [])
        force_delete = request.data.get('force_delete', False)

        logger.info(f"[TrayManage] action={action}, tray_ids={tray_ids}, force_delete={force_delete}, user={request.user}")

        if action == 'list':
            return self._list_trays(request)
        elif action == 'add':
            return self._add_trays(request, tray_ids)
        elif action == 'delete':
            return self._delete_trays(request, tray_ids, force_delete)
        elif action == 'delete_all':
            return self._delete_all_trays(request, force_delete)
        elif action == 'restore':
            return self._restore_trays(request, tray_ids)
        else:
            return Response({
                'status': 'error',
                'message': f'Invalid action: "{action}". Valid actions: add, delete, delete_all, list, restore',
                'data': [],
                'conflicts': []
            }, status=status.HTTP_400_BAD_REQUEST)

    def _list_trays(self, request):
        """List all tray IDs with their status."""
        trays = TrayId.objects.all().order_by('tray_id')
        data = []
        for t in trays:
            is_occupied = bool(t.batch_id_id) or bool(t.lot_id)
            data.append({
                'id': t.pk,
                'tray_id': t.tray_id,
                'tray_type': t.tray_type or '',
                'tray_capacity': t.tray_capacity,
                'is_occupied': is_occupied,
                'lot_id': t.lot_id or '',
                'created': t.date.strftime('%Y-%m-%d %H:%M') if t.date else '',
            })
        logger.info(f"[TrayManage] Listed {len(data)} trays")
        return Response({
            'status': 'success',
            'message': f'{len(data)} tray(s) found',
            'data': data,
            'conflicts': []
        })

    def _add_trays(self, request, tray_ids):
        """Add one or more tray IDs with full backend validation."""
        if not tray_ids or not isinstance(tray_ids, list):
            return Response({
                'status': 'error',
                'message': 'tray_ids must be a non-empty list.',
                'data': [],
                'conflicts': []
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate all tray IDs first
        errors = []
        valid_trays = []
        duplicates_in_request = set()

        for idx, raw_id in enumerate(tray_ids):
            tid = str(raw_id).strip().upper()

            # Format validation
            if not TRAY_FORMAT_PATTERN.match(tid):
                errors.append(f'"{raw_id}" has invalid format. Expected prefix (JB-A, JR-A, JD-A, JL-A, NB-A, NR-A, ND-A, NL-A) + 5 digits.')
                continue

            # Duplicate within same request
            if tid in duplicates_in_request:
                errors.append(f'"{tid}" is duplicated in this request.')
                continue
            duplicates_in_request.add(tid)

            # Duplicate in database
            if TrayId.objects.filter(tray_id__iexact=tid).exists():
                errors.append(f'Tray ID "{tid}" already exists.')
                continue

            valid_trays.append(tid)

        if errors and not valid_trays:
            logger.warning(f"[TrayManage] All trays rejected: {errors}")
            return Response({
                'status': 'error',
                'message': 'All tray IDs failed validation.',
                'data': [],
                'conflicts': errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Determine tray_type and capacity from prefix
        created = []
        with transaction.atomic():
            for tid in valid_trays:
                prefix = tid[0]  # J or N
                if prefix == 'J':
                    tray_type_name = 'Jumbo'
                else:
                    tray_type_name = 'Normal'

                # Look up TrayType for capacity
                tray_type_obj = TrayType.objects.filter(tray_type__icontains=tray_type_name).first()
                capacity = tray_type_obj.tray_capacity if tray_type_obj else None

                tray_obj = TrayId.objects.create(
                    tray_id=tid,
                    tray_type=tray_type_name,
                    tray_capacity=capacity,
                    date=timezone.now(),
                    user=request.user,
                    new_tray=True,
                )
                created.append({
                    'id': tray_obj.pk,
                    'tray_id': tray_obj.tray_id,
                    'tray_type': tray_obj.tray_type or '',
                    'tray_capacity': tray_obj.tray_capacity,
                })

        msg_parts = [f'{len(created)} tray(s) added successfully.']
        if errors:
            msg_parts.append(f'{len(errors)} tray(s) had issues.')

        resp_status = 'success' if not errors else 'warning'
        logger.info(f"[TrayManage] Added {len(created)} trays, {len(errors)} rejected")
        return Response({
            'status': resp_status,
            'message': ' '.join(msg_parts),
            'data': created,
            'conflicts': errors
        }, status=status.HTTP_201_CREATED if created else status.HTTP_400_BAD_REQUEST)

    def _delete_trays(self, request, tray_ids, force_delete):
        """Delete specific tray IDs with allocation check. Returns deleted tray data for undo."""
        if not tray_ids or not isinstance(tray_ids, list):
            return Response({
                'status': 'error',
                'message': 'tray_ids must be a non-empty list.',
                'data': [],
                'conflicts': []
            }, status=status.HTTP_400_BAD_REQUEST)

        not_found = []
        occupied = []
        deleted = []

        for raw_id in tray_ids:
            tid = str(raw_id).strip().upper()
            tray_obj = TrayId.objects.filter(tray_id__iexact=tid).first()

            if not tray_obj:
                not_found.append(tid)
                continue

            is_occupied = bool(tray_obj.batch_id_id) or bool(tray_obj.lot_id)

            if is_occupied and not force_delete:
                occupied.append({
                    'tray_id': tray_obj.tray_id,
                    'lot_id': tray_obj.lot_id or '',
                    'message': f'Tray "{tray_obj.tray_id}" is already occupied (Lot: {tray_obj.lot_id}). Confirm to delete.'
                })
                continue

            # Capture tray details before deletion for undo
            deleted.append({
                'tray_id': tray_obj.tray_id,
                'tray_type': tray_obj.tray_type or '',
                'tray_capacity': tray_obj.tray_capacity,
            })
            logger.info(f"[TrayManage] Deleting tray {tray_obj.tray_id} (occupied={is_occupied}, force={force_delete})")
            tray_obj.delete()

        if occupied and not deleted:
            return Response({
                'status': 'warning',
                'message': f'{len(occupied)} tray(s) are occupied. Confirm to proceed with deletion.',
                'data': [],
                'conflicts': occupied
            })

        msg_parts = []
        if deleted:
            msg_parts.append(f'{len(deleted)} tray(s) deleted.')
        if not_found:
            msg_parts.append(f'{len(not_found)} tray(s) not found: {", ".join(not_found)}.')
        if occupied:
            msg_parts.append(f'{len(occupied)} occupied tray(s) skipped (not force-deleted).')

        logger.info(f"[TrayManage] Deleted={len(deleted)}, NotFound={len(not_found)}, Occupied={len(occupied)}")
        return Response({
            'status': 'success' if deleted else 'error',
            'message': ' '.join(msg_parts) or 'No trays deleted.',
            'data': deleted,
            'conflicts': occupied + [{'tray_id': t, 'message': 'Not found'} for t in not_found]
        })

    def _delete_all_trays(self, request, force_delete):
        """Delete all tray IDs with allocation check."""
        all_trays = TrayId.objects.all()
        total = all_trays.count()

        if total == 0:
            return Response({
                'status': 'error',
                'message': 'No tray IDs exist to delete.',
                'data': [],
                'conflicts': []
            })

        occupied_trays = all_trays.filter(
            Q(batch_id__isnull=False) | ~Q(lot_id__isnull=True) & ~Q(lot_id='')
        )
        occupied_count = occupied_trays.count()

        if occupied_count > 0 and not force_delete:
            occupied_list = list(occupied_trays.values_list('tray_id', flat=True)[:20])
            return Response({
                'status': 'warning',
                'message': f'{occupied_count} of {total} tray(s) are occupied. Confirm to proceed with deletion of all trays.',
                'data': [],
                'conflicts': [{'tray_id': t, 'message': 'Occupied'} for t in occupied_list]
            })

        logger.info(f"[TrayManage] Deleting ALL {total} trays (force={force_delete})")
        deleted_data = list(all_trays.values('tray_id', 'tray_type', 'tray_capacity'))
        all_trays.delete()
        return Response({
            'status': 'success',
            'message': f'All {total} tray(s) deleted successfully.',
            'data': deleted_data,
            'conflicts': []
        })

    def _restore_trays(self, request, tray_ids):
        """Re-create previously deleted tray IDs (undo operation)."""
        if not tray_ids or not isinstance(tray_ids, list):
            return Response({
                'status': 'error',
                'message': 'tray_ids must be a non-empty list of tray objects to restore.',
                'data': [],
                'conflicts': []
            }, status=status.HTTP_400_BAD_REQUEST)

        restored = []
        skipped = []

        with transaction.atomic():
            for item in tray_ids:
                tid = str(item.get('tray_id', '')).strip().upper() if isinstance(item, dict) else str(item).strip().upper()
                tray_type = item.get('tray_type', '') if isinstance(item, dict) else ''
                tray_capacity = item.get('tray_capacity') if isinstance(item, dict) else None

                # Skip if already re-created
                if TrayId.objects.filter(tray_id__iexact=tid).exists():
                    skipped.append(tid)
                    continue

                TrayId.objects.create(
                    tray_id=tid,
                    tray_type=tray_type,
                    tray_capacity=tray_capacity,
                    date=timezone.now(),
                    user=request.user,
                    new_tray=True,
                )
                restored.append(tid)

        msg_parts = []
        if restored:
            msg_parts.append(f'{len(restored)} tray(s) restored successfully.')
        if skipped:
            msg_parts.append(f'{len(skipped)} tray(s) already exist (skipped).')

        logger.info(f"[TrayManage] Restored={len(restored)}, Skipped={len(skipped)}")
        return Response({
            'status': 'success' if restored else 'error',
            'message': ' '.join(msg_parts) or 'No trays restored.',
            'data': [{'tray_id': t} for t in restored],
            'conflicts': [{'tray_id': t, 'message': 'Already exists'} for t in skipped]
        })
# ── End Consolidated Tray Management API ─────────────────────────────────────


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class CategoryAPIView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request):
        """Get all Categories"""
        categories = Category.objects.all()
        serializer = CategorySerializer(categories, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        """Create new Category"""
        try:
            # Add current datetime to the request data
            data = request.data.copy()
            data['date_time'] = timezone.now()
            
            serializer = CategorySerializer(data=data)
            if serializer.is_valid():
                category = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Category created successfully!',
                    'data': CategorySerializer(category).data
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        """Update Category"""
        try:
            category = get_object_or_404(Category, pk=pk)
            serializer = CategorySerializer(category, data=request.data)
            if serializer.is_valid():
                updated_category = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Category updated successfully!',
                    'data': CategorySerializer(updated_category).data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        """Delete Category"""
        try:
            category = get_object_or_404(Category, pk=pk)
            category.delete()
            return Response({
                'success': True,
                'message': 'Category deleted successfully!'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class IPRejectionAPIView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request):
        """Get all IP Rejection Reasons"""
        rejections = IP_Rejection_Table.objects.all()
        serializer = IPRejectionSerializer(rejections, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        """Create new IP Rejection Reason"""
        try:
            data = request.data.copy()
            data['date_time'] = timezone.now()
 
            serializer = IPRejectionSerializer(data=data)
            if serializer.is_valid():
                rejection = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Rejection reason created successfully!',
                    'data': IPRejectionSerializer(rejection).data
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        """Update IP Rejection Reason"""
        try:
            rejection = get_object_or_404(IP_Rejection_Table, pk=pk)
            serializer = IPRejectionSerializer(rejection, data=request.data)
            if serializer.is_valid():
                updated_rejection = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Rejection reason updated successfully!',
                    'data': IPRejectionSerializer(updated_rejection).data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        """Delete IP Rejection Reason"""
        try:
            rejection = get_object_or_404(IP_Rejection_Table, pk=pk)
            rejection.delete()
            return Response({
                'success': True,
                'message': 'Rejection reason deleted successfully!'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class BrassIQFRejectionAPIView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request):
        """Get all Brass/IQF Rejection Reasons (from Brass_QC_Rejection_Table only)"""
        rejections = Brass_QC_Rejection_Table.objects.all()
        data = [
            {
                'id': obj.id,
                'rejection_reason_id': obj.rejection_reason_id,
                'rejection_reason': obj.rejection_reason,
                
            }
            for obj in rejections
        ]
        return Response({
            'success': True,
            'data': data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        """Create new Brass/IQF Rejection Reason in all three tables"""
        try:
            data = request.data.copy()
            serializer = BrassIQFRejectionSerializer(data=data)
            if serializer.is_valid():
                result = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Rejection reason created successfully in all tables!',
                    'data': BrassIQFRejectionSerializer(result).data
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        """Update Brass/IQF Rejection Reason in all three tables by id (Brass_QC_Rejection_Table only)"""
        try:
            qc_obj = get_object_or_404(Brass_QC_Rejection_Table, pk=pk)
            serializer = BrassIQFRejectionSerializer(qc_obj, data=request.data)
            if serializer.is_valid():
                updated_qc = serializer.save()
                # Optionally update other tables if needed
                return Response({
                    'success': True,
                    'message': 'Rejection reason updated successfully!',
                    'data': BrassIQFRejectionSerializer({'qc': updated_qc, 'audit': None, 'iqf': None}).data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        """Delete Brass/IQF Rejection Reason from all three tables by id (Brass_QC_Rejection_Table only)"""
        try:
            qc_obj = get_object_or_404(Brass_QC_Rejection_Table, pk=pk)
            reason_id = qc_obj.rejection_reason_id
            qc_obj.delete()
            # Also delete from other tables by rejection_reason_id
            Brass_Audit_Rejection_Table.objects.filter(rejection_reason_id=reason_id).delete()
            IQF_Rejection_Table.objects.filter(rejection_reason_id=reason_id).delete()
            return Response({
                'success': True,
                'message': 'Rejection reason deleted from all tables!'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class NickelAuditQCRejectionAPIView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request):
        """Get all Nickel QC Rejection Reasons (from Nickel_QC_Rejection_Table only)"""
        rejections = Nickel_QC_Rejection_Table.objects.all()
        data = [
            {
                'id': obj.id,
                'rejection_reason': obj.rejection_reason
            }
            for obj in rejections
        ]
        return Response({
            'success': True,
            'data': data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        """Create new Nickel Audit/QC Rejection Reason in both tables"""
        try:
            data = request.data.copy()
            serializer = NickelAuditQCRejectionSerializer(data=data)
            if serializer.is_valid():
                result = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Nickel Audit/QC rejection reason created successfully in both tables!',
                    'data': NickelAuditQCRejectionSerializer(result).data
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        """Update Nickel QC Rejection Reason by id (Nickel_QC_Rejection_Table only)"""
        try:
            qc_obj = get_object_or_404(Nickel_QC_Rejection_Table, pk=pk)
            serializer = NickelAuditQCRejectionSerializer(qc_obj, data=request.data)
            if serializer.is_valid():
                updated_qc = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Nickel QC rejection reason updated successfully!',
                    'data': NickelAuditQCRejectionSerializer({'qc': updated_qc, 'audit': None}).data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        """Delete Nickel QC Rejection Reason from both tables by id (Nickel_QC_Rejection_Table only)"""
        try:
            qc_obj = get_object_or_404(Nickel_QC_Rejection_Table, pk=pk)
            reason_text = qc_obj.rejection_reason
            qc_obj.delete()
            # Also delete from audit table by rejection_reason
            Nickel_Audit_Rejection_Table.objects.filter(rejection_reason=reason_text).delete()
            return Response({
                'success': True,
                'message': 'Nickel rejection reason deleted from both tables!'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Utility view to get dropdown data
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class ModelMasterDropdownDataAPIView(APIView):
    renderer_classes = [JSONRenderer]
    
    def get(self, request):
        """Get all dropdown data for Model Master form"""
        try:
            data = {
                'polish_finishes': list(PolishFinishType.objects.values('id', 'polish_finish')),
                'plating_colors': list(Plating_Color.objects.values('id', 'plating_color')),
                'tray_types': list(TrayType.objects.values('id', 'tray_type', 'tray_capacity')),
                'vendors': list(Vendor.objects.values('id', 'vendor_name')),
                'model_images': list(ModelImage.objects.values('id', 'master_image')),
                'versions': list(Version.objects.values('id', 'version_name')),
                'locations': list(Location.objects.values('id', 'location_name')),
                'tray_ids': list(TrayId.objects.values('id', 'tray_id', 'tray_type', 'tray_capacity')),
                'categories': list(Category.objects.values('id', 'category_name')),
            }
            return Response({
                'success': True,
                'data': data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Unable to process the request. Please verify the submitted data and try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

""" Module - User Management """
# Class for Admin Portal HTML File Navigation (Dashboard/Settings gear - Dropdown - User Creation)
@method_decorator(login_required(login_url='login-api'), name='dispatch')
@method_decorator(require_admin, name='dispatch')
class AdminPortalView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'AdminPortal/adminPortal.html'
    
    def get(self, request, format=None):
        from .services import is_admin_user

        last_user = User.objects.order_by('-id').first()
        next_user_id = (last_user.id + 1) if last_user else 1
        allowed_modules = get_allowed_modules_for_user(request.user)
        return Response({
            'next_user_id': next_user_id,
            'allowed_modules': allowed_modules,
            'is_admin': is_admin_user(request.user),
        })

# Class for Department List APIs Masters
class DepartmentListAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminPermission]
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        departments = Department.objects.all().values('id', 'name')
        return Response(list(departments))


# Class for Role List APIs Masters
class RoleListAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminPermission]
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        roles = Role.objects.all().values('id', 'name')
        return Response(list(roles))


_HTML_CHARS_RE = re.compile(r'[<>&"\']')
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
_PASSWORD_RE = re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]).{8,}$')


def _validate_user_text_field(value, field_name):
    """Reject values containing HTML characters to prevent stored HTML injection."""
    if value and _HTML_CHARS_RE.search(value):
        return f'{field_name} must not contain HTML characters (< > & \' ").'
    return None


def _validate_email(email):
    if email and not _EMAIL_RE.match(email):
        return 'Invalid email format.'
    return None


def _validate_password_complexity(password, username=''):
    if not password:
        return 'Password is required.'
    if len(password) < 8:
        return 'Password must be at least 8 characters.'
    if not _PASSWORD_RE.match(password):
        return ('Password must contain at least one uppercase letter, one lowercase letter, '
                'one digit, and one special character.')
    if username and password.lower() == username.lower():
        return 'Password cannot be the same as the username.'
    return None


def _normalize_group_ids_from_payload(data):
    """Accept legacy single group payloads and new multi-select group payloads."""
    if not data:
        return []

    def get_values(key):
        if hasattr(data, 'getlist'):
            values = [value for value in data.getlist(key) if value not in (None, '')]
            if values:
                return values

        value = data.get(key)
        if value in (None, ''):
            return []
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith('['):
                try:
                    parsed_value = json.loads(value)
                    if isinstance(parsed_value, list):
                        return parsed_value
                except Exception:
                    pass
            return [item.strip() for item in value.split(',') if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return list(value)
        return [value]

    raw_group_ids = []
    for key in ('group_ids', 'groups', 'group'):
        raw_group_ids = get_values(key)
        if raw_group_ids:
            break

    group_ids = []
    seen_ids = set()
    for raw_group_id in raw_group_ids:
        try:
            group_id = int(raw_group_id)
        except (TypeError, ValueError):
            continue
        if group_id in seen_ids:
            continue
        seen_ids.add(group_id)
        group_ids.append(group_id)
    return group_ids


def _apply_user_groups(user, group_ids, apply_admin_flags=False):
    """Replace user categories with the selected, valid groups without duplicates."""
    if not group_ids:
        return []

    groups_by_id = Group.objects.filter(id__in=group_ids).in_bulk()
    selected_groups = [groups_by_id[group_id] for group_id in group_ids if group_id in groups_by_id]
    if not selected_groups:
        return []

    user.groups.set(selected_groups)
    if apply_admin_flags and any(group.name.lower() == 'admin' for group in selected_groups):
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
    return selected_groups


def _serialize_user_groups(user):
    prefetched_groups = getattr(user, '_prefetched_objects_cache', {}).get('groups')
    if prefetched_groups is not None:
        groups = sorted(prefetched_groups, key=lambda group: group.name.lower())
    else:
        groups = list(user.groups.all().order_by('name'))
    return {
        'group_id': groups[0].id if groups else '',
        'group_ids': [group.id for group in groups],
        'group_names': [group.name for group in groups],
        'groups': [{'id': group.id, 'name': group.name} for group in groups],
        'user_category': ', '.join(group.name for group in groups),
    }


PERSON_NAME_VALIDATION_ERROR = "Only letters, spaces, apostrophes, hyphens and dots are allowed."
PERSON_NAME_ALLOWED_PUNCTUATION = {" ", "'", "-", "."}


def validate_person_name(value):
    name = str(value or "").strip()

    if not name:
        raise ValueError(PERSON_NAME_VALIDATION_ERROR)

    if not any(ch.isalpha() for ch in name):
        raise ValueError(PERSON_NAME_VALIDATION_ERROR)

    for ch in name:
        if ch.isalpha():
            continue

        if ch in PERSON_NAME_ALLOWED_PUNCTUATION:
            continue

        raise ValueError(PERSON_NAME_VALIDATION_ERROR)

    return name


# Class for User Creation API - Fixed

class UserCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminPermission]
    http_method_names = ['post', 'head', 'options']

    def post(self, request, *args, **kwargs):
        from .services import invalidate_user_modules_cache, sync_user_module_provisions_from_group

        data = request.data or {}
        email = (data.get('email') or '').strip()
        try:
            first_name = validate_person_name(data.get('first_name'))
            last_name = validate_person_name(data.get('last_name'))
        except ValueError as exc:
            return Response({'success': False, 'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        password = data.get('password')
        department_id = data.get('department')
        role_id = data.get('role')
        group_ids = _normalize_group_ids_from_payload(data)
        username = (data.get('username') or email or f"{first_name}.{last_name}").strip()

        try:
            with transaction.atomic():
                # If user exists, update instead of failing
                existing = User.objects.filter(username=username).first()
                if existing:
                    user = existing
                    if first_name:
                        user.first_name = first_name
                    if last_name:
                        user.last_name = last_name
                    if email:
                        user.email = email
                    # Update password only when provided
                    if password:
                        user.set_password(password)
                    user.save()

                    selected_groups = _apply_user_groups(user, group_ids)
                    if selected_groups:
                        if not sync_user_module_provisions_from_group(user):
                            invalidate_user_modules_cache(user.id)

                    # Ensure profile exists, then update
                    profile = getattr(user, 'userprofile', None)
                    if not profile:
                        profile = UserProfile.objects.create(user=user)

                    if department_id and Department.objects.filter(id=department_id).exists():
                        profile.department_id = department_id
                    if role_id and Role.objects.filter(id=role_id).exists():
                        profile.role_id = role_id

                    profile.manager = data.get('manager', profile.manager)
                    profile.employment_status = data.get('employment_status', profile.employment_status)
                    profile.save()

                    return Response({
                        'success': True,
                        'user_id': user.id,
                        'user': {
                            'id': user.id,
                            'username': user.username,
                            'email': user.email,
                        },
                        'message': 'Existing user updated.'
                    }, status=status.HTTP_200_OK)

                # Create new user (original behaviour)
                user = User.objects.create_user(username=username, password=password, email=email)
                user.first_name = first_name or ""
                user.last_name = last_name or ""

                # Attach groups and preserve original Admin flag behaviour on creation
                selected_groups = _apply_user_groups(user, group_ids, apply_admin_flags=True)
                if selected_groups:
                    if not sync_user_module_provisions_from_group(user):
                        invalidate_user_modules_cache(user.id)

                user.save()

                # Ensure profile exists (signal may create it) and update it
                profile = getattr(user, "userprofile", None)
                if not profile:
                    profile = UserProfile.objects.create(user=user)

                # Department and role are optional fields
                if department_id and Department.objects.filter(id=department_id).exists():
                    profile.department_id = department_id
                if role_id and Role.objects.filter(id=role_id).exists():
                    profile.role_id = role_id
                profile.manager = data.get('manager')
                profile.employment_status = data.get('employment_status')
                profile.save()

            return Response({
                'success': True,
                'user_id': user.id,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                },
                'message': 'User created successfully.'
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.exception('User creation failed')
            return Response({'success': False, 'error': 'An internal error occurred. Please contact the administrator.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def create_user(request):
    with transaction.atomic():
        # create or get user
        user, created = User.objects.get_or_create(
            username=request.data['username'],
            defaults={
                'first_name': request.data['first_name'],
                'last_name': request.data['last_name'],
                'email': request.data['email']
            }
        )
        
        # create profile only if it doesn't exist
        if not hasattr(user, 'userprofile'):
            UserProfile.objects.create(
                user=user,
                department_id=request.data['department'],
                role_id=request.data['role']
            )
        
        return Response({'success': True, 'user_id': user.id})
    
    
    
class UserListAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminPermission]
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        users = User.objects.select_related('account_lockout').prefetch_related('groups', 'module_provisions').all().order_by('id')
        paginator = Paginator(users, 8)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        user_list = []
        for user in page_obj.object_list:
            try:
                profile = user.userprofile
                department = profile.department.name if profile.department else ""
                role = profile.role.name if profile.role else ""
                manager = profile.manager
                employment_status = profile.employment_status
            except Exception:
                department = role = manager = employment_status = ""
            module_access = user.module_provisions.all()
            modules = [
                {
                    "name": access.module_name,
                    "headings": access.headings
                }
                for access in module_access
            ]
            group_data = _serialize_user_groups(user)
            created = user.date_joined.strftime("%Y-%m-%d %H:%M")
            lockout = getattr(user, 'account_lockout', None)
            is_locked = bool(lockout and lockout.is_locked)
            locked_at = (
                timezone.localtime(lockout.locked_at).strftime("%Y-%m-%d %H:%M")
                if is_locked and lockout.locked_at else ""
            )
            user_list.append({
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "department": department,
                "user_category": group_data['user_category'],
                "user_categories": group_data['groups'],
                "group_ids": group_data['group_ids'],
                "role": role,
                "manager": manager,
                "employment_status": employment_status,
                "modules": modules,
                "created": created,
                "is_superuser": user.is_superuser,
                "is_locked": is_locked,
                "failed_login_attempts": lockout.failed_attempts if lockout else 0,
                "locked_at": locked_at
            })
        return Response({
            "results": user_list,
            "count": paginator.count,
            "num_pages": paginator.num_pages,
            "current_page": page_obj.number
        })



class UserGroupListAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminPermission]
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        from .services import ensure_module_registry_seeded

        ensure_module_registry_seeded()
        groups = Group.objects.all().order_by('name').values('id', 'name')
        return Response(list(groups))



class GroupModulesAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminPermission]
    http_method_names = ['get', 'head', 'options']

    def get(self, request, group_id):
        from .services import ensure_module_registry_seeded

        ensure_module_registry_seeded()
        try:
            group = Group.objects.get(id=group_id)
            modules = Module.objects.filter(groups=group).order_by('id')
            data = [
                {
                    "id": m.id,
                    "name": m.name,
                    "menu_title": m.menu_title,
                    "headings": m.headings or [],
                    "all_headings": m.headings or [],
                    "file_name": m.html_file or "",
                }
                for m in modules
            ]
            return Response({"success": True, "modules": data})
        except Group.DoesNotExist:
            return Response({"success": False, "error": "Group not found"}, status=404)

# Function for User Visibile Modules API (checkbox/unchecked logic)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def user_allowed_modules(request):
    from .services import (
        get_user_allowed_module_payload,
        invalidate_user_modules_cache,
        is_admin_user,
        sync_user_module_provisions_from_group,
    )

    user = request.user
    if not user.is_authenticated:
        return {'allowed_modules': []}

    if not is_admin_user(user):
        logger.warning(
            'UNAUTHORIZED_ADMIN_ACCESS: path=%s method=%s ip=%s',
            request.path, request.method,
            request.META.get('REMOTE_ADDR', 'unknown'),
        )
        return Response({'error': 'Access denied. Admin privileges required.', 'code': 'ADMIN_REQUIRED'}, status=403)

    # ----- POST logic -----
    if request.method == 'POST':
        user_id = request.data.get('user_id')
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response({'success': False, 'error': 'User not found.'}, status=404)

        try:
            modules = request.data.get('modules', [])
            if not isinstance(modules, list):
                return Response({'success': False, 'error': 'Modules should be a list.'}, status=400)

            if sync_user_module_provisions_from_group(user):
                return Response({'success': True, 'message': 'Modules auto-assigned from user category.'})

            UserModuleProvision.objects.filter(user=user).delete()
            seen_module_names = set()
            for mod in modules:
                if not isinstance(mod, dict):
                    continue
                module_name = (mod.get('name') or '').strip()
                if not module_name or module_name in seen_module_names:
                    continue
                seen_module_names.add(module_name)
                headings = mod.get('headings', [])
                if not isinstance(headings, list):
                    headings = []
                UserModuleProvision.objects.update_or_create(
                    user=user,
                    module_name=module_name,
                    defaults={
                        'headings': headings,
                        'file_name': mod.get('file_name', '')
                    }
                )
            invalidate_user_modules_cache(user.id)
            return Response({'success': True, 'message': 'Modules saved successfully.'})
        except Exception as e:
            return Response({'success': False, 'error': 'Unable to process the request. Please verify the submitted data and try again.'}, status=500)

    # ----- GET logic -----
    # ----- GET logic -----
    # Check if a specific user_id is requested (for Admin editing)
    target_user = user
    requested_user_id = request.GET.get('user_id')
    
    # Permission check for fetching other users
    is_admin = is_admin_user(user)

    if requested_user_id and is_admin:
        try:
            target_user = User.objects.get(id=requested_user_id)
        except User.DoesNotExist:
            return Response({'allowed_modules': []}, status=404)

    return Response({"modules": get_user_allowed_module_payload(target_user)})



#Class for User Deletion API (inactive — route is commented out in urls.py)
class UserDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminPermission]
    http_method_names = ['delete', 'head', 'options']

    def delete(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            user.delete()
            return Response({'success': True, 'message': 'User deleted.'}, status=200)
        except User.DoesNotExist:
            return Response({'success': False, 'error': 'User not found.'}, status=404)
        except Exception as e:
            logger.exception('UserDeleteAPIView.delete error: user_id=%s', user_id)
            return Response({'success': False, 'error': 'An internal error occurred. Please contact the administrator.'}, status=500)
        

  
    
@require_admin
@csrf_exempt
def extract_headings_api(request):
    html_file = request.GET.get('html_file')
    if not html_file:
        return JsonResponse({'success': False, 'error': 'No file specified'})
    TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'templates')
    abs_path = os.path.join(TEMPLATES_DIR, html_file)
    if not os.path.exists(abs_path):
        return JsonResponse({'success': False, 'error': 'File not found'})
    headings = extract_table_headings_from_html(abs_path)
    return JsonResponse({'success': True, 'headings': headings})

@login_required(login_url='login-api')
@require_admin
@csrf_exempt
def swap_login(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            username = data.get("username")
            password = data.get("password")
            user = authenticate(request, username=username, password=password)
            if user is not None:
                # Optionally, you can log in the user or just return success
                return JsonResponse({"success": True})
            else:
                return JsonResponse({"success": False, "error": "Invalid credentials"})
        except Exception as e:
            return JsonResponse({"success": False, "error": 'Unable to process the request. Please verify the submitted data and try again.'})
    return JsonResponse({"success": False, "error": "Invalid request"}, status=400)

class UserDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminPermission]
    http_method_names = ['get', 'head', 'options']

    def dispatch(self, request, *args, **kwargs):
        method = request.method.lower()

        # Reject disallowed verbs (DELETE, PUT, POST, OPTIONS, …) with 405 BEFORE
        # authentication so ForbiddenToLoginMiddleware cannot convert the
        # response to a browser redirect.
        if method not in self.http_method_names:
            from django.http import HttpResponseNotAllowed
            response = HttpResponseNotAllowed([m.upper() for m in self.http_method_names])
            response['Allow'] = ', '.join(m.upper() for m in self.http_method_names)
            return response

        return super().dispatch(request, *args, **kwargs)

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            profile = getattr(user, 'userprofile', None)
            group_data = _serialize_user_groups(user)
            return Response({
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "department_id": profile.department.id if profile and profile.department else "",
                "role_id": profile.role.id if profile and profile.role else "",
                "manager": profile.manager if profile else "",
                "employment_status": profile.employment_status if profile else "",
                "group_id": group_data['group_id'],
                "group_ids": group_data['group_ids'],
                "group_names": group_data['group_names'],
                "groups": group_data['groups'],
            })
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)


class UserUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminPermission]
    http_method_names = ['post', 'head', 'options']

    def post(self, request, user_id):
        from .services import invalidate_user_modules_cache, sync_user_module_provisions_from_group

        data = request.data or {}
        new_username = data.get('username')
        new_first_name = data.get('first_name')
        new_last_name = data.get('last_name')
        new_email = data.get('email')
        password = data.get('password')

        try:
            if new_first_name is not None:
                new_first_name = validate_person_name(new_first_name)
            if new_last_name is not None:
                new_last_name = validate_person_name(new_last_name)
        except ValueError as exc:
            return Response({'success': False, 'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=user_id)
            if new_username is not None:
                user.username = str(new_username).strip()
            if new_first_name is not None:
                user.first_name = new_first_name
            if new_last_name is not None:
                user.last_name = new_last_name
            if new_email is not None:
                user.email = str(new_email).strip()

            if password and str(password).strip():
                password = str(password).strip()
                target_username = str(new_username or user.username).strip()
                pwd_err = _validate_password_complexity(password, username=target_username)
                if pwd_err:
                    return Response({'success': False, 'error': pwd_err}, status=400)
                user.set_password(password)

            user.save()

            profile = getattr(user, 'userprofile', None)
            if profile:
                department_id = data.get('department')
                role_id = data.get('role')
                if department_id:
                    profile.department_id = department_id
                if role_id:
                    profile.role_id = role_id
                profile.manager = data.get('manager', profile.manager)
                profile.employment_status = data.get('employment_status', profile.employment_status)
                profile.save()

            selected_groups = _apply_user_groups(user, _normalize_group_ids_from_payload(data))
            if selected_groups:
                if not sync_user_module_provisions_from_group(user):
                    invalidate_user_modules_cache(user.id)

            return Response({'success': True, 'message': 'User updated successfully.'})
        except User.DoesNotExist:
            return Response({'success': False, 'error': 'User not found.'}, status=404)
        except Exception as e:
            logger.exception('UserUpdateAPIView.post error: user_id=%s', user_id)
            return Response({'success': False, 'error': 'An internal error occurred. Please contact the administrator.'}, status=500)


class UserUnlockAPIView(APIView):
    """Administrator-controlled unlock for accounts locked by the lockout policy."""
    permission_classes = [IsAuthenticated, IsAdminPermission]
    http_method_names = ['post', 'head', 'options']

    def post(self, request, user_id):
        from .services import unlock_user_account

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'success': False, 'error': 'User not found.'}, status=404)

        try:
            if not unlock_user_account(user, unlocked_by=request.user):
                return Response({'success': False, 'error': 'Account is not locked.'}, status=400)
            return Response({
                'success': True,
                'message': f'Account "{user.username}" has been unlocked successfully.'
            })
        except Exception:
            logger.exception('UserUnlockAPIView.post error: user_id=%s', user_id)
            return Response({'success': False, 'error': 'An internal error occurred. Please contact the administrator.'}, status=500)


class UserDeletePostAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminPermission]
    http_method_names = ['post', 'head', 'options']

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            user.delete()
            return Response({'success': True, 'message': 'User deleted.'}, status=200)
        except User.DoesNotExist:
            return Response({'success': False, 'error': 'User not found.'}, status=404)
        except Exception as e:
            logger.exception('UserDeletePostAPIView.post error: user_id=%s', user_id)
            return Response({'success': False, 'error': 'An internal error occurred. Please contact the administrator.'}, status=500)


# Safe class - static handling
""" @method_decorator(login_required(login_url='login-api'), name='dispatch')
class DP_PickTableView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'Day_Planning/DP_PickTable.html'

    def get(self, request, format=None):
        # ...your existing logic to get master_data, etc...
        user = request.user
        # Example: Assume module_name is "DayPlanningPickTable"
        module_name = "DP Pick Table"
        # Get allowed headings for this user/module
        allowed_headings = []
        provision = UserModuleProvision.objects.filter(user=user, module_name=module_name).first()
        print('Provision:', provision)
        if provision and provision.headings:
            allowed_headings = provision.headings
            print(f"User {user.username} has specific module provisions: {allowed_headings}")
        else:
            # fallback: show all headings if not restricted
            allowed_headings = [
                "S.No", "Last Updated", "Plating Stk No", "Polishing Stk No", "Plating Color",
                "Category", "Polish Finish", "Version", "Tray Cate-Capacity", "Source",
                "No of Trays", "Input Qty", "Process Status", "Action", "Lot Status",
                "Current Stage", "Remarks"
            ]
            print(f"User {user.username} has no specific module provisions, using default headings: {allowed_headings}" )
        context = {
            # ...existing context...
            'allowed_headings': allowed_headings,
            # ...other context...
        }
        return Response(context)
 """



def get_visible_headings_for_user(user, module_name):
    """
    Returns a dict: {heading: True/False} for all headings of the module.
    True = editable, False = non-editable (blurred).
    """
    module = Module.objects.filter(name=module_name).first()
    all_headings = module.headings if module else []
    provision = UserModuleProvision.objects.filter(user=user, module_name=module_name).first()
    allowed_headings = provision.headings if (provision and provision.headings) else all_headings
    return {h: h in allowed_headings for h in all_headings}


# Class for Generic Module Table View
@method_decorator(login_required(login_url='login-api'), name='dispatch')
class ModuleTableView(APIView):
    """
    Generic view for any module table.
    Usage: pass module_name as a URL kwarg or query param.
    Example URL: /adminportal/module-table/?module_name=DP Pick Table
    """
    renderer_classes = [TemplateHTMLRenderer]

    def get(self, request, *args, **kwargs):
        # 1. Get module_name from URL (query param or kwarg)
        module_name = kwargs.get('module_name') or request.GET.get('module_name')
        if not module_name:
            return Response({'error': 'Module name not specified.'}, status=400)

        # 2. Fetch the Module object
        module = Module.objects.filter(name=module_name).first()
        if not module:
            return Response({'error': f'Module "{module_name}" not found.'}, status=404)

        # 3. Get the template file name from the module
        template_name = module.html_file or 'Day_Planning/DP_PickTable.html'
        self.template_name = template_name

        # 4. Get allowed headings for this user/module from UserModuleProvision
        provision = UserModuleProvision.objects.filter(user=request.user, module_name=module_name).first()
        if provision and provision.headings:
            allowed_headings = provision.headings
        else:
            # fallback: use all headings from the Module master
            allowed_headings = module.headings or []

        visible_headings = get_visible_headings_for_user(request.user, module_name)
        context = {
            'allowed_headings': allowed_headings,
            'module_name': module_name,
            'visible_headings': visible_headings,
        }
        return Response(context)


# Function for checking if a user is an admin for heading blurred logic 
# Function for checking if a user is an admin for heading blurred logic 
def is_admin_user(user):
    """
    Returns True if the user is superuser, in Admin group, or department is Admin.
    """
    if not user.is_authenticated:
        return False
    return (
        user.is_superuser
        or user.groups.filter(name__iexact="Admin").exists()
        or (
            hasattr(user, 'userprofile')
            and user.userprofile.department
            and user.userprofile.department.name.lower() == "admin"
        )
    )

class UserPageAPIView(APIView):
    def get(self, request):
        user_id = request.GET.get('user_id')
        if not user_id:
            return Response({'error': 'User ID required'}, status=400)
        
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)
            
        # Must match UserListAPIView ordering (id ascending)
        position = User.objects.filter(id__lt=user_id).count() 
        
        page_size = 6 # Must match UserListAPIView
        page_number = (position // page_size) + 1
        
        return Response({'page': page_number})


@method_decorator(login_required(login_url='login-api'), name='dispatch')
class LotRemarkHistoryAPIView(APIView):
    """
    GET /adminportal/api/lot_remark_history/?lot_id=<lot_id>
    Returns all pick-stage remarks for a lot in workflow order.
    Queries TotalStockModel (early stages) and JigUnloadAfterTable (post-unloading stages).
    """
    renderer_classes = [JSONRenderer]

    def get(self, request):
        lot_id = (request.GET.get('lot_id') or '').strip()
        if not lot_id:
            return Response({'success': False, 'error': 'lot_id is required'}, status=400)

        remarks = []

        # ── Early stages: TotalStockModel ──────────────────────────────────
        try:
            from modelmasterapp.models import TotalStockModel
            stock = TotalStockModel.objects.select_related('batch_id').filter(lot_id=lot_id).first()
            if stock:
                # Day Planning remark lives on ModelMasterCreation (batch)
                if stock.batch_id and stock.batch_id.dp_pick_remarks:
                    remarks.append({
                        'stage': 'Day Planning',
                        'remark': stock.batch_id.dp_pick_remarks,
                    })
                if stock.IP_pick_remarks:
                    remarks.append({'stage': 'Input Screening', 'remark': stock.IP_pick_remarks})
                if stock.IQF_pick_remarks:
                    remarks.append({'stage': 'IQF', 'remark': stock.IQF_pick_remarks})
                if stock.Bq_pick_remarks:
                    remarks.append({'stage': 'Brass QC', 'remark': stock.Bq_pick_remarks})
                if stock.BA_pick_remarks:
                    remarks.append({'stage': 'Brass Audit', 'remark': stock.BA_pick_remarks})
                if stock.jig_pick_remarks:
                    remarks.append({'stage': 'Jig Loading', 'remark': stock.jig_pick_remarks})
        except Exception as e:
            logger.warning("[LotRemarkHistory] TotalStockModel lookup failed for lot_id=%s: %s", lot_id, e)

        # ── Post-unloading stages: JigUnloadAfterTable ────────────────────
        try:
            from Jig_Unloading.models import JigUnloadAfterTable
            juat = JigUnloadAfterTable.objects.filter(lot_id=lot_id).first()
            if juat:
                if juat.nq_pick_remarks:
                    remarks.append({'stage': 'Nickel Inspection', 'remark': juat.nq_pick_remarks})
                if juat.na_pick_remarks:
                    remarks.append({'stage': 'Nickel Audit', 'remark': juat.na_pick_remarks})
                if juat.spider_pick_remarks:
                    remarks.append({'stage': 'Spider Spindle', 'remark': juat.spider_pick_remarks})
        except Exception as e:
            logger.warning("[LotRemarkHistory] JigUnloadAfterTable lookup failed for lot_id=%s: %s", lot_id, e)

        return Response({
            'success': True,
            'lot_id': lot_id,
            'remarks': remarks,
        })
