import json
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from .models import CustomUser

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """
    Login endpoint that returns a token and user role
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    if not username or not password:
        return JsonResponse({'error': 'Username and password required'}, status=400)
    
    user = authenticate(username=username, password=password)
    if not user:
        return JsonResponse({'error': 'Invalid credentials'}, status=401)
    
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
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        role = data.get('role', 'sales')  # Default to sales role
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    if not username or not password:
        return JsonResponse({'error': 'Username and password required'}, status=400)
    
    # Check if user already exists
    if CustomUser.objects.filter(username=username).exists():
        return JsonResponse({'error': 'Username already exists'}, status=400)
    
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
