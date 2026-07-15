from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Order

@login_required
def order_summary_bad(request):
    """
    REPRODUCING THE REGRESSION:
    This endpoint times out under high load (>200 orders).
    The view filters by User, but fails to eagerly fetch the Tenant relation.
    When accessing `order.tenant.name` in the loop, the Django ORM is forced 
    to hit the database sequentially for every single record (N+1 Query Problem).
    """
    orders = Order.objects.filter(user=request.user) 
    
    summary_data = []
    for order in orders:
        summary_data.append({
            "id": order.id,
            "tenant_name": order.tenant.name,  # DB Hit per iteration!
            "amount": float(order.amount)
        })
        
    return JsonResponse({"status": "success", "orders": summary_data})


@login_required
def order_summary_fixed(request):
    """
    THE FIX:
    By adding `.select_related('tenant')`, the ORM compiler performs a SQL 
    INNER JOIN at the database layer, pulling down all relevant Tenant attributes 
    in a single round-trip. The loop then reads data straight from memory cache.
    """
    orders = Order.objects.filter(user=request.user).select_related('tenant')
    
    summary_data = [
        {
            "id": order.id,
            "tenant_name": order.tenant.name,  # Read instantly from cached memory object
            "amount": float(order.amount)
        }
        for order in orders
    ]
    return JsonResponse({"status": "success", "orders": summary_data})