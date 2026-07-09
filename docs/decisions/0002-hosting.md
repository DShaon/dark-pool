# ADR-0002: Hosting — Oracle Always-Free ARM + Vercel + Supabase + Upstash

**Status:** Accepted (2026-07-06)

**Context.** Build must cost $0; background monitoring needs an always-on process (Render/
Railway free tiers sleep).

**Decision.** Backend 24/7 on Oracle Cloud Always-Free ARM VM. Frontend on Vercel free.
Postgres on Supabase free (500MB). Redis on Upstash free. All infra is env-configured so
any piece can be swapped.

**Consequences.** ARM Linux prod → pure-Python deps (see ADR-0001). DB size budget means
bulk candles are cached, not stored.
