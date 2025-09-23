from django.urls import path
from .views import ComputeQuoteView

app_name = 'pricing_v2'

urlpatterns = [
    path('compute-quote/', ComputeQuoteView.as_view(), name='compute-quote'),
]