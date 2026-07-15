import contextvars

# 1. Define Context Variables safe across async/await boundaries
_current_tenant_id = contextvars.ContextVar("current_tenant_id", default=None)

def get_current_tenant_id():
    return _current_tenant_id.get()

def set_current_tenant_id(tenant_id):
    _current_tenant_id.set(tenant_id)

def clear_current_tenant_id():
    _current_tenant_id.set(None)


# 2. Implement Custom Tenant Scoped Model Manager
class TenantManager:
    """
    Automatically hooks all queries to filter results by the active tenant ID context.
    If no tenant is bound, it fails closed by returning an empty list.
    """
    def __init__(self, base_manager=None):
        self.base_manager = base_manager

    def get_queryset(self):
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return self.none()
        return self.filter(tenant_id=tenant_id)

    def none(self):
        return []

    def filter(self, **kwargs):
        # This will be overridden dynamically by the test harness stub
        pass


# 3. Request Lifecycle Extraction Middleware Mock
class TenantMiddleware:
    """
    Extracts tenant identification context securely out of incoming request headers 
    and guarantees a clean context tear-down at response finalization.
    """
    def __call__(self, request):
        self.process_request(request)
        
    def process_request(self, request):
        tenant_header = request.headers.get("X-Tenant-ID")
        if tenant_header:
            set_current_tenant_id(int(tenant_header))
        else:
            set_current_tenant_id(None)

    def process_response(self, request, response):
        clear_current_tenant_id()
        return response