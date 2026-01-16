import json
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle
from .models import CustomUser

def _error(detail: str, status_code: int):
    """Consistent error payload shape across API: {'detail': ...}."""
    return JsonResponse({'detail': detail}, status=status_code)


class LoginRateThrottle(ScopedRateThrottle):
    """Throttle for login attempts - uses 'login' scope from settings."""
    scope = 'login'


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
        return _error('Invalid JSON', 400)
    
    if not username or not password:
        return _error('Username and password required', 400)
    
    user = authenticate(username=username, password=password)
    if not user:
        return _error('Invalid credentials', 401)
    
    # Get or create token for the user
    token, created = Token.objects.get_or_create(user=user)
    
    return JsonResponse({
        'token': token.key,
        'role': user.role,
        'username': user.username
    })

login_view.throttle_scope = 'login'

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
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
        return _error('Invalid JSON', 400)
    
    if not username or not password:
        return _error('Username and password required', 400)
    
    # Check if user already exists
    if CustomUser.objects.filter(username=username).exists():
        return _error('Username already exists', 400)
    
    # Create user with hashed password - always 'sales' role
    user = CustomUser.objects.create(
        username=username,
        password=make_password(password),
        role=CustomUser.ROLE_SALES  # Always sales - no role self-assignment
    )
    
    # Create token for the user
    token = Token.objects.create(user=user)
    
    return JsonResponse({
        'token': token.key,
        'role': user.role,
        'username': user.username
    }, status=201)
