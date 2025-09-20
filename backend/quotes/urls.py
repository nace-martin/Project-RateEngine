from django.urls import path

from .views import QuoteComputeView, QuoteDetailView, QuoteListView
from .views_v2 import compute_v2

urlpatterns = [
    path('compute', QuoteComputeView.as_view(), name='quote-compute'),
    path('compute2', compute_v2, name='quote-compute-v2'),
    path('', QuoteListView.as_view(), name='quote-list'),
    path('<int:quote_id>/', QuoteDetailView.as_view(), name='quote-detail'),
]
