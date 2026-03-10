# backend/quotes/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    QuoteV3ViewSet,
    QuoteComputeV3APIView,
    CustomerDetailAPIView,
    RatecardListAPIView,
    RatecardUploadAPIView,
    StationListAPIView,
    QuoteVersionCreateAPIView,
    AIRateIntakeAPIView,
    QuoteTransitionAPIView,
    QuoteCloneAPIView,
    QuotePDFAPIView,
    QuotePublicDetailAPIView,
)
from .reporting_views import ReportsViewSet
from .spot_views import (
    SpotScopeValidateAPIView,
    SpotTriggerEvaluateAPIView,
    StandardChargesAPIView,
    SpotEnvelopeListCreateAPIView,
    SpotEnvelopeDetailAPIView,
    SpotEnvelopeAcknowledgeAPIView,
    SpotEnvelopeApproveAPIView,
    SpotEnvelopeComputeAPIView,
    SpotReplyAnalysisAPIView,
    SpotEnvelopeCreateQuoteAPIView,
)

app_name = 'quotes'

# --- V3 Router ---
router_v3 = DefaultRouter()
router_v3.register(r'quotes', QuoteV3ViewSet, basename='quote-v3')
router_v3.register(r'reports', ReportsViewSet, basename='reports')


urlpatterns = [
    path('v3/quotes/compute/', QuoteComputeV3APIView.as_view(), name='quote-compute-v3'),
    path('v3/quotes/<uuid:quote_id>/versions/', QuoteVersionCreateAPIView.as_view(), name='quote-version-create'),
    path('v3/quotes/<uuid:quote_id>/ai-intake/', AIRateIntakeAPIView.as_view(), name='ai-rate-intake'),
    path('v3/quotes/<uuid:quote_id>/transition/', QuoteTransitionAPIView.as_view(), name='quote-transition'),
    path('v3/quotes/<uuid:quote_id>/clone/', QuoteCloneAPIView.as_view(), name='quote-clone'),
    path('v3/quotes/<uuid:quote_id>/pdf/', QuotePDFAPIView.as_view(), name='quote-pdf'),
    path('v3/quotes/public/', QuotePublicDetailAPIView.as_view(), name='quote-public-detail'),
    # Dedicated customer profile endpoint used by customer edit UI.
    # Keep this separate from parties router '/v3/customers/<id>/' to avoid URL overlap.
    path('v3/customer-details/<uuid:customer_id>/', CustomerDetailAPIView.as_view(), name='customer-detail'),
    path('v3/ratecards/', RatecardListAPIView.as_view(), name='ratecard-list'),
    path('v3/ratecards/upload/', RatecardUploadAPIView.as_view(), name='ratecard-upload'),
    path('v3/stations/', StationListAPIView.as_view(), name='station-list'),
    path('v3/', include(router_v3.urls)),
    
    # --- SPOT Mode Endpoints ---
    path('v3/spot/validate-scope/', SpotScopeValidateAPIView.as_view(), name='spot-validate-scope'),
    path('v3/spot/evaluate-trigger/', SpotTriggerEvaluateAPIView.as_view(), name='spot-evaluate-trigger'),
    path('v3/spot/standard-charges/', StandardChargesAPIView.as_view(), name='spot-standard-charges'),
    path('v3/spot/envelopes/', SpotEnvelopeListCreateAPIView.as_view(), name='spot-envelope-list-create'),
    path('v3/spot/envelopes/<uuid:envelope_id>/', SpotEnvelopeDetailAPIView.as_view(), name='spot-envelope-detail'),
    path('v3/spot/envelopes/<uuid:envelope_id>/acknowledge/', SpotEnvelopeAcknowledgeAPIView.as_view(), name='spot-envelope-acknowledge'),
    path('v3/spot/envelopes/<uuid:envelope_id>/approve/', SpotEnvelopeApproveAPIView.as_view(), name='spot-envelope-approve'),
    path('v3/spot/envelopes/<uuid:envelope_id>/compute/', SpotEnvelopeComputeAPIView.as_view(), name='spot-envelope-compute'),
    path('v3/spot/analyze-reply/', SpotReplyAnalysisAPIView.as_view(), name='spot-analyze-reply'),
    path('v3/spot/envelopes/<uuid:envelope_id>/create-quote/', SpotEnvelopeCreateQuoteAPIView.as_view(), name='spot-envelope-create-quote'),
]
