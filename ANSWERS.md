# Technical Assessment Written Explanations

## Section 1: Diagnose a Broken System

### 1. Incident Investigation Log
1. **Analyze Symptoms:** Reviewed the API metrics.The `/api/orders/summary/` endpoint normalizes at ~80ms but degrades to 30+ seconds solely for users exceeding 200 historical order records immediately following a deployment. 
2. **Review DB Connection Queries:** Wrapped local target unit tests in standard Django connection query counters. We observed that processing 1 order executes 2 total SQL queries, whereas 250 orders execute 251 sequential query queries. 
3. **Inspect Migration Changes:** Checked the repository's git diff logs for database updates.A new `Tenant` foreign key relationship had been added to the base `Order` model schema.

### 2. Root Cause Justification
* **Category:** **N+1 Query Problem via ORM Lazy Loading**.
* **Justification:** The view logic filters base records by user but does not eagerly load related relational tables. When iterating through the order array inside the view loop to compile the property string `order.tenant.name`, the Django ORM lazily runs separate standalone `SELECT` statements for every loop index. This introduces massive sequential network latency overhead that scales linearly with data size ($O(N)$ query footprint).

### 3. ORM Mechanics of the Fix
By explicitly appending `.select_related('tenant')` to the filtering queryset evaluation, we change the core compiler behavior. Instead of loading only order attributes, Django builds a single SQL `INNER JOIN` statement at the database layer. All relevant tenant names are loaded into application layer cache during the original database trip, dropping the endpoint query footprint to a constant $O(1)$ scaling depth.

---

## Section 2: Worker Process SIGKILL Failure Modes
* **The Scenario:** A worker process is instantly terminated via `SIGKILL` while midway through executing a transactional email task.
* **Default Vulnerability:** By default, Celery acknowledges messages immediately upon ingestion (`acks_early`). Under a hard crash, the uncompleted job is lost forever.
* **Mitigation Strategy:** We explicitly defined **`acks_late = True`** on our execution block. This instructs the Celery broker to retain the job lease locked inside the queue. The task acknowledgment is transmitted only *after* successful return execution. If a worker drops dead, Redis safely re-queues the message to an active worker cluster node. **Tasks are developed to be strictly idempotent** to prevent double-delivery side effects.

---

## Section 3: Thread-Locals in Asynchronous Views
* **The Danger:** Thread-local context boundaries (`threading.local`) match variables explicitly to an operating system thread ID.
* **Failure Mode in Async Django:** Modern async views run concurrent coroutines on shared event loops inside a single worker thread. When an asynchronous view hits an `await` marker (e.g., waiting on an external database hit), the execution thread context yields control to handle an incoming alternative coroutine. If Request A sets the thread-local tenant variable and pauses, Request B can read or overwrite that identical global thread space, resulting in cross-tenant data leaks.
* **The safe fix:** We use Python's built-in **`contextvars`** library. `ContextVar` naturally wraps values inside independent asynchronous execution pathways rather than static thread borders, ensuring isolation security across active coroutines.

---

## Section 4: Architectural Review

### Question A: Django Admin Performance at Scale (500k+ Records)
When an admin model grows past 500,000 records, three critical issues slow down page loads:

1. **Pagination Row-Counting Operations:** Django Admin naturally invokes an exact `SELECT COUNT(*)` lookup to render pagination counts. Large relational databases must perform sequential index scans to generate exact matching tallies, which slows down response times.
   * *Fix:* Set `show_full_result_count = False` inside the custom `ModelAdmin` configuration subclass to bypass exact counts and perform rapid estimations.
2. **Relational Field Lookups (N+1 Errors):** Renders listing rows with relational model fields without eager loading.
   * *Fix:* Explicitly declare the `list_select_related = ['related_model_name']` parameter inside the target `ModelAdmin` subclass to force joined database calls.
3. **Bulky Dropdowns:** Standard relational UI widgets load all 500,000 items as raw `<option>` parameters into the HTML body.
   * *Fix:* Set `raw_id_fields = ('related_field',)` or implement `autocomplete_fields` to offload row filtering to an async search backend.

### Question B: Pagination Trade-offs at Scale
1. **Offset-Based Pagination (`LIMIT X OFFSET Y`)**:
   * *Behavior at Scale:* Deep paging requests (e.g., `OFFSET 490000 LIMIT 20`) force the engine to scan and sort through all 490,000 preceding rows into temporary memory blocks before discarding them to extract the targeted tail elements.
   * *Real-World Impact:* Causes severe performance degradation as users scroll deeper. Furthermore, if records are mutated or added during an active mobile app scroll session, items shift window indexes, causing users to see duplicate items or skip entries entirely.
2. **Cursor-Based Pagination (`WHERE id > last_seen_id LIMIT X`)**:
   * *Behavior at Scale:* Direct direct index bounds comparisons seek directly to the row boundary segment, yielding constant $O(1)$ speeds regardless of page depth.
   * *Real-World Impact:* Provides smooth infinite scrolls on high-velocity tables since mutations won't cause items to shift positions across pages.
   * *Trade-off:* The trade-off is losing the ability to jump to arbitrary page numbers (e.g., jumping straight to page 12). Use offset pagination only for small tables with custom page-number selectors, and default to cursors for large infinite-scroll applications.