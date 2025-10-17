# backend/quotes/views_v2.py

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
# import weasyprint

from pricing_v2.pricing_service_v2 import PricingServiceV2
from .models import Quote # Make sure Quote is imported
from .serializers_v2 import QuoteCreateSerializerV2, QuoteResponseSerializerV2

class CreateQuoteAPIViewV2(APIView):
    """
    The main V2 endpoint for computing and creating a new quote.
    """
    
    def post(self, request, *args, **kwargs):
        # 1. Validate the incoming request data
        serializer = QuoteCreateSerializerV2(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data
        
        try:
            # 2. Instantiate and call our pricing service
            service = PricingServiceV2()
            new_quote = service.create_quote(validated_data)
            
            # 3. Format the response using our response serializer
            response_serializer = QuoteResponseSerializerV2(new_quote)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            
        except NotImplementedError as e:
            return Response({"error": str(e)}, status=status.HTTP_501_NOT_IMPLEMENTED)
        except Exception as e:
            # Generic error handler for now
            return Response({"error": f"An unexpected error occurred: {repr(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# class QuotePDFView(View):
#     def get(self, request, quote_id):
#         """
#         Generates and returns a PDF document for a given quote.
#         """
#         try:
#             quote = Quote.objects.get(pk=quote_id)
#         except Quote.DoesNotExist:
#             return HttpResponse("Quote not found", status=404)
# 
#         # Prepare the context data for the template
#         context = {
#             'quote': quote,
#             'lines': quote.lines.all().order_by('section'),
#             'totals': quote.totals,
#         }
# 
#         # Render the HTML template
#         html_string = render_to_string('quotes/pdf_template.html', context)
# 
#         # Generate the PDF
#         pdf_file = weasyprint.HTML(string=html_string).write_pdf()
# 
#         # Create the HTTP response to trigger a download
#         response = HttpResponse(pdf_file, content_type='application/pdf')
#         response['Content-Disposition'] = f'attachment; filename="Quote-{quote.quote_number}.pdf"'
# 
#         return response

class GetQuoteAPIViewV2(APIView):
    """
    Retrieves a single quote by its ID.
    """
    def get(self, request, quote_id, *args, **kwargs):
        try:
            quote = Quote.objects.get(id=quote_id)
            serializer = QuoteResponseSerializerV2(quote)
            return Response(serializer.data)
        except Quote.DoesNotExist:
            return Response({"error": "Quote not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
