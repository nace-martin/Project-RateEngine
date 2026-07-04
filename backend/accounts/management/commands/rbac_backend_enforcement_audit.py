import json
import inspect
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Audit backend API RBAC enforcement and scope validation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--format',
            choices=['text', 'json'],
            default='text',
            help='Output format. Defaults to text.',
        )

    def handle(self, *args, **options):
        report = self.build_detailed_audit_report()

        if options['format'] == 'json':
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return

        self.write_detailed_text_report(report)

    def build_detailed_audit_report(self):
        report = {
            'phase': '11A',
            'audit_type': 'Backend RBAC Enforcement',
            'findings': {
                'detailed_endpoint_audit': [],
                'summary_stats': {},
                'gaps_found': []
            },
            'summary': {
                'total_sensitive_endpoints': 0,
                'properly_secured_endpoints': 0,
                'improperly_secured_endpoints': 0,
                'gaps_count': 0,
                'status': 'NOT_READY'  # Default to NOT_READY
            }
        }

        # Perform detailed endpoint audit
        detailed_audit = self.audit_detailed_endpoints()
        report['findings']['detailed_endpoint_audit'] = detailed_audit

        # Calculate summary statistics
        report['summary']['total_sensitive_endpoints'] = len(detailed_audit)
        properly_secured = sum(1 for endpoint in detailed_audit if endpoint['status'] == 'SECURE')
        report['summary']['properly_secured_endpoints'] = properly_secured
        report['summary']['improperly_secured_endpoints'] = len(detailed_audit) - properly_secured

        # Identify gaps
        report['findings']['gaps_found'] = [endpoint for endpoint in detailed_audit if endpoint['status'] != 'SECURE']
        report['summary']['gaps_count'] = len(report['findings']['gaps_found'])

        # Determine final status
        if report['summary']['gaps_count'] == 0:
            report['summary']['status'] = 'READY'
        else:
            report['summary']['status'] = 'NOT_READY'

        return report

    def audit_detailed_endpoints(self):
        """Perform detailed audit of each sensitive endpoint by inspecting actual view/queryset/permission behavior"""
        endpoints = []

        def inspected(endpoint, model, view_class_path, details):
            list_scoped = self._inspect_view_queryset(view_class_path)
            object_validation = self._inspect_get_object_method(view_class_path)
            role_validation = self._inspect_permission_classes(view_class_path)
            return {
                'endpoint': endpoint,
                'model': model,
                'list_scoped': list_scoped,
                'object_validation': object_validation,
                'role_validation': role_validation,
                'status': 'SECURE' if (list_scoped and object_validation and role_validation) else 'NEEDS_TEST',
                'details': details,
            }

        def asserted(endpoint, model, details, status='NEEDS_TEST'):
            return {
                'endpoint': endpoint,
                'model': model,
                'list_scoped': 'ASSERTED',
                'object_validation': 'ASSERTED',
                'role_validation': 'ASSERTED',
                'status': status,
                'details': details,
            }

        # CRM Endpoints - Check actual implementations
        endpoints.extend([
            inspected('CRM_Companies', 'parties.Company', 'parties.views.CustomerV3ViewSet', 'Companies endpoint inspected for scoped queryset, object lookup, and permissions'),
            asserted('CRM_Contacts', 'parties.Contact', 'Contacts are exposed as a company-nested list; retrieve endpoint is not inspectable in this audit', 'NOT_INSPECTABLE'),
            inspected('CRM_Opportunities', 'crm.Opportunity', 'crm.views.OpportunityViewSet', 'Opportunities endpoint inspected for scoped queryset, object lookup, and permissions'),
            inspected('CRM_Interactions', 'crm.Interaction', 'crm.views.InteractionViewSet', 'Interactions endpoint inspected for scoped queryset, object lookup, and permissions'),
            inspected('CRM_Tasks', 'crm.Task', 'crm.views.TaskViewSet', 'Tasks endpoint inspected for scoped queryset, object lookup, and permissions'),
        ])

        # Quote Endpoints
        endpoints.extend([
            inspected('Quotes_List', 'quotes.Quote', 'quotes.views.lifecycle.QuoteV3ViewSet', 'Quote viewset inspected for get_quotes_for_user/get_quote_for_user and permissions'),
            inspected('Quotes_Detail', 'quotes.Quote', 'quotes.views.lifecycle.QuoteV3ViewSet', 'Quote viewset inspected for get_quotes_for_user/get_quote_for_user and permissions'),
            inspected('Draft_Quote_Read', 'quotes.SpotPricingEnvelopeDB', 'quotes.spot_views.SpotEnvelopeDraftQuoteAPIView', 'Draft quote read inspected for SPE object lookup and permissions'),
            inspected('Draft_Quote_Resolve', 'quotes.SpotPricingEnvelopeDB', 'quotes.spot_views.SpotEnvelopeDraftQuoteResolveAPIView', 'Draft quote resolve inspected for SPE object lookup and permissions'),
        ])

        # SPOT Envelope Endpoints
        endpoints.extend([
            inspected('SPOT_Envelopes_List', 'quotes.SpotPricingEnvelopeDB', 'quotes.spot_views.SpotEnvelopeListCreateAPIView', 'SPOT envelope list/create inspected for scoped SPE queryset and permissions'),
            inspected('SPOT_Envelopes_Detail', 'quotes.SpotPricingEnvelopeDB', 'quotes.spot_views.SpotEnvelopeDetailAPIView', 'SPOT envelope detail inspected for SPE object lookup and permissions'),
        ])

        # ProductCode Endpoints
        endpoints.extend([
            asserted('ProductCode_Requests', 'pricing_v4.ProductCodeCreationRequest', 'ProductCode request coverage requires API tests; audit does not prove scope from static assumptions'),
            asserted('ProductCode_Review', 'pricing_v4.ProductCodeCreationRequest', 'ProductCode review coverage requires API tests; audit does not prove role/scope from static assumptions'),
        ])

        # Manager/Admin Override Endpoints
        endpoints.extend([
            asserted('Manager_Override', 'accounts.UserMembership', 'Manager override is asserted by role behavior and must be backed by API tests'),
            asserted('Admin_Override', 'accounts.UserMembership', 'Admin override is asserted by role behavior and must be backed by API tests'),
        ])

        # Cross-Scope Endpoints
        endpoints.extend([
            asserted('Cross_Organization_Access', 'parties.Organization', 'Cross-organization behavior is asserted and needs API tests'),
            asserted('Cross_OperatingEntity_Access', 'parties.OperatingEntity', 'Cross-operating entity behavior is asserted and needs API tests'),
            asserted('Cross_Branch_Access', 'parties.Branch', 'Cross-branch behavior is asserted and needs API tests'),
            asserted('Cross_Department_Access', 'parties.Department', 'Cross-department behavior is asserted and needs API tests'),
        ])

        # Anonymous and ID Guessing Endpoints
        endpoints.extend([
            asserted('ID_Guessing_Protection', 'Various', 'ID guessing behavior must be proven by API tests'),
            asserted('Anonymous_Access', 'Various', 'Anonymous access behavior must be proven by API tests'),
        ])

        return endpoints

    def _inspect_view_queryset(self, view_class_path):
        """Inspect if a view properly implements queryset scoping"""
        try:
            module_path, class_name = view_class_path.rsplit('.', 1)
            module = __import__(module_path, fromlist=[class_name])
            view_class = getattr(module, class_name)

            if hasattr(view_class, 'get_queryset'):
                source = inspect.getsource(view_class.get_queryset)
            else:
                source = inspect.getsource(view_class)
            return any(token in source for token in (
                'scoped_queryset_for_user',
                'get_quotes_for_user',
                'get_spes_for_user',
            ))
        except (ImportError, AttributeError):
            pass
        return False

    def _inspect_get_object_method(self, view_class_path):
        """Inspect if a view implements proper object-level validation"""
        try:
            module_path, class_name = view_class_path.rsplit('.', 1)
            module = __import__(module_path, fromlist=[class_name])
            view_class = getattr(module, class_name)

            source = inspect.getsource(view_class)
            return any(token in source for token in (
                'get_quote_for_user',
                'get_spes_for_user',
                '_get_spe_or_404',
                'self.get_queryset()',
                'filter_queryset(self.get_queryset())',
            ))
        except (ImportError, AttributeError):
            pass
        return False

    def _inspect_permission_classes(self, view_class_path):
        """Inspect if a view implements proper permission classes"""
        try:
            module_path, class_name = view_class_path.rsplit('.', 1)
            module = __import__(module_path, fromlist=[class_name])
            view_class = getattr(module, class_name)

            permission_classes = getattr(view_class, 'permission_classes', None)
            return bool(permission_classes)
        except (ImportError, AttributeError):
            pass
        return False

    def write_detailed_text_report(self, report):
        self.stdout.write("RBAC Backend Enforcement Audit Report")
        self.stdout.write("=" * 50)
        self.stdout.write(f"Phase: {report['phase']}")
        self.stdout.write(f"Audit Type: {report['audit_type']}")
        self.stdout.write(f"Status: {report['summary']['status']}")
        self.stdout.write("")

        self.stdout.write(f"Summary:")
        self.stdout.write(f"  - Total sensitive endpoints: {report['summary']['total_sensitive_endpoints']}")
        self.stdout.write(f"  - Properly secured endpoints: {report['summary']['properly_secured_endpoints']}")
        self.stdout.write(f"  - Improperly secured endpoints: {report['summary']['improperly_secured_endpoints']}")
        self.stdout.write(f"  - Total gaps found: {report['summary']['gaps_count']}")
        self.stdout.write("")

        if report['findings']['gaps_found']:
            self.stdout.write("GAPS IDENTIFIED:")
            self.stdout.write("-" * 20)
            for gap in report['findings']['gaps_found']:
                self.stdout.write(f"  - {gap['endpoint']}: {gap['details']}")
            self.stdout.write("")
        else:
            self.stdout.write("No gaps found! All systems appear to be properly enforced.")
            self.stdout.write("")

        self.stdout.write("DETAILED ENDPOINT AUDIT:")
        self.stdout.write("-" * 80)
        self.stdout.write(f"{'Endpoint':<30} {'Model':<30} {'List':<6} {'Obj':<6} {'Role':<6} {'Status':<8}")
        self.stdout.write("-" * 80)

        for endpoint in report['findings']['detailed_endpoint_audit']:
            self.stdout.write(f"{endpoint['endpoint']:<30} {endpoint['model']:<30} {str(endpoint['list_scoped'])[0]:<6} {str(endpoint['object_validation'])[0]:<6} {str(endpoint['role_validation'])[0]:<6} {endpoint['status']:<8}")

        self.stdout.write("")
        self.stdout.write("Endpoint Details:")
        for endpoint in report['findings']['detailed_endpoint_audit']:
            self.stdout.write(f"  {endpoint['endpoint']}: {endpoint['details']}")

        self.stdout.write("")
        self.stdout.write("Recommendations:")
        if report['summary']['gaps_count'] > 0:
            self.stdout.write("  - Fix identified gaps before production deployment")
            self.stdout.write("  - Implement missing permission checks")
            self.stdout.write("  - Add object-level validation where missing")
        else:
            self.stdout.write("  - System appears ready for production")
            self.stdout.write("  - Continue monitoring for any new endpoints")
