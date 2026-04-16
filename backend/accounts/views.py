import json
import logging

from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from core.security import get_request_ip
from core.storage_utils import file_field_storage_exists
from parties.branding_urls import build_public_branding_logo_url

from .models import CustomUser


logger = logging.getLogger(__name__)

def _error(detail: str, status_code: int):
    """Consistent error payload shape across API: {'detail': ...}."""
    return JsonResponse({'detail': detail}, status=status_code)


class LoginRateThrottle(ScopedRateThrottle):
    """Throttle for login attempts - uses 'login' scope from settings."""
    scope = 'login'


class RegisterRateThrottle(ScopedRateThrottle):
    """Throttle for self-registration attempts."""
    scope = 'register'


def _serialize_branding(branding, request=None):
    if not branding:
        return None

    logo_url = None
    if file_field_storage_exists(getattr(branding, "logo_small", None)):
        logo_url = build_public_branding_logo_url(branding, "small", request=request)
    elif file_field_storage_exists(getattr(branding, "logo_primary", None)):
        logo_url = build_public_branding_logo_url(branding, "primary", request=request)

    return {
        'display_name': branding.display_name,
        'primary_color': branding.primary_color or None,
        'accent_color': branding.accent_color or None,
        'logo_url': logo_url,
    }


def _serialize_organization(organization, request=None):
    if not organization:
        return None

    branding = getattr(organization, 'branding', None)
    return {
        'id': str(organization.id),
        'name': organization.name,
        'slug': organization.slug,
        'branding': _serialize_branding(branding, request=request),
    }


def _serialize_user(user: CustomUser, request=None):
    organization = getattr(user, 'organization', None)
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'organization': _serialize_organization(organization, request=request),
    }


def _default_organization():
    from parties.models import Organization

    organization = (
        Organization.objects
        .filter(is_active=True)
        .exclude(slug='default-organization')
        .order_by('name')
        .first()
    )
    if organization is None:
        organization = Organization.objects.filter(is_active=True).order_by('name').first()
    if organization is None:
        organization = (
            Organization.objects
            .exclude(slug='default-organization')
            .order_by('name')
            .first()
        )
    if organization is None:
        organization = Organization.objects.order_by('name').first()
    return organization


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def login_view(request):
    """
    Login endpoint that returns a token and user role
    """
    if request.method != 'POST':
        return _error('Only POST method allowed', 405)
    
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
    except json.JSONDecodeError:
        logger.warning("Rejected login with invalid JSON from ip=%s", get_request_ip(request))
        return _error('Invalid JSON', 400)
    
    if not username or not password:
        logger.warning("Rejected login with missing credentials username=%s ip=%s", username or "<blank>", get_request_ip(request))
        return _error('Username and password required', 400)
    
    user = authenticate(username=username, password=password)
    if not user:
        logger.warning("Failed login for username=%s ip=%s", username, get_request_ip(request))
        return _error('Invalid credentials', 401)
    
    # Get or create token for the user
    token, created = Token.objects.get_or_create(user=user)
    logger.info("Successful login for username=%s ip=%s", user.username, get_request_ip(request))
    
    return JsonResponse({
        'token': token.key,
        'role': user.role,
        'username': user.username,
        'user': _serialize_user(user, request=request),
    })

login_view.throttle_scope = 'login'

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([RegisterRateThrottle])
def register_view(request):
    """
    User registration endpoint.
    
    SECURITY: This endpoint is DISABLED in production.
    Users must be created by an admin through the admin panel or API.
    
    To enable self-registration, set ALLOW_SELF_REGISTRATION=True in environment.
    Even when enabled, users are always assigned the 'sales' role (no role self-assignment).
    """
    # Check if self-registration is explicitly enabled
    import os
    if not os.environ.get('ALLOW_SELF_REGISTRATION', '').lower() == 'true':
        logger.warning("Rejected self-registration while disabled ip=%s", get_request_ip(request))
        return _error(
            'Self-registration is disabled. Please contact an administrator to create an account.',
            403
        )
    
    if request.method != 'POST':
        return _error('Only POST method allowed', 405)
    
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        # SECURITY: Role is always 'sales' - users cannot set their own role
        # Admin must update role after creation if needed
    except json.JSONDecodeError:
        logger.warning("Rejected registration with invalid JSON ip=%s", get_request_ip(request))
        return _error('Invalid JSON', 400)
    
    if not username or not password:
        logger.warning("Rejected registration with missing username/password ip=%s", get_request_ip(request))
        return _error('Username and password required', 400)
    
    # Check if user already exists
    if CustomUser.objects.filter(username=username).exists():
        logger.warning("Rejected registration for existing username=%s ip=%s", username, get_request_ip(request))
        return _error('Username already exists', 400)

    try:
        validate_password(password)
    except Exception as exc:
        logger.warning("Rejected registration for username=%s due to password validation ip=%s", username, get_request_ip(request))
        detail = getattr(exc, "messages", None) or ["Password does not meet security requirements."]
        return JsonResponse({'detail': detail}, status=400)
    
    # Create user with hashed password - always 'sales' role
    user = CustomUser.objects.create(
        username=username,
        password=make_password(password),
        role=CustomUser.ROLE_SALES,  # Always sales - no role self-assignment
        organization=_default_organization(),
        department=CustomUser.DEPARTMENT_GENERAL,
    )
    
    # Create token for the user
    token = Token.objects.create(user=user)
    logger.info("Self-registration created username=%s ip=%s", user.username, get_request_ip(request))
    
    return JsonResponse({
        'token': token.key,
        'role': user.role,
        'username': user.username,
        'user': _serialize_user(user, request=request),
    }, status=201)


@csrf_exempt
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    return JsonResponse(_serialize_user(request.user, request=request))


register_view.throttle_scope = 'register'
