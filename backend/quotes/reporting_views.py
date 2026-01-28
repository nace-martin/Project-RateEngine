import csv
import logging
from datetime import datetime, timedelta

from django.db.models import Sum, Count, Q, Avg, F, OuterRef, Subquery
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Quote, QuoteTotal, QuoteVersion, QuoteEvent
from parties.models import Company
from accounts.permissions import IsManagerOrAdmin, IsFinanceOrAdmin

logger = logging.getLogger(__name__)


class ReportsViewSet(viewsets.ViewSet):
    """
    Commercial Reporting endpoints for Management and Finance.
    Phase 1 MVP: Quote Funnel, Revenue/Margin, User Performance.
    """
    permission_classes = [IsAuthenticated, IsManagerOrAdmin | IsFinanceOrAdmin]

    def _get_user_scope(self, request):
        """
        Determine if the user should be restricted to their own data.
        Returns user_id to filter by, or None if user has full access.
        """
        user = request.user
        # Sales users are restricted. Managers, Admin, Finance are not.
        # Check based on role constants from CustomUser
        if user.role in [user.ROLE_MANAGER, user.ROLE_ADMIN, user.ROLE_FINANCE] or user.is_superuser:
            return None
        return user.id

    def _parse_date_params(self, request):
        """Parse start_date and end_date query params. Default to current month."""
        today = timezone.now().date()
        start_of_month = today.replace(day=1)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                start_date = start_of_month
        else:
            start_date = start_of_month

        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                end_date = today
        else:
            end_date = today

        return start_date, end_date

    def _get_latest_total_subquery(self):
        """Subquery to get the latest QuoteTotal for each quote."""
        return QuoteTotal.objects.filter(
            quote_version__quote_id=OuterRef('pk')
        ).order_by('-quote_version__version_number')

    def _quotes_with_financials(self, start_date=None, end_date=None, user_id=None, mode=None):
        """
        Get quotes annotated with their latest version's financial totals.
        Optionally filter by date range, user, and mode.
        """
        latest_total = self._get_latest_total_subquery()

        qs = Quote.objects.annotate(
            latest_total_sell_pgk=Subquery(latest_total.values('total_sell_pgk')[:1]),
            latest_total_cost_pgk=Subquery(latest_total.values('total_cost_pgk')[:1]),
        ).exclude(is_archived=True)

        if start_date and end_date:
            qs = qs.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)

        if user_id:
            qs = qs.filter(created_by_id=user_id)

        if mode and mode.upper() in ['AIR', 'SEA']:
            qs = qs.filter(mode=mode.upper())

        return qs

    @action(detail=False, methods=['get'])
    def funnel_metrics(self, request):
        """
        Quote funnel metrics with time-to-quote analysis.
        
        Returns:
            - quotes_created: Count of quotes created in period
            - quotes_sent: Count of quotes sent
            - quotes_accepted: Count of accepted (won) quotes
            - conversion_rate: (Accepted / Sent) * 100
            - avg_time_to_quote: Average time between CREATED and SENT events
        """
        start_date, end_date = self._parse_date_params(request)
        user_id = request.query_params.get('user_id')
        mode = request.query_params.get('mode')

        qs = self._quotes_with_financials(start_date, end_date, user_id, mode)

        # Count by status
        counts = qs.aggregate(
            created=Count('id'),
            sent=Count('id', filter=Q(status__in=[Quote.Status.SENT, Quote.Status.ACCEPTED, Quote.Status.LOST])),
            accepted=Count('id', filter=Q(status=Quote.Status.ACCEPTED)),
            lost=Count('id', filter=Q(status=Quote.Status.LOST)),
        )

        # Calculate conversion rate
        sent_count = counts['sent'] or 0
        accepted_count = counts['accepted'] or 0
        conversion_rate = (accepted_count / sent_count * 100) if sent_count > 0 else 0

        # Calculate average time to quote from QuoteEvent table
        # Find quotes where we have both CREATED and SENT events
        avg_time_minutes = None
        try:
            from django.db.models import Min, Max
            from django.db.models.functions import Extract

            # Get quotes with both events in the date range
            quotes_with_events = Quote.objects.filter(
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
                events__event_type=QuoteEvent.EventType.CREATED
            ).filter(
                events__event_type__in=[QuoteEvent.EventType.SENT, QuoteEvent.EventType.FINALIZED]
            ).distinct()

            if user_id:
                quotes_with_events = quotes_with_events.filter(created_by_id=user_id)
            if mode and mode.upper() in ['AIR', 'SEA']:
                quotes_with_events = quotes_with_events.filter(mode=mode.upper())

            total_minutes = 0
            count = 0
            for quote in quotes_with_events[:100]:  # Limit for performance
                created_event = quote.events.filter(event_type=QuoteEvent.EventType.CREATED).first()
                sent_event = quote.events.filter(
                    event_type__in=[QuoteEvent.EventType.SENT, QuoteEvent.EventType.FINALIZED]
                ).first()
                if created_event and sent_event:
                    delta = sent_event.timestamp - created_event.timestamp
                    total_minutes += delta.total_seconds() / 60
                    count += 1

            if count > 0:
                avg_time_minutes = total_minutes / count
        except Exception as e:
            logger.warning(f"Error calculating avg time to quote: {e}")
            avg_time_minutes = None

        return Response({
            'quotes_created': counts['created'],
            'quotes_sent': counts['sent'],
            'quotes_accepted': accepted_count,
            'quotes_lost': counts['lost'],
            'conversion_rate': round(conversion_rate, 1),
            'avg_time_to_quote_minutes': round(avg_time_minutes, 1) if avg_time_minutes else None,
            'filters': {
                'start_date': str(start_date),
                'end_date': str(end_date),
                'user_id': user_id,
                'mode': mode,
            }
        })

    @action(detail=False, methods=['get'])
    def revenue_margin(self, request):
        """
        Aggregated revenue and margin metrics.
        
        Returns:
            - total_revenue: Sum of sell prices for won quotes
            - total_cost: Sum of cost (COGS)
            - total_gross_profit: Revenue - Cost
            - avg_margin_percent: Average margin across quotes
            - by_mode: Breakdown by transport mode
        """
        start_date, end_date = self._parse_date_params(request)
        user_id = request.query_params.get('user_id')
        mode = request.query_params.get('mode')

        qs = self._quotes_with_financials(start_date, end_date, user_id, mode)

        # Only include finalized/sent/accepted quotes in financials
        financial_statuses = [Quote.Status.FINALIZED, Quote.Status.SENT, Quote.Status.ACCEPTED]
        qs_financial = qs.filter(status__in=financial_statuses)

        # Aggregate totals
        totals = qs_financial.aggregate(
            total_revenue=Sum('latest_total_sell_pgk'),
            total_cost=Sum('latest_total_cost_pgk'),
        )

        total_revenue = totals['total_revenue'] or 0
        total_cost = totals['total_cost'] or 0
        total_gp = total_revenue - total_cost
        avg_margin = (total_gp / total_revenue * 100) if total_revenue > 0 else 0

        # Breakdown by mode
        by_mode = qs_financial.values('mode').annotate(
            revenue=Sum('latest_total_sell_pgk'),
            cost=Sum('latest_total_cost_pgk'),
            count=Count('id'),
        ).order_by('mode')

        mode_breakdown = []
        for item in by_mode:
            rev = item['revenue'] or 0
            cost = item['cost'] or 0
            gp = rev - cost
            margin = (gp / rev * 100) if rev > 0 else 0
            mode_breakdown.append({
                'mode': item['mode'],
                'revenue': float(rev),
                'cost': float(cost),
                'gross_profit': float(gp),
                'margin_percent': round(margin, 1),
                'count': item['count'],
            })

        return Response({
            'total_revenue': float(total_revenue),
            'total_cost': float(total_cost),
            'total_gross_profit': float(total_gp),
            'avg_margin_percent': round(avg_margin, 1),
            'by_mode': mode_breakdown,
            'filters': {
                'start_date': str(start_date),
                'end_date': str(end_date),
                'user_id': user_id,
                'mode': mode,
            }
        })

    @action(detail=False, methods=['get'])
    def user_performance(self, request):
        """
        Per-user sales performance metrics.
        
        Returns list of users with:
            - quotes_issued: Total quotes created
            - quotes_sent: Quotes sent to customers
            - quotes_won: Accepted quotes
            - conversion_rate: (Won / Sent) * 100
            - total_gp: Total Gross Profit generated
            - avg_margin: Average margin percentage
        """
        start_date, end_date = self._parse_date_params(request)
        mode = request.query_params.get('mode')

        qs = self._quotes_with_financials(start_date, end_date, mode=mode)

        # Group by user
        performance = qs.values(
            'created_by__id',
            'created_by__username',
            'created_by__first_name',
            'created_by__last_name',
        ).annotate(
            quotes_issued=Count('id'),
            quotes_sent=Count('id', filter=Q(status__in=[Quote.Status.SENT, Quote.Status.ACCEPTED, Quote.Status.LOST])),
            quotes_won=Count('id', filter=Q(status=Quote.Status.ACCEPTED)),
            quotes_lost=Count('id', filter=Q(status=Quote.Status.LOST)),
            total_revenue=Sum(
                'latest_total_sell_pgk',
                filter=Q(status__in=[Quote.Status.FINALIZED, Quote.Status.SENT, Quote.Status.ACCEPTED])
            ),
            total_cost=Sum(
                'latest_total_cost_pgk',
                filter=Q(status__in=[Quote.Status.FINALIZED, Quote.Status.SENT, Quote.Status.ACCEPTED])
            ),
        ).order_by('-total_revenue')

        results = []
        for user in performance:
            if not user['created_by__id']:
                continue

            revenue = user['total_revenue'] or 0
            cost = user['total_cost'] or 0
            gp = revenue - cost
            margin = (gp / revenue * 100) if revenue > 0 else 0
            sent = user['quotes_sent'] or 0
            won = user['quotes_won'] or 0
            conversion = (won / sent * 100) if sent > 0 else 0

            results.append({
                'user_id': user['created_by__id'],
                'username': user['created_by__username'],
                'full_name': f"{user['created_by__first_name'] or ''} {user['created_by__last_name'] or ''}".strip(),
                'quotes_issued': user['quotes_issued'],
                'quotes_sent': sent,
                'quotes_won': won,
                'quotes_lost': user['quotes_lost'],
                'conversion_rate': round(conversion, 1),
                'total_revenue': float(revenue),
                'total_gp': float(gp),
                'avg_margin': round(margin, 1),
            })

        return Response({
            'users': results,
            'filters': {
                'start_date': str(start_date),
                'end_date': str(end_date),
                'mode': mode,
            }
        })

    @action(detail=False, methods=['get'])
    def export_data(self, request):
        """
        Export quote data as CSV for the selected date range.
        
        Returns CSV file with columns:
            Quote #, Customer, Route, Mode, Cost, Sell, GP, Margin %, Status, User, Date
        """
        start_date, end_date = self._parse_date_params(request)
        user_id = request.query_params.get('user_id')
        mode = request.query_params.get('mode')

        qs = self._quotes_with_financials(start_date, end_date, user_id, mode)

        # Include all statuses except DRAFT
        qs = qs.exclude(status=Quote.Status.DRAFT).select_related(
            'customer', 'origin_location', 'destination_location', 'created_by'
        ).order_by('-created_at')

        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        filename = f"quotes_export_{start_date}_to_{end_date}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow([
            'Quote #', 'Customer', 'Origin', 'Destination', 'Mode',
            'Cost (PGK)', 'Sell (PGK)', 'GP (PGK)', 'Margin %',
            'Status', 'User', 'Created Date'
        ])

        for quote in qs[:1000]:  # Limit to 1000 rows
            cost = quote.latest_total_cost_pgk or 0
            sell = quote.latest_total_sell_pgk or 0
            gp = sell - cost
            margin = (gp / sell * 100) if sell > 0 else 0

            origin = quote.origin_location.code if quote.origin_location else ''
            dest = quote.destination_location.code if quote.destination_location else ''
            customer_name = quote.customer.name if quote.customer else ''
            user_name = quote.created_by.username if quote.created_by else ''

            writer.writerow([
                quote.quote_number,
                customer_name,
                origin,
                dest,
                quote.mode,
                float(cost),
                float(sell),
                float(gp),
                round(margin, 1),
                quote.status,
                user_name,
                quote.created_at.strftime('%Y-%m-%d'),
            ])

        return response

    # Keep legacy endpoints for backward compatibility
    @action(detail=False, methods=['get'])
    def dashboard_metrics(self, request):
        """
        Dashboard metrics with timeframe filtering for sales tracking.
        
        Query params:
            timeframe: 'weekly' (last 7 days), 'monthly' (current month), 'ytd' (year to date)
        
        Returns comprehensive metrics including:
            - Pipeline count and value
            - Finalized count and value
            - Win Rate % (ACCEPTED / total sent * 100)
            - Avg Quote Value
            - Lost Opportunity (LOST + EXPIRED value)
            - Weekly activity chart data
        """
        today = timezone.now().date()
        timeframe = request.query_params.get('timeframe', 'monthly')
        
        # Parse timeframe to date range
        if timeframe == 'weekly':
            start_date = today - timedelta(days=6)  # Last 7 days including today
            end_date = today
        elif timeframe == 'ytd':
            start_date = today.replace(month=1, day=1)
            end_date = today
        else:  # default to monthly
            timeframe = 'monthly'
            start_date = today.replace(day=1)
            end_date = today
        
        # Get quotes with financial data for the timeframe
        latest_total = self._get_latest_total_subquery()
        
        qs = Quote.objects.annotate(
            latest_total_sell_pgk=Subquery(latest_total.values('total_sell_pgk')[:1]),
            latest_total_sell_pgk_incl_gst=Subquery(latest_total.values('total_sell_pgk_incl_gst')[:1]),
            latest_total_cost_pgk=Subquery(latest_total.values('total_cost_pgk')[:1]),
        ).exclude(is_archived=True).filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        
        # Pipeline: DRAFT status quotes
        pipeline_stats = qs.filter(status=Quote.Status.DRAFT).aggregate(
            count=Count('id'),
            value=Sum('latest_total_sell_pgk_incl_gst')
        )
        
        # Finalized: FINALIZED status quotes
        finalized_stats = qs.filter(status=Quote.Status.FINALIZED).aggregate(
            count=Count('id'),
            value=Sum('latest_total_sell_pgk_incl_gst')
        )
        
        # Sent quotes (includes SENT, ACCEPTED, LOST for win rate calculation)
        sent_statuses = [Quote.Status.SENT, Quote.Status.ACCEPTED, Quote.Status.LOST]
        sent_stats = qs.filter(status__in=sent_statuses).aggregate(
            total_sent=Count('id'),
            accepted=Count('id', filter=Q(status=Quote.Status.ACCEPTED)),
            lost=Count('id', filter=Q(status=Quote.Status.LOST)),
        )
        
        # Expired quotes
        expired_count = qs.filter(status=Quote.Status.EXPIRED).count()
        
        # Win Rate: ACCEPTED / (SENT + ACCEPTED + LOST) * 100
        total_sent = sent_stats['total_sent'] or 0
        accepted = sent_stats['accepted'] or 0
        win_rate = (accepted / total_sent * 100) if total_sent > 0 else 0
        
        # Average Quote Value (all quotes in timeframe, excluding drafts)
        avg_stats = qs.exclude(status=Quote.Status.DRAFT).aggregate(
            avg_value=Avg('latest_total_sell_pgk_incl_gst')
        )
        
        # Lost Opportunity: Sum of LOST + EXPIRED quote values
        lost_opportunity = qs.filter(
            status__in=[Quote.Status.LOST, Quote.Status.EXPIRED]
        ).aggregate(
            value=Sum('latest_total_sell_pgk_incl_gst')
        )
        
        # Weekly activity (always last 7 days for chart)
        weekly_start = today - timedelta(days=6)
        weekly_activity = []
        for i in range(7):
            day = weekly_start + timedelta(days=i)
            day_count = Quote.objects.filter(
                created_at__date=day,
                is_archived=False
            ).count()
            weekly_activity.append({
                'day': str(day),
                'count': day_count
            })
        
        return Response({
            'timeframe': timeframe,
            'start_date': str(start_date),
            'end_date': str(end_date),
            
            # Pipeline metrics
            'pipeline_count': pipeline_stats['count'] or 0,
            'pipeline_value': float(pipeline_stats['value'] or 0),
            
            # Finalized metrics
            'finalized_count': finalized_stats['count'] or 0,
            'finalized_value': float(finalized_stats['value'] or 0),
            
            # Sales efficiency metrics
            'total_quotes_sent': total_sent,
            'quotes_accepted': accepted,
            'quotes_lost': sent_stats['lost'] or 0,
            'quotes_expired': expired_count,
            'win_rate_percent': round(win_rate, 1),
            'avg_quote_value': float(avg_stats['avg_value'] or 0),
            'lost_opportunity_value': float(lost_opportunity['value'] or 0),
            
            # Chart data
            'weekly_activity': weekly_activity,
        })

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def tier1_customer_stats(self, request):
        """
        Tier-1 Customer Stats for the dashboard.
        Accessible by Sales (scoped to own quotes) and Management (scoped to all).
        """
        start_date, end_date = self._parse_date_params(request)
        target_user_id = self._get_user_scope(request)
        
        # Base QuerySet for the selected period
        qs_period = Quote.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).exclude(is_archived=True)
        
        if target_user_id:
            qs_period = qs_period.filter(created_by_id=target_user_id)
            
        # 1. Active Customers
        # Count distinct customers with >=1 quote
        active_customers_count = qs_period.values('customer').distinct().count()
        
        # 2. Repeat Customers (%)
        # Customers with 2+ quotes in period
        customer_counts = qs_period.values('customer').annotate(
            quote_count=Count('id')
        ).filter(quote_count__gte=2)
        
        repeat_customers_count = customer_counts.count()
        repeat_customers_pct = 0.0
        if active_customers_count > 0:
            repeat_customers_pct = (repeat_customers_count / active_customers_count) * 100
            
        # 3. Top 5 Customers by Pipeline Value (MTD)
        # "Time filter: Monthly only (ignore Weekly / YTD)."
        today = timezone.now().date()
        mtd_start = today.replace(day=1)
        
        # Pipeline = DRAFT, FINALIZED, SENT (Excluding Accepted/Lost/Expired for "Pipeline" usually, 
        # but user said "open / draft / in-progress")
        pipeline_statuses = [Quote.Status.DRAFT, Quote.Status.FINALIZED, Quote.Status.SENT]
        
        qs_pipeline = Quote.objects.filter(
            created_at__date__gte=mtd_start,
            created_at__date__lte=today,
            status__in=pipeline_statuses
        ).exclude(is_archived=True)
        
        if target_user_id:
            qs_pipeline = qs_pipeline.filter(created_by_id=target_user_id)
            
        latest_total = self._get_latest_total_subquery()
        qs_pipeline = qs_pipeline.annotate(
            total_val=Subquery(latest_total.values('total_sell_pgk_incl_gst')[:1])
        )
        
        top_customers = qs_pipeline.values(
            'customer__name'
        ).annotate(
            pipeline_value=Sum('total_val')
        ).order_by('-pipeline_value')[:5]
        
        # 4. Dormant Customers
        # Customers with no quotes in last 30/60/90 days
        # We look at ALL history for the user/company to find last activity
        qs_all_activity = Quote.objects.exclude(is_archived=True)
        if target_user_id:
            qs_all_activity = qs_all_activity.filter(created_by_id=target_user_id)
            
        # Find last quote date for each customer
        from django.db.models import Max
        customer_last_dates = qs_all_activity.values('customer').annotate(
            last_quote_date=Max('created_at')
        )
        
        dormant_30 = 0
        dormant_60 = 0
        dormant_90 = 0
        
        now = timezone.now()
        
        for entry in customer_last_dates:
            last_date = entry['last_quote_date']
            if not last_date:
                continue
            
            delta_days = (now - last_date).days
            
            if 30 <= delta_days < 60:
                dormant_30 += 1
            elif 60 <= delta_days < 90:
                dormant_60 += 1
            elif delta_days >= 90:
                dormant_90 += 1
                
        return Response({
            'active_customers': active_customers_count,
            'repeat_customers_pct': round(repeat_customers_pct, 1),
            'top_customers': [
                {
                    'name': c['customer__name'] or 'Unknown', 
                    'value': float(c['pipeline_value'] or 0)
                } 
                for c in top_customers
            ],
            'dormant_customers': {
                '30d': dormant_30,
                '60d': dormant_60,
                '90d': dormant_90
            }
        })

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """
        Legacy aggregate high-level metrics for the dashboard.
        """
        latest_total_subquery = QuoteTotal.objects.filter(
            quote_version__quote_id=OuterRef('pk')
        ).order_by('-quote_version__version_number').values('total_sell_pgk')[:1]

        quotes_with_latest_total = Quote.objects.annotate(
            latest_total_sell_pgk=Subquery(latest_total_subquery)
        )

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

        # 3. Conversion Rates
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
        Legacy sales performance metrics grouped by user.
        """
        latest_total_subquery = QuoteTotal.objects.filter(
            quote_version__quote_id=OuterRef('pk')
        ).order_by('-quote_version__version_number').values('total_sell_pgk')[:1]

        quotes_with_latest_total = Quote.objects.annotate(
            latest_total_sell_pgk=Subquery(latest_total_subquery)
        )

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
