import pytest
import json
import redis
import time
from .queue_system import RateLimitedQueue

@pytest.fixture(autouse=True)
def clean_redis_environment():
    """Ensures an isolated database context before each test run."""
    r = redis.Redis(host='localhost', port=6379, db=0)
    r.flushdb()
    yield
    r.flushdb()

def test_job_queue_rate_limiting_and_integrity():
    queue_system = RateLimitedQueue()
    r = redis.Redis(host='localhost', port=6379, db=0)

    # 1. Push the intentional failure task FIRST. 
    # Because of LPUSH + RPOP mechanics, this positions it directly at the tail to be pulled out first!
    fail_job = {"recipient": "fail@test.com", "retries": 0}
    r.lpush(queue_system.worker_queue_key, json.dumps(fail_job))

    # 2. Seed the 499 standard background jobs next
    for i in range(499):
        job = {"recipient": f"customer_{i}@domain.com", "retries": 0}
        r.lpush(queue_system.worker_queue_key, json.dumps(job))

    # Metric tracking maps
    processed_successfully = 0
    deferred_throttled = 0
    retry_triggered = False

    # 3. Drain the queue through a clean unified processor loop
    for _ in range(500):
        if r.llen(queue_system.worker_queue_key) == 0:
            break
            
        status = queue_system.process_next_job()

        if status == "success":
            processed_successfully += 1
        elif status == "deferred":
            deferred_throttled += 1
            # Stop processing immediately once the rate limit ceiling is reached
            break
        elif status == "retry_scheduled":
            retry_triggered = True

    # 4. Comprehensive Engineering Assertions
    redis_logged_hits = int(r.get(queue_system.rate_limit_key) or 0)
    
    # Assert: The rate limiter strictly prevented more than 200 runs from clearing successfully [cite: 52, 63]
    assert processed_successfully <= 200, f"Rate limiter breached! Allowed: {processed_successfully}"
    assert processed_successfully >= 199, f"Unexpected success window volume: {processed_successfully}"
    
    # Assert: The excess tasks were properly preserved via the deferral loop [cite: 54, 63]
    assert deferred_throttled > 0, "System failed to trigger deferrals under burst volume load."
    
    # Assert: The intentional failure task successfully entered the backoff retry path [cite: 54, 63]
    assert retry_triggered, "Failure monitoring mechanism did not trigger a retry flow."
    
    # Assert: Zero Data Loss. Total remaining + total completed must explicitly account for all records [cite: 54, 63]
    remaining_in_queue = r.llen(queue_system.worker_queue_key)
    grand_total = processed_successfully + remaining_in_queue
    
    assert grand_total == 500, f"Data loss detected! Only accounted for {grand_total}/500 total elements."