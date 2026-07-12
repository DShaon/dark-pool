"use client";

/** Model Desk (ADR-0016) — add any OpenAI-compatible provider (free or paid),
 *  paste its key, and assign any model to any desk role. Keys are sent once to
 *  the server (gitignored store) and only ever come back MASKED (`····last4`);
 *  this component never persists a key in the browser. Every save is
 *  live-tested server-side first, so a broken entry can't be stored — "without
 *  facing any error." Config-over-code (invariant 6) with a real UI over it.
 */

import { useCallback, useEffect, useState } from "react";

import {
  addProvider,
  deleteModelRole,
  deleteProvider,
  fetchRoster,
  setModelRole,
  testModel,
  type RosterView,
} from "@/lib/api";

const PRESETS: Array<{ label: string; url: string }> = [
  { label: "groq", url: "https://api.groq.com/openai/v1" },
  { label: "openrouter", url: "https://openrouter.ai/api/v1" },
  { label: "gemini", url: "https://generativelanguage.googleapis.com/v1beta/openai" },
  { label: "deepseek", url: "https://api.deepseek.com/v1" },
  { label: "together", url: "https://api.together.xyz/v1" },
  { label: "ollama (local)", url: "http://localhost:11434/v1" },
];

const ROLE_META: Record<string, { label: string; bn: string; gold: boolean }> = {
  quick_read: { label: "QUICK READ", bn: "দ্রুত পাঠ", gold: false },
  trend: { label: "TREND", bn: "ধারাবাহিকতা", gold: false },
  contrarian: { label: "CONTRARIAN", bn: "উল্টো দিক", gold: false },
  derivatives: { label: "DERIVATIVES", bn: "পজিশন", gold: false },
  risk: { label: "RISK OFFICER", bn: "ঝুঁকি", gold: false },
  cio: { label: "CIO · SYNTHESIS", bn: "চূড়ান্ত রায়", gold: true },
  scenario: { label: "SCENARIO PATH", bn: "দৃশ্যকল্প", gold: true },
};

type Busy = { kind: string; msg: string; ok: boolean } | null;

export default function ModelDesk() {
  const [roster, setRoster] = useState<RosterView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<Busy>(null);

  const load = useCallback(async () => {
    try {
      setRoster(await fetchRoster());
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed to load roster");
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const flash = (kind: string, msg: string, ok: boolean) => {
    setBusy({ kind, msg, ok });
    window.setTimeout(() => setBusy((b) => (b?.kind === kind ? null : b)), 4000);
  };

  return (
    <div className="card dp-rise card-ai lg:col-span-2" style={{ animationDelay: "180ms" }}>
      <div className="flex items-center justify-between border-b border-[rgba(232,197,116,0.18)] px-5 py-3">
        <span className="micro-label" style={{ color: "var(--ai-gold)", opacity: 0.9 }}>
          model desk · adr-0016
        </span>
        <span className="bn-sub">মডেল ব্যবস্থাপনা</span>
      </div>

      <div className="px-5 py-4">
        {err && <div className="mb-3 rounded-md border border-bear/40 bg-bear/5 px-3 py-2 font-mono text-[11px] text-bear">{err}</div>}

        {/* ── Role matrix ── */}
        <div className="mb-1 flex items-baseline justify-between">
          <span className="micro-label">role assignments</span>
          <span className="font-mono text-[9px] text-dim">who plays what</span>
        </div>
        <div className="space-y-1.5">
          {roster?.roles.map((role) => (
            <RoleRow
              key={role}
              role={role}
              roster={roster}
              onChanged={load}
              onFlash={flash}
            />
          ))}
        </div>

        {/* ── Providers ── */}
        <div className="mt-5 mb-1 flex items-baseline justify-between border-t border-hair/50 pt-4">
          <span className="micro-label">providers</span>
          <span className="font-mono text-[9px] text-dim">keys stay server-side, shown masked</span>
        </div>
        <div className="space-y-1.5">
          {roster?.providers.map((p) => (
            <div key={p.name} className="flex items-center gap-2 text-[11.5px]">
              <span className={`live-dot mr-0.5 ${p.editable ? "bg-pulse" : "bg-bull"}`} />
              <span className="font-mono text-hi">{p.name}</span>
              <span className="font-mono text-[9px] text-dim">{p.api_key === "env" ? "env key" : p.api_key}</span>
              <span className="leader" />
              <span className="font-mono text-[9px] text-dim">{p.source}</span>
              {p.editable && (
                <button
                  onClick={async () => {
                    try {
                      await deleteProvider(p.name);
                      flash("del", `removed ${p.name}`, true);
                      load();
                    } catch (e) {
                      flash("del", e instanceof Error ? e.message : "delete failed", false);
                    }
                  }}
                  className="font-mono text-[11px] text-dim transition-colors hover:text-bear"
                  title={`remove ${p.name}`}
                >
                  ×
                </button>
              )}
            </div>
          ))}
        </div>

        <AddProvider onAdded={load} onFlash={flash} />

        {busy && (
          <div className={`mt-3 font-mono text-[10.5px] ${busy.ok ? "text-bull" : "text-bear"}`}>
            {busy.ok ? "✓ " : "✕ "}
            {busy.msg}
          </div>
        )}
        <p className="mt-3 text-[11px] leading-snug text-dim">
          Any OpenAI-compatible endpoint works (free or paid). Each save is live-tested
          before it&apos;s stored, so a bad key or model is caught here — never mid-run.
          Gold roles are the desk&apos;s judgment voice.
        </p>
      </div>
    </div>
  );
}

function RoleRow({
  role,
  roster,
  onChanged,
  onFlash,
}: {
  role: string;
  roster: RosterView;
  onChanged: () => void;
  onFlash: (k: string, m: string, ok: boolean) => void;
}) {
  const a = roster.assignments[role];
  const meta = ROLE_META[role] ?? { label: role.toUpperCase(), bn: "", gold: false };
  const [editing, setEditing] = useState(false);
  const [provider, setProvider] = useState(a?.provider ?? "");
  const [model, setModel] = useState(a?.model ?? "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!provider || !model.trim()) return;
    setSaving(true);
    try {
      await setModelRole(role, provider, model.trim());
      onFlash(role, `${role} → ${provider}/${model.trim()}`, true);
      setEditing(false);
      onChanged();
    } catch (e) {
      onFlash(role, e instanceof Error ? e.message : "save failed", false);
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    try {
      await deleteModelRole(role);
      onFlash(role, `${role} reset to default`, true);
      setEditing(false);
      onChanged();
    } catch (e) {
      onFlash(role, e instanceof Error ? e.message : "reset failed", false);
    }
  };

  return (
    <div className="rounded-md border border-hair/60 bg-abyss/30 px-3 py-1.5">
      <div className="flex items-center gap-2 text-[11.5px]">
        <span className={`live-dot ${a?.ready ? "bg-bull" : "bg-bear"}`} title={a?.ready ? "ready" : "provider key missing"} />
        <span className={`w-[120px] shrink-0 font-mono text-[10px] tracking-[0.1em] ${meta.gold ? "text-gold" : "text-mid"}`}>
          {meta.label}
        </span>
        <span className={`min-w-0 truncate font-mono ${meta.gold ? "text-gold" : "text-hi"}`}>
          {a?.provider}/{a?.model}
        </span>
        <span className="leader" />
        <span className="shrink-0 font-mono text-[9px] text-dim">{a?.source}</span>
        <button
          onClick={() => setEditing((v) => !v)}
          className="shrink-0 font-mono text-[10px] text-dim transition-colors hover:text-hi"
        >
          {editing ? "cancel" : "edit"}
        </button>
      </div>

      {editing && (
        <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-hair/50 pt-2">
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="rounded-md border border-hair bg-abyss px-2 py-1 font-mono text-[11px] text-hi outline-none"
          >
            <option value="">provider…</option>
            {roster.providers.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="model id, e.g. deepseek-chat"
            spellCheck={false}
            className="min-w-0 flex-1 rounded-md border border-hair bg-abyss px-2 py-1 font-mono text-[11px] text-hi outline-none placeholder:text-dim/70"
          />
          <button
            onClick={save}
            disabled={saving || !provider || !model.trim()}
            className="rounded-md border border-pulse/40 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-hi transition-colors hover:border-pulse/70 disabled:opacity-40"
          >
            {saving ? "saving…" : "save"}
          </button>
          {a?.source === "user" && (
            <button
              onClick={reset}
              className="rounded-md border border-hair px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-dim transition-colors hover:text-warn"
            >
              default
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function AddProvider({
  onAdded,
  onFlash,
}: {
  onAdded: () => void;
  onFlash: (k: string, m: string, ok: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [key, setKey] = useState("");
  const [model, setModel] = useState("");
  const [testing, setTesting] = useState(false);
  const [adding, setAdding] = useState(false);

  const test = async () => {
    if (!url || !key || !model) return;
    setTesting(true);
    try {
      const r = await testModel(url, key, model.trim());
      onFlash("test", r.ok ? `test ok — ${name || "provider"} reachable` : `test failed: ${r.message}`, r.ok);
    } catch (e) {
      onFlash("test", e instanceof Error ? e.message : "test failed", false);
    } finally {
      setTesting(false);
    }
  };

  const add = async () => {
    if (!name || !url || !key) return;
    setAdding(true);
    try {
      const r = await addProvider(name.trim(), url.trim(), key.trim());
      onFlash("add", r.note ? `added ${name} (note: ${r.note})` : `added ${name}`, true);
      setName("");
      setUrl("");
      setKey("");
      setModel("");
      setOpen(false);
      onAdded();
    } catch (e) {
      onFlash("add", e instanceof Error ? e.message : "add failed", false);
    } finally {
      setAdding(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-2 rounded-md border border-hair px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-mid transition-colors hover:border-pulse/40 hover:text-hi"
      >
        + add provider · প্রোভাইডার যোগ
      </button>
    );
  }

  return (
    <div className="mt-2 rounded-md border border-hair/70 bg-abyss/40 px-3 py-3">
      <div className="mb-2 flex flex-wrap gap-1.5">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => {
              setUrl(p.url);
              if (!name) setName(p.label.split(" ")[0]);
            }}
            className={`rounded-md border px-2 py-0.5 font-mono text-[9.5px] transition-colors ${
              url === p.url ? "border-pulse/50 text-hi" : "border-hair text-dim hover:text-mid"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value.toLowerCase())}
          placeholder="name (e.g. deepseek)"
          spellCheck={false}
          className="rounded-md border border-hair bg-abyss px-2 py-1.5 font-mono text-[11px] text-hi outline-none placeholder:text-dim/70"
        />
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="base url (https://…/v1)"
          spellCheck={false}
          className="rounded-md border border-hair bg-abyss px-2 py-1.5 font-mono text-[11px] text-hi outline-none placeholder:text-dim/70"
        />
        <input
          value={key}
          onChange={(e) => setKey(e.target.value)}
          type="password"
          placeholder="api key (stored server-side only)"
          spellCheck={false}
          autoComplete="off"
          className="rounded-md border border-hair bg-abyss px-2 py-1.5 font-mono text-[11px] text-hi outline-none placeholder:text-dim/70"
        />
        <input
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="a model to test (e.g. deepseek-chat)"
          spellCheck={false}
          className="rounded-md border border-hair bg-abyss px-2 py-1.5 font-mono text-[11px] text-hi outline-none placeholder:text-dim/70"
        />
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button
          onClick={test}
          disabled={testing || !url || !key || !model}
          className="rounded-md border border-hair px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-mid transition-colors hover:text-hi disabled:opacity-40"
        >
          {testing ? "testing…" : "test"}
        </button>
        <button
          onClick={add}
          disabled={adding || !name || !url || !key}
          className="rounded-md border border-pulse/40 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-hi transition-colors hover:border-pulse/70 disabled:opacity-40"
        >
          {adding ? "adding…" : "add"}
        </button>
        <button
          onClick={() => setOpen(false)}
          className="ml-auto font-mono text-[10px] text-dim transition-colors hover:text-hi"
        >
          cancel
        </button>
      </div>
    </div>
  );
}
