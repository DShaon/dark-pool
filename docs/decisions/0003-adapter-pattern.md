# ADR-0003: All external I/O through the adapter layer

**Status:** Accepted (2026-07-06)

**Context.** Data sources will change constantly (free today, paid tomorrow, new ones
discovered). Vendor lock-in anywhere in analysis code would make swaps expensive.

**Decision.** Every external source is one class in `backend/app/adapters/` implementing
the `DataProvider` interface, registered via config. No HTTP calls exist outside adapters.
Each adapter owns its rate limiter.

**Consequences.** Adding Coinglass/Glassnode/OANDA/Alpaca later = one file + one config
entry. Analysis code never knows vendor names.
