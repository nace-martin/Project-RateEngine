from rest_framework import status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Organizations


class OrganizationsListView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = Organizations.objects.all().order_by("name").values("id", "name")
        return Response(list(rows), status=status.HTTP_200_OK)
