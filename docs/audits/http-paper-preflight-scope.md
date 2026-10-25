# HTTP preflight scope

This draft tests only the **existing** API's authentication, invalid-input
refusal and absence of a new fenced route. It does not enable or call the
new transactional PostgreSQL service. It is not a successful end-to-end
transaction or readiness test. The production API remains unsafe for a
mixed legacy/new migration until the canonical NUMERIC schema, fence
and every writer have been integrated and reviewed.

CI uses a disposable SQLite database configured in the workflow.
No orders, VPS access, or production schema changes are performed.
