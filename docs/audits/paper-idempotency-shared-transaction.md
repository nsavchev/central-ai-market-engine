# Idempotency design — blocked until shared transaction

The integration service currently opens its own transaction. An HTTP adapter
cannot atomically reserve a request key and write ledger state without modifying
the service to accept a caller-owned PostgreSQL connection.

This branch adds canonical request hashing and an intentionally fail-closed
adapter. It is **not** an idempotency implementation and must not be used as one.
The next integration change must:
1. Use UNIQUE(account_id, request_key), with request hash and committed result.
2. Reserve or lock the key and check the fence in the **same PostgreSQL transaction**.
3. Reject the same key with a different canonical payload (409).
4. Return the recorded result on exact retries without incrementing trades.
5. Recheck duplicate key conflicts after concurrent requests, including after
   restart and transaction rollback.
6. Keep the production API disabled until a tested schema migration exists.
