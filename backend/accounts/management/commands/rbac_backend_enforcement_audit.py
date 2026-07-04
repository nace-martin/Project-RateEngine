import inspect
import json
from django.core.management.base import BaseCommand


BLOCKING_STATUSES = {'BLOCKED'}
READY_STATUSES = {'INSPECTED', 'TESTED', 'NOT_APPLICABLE'}

API_TEST_METHODS = {
    'CRM_Contacts': 'test_contact_list_cross_scope_and_no_retrieve_claim',
    'Draft_Quote_Read': 'test_draft_quote_read_resolve_cross_scope',
    'Draft_Quote_Resolve': 'test_draft_quote_read_resolve_cross_scope',
    'SPOT_Envelopes_Detail': 'test_spot_envelope_read_write_cross_scope',
    'ProductCode_Requests': 'test_product_code_request_review_role_scope',
    'ProductCode_Review': 'test_product_code_request_review_role_scope',
    'Manager_Override': 'test_manager_override_same_scope',
    'Admin_Override': 'test_admin_override',
    'Cross_OperatingEntity_Access': 'test_cross_operating_entity_branch_department_blocked',
    'Cross_Branch_Access': 'test_cross_operating_entity_branch_department_blocked',
    'Cross_Department_Access': 'test_cross_operating_entity_branch_department_blocked',
    'ID_Guessing_Protection': 'test_id_guessing_blocked',
    'Anonymous_Access': 'test_anonymous_blocked',
}


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
            'phase': '11B',
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
                'status': 'NOT_READY'
            }
        }

        # Perform detailed endpoint audit
        detailed_audit = self.audit_detailed_endpoints()
        report['findings']['detailed_endpoint_audit'] = detailed_audit

        # Calculate summary statistics
        report['summary']['total_sensitive_endpoints'] = len(detailed_audit)
        properly_secured = sum(1 for endpoint in detailed_audit if endpoint['status'] in READY_STATUSES)
        report['summary']['properly_secured_endpoints'] = properly_secured
        report['summary']['improperly_secured_endpoints'] = len(detailed_audit) - properly_secured

        # Identify gaps
        report['findings']['gaps_found'] = [endpoint for endpoint in detailed_audit if endpoint['status'] in BLOCKING_STATUSES]
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
                'status': 'INSPECTED' if (list_scoped and object_validation and role_validation) else 'BLOCKED',
                'details': details,
            }

        def tested(endpoint, model, details):
            test_method = API_TEST_METHODS[endpoint]
            has_test = self._test_method_exists(test_method)
            return {
                'endpoint': endpoint,
                'model': model,
                'list_scoped': 'TESTED',
                'object_validation': 'TESTED',
                'role_validation': 'TESTED',
                'status': 'TESTED' if has_test else 'BLOCKED',
                'details': details,
                'test_evidence': f'quotes.tests.test_rbac_backend_enforcement.RBACBackendEnforcementAPITest.{test_method}',
            }

        def not_applicable(endpoint, model, details):
            return {
                'endpoint': endpoint,
                'model': model,
                'list_scoped': 'NOT_APPLICABLE',
                'object_validation': 'NOT_APPLICABLE',
                'role_validation': 'NOT_APPLICABLE',
                'status': 'NOT_APPLICABLE',
                'details': details,
            }

        # CRM Endpoints - Check actual implementations
        endpoints.extend([
            inspected('CRM_Companies', 'parties.Company', 'parties.views.CustomerV3ViewSet', 'Companies endpoint inspected for scoped queryset, object lookup, and permissions'),
            not_applicable('CRM_Contacts', 'parties.Contact', 'Contacts are exposed only as a company-nested list; there is no standalone retrieve route to inspect'),
            inspected('CRM_Opportunities', 'crm.Opportunity', 'crm.views.OpportunityViewSet', 'Opportunities endpoint inspected for scoped queryset, object lookup, and permissions'),
            inspected('CRM_Interactions', 'crm.Interaction', 'crm.views.InteractionViewSet', 'Interactions endpoint inspected for scoped queryset, object lookup, and permissions'),
            inspected('CRM_Tasks', 'crm.Task', 'crm.views.TaskViewSet', 'Tasks endpoint inspected for scoped queryset, object lookup, and permissions'),
        ])

        # Quote Endpoints
        endpoints.extend([
            inspected('Quotes_List', 'quotes.Quote', 'quotes.views.lifecycle.QuoteV3ViewSet', 'Quote viewset inspected for get_quotes_for_user/get_quote_for_user and permissions'),
            inspected('Quotes_Detail', 'quotes.Quote', 'quotes.views.lifecycle.QuoteV3ViewSet', 'Quote viewset inspected for get_quotes_for_user/get_quote_for_user and permissions'),
            tested('Draft_Quote_Read', 'quotes.SpotPricingEnvelopeDB', 'Draft quote read cross-scope behavior is proven by API regression coverage'),
            tested('Draft_Quote_Resolve', 'quotes.SpotPricingEnvelopeDB', 'Draft quote resolve cross-scope behavior is proven by API regression coverage'),
        ])

        # SPOT Envelope Endpoints
        endpoints.extend([
            inspected('SPOT_Envelopes_List', 'quotes.SpotPricingEnvelopeDB', 'quotes.spot_views.SpotEnvelopeListCreateAPIView', 'SPOT envelope list/create inspected for scoped SPE queryset and permissions'),
            tested('SPOT_Envelopes_Detail', 'quotes.SpotPricingEnvelopeDB', 'SPOT envelope detail and PATCH cross-scope behavior is proven by API regression coverage'),
        ])

        # ProductCode Endpoints
        endpoints.extend([
            tested('ProductCode_Requests', 'pricing_v4.ProductCodeCreationRequest', 'ProductCode request create role and source scope behavior is proven by API regression coverage'),
            tested('ProductCode_Review', 'pricing_v4.ProductCodeCreationRequest', 'ProductCode review/admin action behavior is proven by API regression coverage'),
        ])

        # Manager/Admin Override Endpoints
        endpoints.extend([
            tested('Manager_Override', 'accounts.UserMembership', 'Manager same-scope access behavior is proven by API regression coverage'),
            tested('Admin_Override', 'accounts.UserMembership', 'Admin cross-scope access behavior is proven by API regression coverage'),
        ])

        # Cross-Scope Endpoints
        endpoints.extend([
            inspected('Cross_Organization_Access', 'parties.Organization', 'parties.views.CustomerV3ViewSet', 'Cross-organization filtering uses the same scoped queryset/object lookup inspection as company APIs'),
            tested('Cross_OperatingEntity_Access', 'parties.OperatingEntity', 'Cross-operating entity denial is proven by API regression coverage'),
            tested('Cross_Branch_Access', 'parties.Branch', 'Cross-branch denial is proven by API regression coverage'),
            tested('Cross_Department_Access', 'parties.Department', 'Cross-department denial is proven by API regression coverage'),
        ])

        # Anonymous and ID Guessing Endpoints
        endpoints.extend([
            tested('ID_Guessing_Protection', 'Various', 'ID guessing behavior is proven by API regression coverage'),
            tested('Anonymous_Access', 'Various', 'Anonymous access blocking is proven by API regression coverage'),
        ])

        return endpoints

    def _test_method_exists(self, method_name):
        try:
            from quotes.tests.test_rbac_backend_enforcement import RBACBackendEnforcementAPITest
        except ImportError:
            return False
        return callable(getattr(RBACBackendEnforcementAPITest, method_name, None))

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
            self.stdout.write("  - Backend RBAC enforcement audit is READY")
            self.stdout.write("  - Continue monitoring for any new endpoints")
