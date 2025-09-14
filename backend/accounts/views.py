import json
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from .models import CustomUser

def _error(detail: str, status_code: int):
    """Consistent error payload shape across API: {'detail': ...}."""
    return JsonResponse({'detail': detail}, status=status_code)

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
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

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    """
    Registration endpoint for creating new users
    """
    if request.method != 'POST':
        return _error('Only POST method allowed', 405)
    
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        role = data.get('role', 'sales')  # Default to sales role
    except json.JSONDecodeError:
        return _error('Invalid JSON', 400)
    
    if not username or not password:
        return _error('Username and password required', 400)
    
    # Check if user already exists
    if CustomUser.objects.filter(username=username).exists():
        return _error('Username already exists', 400)
    
    # Create user with hashed password
    user = CustomUser.objects.create(
        username=username,
        password=make_password(password),
        role=role
    )
    
    # Create token for the user
    token = Token.objects.create(user=user)
    
    return JsonResponse({
        'token': token.key,
        'role': user.role,
        'username': user.username
    }, status=201)
