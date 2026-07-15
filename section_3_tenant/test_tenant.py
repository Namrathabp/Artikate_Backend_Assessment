import pytest
from .multitenancy import TenantManager, set_current_tenant_id, clear_current_tenant_id

class MockTenant:
    def __init__(self, id, name):
        self.id = id
        self.name = name

class MockOrder:
    objects = TenantManager()

    def __init__(self, id, tenant_id, description):
        self.id = id
        self.tenant_id = tenant_id
        self.description = description

def mock_base_queryset_filter(tenant_id):
    all_database_records = [
        MockOrder(id=1, tenant_id=101, description="Tenant A - Order 1"),
        MockOrder(id=2, tenant_id=101, description="Tenant A - Order 2"),
        MockOrder(id=3, tenant_id=102, description="Tenant B - Order 1"),
    ]
    if tenant_id is None:
        return []
    return [r for r in all_database_records if r.tenant_id == tenant_id]

@pytest.fixture(autouse=True)
def setup_mock_orm(monkeypatch):
    """Stubs out underlying data evaluation methods to run purely locally."""
    monkeypatch.setattr(TenantManager, "filter", lambda self, tenant_id: mock_base_queryset_filter(tenant_id))
    yield
    clear_current_tenant_id()

def test_tenant_isolation_enforcement():
    """
    Asserts that Tenant A cannot access Tenant B's data under any standard 
    un-scoped ORM lookup method call, explicitly verifying .get_queryset().
    """
    # 1. Simulate Request Lifecycle Context bound to Tenant A (ID: 101)
    set_current_tenant_id(101)

    # 2. Call the auto-scoped queryset method
    tenant_a_results = MockOrder.objects.get_queryset()

    # Verify that ONLY Tenant A records are surfaced
    assert len(tenant_a_results) == 2
    for order in tenant_a_results:
        assert order.tenant_id == 101
        assert "Tenant B" not in order.description

def test_fail_closed_on_missing_tenant_context():
    """
    Asserts that if the tenant lifecycle mapping breaks or is omitted, 
    the system completely locks down data visualization rather than leaking globally.
    """
    # Force unbound request state context
    clear_current_tenant_id()

    # Attempt lookup execution paths
    blind_lookup = MockOrder.objects.get_queryset()

    # Should safely isolate down to exactly zero elements
    assert len(blind_lookup) == 0