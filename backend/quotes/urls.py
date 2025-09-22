from django.urls import path

from .views import QuoteComputeView, QuoteDetailView, QuoteListView

urlpatterns = [
    path('compute', QuoteComputeView.as_view(), name='quote-compute'),
    path('', QuoteListView.as_view(), name='quote-list'),
    path('<int:quote_id>/', QuoteDetailView.as_view(), name='quote-detail'),
]
