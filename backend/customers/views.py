from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Customer, Address
from .serializers import AddressSerializer, CustomerListSerializer, CustomerDetailSerializer

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.select_related('primary_address').all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return CustomerListSerializer
        return CustomerDetailSerializer

class AddressViewSet(viewsets.ModelViewSet):
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]
