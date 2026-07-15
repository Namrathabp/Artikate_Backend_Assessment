import json
import math
import redis

class RateLimitedQueue:
    def __init__(self, redis_host='localhost', redis_port=6379, db=0):
        # Establish connection with decode_responses=True for clean string parsing
        self.r = redis.Redis(host=redis_host, port=redis_port, db=db, decode_responses=True)
        self.rate_limit_key = "email_rate_limit:window"
        self.worker_queue_key = "worker_queue"
        self.dlq_key = "dlq:transactional_emails"
        
        # Operational Constraints matching prompt scenario
        self.limit = 200        # Max 200 emails per minute
        self.window = 60        # Sliding/Fixed window scope in seconds

    def is_rate_limited(self) -> tuple[bool, int]:
        """
        Executes an atomic check-and-increment rate limit evaluation via a Redis Pipeline.
        Guarantees thread-safe atomicity without using heavy Lua scripts.
        Returns:
            (is_limited: bool, time_to_reset_seconds: int)
        """
        pipe = self.r.pipeline()
        pipe.incr(self.rate_limit_key)
        pipe.ttl(self.rate_limit_key)
        current_count, ttl = pipe.execute()

        # If the key was just initialized (TTL == -1), bind the structural window expiry
        if current_count == 1 or ttl == -1:
            self.r.expire(self.rate_limit_key, self.window)
            ttl = self.window

        # If the absolute count breaches the 200-item ceiling, trigger throttling
        if current_count > self.limit:
            return True, max(ttl, 1)
        
        return False, 0

    def process_next_job(self, max_retries=5) -> str:
        """
        Pulls a single job from the queue and processes it. Emulates an operational 
        Celery worker while maintaining strict rate limits and error policies.
        """
        # Right-pop to maintain standard FIFO queue behavior alongside LPUSH insertions
        raw_job = self.r.rpop(self.worker_queue_key)
        if not raw_job:
            return "empty"

        job_data = json.loads(raw_job)
        recipient = job_data.get("recipient")
        retries = job_data.get("retries", 0)

        # 1. Enforce Rate Limiting Constraints
        limited, wait_time = self.is_rate_limited()
        if limited:
            # Re-queue the task to the front of the queue instantly (simulating task deferral)
            # We do NOT increment the retry counter since this is a system throttle, not a task failure.
            self.r.lpush(self.worker_queue_key, json.dumps(job_data))
            return "deferred"

        # 2. Execute Business Logic & Handle Task Failures
        try:
            # Simulating an intentional transactional failure profile
            if recipient == "fail@test.com" and retries < 2:
                raise RuntimeError("SMTP Provider Timeout (Simulated Drop)")
            
            # Happy path successfully executed
            return "success"

        except Exception as exc:
            if retries < max_retries:
                # Calculate Exponential Backoff: 2^retries (e.g., 1s, 2s, 4s, 8s...)
                backoff_countdown = int(math.pow(2, retries))
                job_data["retries"] = retries + 1
                job_data["last_error"] = str(exc)
                
                # Re-queue back onto worker execution stream
                self.r.lpush(self.worker_queue_key, json.dumps(job_data))
                return "retry_scheduled"
            else:
                # Exceeded max retries. Route task record to Dead-Letter Queue (DLQ)
                job_data["final_error"] = str(exc)
                self.r.lpush(self.dlq_key, json.dumps(job_data))
                return "dlq_routed"