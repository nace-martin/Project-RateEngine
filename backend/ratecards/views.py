from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import RatecardFile
from .serializers import RatecardFileSerializer
from .services import RateCardParsingService # Import the new service

class RatecardFileViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows RatecardFiles to be viewed or edited.
    """
    queryset = RatecardFile.objects.all()
    serializer_class = RatecardFileSerializer

    def perform_create(self, serializer):
        """
        Override the default create behavior to trigger the parsing service.
        """
        # First, save the file instance as normal
        ratecard_file_instance = serializer.save()

        # Next, instantiate our service and call the parsing method
        try:
            parser = RateCardParsingService()
            parser.parse_and_store(ratecard_file_instance)
        except Exception as e:
            # If parsing fails, it's good practice to delete the created file object
            # so the user can try uploading again after fixing the file.
            # The transaction in the service should prevent partial data saving.
            ratecard_file_instance.delete()
            
            # Re-raise the exception to return a 400 Bad Request to the user
            # It's better to create a custom exception class for parsing errors
            # but for now, a generic message will do.
            raise ValueError(f"Failed to parse rate card file: {e}")

    def create(self, request, *args, **kwargs):
        """
        Override the main create method to provide a clear error message on failure.
        """
        try:
            return super().create(request, *args, **kwargs)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)