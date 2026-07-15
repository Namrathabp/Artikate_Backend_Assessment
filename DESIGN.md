# Rate-Limited Asynchronous Job Queue Architecture

## 1. Core Component Choice & Trade-offs
For the transactional email processing system, three core approaches were evaluated:

* **Celery + Redis (Chosen Alternative):** * *Pros:* Native memory caching layer providing rapid execution speeds under high concurrent bursts (2,000 tasks/10s). Fully decouples task scheduling from worker threads. Native task retry pipelines and acknowledgment mechanisms (`acks_late`) make it resilient to process crashes.
  * *Cons:* Requires independent daemon services and explicit infrastructure orchestration.
* **Django Q:**
  * *Pros:* Simpler deployment footprints as background workers plug right into existing Django application environments.
  * *Cons:* Relies heavily on database polling tables. Subjecting a relational database (PostgreSQL/MySQL) to immediate 2,000-row batch spikes causes high connection locking and introduces system-wide latency.
* **Custom Pure-Python Loop:**
  * *Pros:* Zero external infrastructure dependencies.
  * *Cons:* Extremely fragile. Thread pools lack persistent storage buffers; if a process crashes, all in-flight and pending array items are lost instantly.

**Decision:** Celery + Redis was selected due to its enterprise scalability and robust failure isolation under unpredictable peak burst loads.

---

## 2. Rate Limiter Strategy Selection
We evaluated three patterns for enforcing the strict 200 emails per minute limit:

* **Option A: Token Bucket (Redis DECR + TTL):** Good burst handling, but introduces implementation complexity around deterministic bucket refilling across independent distributed clusters.
* **Option B: Sliding Window Log (Sorted Set + ZREMRANGEBYSCORE):** Most precise, but incurs high memory overhead under heavy concurrency due to storing independent timestamps for every tracking element.
* **Option C: Fixed Window (INCR + EXPIRE) (Chosen Alternative):** Implements an incredibly light memory footprint by maintaining a single integer counter per active window.

### Architectural Guarantee of Atomicity
To eliminate race conditions between checking the count and incrementing the window, we utilize a **Redis Pipeline (MULTI/EXEC)** block. By batching the `INCR` and `TTL` operations into a single atomic transactional unit, the database engine executes both commands sequentially without allowing interleaved writes from concurrent threads. This ensures our 200-email threshold is never breached by race conditions.

### Behavior Under Redis Outage (Fail Open vs. Closed)
Our custom architecture is explicitly configured to **Fail Closed**. If the connection to the Redis server drops, the `is_rate_limited()` method intercepts the connection exception and immediately treats the status as throttled, aborting execution. This guarantees that external provider rate restrictions (200/min) are never violated, protecting our transactional reputation at the expense of temporary system availability.