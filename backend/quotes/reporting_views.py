import logging
from django.db.models import Sum, Count, Q, OuterRef, Subquery
from django.db.models.functions import TruncMonth
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Quote, QuoteTotal
from accounts.permissions import IsManagerOrAdmin, IsFinanceOrAdmin

logger = logging.getLogger(__name__)

class ReportsViewSet(viewsets.ViewSet):
    """
    Reporting endpoints for Management and Finance.
    """
    permission_classes = [IsAuthenticated, IsManagerOrAdmin | IsFinanceOrAdmin]

    def _quotes_with_latest_total(self):
        latest_total_subquery = QuoteTotal.objects.filter(
            quote_version__quote_id=OuterRef('pk')
        ).order_by('-quote_version__version_number').values('total_sell_pgk')[:1]
        return Quote.objects.annotate(
            latest_total_sell_pgk=Subquery(latest_total_subquery)
        )

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """
        Aggregate high-level metrics for the dashboard.
        """
        quotes_with_latest_total = self._quotes_with_latest_total()

        # 1. Total Revenue (Accepted/Finalized)
        total_revenue = quotes_with_latest_total.filter(
            status__in=[Quote.Status.FINALIZED, Quote.Status.ACCEPTED, Quote.Status.SENT]
        ).exclude(is_archived=True).aggregate(
            total=Sum('latest_total_sell_pgk')
        )['total'] or 0

        # 2. Quote Volume by Mode
        volume_by_mode = quotes_with_latest_total.exclude(is_archived=True).values('mode').annotate(
            count=Count('id'),
            revenue=Sum(
                'latest_total_sell_pgk',
                filter=Q(status__in=[Quote.Status.FINALIZED, Quote.Status.ACCEPTED, Quote.Status.SENT])
            )
        )

        # 3. Conversion Rates (Draft vs Finalized/Sent/Accepted)
        conversion = Quote.objects.exclude(is_archived=True).aggregate(
            total=Count('id'),
            drafts=Count('id', filter=Q(status='DRAFT')),
            finalized=Count('id', filter=Q(status__in=['FINALIZED', 'SENT', 'ACCEPTED'])),
            lost=Count('id', filter=Q(status='LOST')),
        )
        
        return Response({
            'total_revenue': total_revenue,
            'volume_by_mode': volume_by_mode,
            'conversion': conversion,
        })

    @action(detail=False, methods=['get'])
    def sales_performance(self, request):
        """
        Sales performance metrics grouped by user.
        """
        quotes_with_latest_total = self._quotes_with_latest_total()
        performance = quotes_with_latest_total.exclude(is_archived=True).values(
            'created_by__username',
            'created_by__first_name',
            'created_by__last_name'
        ).annotate(
            total_quotes=Count('id'),
            total_revenue=Sum(
                'latest_total_sell_pgk',
                filter=Q(status__in=[Quote.Status.FINALIZED, Quote.Status.ACCEPTED, Quote.Status.SENT])
            ),
            converted_quotes=Count('id', filter=Q(status__in=[Quote.Status.FINALIZED, Quote.Status.ACCEPTED, Quote.Status.SENT]))
        ).order_by('-total_revenue')

        return Response(performance)
