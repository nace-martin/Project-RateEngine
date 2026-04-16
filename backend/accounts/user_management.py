# backend/accounts/user_management.py
"""
User Management API

Provides CRUD operations for users.
Only accessible by Manager and Admin roles.
"""
from rest_framework import generics, serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.hashers import make_password

from .models import CustomUser
from parties.models import Organization


class UserSerializer(serializers.ModelSerializer):
    """Serializer for listing and viewing users."""
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    department = serializers.ChoiceField(choices=CustomUser.DEPARTMENT_CHOICES, required=True)
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), required=True)
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'department', 'organization', 'organization_name',
            'is_active', 'date_joined', 'last_login',
            'password'
        ]
        read_only_fields = ['id', 'date_joined', 'last_login']
    
    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = CustomUser(**validated_data)
        if password:
            user.password = make_password(password)
        user.save()
        return user
    
    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.password = make_password(password)
        instance.save()
        return instance


class CanManageUsers(IsAuthenticated):
    """Permission: Only Manager and Admin can manage users."""
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return getattr(request.user, 'can_manage_users', False)


class OrganizationOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'slug', 'is_active']


class OrganizationListAPIView(generics.ListAPIView):
    serializer_class = OrganizationOptionSerializer
    permission_classes = [CanManageUsers]

    def get_queryset(self):
        return Organization.objects.order_by('-is_active', 'name')


class UserViewSet(viewsets.ModelViewSet):
    """
    CRUD API for User Management.
    
    GET /api/users/ - List all users
    POST /api/users/ - Create new user
    GET /api/users/{id}/ - Retrieve user
    PUT /api/users/{id}/ - Update user
    PATCH /api/users/{id}/ - Partial update
    DELETE /api/users/{id}/ - Deactivate user (sets is_active=False)
    """
    queryset = CustomUser.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer
    permission_classes = [CanManageUsers]
    
    def get_queryset(self):
        qs = super().get_queryset()
        
        # Filter by role
        role = self.request.query_params.get('role')
        if role:
            qs = qs.filter(role=role)
        
        # Filter by department
        department = self.request.query_params.get('department')
        if department:
            qs = qs.filter(department=department)
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')
        
        # Search by username/email
        search = self.request.query_params.get('search')
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        
        return qs
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete - deactivate user instead of deleting."""
        instance = self.get_object()
        
        # Prevent self-deactivation
        if instance == request.user:
            return Response(
                {'detail': 'You cannot deactivate your own account.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        
        return Response(
            {'detail': f'User {instance.username} has been deactivated.'},
            status=status.HTTP_200_OK
        )
