// EmberHeart Reborn — no-build Preact UI.
import { h, render } from "https://esm.sh/preact@10.20.2";
import { useState, useEffect, useRef, useCallback } from "https://esm.sh/preact@10.20.2/hooks";
import htm from "https://esm.sh/htm@3.1.1";

const html = htm.bind(h);

// ----------------------------------------------------------------- api helper
const pw = () => localStorage.getItem("eh_pw") || "";
async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (pw()) headers["X-App-Password"] = pw();
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) {
    const p = prompt("App password:");
    if (p) { localStorage.setItem("eh_pw", p); return api(path, opts); }
  }
  return res.json();
}
const post = (p, body) => api(p, { method: "POST", body: JSON.stringify(body || {}) });

// --------------------------------------------------------------------- toasts
let _toastId = 0;
function useToasts() {
  const [toasts, setToasts] = useState([]);
  const add = useCallback((message, kind = "info") => {
    const id = ++_toastId;
    setToasts((t) => [...t, { id, message, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);
  return { toasts, add };
}
function Toasts({ toasts }) {
  return html`<div class="toasts">
    ${toasts.map((t) => html`<div class=${"toast " + t.kind} key=${t.id}>${t.message}</div>`)}
  </div>`;
}

// --------------------------------------------------------------------- header
function Header({ health, conn, model, onMenu }) {
  const cls = conn === "open" ? "on" : conn === "connecting" ? "warn" : "off";
  const m = model || health?.narration_model || "";
  const isCloud = m.includes(":cloud");
  const shortM = m.split("/").pop();  // drop org prefix (e.g. sparksammy/…)
  const modelReady = !m || isCloud || health?.narration_ready;
  return html`
    <header>
      <h1>EmberHeart Reborn</h1>
      <span class="sub">— Chronicle Weaver · the Origins Era</span>
      <span class="spacer"></span>
      ${m ? html`<span class="small model-tag" title=${"active narration model: " + m}>
        ${isCloud ? "☁️" : "🧠"} ${shortM}${!modelReady ? " ⚠" : ""}</span>` : null}
      <span class="small" style="margin-left:14px"><span class=${"dot " + cls}></span>link ${conn}</span>
      <span class="small" style="margin-left:14px">
        <span class=${"dot " + (health?.ollama ? "on" : "off")}></span>
        Ollama ${health?.ollama ? "ready" : "offline"}
      </span>
      <button class="menu-btn" onClick=${onMenu} aria-label="toggle panels">☰</button>
    </header>`;
}

// ----------------------------------------------------------------- play column
function Play({ onStateChange, onCombat, toast, reportConn, onModel }) {
  const [beats, setBeats] = useState([]);
  const [streaming, setStreaming] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [picks, setPicks] = useState([]);   // indices of selected suggestions (multi-select)
  const [suggCollapsed, setSuggCollapsed] = useState(false);  // mobile: hide suggestions while scrolled up reading
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [conn, setConn] = useState("connecting");
  const wsRef = useRef(null);
  const logRef = useRef(null);
  const acc = useRef("");
  const retry = useRef(0);
  const lastSeq = useRef(0);

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= 1) return;  // already connecting/open
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${location.host}/api/play/ws${pw() ? "?pw=" + encodeURIComponent(pw()) : ""}`;
    setConn("connecting"); reportConn && reportConn("connecting");
    const ws = new WebSocket(url);
    ws.onopen = () => { setConn("open"); reportConn && reportConn("open"); retry.current = 0; };
    ws.onmessage = (ev) => handleEvent(JSON.parse(ev.data));
    ws.onclose = () => {
      setConn("closed"); reportConn && reportConn("closed"); setBusy(false);
      const delay = Math.min(8000, 500 * 2 ** retry.current++);
      setTimeout(connect, delay);
    };
    ws.onerror = () => ws.close();
    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();
    // mobile browsers drop the socket when backgrounded — reconnect on return so the
    // broker can replay any turn that finished while we were away
    const onVis = () => {
      if (document.visibilityState === "visible" &&
          (!wsRef.current || wsRef.current.readyState > 1)) connect();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      wsRef.current && wsRef.current.close();
    };
  }, []);
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
    setSuggCollapsed(false);   // new content scrolls to bottom -> show suggestions again
  }, [beats, streaming]);

  const seen = (e) => e.seq && e.seq <= lastSeq.current;  // already-displayed turn (replay)

  const handleEvent = useCallback((e) => {
    if (e.type === "replay_start") {
      // (re)connected mid/after a turn. If it's still running and new, show the spinner.
      if (e.status === "running" && !seen(e)) { setBusy(true); acc.current = ""; setStreaming(""); }
      return;
    }
    if (e.type === "start") {
      if (seen(e)) return;
      if (e.model && onModel) onModel(e.model);
      acc.current = ""; setStreaming(""); setBusy(true); return;
    }
    if (e.type === "narrative_reset") { acc.current = ""; setStreaming(""); return; }
    if (e.type === "token") {
      if (seen(e)) return;          // suppress token replay of a turn we already rendered
      acc.current += e.text; setStreaming(acc.current); return;
    }
    if (e.type === "result") {
      if (seen(e)) { setStreaming(""); return; }   // dedupe the replayed result
      if (e.seq) lastSeq.current = e.seq;
      if (e.model && onModel) onModel(e.model);  // reflect routing/fallback swaps
      setStreaming("");
      setBeats((b) => [...b, {
        who: "Chronicle Weaver", cls: "dm", body: e.narrative,
        applied: e.applied, rejected: e.rejected, notes: e.notes,
        rolls: e.rolls, combat_log: e.combat_log,
      }]);
      setSuggestions(e.suggestions || []);
      setPicks([]);
      setBusy(false);
      onCombat && onCombat(e.combat || null);
      onStateChange && onStateChange();
      if (e.parse_notes?.length) toast("DM output needed repair (recovered).", "warn");
      return;
    }
    if (e.type === "turn_done") { setBusy(false); setStreaming(""); return; }
    if (e.type === "notice") { toast(e.message, "warn"); return; }
    if (e.type === "error") {
      setStreaming(""); setBusy(false);
      setBeats((b) => [...b, { who: "System", cls: "sys", body: "⚠ " + e.message }]);
      toast(e.message, "error");
    }
  }, []);

  const send = (text) => {
    const action = (text ?? input).trim();
    if (!action || busy) return;
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      toast("Not connected — reconnecting…", "warn"); return;
    }
    setBeats((b) => [...b, { who: "You", cls: "player", body: action }]);
    setSuggestions([]); setPicks([]); setInput(""); setBusy(true);
    wsRef.current.send(JSON.stringify({ action }));
  };

  const togglePick = (i) =>
    setPicks((p) => (p.includes(i) ? p.filter((x) => x !== i) : [...p, i]));

  const sendPicks = () => {
    const texts = picks.map((i) => suggestions[i]?.text).filter(Boolean);
    if (!texts.length) return;
    send(texts.length === 1 ? texts[0] : "I'll do these: " + texts.join("; "));
  };

  const startSession = async () => {
    const r = await post("/api/session/start");
    const recap = r.previously ? `Previously on EmberHeart — ${r.previously}` : "A new tale begins.";
    const moves = (r.faction_moves || []).map((m) => `${m.faction} ${m.move}.`).join(" ");
    setBeats((b) => [...b, { who: "Chronicle Weaver", cls: "dm", body: recap + (moves ? "\n\n" + moves : "") }]);
    toast("Session started · auto-backup saved", "info");
    if ((r.warming || "").includes(":cloud")) toast(`Warming ${r.warming}… first turn may lag`, "warn");
    onStateChange && onStateChange();
  };

  return html`
    <div class="play">
      <div class="toolbar">
        <button onClick=${startSession}>▶ Start session</button>
        <button onClick=${async () => { const r = await post("/api/session/end"); toast(r.summary ? "Session summarized & backed up" : "Session ended", "info"); }}>■ End</button>
        <span class="muted small">Speak your action and the Weaver answers.</span>
      </div>
      <div class="log" ref=${logRef} onScroll=${() => {
        const el = logRef.current; if (!el) return;
        setSuggCollapsed(el.scrollHeight - el.scrollTop - el.clientHeight > 80);
      }}>
        ${beats.map((b, i) => html`
          <div class=${"beat " + b.cls} key=${i}>
            <div class="who">${b.who}</div>
            <div class="body">${b.body}</div>
            ${b.combat_log?.length ? html`<div class="rolls">${b.combat_log.map((l) => html`⚔ ${l}<br/>`)}</div>` : null}
            ${b.rolls?.length ? html`<div class="rolls">${b.rolls.map((r) =>
              html`🎲 ${r.label}: ${r.total}${r.outcome ? " → " + r.outcome : ""}<br/>`)}</div>` : null}
            ${b.applied?.length ? html`<div class="applied">${b.applied.map((a) => html`<span>${a}</span>`)}</div>` : null}
            ${b.notes?.length ? html`<div class="applied">${b.notes.map((a) => html`<span class="note">✎ ${a}</span>`)}</div>` : null}
            ${b.rejected?.length ? html`<div class="applied">${b.rejected.map((a) => html`<span class="rej">⨯ ${a}</span>`)}</div>` : null}
          </div>`)}
        ${streaming ? html`<div class="beat dm"><div class="who">Chronicle Weaver</div>
          <div class="body streaming">${streaming}▌</div></div>` : null}
        ${busy && !streaming ? html`<div class="muted small" style="padding:8px 0">The Weaver is considering…</div>` : null}
      </div>
      ${suggestions.length ? html`<div class=${"suggestions" + (suggCollapsed ? " collapsed" : "")}>
        ${suggestions.map((s, i) => html`<button key=${i}
            class=${"sugg" + (picks.includes(i) ? " picked" : "")} disabled=${busy}
            onClick=${() => togglePick(i)}>
          <span class="sugg-mark">${picks.includes(i) ? "✓" : (i + 1) + "."}</span> ${s.text}
          ${s.requires_roll ? html`<span class="muted small"> (roll${s.roll_hint ? ": " + s.roll_hint : ""})</span>` : ""}
        </button>`)}
        <button class="primary sugg-go" disabled=${!picks.length || busy} onClick=${sendPicks}>
          ▶ ${picks.length > 1 ? `Do these ${picks.length}` : "Do this"}${picks.length ? "" : " — pick one or more"}
        </button>
      </div>` : null}
      <div class="composer">
        <input placeholder=${busy ? "The Weaver is narrating…" : conn !== "open" ? "Reconnecting…" : "What do you do?"}
          value=${input} disabled=${busy}
          onInput=${(e) => setInput(e.target.value)}
          onKeyDown=${(e) => e.key === "Enter" && send()} />
        <button class="primary" disabled=${busy} onClick=${() => send()}>Act</button>
      </div>
    </div>`;
}

// --------------------------------------------------------------------- sidebar
function Bar({ value, max }) {
  return html`<div class="bar"><div style=${{ width: Math.max(0, Math.min(100, (value / max) * 100)) + "%" }}></div></div>`;
}

function Sidebar({ world, combat, reload, toast, open, onClose }) {
  const [tab, setTab] = useState("world");
  const [pcs, setPcs] = useState([]);
  const [npcs, setNpcs] = useState([]);
  const [mem, setMem] = useState({ total: 0, embedded: 0 });
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [dossier, setDossier] = useState(null);
  const [questView, setQuestView] = useState("active");

  const openDossier = async (hk) => {
    setDossier({ loading: true, hook: hk });
    setDossier(await api(`/api/hooks/${hk.id}/dossier`));
  };

  const refresh = async () => {
    setPcs(await api("/api/pcs"));
    setNpcs(await api("/api/npcs"));
    setMem(await api("/api/memory/stats"));
  };
  useEffect(() => { refresh(); }, [world]);
  useEffect(() => { if (combat) setTab("combat"); }, [combat]);

  const heroes = pcs.filter((p) => p.is_player);
  const companions = pcs.filter((p) => !p.is_player);
  const tabs = [
    ["world", "World"], ["pcs", "Heroes"], ["party", "Party"], ["inventory", "Inventory"],
    ["combat", "Combat"], ["idle", "Idle"], ["factions", "Factions"], ["quests", "Quests"],
    ["journal", "Journal"], ["kingdom", "Kingdom"], ["gallery", "Gallery"], ["memory", "Memory"], ["gm", "GM"],
  ];
  const w = world?.world || {};
  const search = async () => setResults((await post("/api/memory/search", { query })).results || []);

  return html`
    <div class=${"side" + (open ? " open" : "")}>
      <div class="tabs">
        ${tabs.map(([k, label]) => html`<button key=${k}
          class=${tab === k ? "active" : ""} onClick=${() => setTab(k)}>
          ${label}${k === "combat" && combat ? " ⚔" : ""}</button>`)}
        <button class="side-close" onClick=${onClose} aria-label="close panels">✕</button>
      </div>

      ${tab === "world" && html`<div class="pane">
        <h3>The World</h3>
        <div class="card">
          <div class="kv"><span class="k">Arc</span><span>${w.arc_phase}${w.domain_ruled ? " · ruling" : ""}</span></div>
          <div class="kv"><span class="k">Date</span><span>Yr ${w.year}, ${w.season}, day ${w.day}</span></div>
          <div class="kv"><span class="k">Time</span><span>${w.time_of_day}</span></div>
          <div class="kv"><span class="k">Weather</span><span>${w.weather}</span></div>
          <div class="kv"><span class="k">Turn</span><span>${w.turn_counter}</span></div>
        </div>
        <h3>Recent Chronicle</h3>
        ${(world?.chronicle || []).slice().reverse().map((c, i) => html`<div class="card small" key=${i}>${c.content}</div>`)}
      </div>`}

      ${tab === "pcs" && html`<${HeroesPane} pcs=${heroes} kind="hero" toast=${toast}
        onChange=${() => { refresh(); reload(); }} />`}

      ${tab === "party" && html`<${HeroesPane} pcs=${companions} kind="party" toast=${toast}
        npcs=${npcs.filter((n) => n.status === "alive")}
        onChange=${() => { refresh(); reload(); }} />`}

      ${tab === "combat" && html`<${CombatPane} combat=${combat} reload=${reload} toast=${toast} />`}

      ${tab === "factions" && html`<div class="pane">
        <h3>Factions</h3>
        ${(world?.factions || []).length === 0 && html`<p class="muted small">No factions yet.</p>`}
        ${(world?.factions || []).map((f) => html`<div class="card" key=${f.id}>
          <strong>${f.name}</strong> <span class="muted small">${f.goal_tier}</span>
          <div class="kv"><span class="k">Resources</span><span>${f.resources}</span></div>
        </div>`)}
      </div>`}

      ${tab === "quests" && (() => {
        const all = world?.quests || [];
        const active = all.filter((q) => q.status !== "completed");
        const done = all.filter((q) => q.status === "completed");
        const shown = questView === "completed" ? done : active;
        return html`<div class="pane">
        <div class="subtabs">
          <button class=${questView === "active" ? "active" : ""}
            onClick=${() => setQuestView("active")}>Active${active.length ? ` (${active.length})` : ""}</button>
          <button class=${questView === "completed" ? "active" : ""}
            onClick=${() => setQuestView("completed")}>Completed${done.length ? ` (${done.length})` : ""}</button>
        </div>
        ${shown.length === 0 && html`<p class="muted small">${questView === "completed" ? "Nothing completed yet." : "No active quests."}</p>`}
        ${shown.map((q) => html`<div class=${"card" + (questView === "completed" ? " quest-done" : "")} key=${q.id}>
          <strong>${questView === "completed" ? "✓ " : ""}${q.title}</strong>
          ${q.description ? html`<div class="small">${q.description}</div>` : null}
          ${questView !== "completed" ? html`<button class="small" style="margin-top:7px" onClick=${async () => {
            const r = await post("/api/play/submit", { text: `I turn my attention back to the quest "${q.title}"${q.description ? ` (${q.description})` : ""}. Weave it back into the story — where do we stand, and what's the next move?` });
            toast(r.ok ? "↪ Sent to the Weaver — open the story" : "The Weaver's mid-turn — try again in a sec", r.ok ? "info" : "warn");
            if (r.ok && onClose) onClose();
          }}>↪ Pick this up</button>` : null}</div>`)}
        <div class="row" style="margin:8px 0 4px; align-items:center">
          <h3 style="margin:0">Threads</h3>
          ${(world?.hooks || []).length > 6 ? html`<button style="margin-left:auto" onClick=${async () => {
            toast("Consolidating threads into quests…", "info");
            const r = await post("/api/hooks/consolidate", {});
            toast(r.error ? r.error : `Made ${r.quests_created} quests · retired ${r.hooks_retired} threads`, r.error ? "error" : "info");
            reload();
          }}>🧹 Consolidate</button>` : null}
        </div>
        <p class="muted small">Click a hook for what's known.</p>
        ${(world?.hooks || []).map((hk, i) => html`<div class="card small hook" key=${hk.id ?? i}
          onClick=${() => openDossier(hk)} title="click to investigate">
          🪝 ${hk.description}
          ${hk.status && hk.status !== "seeded" ? html`<span class="muted"> · ${hk.status}</span>` : ""}
        </div>`)}
      </div>`;
      })()}

      ${tab === "inventory" && html`<${InventoryPane} toast=${toast} />`}

      ${tab === "journal" && html`<${JournalPane} toast=${toast} />`}

      ${tab === "gallery" && html`<${GalleryPane} />`}

      ${tab === "idle" && html`<${IdlePane} toast=${toast} domain=${world?.domain} reload=${reload} />`}

      ${tab === "kingdom" && html`<${KingdomPane} world=${world} reload=${reload} />`}

      ${tab === "memory" && html`<div class="pane">
        <h3>Semantic Memory</h3>
        <div class="card">
          <div class="kv"><span class="k">Chunks</span><span>${mem.total}</span></div>
          <div class="kv"><span class="k">Embedded</span><span>${mem.embedded}</span></div>
        </div>
        <div class="row">
          <input style="flex:1" placeholder="probe memory…" value=${query}
            onInput=${(e) => setQuery(e.target.value)} onKeyDown=${(e) => e.key === "Enter" && search()} />
          <button onClick=${search}>Search</button>
        </div>
        ${results.map((r, i) => html`<div class="card small" key=${i}><span class="muted">${r.kind} · ${r.score}</span><br/>${r.text}</div>`)}
      </div>`}

      ${tab === "gm" && html`<${GMPane} world=${world} reload=${reload} refresh=${refresh} toast=${toast} />`}

      ${dossier && html`<${HookModal} data=${dossier} onClose=${() => setDossier(null)}
        onResolve=${async () => {
          await post(`/api/hooks/${dossier.hook.id}/resolve`);
          toast("Thread marked resolved", "info"); setDossier(null); reload();
        }} />`}
    </div>`;
}

const ABILS = ["str", "dex", "con", "int", "wis", "cha"];

function RecruitList({ npcs, onRecruit }) {
  if (!npcs.length) return html`<p class="muted small">No available allies to recruit right now.</p>`;
  return html`<div>
    <p class="muted small">Recruit an ally into your party — you'll manage their sheet & levels; the DM plays them.</p>
    ${npcs.map((n) => html`<div class="card small" key=${n.id}>
      <strong>${n.name}</strong> <span class="muted">${n.role || ""}${n.pronouns ? " · " + n.pronouns : ""}</span>
      <div class="row"><button class="primary" onClick=${() => onRecruit(n)}>＋ Bring into party</button></div>
    </div>`)}
  </div>`;
}

function HeroesPane({ pcs, kind = "hero", npcs = [], toast, onChange }) {
  const [pid, setPid] = useState(null);
  const [sheet, setSheet] = useState(null);
  const [lvl, setLvl] = useState(null);
  const [chat, setChat] = useState(null);
  const [asc, setAsc] = useState(null);
  const [mounts, setMounts] = useState([]);
  const party = kind === "party";
  const title = party ? "Party" : "Heroes";

  const load = async (id) => { if (id) setSheet(await api(`/api/pcs/${id}/sheet`)); };
  useEffect(() => { const f = pcs[0]?.id; setPid(f); if (f) load(f); else setSheet(null); }, [pcs]);
  useEffect(() => { if (!party) api("/api/ascension").then(setAsc).catch(() => {}); }, [party]);
  useEffect(() => { api("/api/mounts").then(setMounts).catch(() => {}); }, [pcs]);

  const recruit = async (n) => {
    await post(`/api/npcs/${n.id}/promote`, {});
    toast(`${n.name} joined the party`, "info");
    onChange && onChange();
  };

  if (!pcs.length) return html`<div class="pane"><h3>${title}</h3>
    ${party
      ? html`<${RecruitList} npcs=${npcs} onRecruit=${recruit} />`
      : html`<p class="muted small">No heroes yet — create one in the GM tab.</p>`}</div>`;
  if (!sheet) return html`<div class="pane"><h3>${title}</h3><p class="muted">Loading sheet…</p></div>`;

  const s = sheet, ab = s.abilities || {}, mod = s.modifiers || {};
  const openLevelup = async () => setLvl(await api(`/api/pcs/${pid}/levelup`));

  return html`<div class="pane">
    ${pcs.length > 1 ? html`<select value=${pid}
        onChange=${(e) => { setPid(e.target.value); load(e.target.value); }}>
        ${pcs.map((p) => html`<option value=${p.id}>${p.name}</option>`)}</select>` : null}
    <h3>${s.name}</h3>
    <div class="muted small">${s.race} · ${s.class}${s.subclass ? " / " + s.subclass : ""} · Level ${s.level}${s.status !== "alive" ? " · " + s.status : ""}</div>
    ${party ? html`<div class="row" style="margin:4px 0">
      <div class="chip" style="border-color:var(--ember); color:var(--ember-2)">🤝 DM-controlled companion</div>
      <button onClick=${() => setChat({ id: pid, name: s.name })}>💬 Talk privately</button>
    </div>` : null}
    ${s.notes ? html`<div class="small" style="margin:5px 0 8px">${s.notes}</div>` : null}

    <div class="abilities">
      ${ABILS.map((k) => html`<div class="abil" key=${k}>
        <div class="abil-name">${k.toUpperCase()}</div>
        <div class="abil-score">${ab[k] ?? "—"}</div>
        <div class="abil-mod">${(mod[k] >= 0 ? "+" : "")}${mod[k] ?? 0}</div></div>`)}
    </div>

    <div class="card">
      <div class="kv"><span class="k">HP</span><span>${s.hp}/${s.max_hp}</span></div>
      <${Bar} value=${s.hp} max=${s.max_hp} />
      <div class="sheet-grid" style="margin-top:6px">
        <div class="kv"><span class="k">AC</span><span>${s.ac}</span></div>
        <div class="kv"><span class="k">Init</span><span>${s.initiative >= 0 ? "+" : ""}${s.initiative}</span></div>
        <div class="kv"><span class="k">Prof</span><span>+${s.proficiency_bonus}</span></div>
        <div class="kv"><span class="k">Pass. Per</span><span>${s.passive_perception}</span></div>
      </div>
    </div>

    <div class="card">
      <div class="kv"><span class="k">XP</span><span>${s.xp}${s.xp_next_level ? ` / ${s.xp_next_level}` : " (max)"}</span></div>
      ${s.xp_needed ? html`<${Bar} value=${s.xp_into_level} max=${s.xp_needed} />` : null}
      ${s.level < 20 ? html`<button class="primary" style="margin-top:8px;width:100%"
        onClick=${openLevelup}>⬆ Level Up${s.levelup_available ? "" : " (GM override)"}</button>` : null}
    </div>

    ${(s.features || []).length ? html`<h3>Actions & Features</h3>
      ${s.features.map((f, i) => html`<div class="card small" key=${i}>
        <strong>${f.name}</strong> <span class="muted">${f.type}${f.level ? ` · L${f.level}` : ""}</span>
        ${f.desc ? html`<div>${f.desc}</div>` : null}</div>`)}`
      : html`<h3>Actions & Features</h3>
        <p class="muted small">None yet. <a href="#" onClick=${async (e) => { e.preventDefault(); await post(`/api/pcs/${pid}/seed-features`, {}); load(pid); toast("Seeded class features", "info"); }}>Backfill class features</a> or level up.</p>`}

    <h3>Skills</h3>
    <div class="chips">${Object.entries(s.skills || {}).filter(([_, v]) => v > 1)
      .map(([k, v]) => html`<span class="chip" key=${k}>${k} ${v}</span>`)}</div>

    ${(() => {
      const mine = mounts.filter((m) => m.owner_pc_id === pid);
      return mine.length ? html`<h3>🐎 Mount${mine.length > 1 ? "s" : ""}</h3>
        ${mine.map((m) => html`<div class="card" key=${m.id}>
          <div class="row" style="margin:0; align-items:baseline">
            <strong>${m.name}</strong>
            <span class="muted small">${m.kind}${m.status !== "active" ? " · " + m.status : ""}</span>
          </div>
          <div class="kv"><span class="k">HP</span><span>${m.hp}/${m.max_hp}</span></div>
          <${Bar} value=${m.hp} max=${m.max_hp} />
          <div class="sheet-grid" style="margin-top:6px">
            <div class="kv"><span class="k">Speed</span><span>${m.speed} ft</span></div>
            <div class="kv"><span class="k">Bond</span><span>${"❤".repeat(Math.max(1, Math.min(5, m.bond || 1)))}</span></div>
          </div>
          ${(m.traits || []).length ? html`<div class="chips" style="margin-top:6px">
            ${m.traits.map((t) => html`<span class="chip" key=${t}>${t}</span>`)}</div>` : null}
          ${m.notes ? html`<div class="small" style="margin-top:4px">${m.notes}</div>` : null}
        </div>`)}` : null;
    })()}

    ${(s.inventory || []).length ? html`<div class="muted small" style="margin-top:6px">
      🎒 ${s.inventory.length} items in pack — manage them in the <strong>Inventory</strong> tab.</div>` : null}

    ${!party && asc ? html`<${AscensionTracker} asc=${asc} />` : null}

    ${party ? html`<h3>Recruit more</h3><${RecruitList} npcs=${npcs} onRecruit=${recruit} />` : null}

    ${chat ? html`<${ChatModal} partner=${chat} onClose=${() => setChat(null)} />` : null}

    ${lvl ? html`<${LevelUpModal} pid=${pid} data=${lvl} toast=${toast}
       onClose=${() => setLvl(null)}
       onDone=${(log) => { setLvl(null); load(pid); onChange && onChange(); (log || []).forEach((l) => toast(l, "info")); }} />` : null}
  </div>`;
}

const ASC_GLYPH = { Dream: "🌙", Fire: "🔥", Memory: "🕯", Sacrifice: "⚖" };
const ASC_STATUS = {
  claimed: { label: "claimed", cls: "asc-claimed" },
  in_progress: { label: "in progress", cls: "asc-active" },
  revealed: { label: "awaits", cls: "asc-revealed" },
  unknown: { label: "???", cls: "asc-unknown" },
};

function AscensionTracker({ asc }) {
  const domains = asc.domains || [];
  return html`<h3>✨ Ascension</h3>
    <div class="card asc-card">
      <div class="asc-anchor">
        <div class="asc-orb">❤️‍🔥</div>
        <div><strong>${asc.anchor?.name || "The EmberHeart"}</strong>
          <div class="muted small">the forge of rebirth · ${asc.claimed}/${asc.total} domains claimed</div></div>
      </div>
      <div class="asc-domains">
        ${domains.map((d) => {
          const st = ASC_STATUS[d.status] || ASC_STATUS.unknown;
          const known = d.status !== "unknown";
          return html`<div class=${"asc-domain " + st.cls} key=${d.domain}>
            <div class="asc-glyph">${known ? (ASC_GLYPH[d.domain] || "◇") : "❔"}</div>
            <div class="asc-dname">${known ? d.domain : "Unknown"}</div>
            ${d.crystal ? html`<div class="muted small">${d.crystal}</div>` : null}
            <div class="asc-stat">${st.label}</div>
          </div>`;
        })}
      </div>
      ${asc.rebirth ? html`<div class="small asc-price">⟡ ${asc.rebirth}</div>` : null}
    </div>`;
}

const MAT_WORDS = ["wood", "ore", "stone", "pelt", "hide", "leather", "fiber", "meat",
  "fish", "berries", "herb", "rime", "bar", "sinew", "ash", "thistle", "moss", "petal"];
const isMaterial = (n) => MAT_WORDS.some((w) => n.toLowerCase().includes(w));

function InventoryPane({ toast }) {
  const [pid, setPid] = useState(null);
  const [inv, setInv] = useState(null);
  const [q, setQ] = useState("");

  const load = async () => {
    const pcs = await api("/api/pcs");
    const hero = pcs.find((p) => p.is_player) || pcs[0];
    if (!hero) { setInv([]); return; }
    setPid(hero.id);
    const s = await api(`/api/pcs/${hero.id}/sheet`);
    setInv(s.inventory || []);
  };
  useEffect(() => { load(); }, []);
  if (inv === null) return html`<div class="pane"><h3>Inventory</h3><p class="muted">Loading…</p></div>`;

  const setQty = async (item, qty) => {
    const r = await post(`/api/pcs/${pid}/inventory/set`, { item, qty: Number(qty) });
    setInv(r.sheet.inventory || []);
  };
  const tidy = async () => {
    const r = await post(`/api/pcs/${pid}/inventory/tidy`, {});
    setInv(r.sheet.inventory || []);
    toast("Pack tidied — dupes merged, junk stripped", "info");
  };
  const ql = q.toLowerCase();
  const shown = inv.filter((it) => it.item.toLowerCase().includes(ql));
  const mats = shown.filter((it) => isMaterial(it.item));
  const gear = shown.filter((it) => !isMaterial(it.item));

  const row = (it) => html`<div class="card small inv-row" key=${it.item}>
    <span class="inv-name">${it.item}</span>
    <input type="number" min="0" value=${it.qty ?? 1} class="inv-qty"
      onChange=${(e) => setQty(it.item, e.target.value)} />
    <button class="link-x" title="drop" onClick=${() => setQty(it.item, 0)}>🗑</button>
  </div>`;

  return html`<div class="pane">
    <div class="row" style="align-items:center">
      <h3 style="margin:0">Inventory <span class="muted small">${inv.length} stacks</span></h3>
      <button style="margin-left:auto" onClick=${tidy}>🧹 Tidy</button>
    </div>
    <input placeholder="filter the pack…" value=${q} onInput=${(e) => setQ(e.target.value)}
      style="width:100%; margin:6px 0" />
    ${shown.length === 0 ? html`<p class="muted small">Nothing matches.</p>` : null}
    ${gear.length ? html`<h3>Gear & Items</h3>${gear.map(row)}` : null}
    ${mats.length ? html`<h3>Materials</h3>${mats.map(row)}` : null}
  </div>`;
}

function GalleryPane() {
  const [imgs, setImgs] = useState(null);
  const [zoom, setZoom] = useState(null);
  useEffect(() => { api("/api/gallery").then(setImgs).catch(() => setImgs([])); }, []);

  if (imgs === null) return html`<div class="pane"><h3>Gallery</h3><p class="muted">Loading…</p></div>`;
  return html`<div class="pane">
    <h3>Gallery <span class="muted small">${imgs.length || ""}</span></h3>
    ${imgs.length === 0
      ? html`<p class="muted small">Empty. Drop images into <code>frontend/gallery/</code> and refresh — they'll appear here.</p>`
      : html`<div class="gallery-grid">
          ${imgs.map((im) => html`<figure class="gallery-item" key=${im.file} onClick=${() => setZoom(im)}>
            <img src=${im.url} alt=${im.caption} loading="lazy" />
            <figcaption>${im.caption}</figcaption>
          </figure>`)}
        </div>`}
    ${zoom ? html`<div class="lightbox" onClick=${() => setZoom(null)}>
      <img src=${zoom.url} alt=${zoom.caption} onClick=${(e) => e.stopPropagation()} />
      <div class="lightbox-cap">${zoom.caption}</div>
      <button class="lightbox-x" onClick=${() => setZoom(null)}>✕</button>
    </div>` : null}
  </div>`;
}

function JournalPane({ toast }) {
  const [entries, setEntries] = useState(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({ title: "", body: "", mood: "" });

  const load = async () => setEntries(await api("/api/journal"));
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!draft.body.trim()) { toast("Write something first", "error"); return; }
    await post("/api/journal", draft);
    setDraft({ title: "", body: "", mood: "" });
    setOpen(false);
    toast("Entry written", "info");
    load();
  };
  const remove = async (id) => {
    await api(`/api/journal/${id}`, { method: "DELETE" });
    load();
  };

  return html`<div class="pane">
    <div class="row" style="align-items:center">
      <h3 style="margin:0">Journal</h3>
      <button style="margin-left:auto" onClick=${() => setOpen(!open)}>${open ? "✕ Cancel" : "✍ New entry"}</button>
    </div>
    <p class="muted small">Where feels go — moods, fears, bonds. Not quests.</p>

    ${open ? html`<div class="card">
      <input placeholder="Title (optional)" value=${draft.title}
        onInput=${(e) => setDraft({ ...draft, title: e.target.value })} />
      <input placeholder="Mood (optional)" value=${draft.mood} style="margin-top:6px"
        onInput=${(e) => setDraft({ ...draft, mood: e.target.value })} />
      <textarea placeholder="What's on your heart…" rows="4" value=${draft.body} style="margin-top:6px;width:100%"
        onInput=${(e) => setDraft({ ...draft, body: e.target.value })}></textarea>
      <button class="primary" style="margin-top:6px;width:100%" onClick=${save}>Save to journal</button>
    </div>` : null}

    ${entries === null ? html`<p class="muted">Opening the journal…</p>`
      : entries.length === 0 ? html`<p class="muted small">No entries yet.</p>`
      : entries.map((e) => html`<div class="card journal-entry" key=${e.id}>
        <div class="row" style="align-items:baseline">
          <strong>${e.title || "Untitled"}</strong>
          ${e.mood ? html`<span class="chip" style="margin-left:6px">${e.mood}</span>` : null}
          <button class="link-x" style="margin-left:auto" title="delete"
            onClick=${() => remove(e.id)}>✕</button>
        </div>
        <div class="small" style="white-space:pre-wrap;margin-top:4px">${e.body}</div>
        ${e.author ? html`<div class="muted small" style="margin-top:4px">— ${e.author}</div>` : null}
      </div>`)}
  </div>`;
}

function LevelUpModal({ pid, data, onClose, onDone, toast }) {
  const [picks, setPicks] = useState({});
  const [force, setForce] = useState(!data.eligible);
  const [custom, setCustom] = useState([]);
  const [cf, setCf] = useState({ name: "", type: "action", desc: "" });
  const set = (key, val) => setPicks((p) => ({ ...p, [key]: val }));

  const confirm = async () => {
    const out = {};
    for (const c of data.choices) {
      const raw = picks[c.key];
      if (!raw) continue;
      if (c.type === "expertise") out[c.key] = raw;
      else if (c.type === "asi") {
        if (raw.mode === "feat") out[c.key] = { mode: "feat", feat: raw.feat };
        else { const a = {}; if (raw.a1) a[raw.a1] = (a[raw.a1] || 0) + 1; if (raw.a2) a[raw.a2] = (a[raw.a2] || 0) + 1; out[c.key] = { mode: "asi", abilities: a }; }
      }
    }
    // fold in a typed-but-not-yet-"+added" custom so it isn't silently dropped
    const allCustom = cf.name ? [...custom, cf] : custom;
    const d = await post(`/api/pcs/${pid}/levelup`, { picks: { ...out, custom: allCustom }, force });
    if (d.detail) { toast(d.detail, "error"); return; }
    onDone(d.log);
  };

  return html`<div class="modal-overlay" onClick=${onClose}>
    <div class="modal" onClick=${(e) => e.stopPropagation()}>
      <div class="modal-head"><strong>⬆ Level ${data.new_level}</strong><button onClick=${onClose}>✕</button></div>
      <div class="modal-body">
        <div class="card small">
          <div class="kv"><span class="k">Max HP</span><span>+${data.hp_gain}</span></div>
          <div class="kv"><span class="k">Proficiency</span><span>+${data.proficiency_bonus}</span></div>
          ${data.sneak_attack ? html`<div class="kv"><span class="k">Sneak Attack</span><span>${data.sneak_attack}</span></div>` : null}
          ${data.psionic ? html`<div class="kv"><span class="k">Psionic</span><span>${data.psionic.pool}× ${data.psionic.die}</span></div>` : null}
        </div>
        ${data.auto_features.length ? html`<h4>Gained automatically</h4>
          ${data.auto_features.map((f, i) => html`<div class="card small" key=${i}><strong>${f.name}</strong>${f.desc ? html`<div>${f.desc}</div>` : null}</div>`)}` : null}

        ${data.choices.map((c) => html`<div key=${c.key}>
          <h4>${c.prompt}</h4>
          ${c.type === "expertise" ? html`<div class="chips">
            ${c.options.map((o) => { const sel = picks[c.key] || []; const on = sel.includes(o);
              return html`<button key=${o} class=${"choice-opt" + (on ? " active" : "")}
                onClick=${() => { let n = on ? sel.filter((x) => x !== o) : [...sel, o]; if (n.length <= c.pick) set(c.key, n); }}>${o}</button>`; })}
            <div class="muted small">pick ${c.pick}</div></div>` : null}

          ${c.type === "asi" ? html`<${AsiPicker} choice=${c} value=${picks[c.key]} onChange=${(v) => set(c.key, v)} />` : null}
        </div>`)}

        <h4>Custom action / spell (homebrew)</h4>
        ${custom.map((c, i) => html`<div class="card small" key=${i}><strong>${c.name}</strong> <span class="muted">${c.type}</span></div>`)}
        <div class="row">
          <input style="flex:1" placeholder="name" value=${cf.name} onInput=${(e) => setCf({ ...cf, name: e.target.value })} />
          <select value=${cf.type} onChange=${(e) => setCf({ ...cf, type: e.target.value })}>
            ${["action", "spell", "feature", "feat"].map((t) => html`<option>${t}</option>`)}</select>
        </div>
        <div class="row">
          <input style="flex:1" placeholder="description" value=${cf.desc} onInput=${(e) => setCf({ ...cf, desc: e.target.value })} />
          <button onClick=${() => { if (cf.name) { setCustom([...custom, cf]); setCf({ name: "", type: "action", desc: "" }); } }}>+ add</button>
        </div>
      </div>
      <div class="modal-foot">
        ${!data.eligible ? html`<label class="small muted" style="margin-right:auto">
          <input type="checkbox" checked=${force} onChange=${(e) => setForce(e.target.checked)} /> GM override (not enough XP)</label>` : null}
        <button onClick=${onClose}>Cancel</button>
        <button class="primary" onClick=${confirm}>Confirm level up</button>
      </div>
    </div>
  </div>`;
}

function AsiPicker({ choice, value, onChange }) {
  const v = value || { mode: "asi", a1: "", a2: "", feat: "" };
  const up = (patch) => onChange({ ...v, ...patch });
  return html`<div>
    <div class="row">
      <button class=${v.mode !== "feat" ? "active" : ""} onClick=${() => up({ mode: "asi" })}>Ability +1/+1</button>
      <button class=${v.mode === "feat" ? "active" : ""} onClick=${() => up({ mode: "feat" })}>Feat</button>
    </div>
    ${v.mode === "feat" ? html`<select onChange=${(e) => up({ feat: e.target.value })} value=${v.feat}>
        <option value="">— choose feat —</option>
        ${choice.feats.map((f) => html`<option value=${f.name} title=${f.desc}>${f.name}</option>`)}</select>
      ${v.feat ? html`<div class="muted small">${(choice.feats.find((f) => f.name === v.feat) || {}).desc}</div>` : null}`
      : html`<div class="row">
        ${["a1", "a2"].map((slot) => html`<select key=${slot} value=${v[slot]} onChange=${(e) => up({ [slot]: e.target.value })}>
          <option value="">+1 to…</option>
          ${choice.abilities.map((a) => html`<option value=${a}>${a.toUpperCase()}</option>`)}</select>`)}
      </div>`}
  </div>`;
}

function ChatModal({ partner, onClose }) {
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [regard, setRegard] = useState(null);
  const bodyRef = useRef(null);

  useEffect(() => {
    api(`/api/chat/${partner.id}`).then((d) => { setMsgs(d.history || []); setRegard(d.disposition); });
  }, [partner.id]);
  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [msgs, busy]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setMsgs((m) => [...m, { role: "user", content: text }]);
    setInput(""); setBusy(true);
    const d = await post(`/api/chat/${partner.id}`, { text });
    setRegard(d.disposition);
    const extra = [{ role: "assistant", content: d.reply || "…" }];
    if (d.delta) extra.push({ role: "system",
      content: `${partner.name}'s regard for you ${d.delta > 0 ? "rose ▲" : "fell ▼"} (${d.delta > 0 ? "+" : ""}${d.delta})` });
    setMsgs((m) => [...m, ...extra]);
    setBusy(false);
  };

  return html`<div class="modal-overlay" onClick=${onClose}>
    <div class="modal chat-modal" onClick=${(e) => e.stopPropagation()}>
      <div class="modal-head">
        <strong>💬 ${partner.name}</strong>
        ${regard != null ? html`<span class="chip small" style="margin-left:8px" title="how they feel about you">❤ ${regard}</span>` : null}
        <span class="muted small" style="margin-left:8px">private</span>
        <button style="margin-left:auto" onClick=${onClose}>✕</button>
      </div>
      <div class="chat-body" ref=${bodyRef}>
        ${msgs.length === 0 ? html`<p class="muted small">Just the two of you. Say something.</p>` : null}
        ${msgs.map((m, i) => m.role === "system"
          ? html`<div class="chat-sys" key=${i}>— ${m.content} —</div>`
          : html`<div class=${"bubble " + (m.role === "user" ? "me" : "them")} key=${i}>${m.content}</div>`)}
        ${busy ? html`<div class="bubble them muted">…</div>` : null}
      </div>
      <div class="composer">
        <input placeholder=${`Talk to ${partner.name}…`} value=${input} disabled=${busy}
          onInput=${(e) => setInput(e.target.value)} onKeyDown=${(e) => e.key === "Enter" && send()} />
        <button class="primary" disabled=${busy} onClick=${send}>Send</button>
      </div>
      <div class="modal-foot">
        <button onClick=${async () => { await api(`/api/chat/${partner.id}`, { method: "DELETE" }); setMsgs([]); }}>Clear chat</button>
        <button class="primary" onClick=${onClose}>Done</button>
      </div>
    </div>
  </div>`;
}

function HookModal({ data, onClose, onResolve }) {
  const hk = data.hook || {};
  return html`<div class="modal-overlay" onClick=${onClose}>
    <div class="modal" onClick=${(e) => e.stopPropagation()}>
      <div class="modal-head"><strong>🪝 Thread</strong><button onClick=${onClose}>✕</button></div>
      <div class="modal-body">
        <p class="hook-desc">${hk.description}</p>
        <div class="muted small">status: ${hk.status || "seeded"} · planted turn ${hk.planted_turn ?? "?"}</div>
        <h4>What's known so far</h4>
        ${data.loading
          ? html`<p class="muted">Consulting the loremaster…</p>`
          : html`<p class="synth">${data.synthesis}</p>`}
        ${(data.related || []).length ? html`<h4>Related records</h4>
          ${data.related.map((r, i) => html`<div class="card small" key=${i}>
            <span class="muted">${r.kind} · ${r.score}</span><br/>${r.text}</div>`)}` : ""}
      </div>
      <div class="modal-foot">
        <button onClick=${onResolve}>Mark resolved</button>
        <button class="primary" onClick=${onClose}>Close</button>
      </div>
    </div>
  </div>`;
}

function CombatPane({ combat, reload, toast }) {
  const [enemy, setEnemy] = useState("Frost Wolf x2 hp7 ac13 ai:tactical");
  const refresh = async () => reload();
  if (!combat) {
    return html`<div class="pane">
      <h3>Combat</h3>
      <p class="muted small">No active encounter. The DM starts fights in the story (COMBAT_START), or you can spawn one here.</p>
      <div class="row">
        <input style="flex:1" value=${enemy} onInput=${(e) => setEnemy(e.target.value)} />
      </div>
      <button class="primary" onClick=${async () => {
        // turn the freeform spec into one enemy via the API's structured shape
        const m = enemy.match(/hp(\d+)/), a = enemy.match(/ac(\d+)/), ai = enemy.match(/ai:(\w+)/);
        const name = enemy.replace(/(x\d+|hp\d+|ac\d+|atk\d+|dmg\S+|ai:\w+)/g, "").trim() || "Enemy";
        await post("/api/combat/start", { enemies: [{ name, hp: m ? +m[1] : 8, ac: a ? +a[1] : 12, ai: ai ? ai[1] : "berserker" }] });
        toast("Encounter started", "info"); refresh();
      }}>Start encounter</button>
    </div>`;
  }
  return html`<div class="pane">
    <h3>Combat — Round ${combat.round}</h3>
    ${combat.participants.map((p) => html`<div class="card" key=${p.id || p.name}>
      <strong class=${p.side === "enemy" ? "enemy-name" : ""}>${p.name}</strong>
      <span class="muted small">${p.side}${p.zone ? " · " + p.zone : ""}${p.down ? " · down" : ""}</span>
      <div class="kv"><span class="k">HP</span><span>${p.hp}/${p.max_hp}</span></div>
      <${Bar} value=${p.hp} max=${p.max_hp} />
      ${p.conditions?.length ? html`<div class="small muted">${p.conditions.map((c) => c.name).join(", ")}</div>` : null}
    </div>`)}
    <div class="row">
      <button onClick=${async () => { await post("/api/combat/advance"); refresh(); }}>Resolve enemies →</button>
      <button onClick=${async () => { await post("/api/combat/end"); toast("Combat ended", "info"); refresh(); }}>End combat</button>
    </div>
    <h3>Log</h3>
    ${(combat.log || []).slice(-12).map((l, i) => html`<div class="small" key=${i}>⚔ ${l}</div>`)}
  </div>`;
}

function IdlePane({ toast, domain, reload }) {
  const [st, setSt] = useState(null);
  const [dep, setDep] = useState({});
  const load = async () => setSt(await api("/api/idle"));
  useEffect(() => {
    load();
    const t = setInterval(load, 8000);  // live-ish accumulation
    return () => clearInterval(t);
  }, []);
  if (!st) return html`<div class="pane"><h3>Idle Skilling</h3><p class="muted">Loading…</p></div>`;

  const start = async (name) => { setSt(await post("/api/idle/start", { activity: name })); };
  const stop = async () => { setSt(await post("/api/idle/stop", {})); };
  const deposit = async (mat, qty) => {
    const r = await post("/api/idle/deposit", { material: mat, qty: Number(qty) });
    if (r.ok === false) { toast(r.detail || "not enough", "error"); return; }
    toast(`Moved ${r.deposited} ${mat.replace(/_/g, " ")} to your pack`, "info");
    setDep({}); setSt(r);
  };
  const invest = async (mat, qty) => {
    const r = await post("/api/world/invest", { material: mat, qty: Number(qty) });
    if (r.ok === false) { toast(r.detail || "not enough", "error"); return; }
    toast(`Invested ${r.invested} ${mat.replace(/_/g, " ")} into the kingdom (${r.bucket})`, "info");
    setDep({}); load(); reload && reload();
  };
  const mats = Object.entries(st.materials || {});

  return html`<div class="pane">
    <h3>Idle Skilling</h3>
    ${st.active
      ? html`<div class="card"><div class="row" style="margin:0">
          <span>⛏ Working: <strong>${st.active}</strong> <span class="muted small">(auto, even while closed)</span></span>
          <button style="margin-left:auto" onClick=${stop}>Stop</button></div></div>`
      : html`<p class="muted small">Idle. Pick an activity below — it runs on its own, even while the app's closed.</p>`}

    <h3>Stockpile <span class="muted small">— deposit to your pack to use in the story</span></h3>
    ${mats.length === 0 ? html`<p class="muted small">Empty. Gather something.</p>`
      : mats.map(([k, v]) => html`<div class="card small" key=${k}>
          <div class="row" style="margin:0; align-items:center; gap:6px">
            <span>${k.replace(/_/g, " ")} <strong>${v}</strong></span>
            <input type="number" min="1" max=${v} value=${dep[k] ?? v} style="width:74px; margin-left:auto"
              onInput=${(e) => setDep({ ...dep, [k]: e.target.value })} />
            <button onClick=${() => deposit(k, dep[k] ?? v)}>📦 pack</button>
            ${domain ? html`<button onClick=${() => invest(k, dep[k] ?? v)}>🏰 kingdom</button>` : null}
          </div></div>`)}

    <h3>Activities</h3>
    ${st.activities.map((a) => {
      const ins = Object.entries(a.inputs || {});
      return html`<div class=${"card" + (a.active ? " idle-active" : "")} key=${a.name}>
        <div class="row" style="margin:0">
          <div>
            <strong>${a.name}</strong>
            <span class="muted small"> · ${a.skill} Lv ${a.level}${a.min_level > 1 ? ` (req ${a.min_level})` : ""}</span>
            <div class="small muted">
              ${ins.length ? "needs " + ins.map(([k, v]) => `${k.replace(/_/g, " ")}×${v}`).join(", ") + " → " : "→ "}
              ${a.outputs.map((o) => o.replace(/_/g, " ")).join(", ")}
            </div>
          </div>
          <div style="margin-left:auto">
            ${a.active ? html`<button onClick=${stop}>Stop</button>`
              : a.unlocked ? html`<button class="primary" onClick=${() => start(a.name)}>Start</button>`
              : html`<button disabled title=${"needs " + a.skill + " Lv " + a.min_level}>🔒 Lv ${a.min_level}</button>`}
          </div>
        </div>
      </div>`;
    })}
  </div>`;
}

function KingdomPane({ world, reload }) {
  const d = world?.domain;
  const summary = world?.kingdom_summary;
  const [name, setName] = useState("");
  const [sub, setSub] = useState("overview");
  const [laborDraft, setLaborDraft] = useState({});
  const [autoMsg, setAutoMsg] = useState("");
  const [kchron, setKchron] = useState([]);
  const [crewDraft, setCrewDraft] = useState(null);

  const labor = d?.labor || {};
  const pop = d?.population || 0;
  const stock = d?.stockpiles || {};
  const built = d?.buildings || [];
  const projects = d?.projects || [];
  const catalog = summary?.catalog || {};
  const crews = crewDraft ?? (d?.crews || []);

  const loadChronicle = async () => {
    const r = await api("/api/world/kingdom-chronicle?limit=20");
    setKchron(r.chronicle || []);
  };

  const invest = async (mat) => {
    const qty = prompt(`Invest how much ${mat}?`, "10");
    if (!qty) return;
    await post("/api/world/invest", { material: mat, qty: parseInt(qty, 10) || 0 });
    reload();
  };

  const build = async (key) => {
    await post("/api/world/build", { key });
    reload();
  };

  const tickProjects = async () => {
    await post("/api/world/project-tick");
    reload();
  };

  const commitLabor = async () => {
    const body = {};
    Object.keys(laborDraft).forEach((k) => { body[k] = parseInt(laborDraft[k], 10) || 0; });
    await post("/api/world/labor", { labor: body });
    setAutoMsg("");
    reload();
  };

  const autoLabor = async () => {
    const r = await post("/api/world/labor-auto");
    if (r && r.ok === false) { setAutoMsg(r.detail || "no kingdom"); return; }
    if (r && r.labor) setLaborDraft(r.labor);
    setAutoMsg(r?.rationale || "Labor auto-allocated.");
    reload();
  };

  const commitCrews = async () => {
    await post("/api/world/crews", { crews });
    setCrewDraft(null);
    reload();
  };
  const editCrew = (i, field, val) => {
    setCrewDraft(crews.map((c, j) => j === i
      ? { ...c, [field]: field === "size" ? (parseInt(val, 10) || 0) : val } : c));
  };
  const addCrew = () => setCrewDraft([...crews, { name: "New Crew", size: 0, role: "" }]);
  const removeCrew = (i) => setCrewDraft(crews.filter((_, j) => j !== i));
  const crewTotal = crews.reduce((a, c) => a + (parseInt(c.size, 10) || 0), 0);

  const totalLabor = Object.values(labor).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);

  if (!d) {
    return html`<div class="pane">
      <h3>Kingdom</h3>
      <p class="muted small">You rule no domain yet. Found one to enter the kingdom-building phase — this also wakes the economy tick.</p>
      <div class="row">
        <input placeholder="domain name" value=${name} onInput=${(e) => setName(e.target.value)} />
        <button class="primary" onClick=${async () => { await post("/api/world/found-domain", { name }); reload(); }}>Found domain</button>
      </div>
    </div>`;
  }

  return html`<div class="pane">
    <div class="row" style="align-items:center">
      <h3 style="margin:0">${d.name}</h3>
      <span class="muted small">Year ${d.founded_year || 1} · Pop ${pop}</span>
    </div>
    <div class="subtabs">
      ${[["overview","Overview"],["buildings","Buildings"],["labor","Labor"],["chronicle","Chronicle"]].map(([k,l]) =>
        html`<button class=${k===sub?"active":""} onClick=${()=>{setSub(k);if(k==="chronicle")loadChronicle();}}>${l}</button>`)}
    </div>

    ${sub === "overview" && html`<div>
      <div class="kdash-grid">
        <div class="kdash-card">
          <div class="kdash-label">Treasury</div>
          <div class="kdash-big">${d.treasury}</div>
          <div class="kdash-bar"><${Bar} value=${Math.min(d.treasury,500)} max=${500} /></div>
        </div>
        <div class="kdash-card">
          <div class="kdash-label">Military</div>
          <div class="kdash-big">${d.military}</div>
          <div class="kdash-bar"><${Bar} value=${d.military} max=${Math.max(d.military,30)} /></div>
        </div>
        <div class="kdash-card">
          <div class="kdash-label">Morale</div>
          <div class="kdash-big">${d.morale}<span class="kdash-denom">/5</span></div>
          <div class="kdash-bar"><${Bar} value=${d.morale} max=${5} /></div>
        </div>
        <div class="kdash-card">
          <div class="kdash-label">Infrastructure</div>
          <div class="kdash-big">${d.infrastructure || 0}</div>
        </div>
      </div>
      <div class="card" style="margin-top:10px">
        <strong class="small">Stockpiles</strong>
        <div class="kdash-stock">
          ${Object.entries(stock).map(([k,v]) => html`<div class="kdash-stock-item">
            <span class="kdash-stock-name">${k}</span>
            <span class="kdash-stock-val">${v}</span>
            <button class="small" onClick=${()=>invest(k)}>Invest</button>
          </div>`)}
        </div>
      </div>
      <div class="row" style="margin-top:10px">
        <button onClick=${async ()=>{await post("/api/world/economy-tick");reload();}}>Tick economy</button>
        <button onClick=${async ()=>{await post("/api/world/seasonal-event");reload();}}>Seasonal event</button>
        <button onClick=${async ()=>{await post("/api/world/project-tick");reload();}}>Tick projects</button>
      </div>
    </div>`}

    ${sub === "buildings" && html`<div>
      <div class="card"><strong class="small">Active Projects</strong>
        ${projects.length ? projects.map(p => html`<div class="kdash-project" key=${p.key}>
          <div class="row" style="margin:0">
            <span>${p.label}</span>
            <span class="muted small">${p.turns_left}/${p.turns_total} turns</span>
          </div>
          <div class="kdash-progbar"><div style=${{width: Math.max(0,Math.min(100,((p.turns_total-p.turns_left)/p.turns_total)*100))+"%"}}></div></div>
        </div>`) : html`<div class="muted small">No construction underway.</div>`}
      </div>
      <div class="card"><strong class="small">Built</strong>
        ${built.length ? built.map(k => html`<div class="chip" key=${k}>${catalog[k]?.label || k}</div>`) : html`<div class="muted small">Nothing built yet.</div>`}
      </div>
      ${(() => {
        const byCat = {};
        const upgradeMap = {};
        Object.entries(catalog).forEach(([k,spec]) => {
          if (spec.upgrades_from) { upgradeMap[spec.upgrades_from] = [k, spec]; return; }
          const cat = spec.category || "other";
          byCat[cat] = byCat[cat] || [];
          byCat[cat].push([k, spec]);
        });
        const catOrder = ["infrastructure","defense","divine","leadership","sustenance","industry","civilian"];
        const catLabel = {infrastructure:"Infrastructure",defense:"Defense",divine:"Divine",leadership:"Leadership",sustenance:"Sustenance",industry:"Industry",civilian:"Civilian"};
        return catOrder.map(cat => {
          const items = byCat[cat];
          if (!items) return null;
          return html`<div class="card" key=${cat}>
            <strong class="small" style="text-transform:capitalize">${catLabel[cat] || cat}</strong>
            ${items.map(([k,spec]) => {
              const already = built.includes(k);
              const active = projects.some(p=>p.key===k);
              const reqsMet = (spec.requires || []).every(r => built.includes(r));
              const canAfford = Object.entries(spec.cost).every(([ck,cv])=>{
                if (ck==="treasury") return (d.treasury||0) >= cv;
                return (stock[ck]||0) >= cv;
              });
              const locked = !reqsMet && !already;
              const reqLabels = (spec.requires || []).map(r => catalog[r]?.label || r);
              return html`<div class="kdash-build-row ${locked ? 'kdash-locked' : ''}" key=${k}>
                <div class="row" style="margin:0;align-items:flex-start">
                  <div style="flex:1">
                    <div><strong>${spec.label}</strong> ${already?html`<span class="chip" style="margin-left:6px">built</span>`:null} ${active?html`<span class="chip" style="margin-left:6px">building</span>`:null} ${locked?html`<span class="chip" style="margin-left:6px">locked</span>`:null}</div>
                    <div class="muted small">${spec.desc}</div>
                    <div class="small" style="margin-top:3px">
                      ${Object.keys(spec.cost).length ? html`Cost: ${Object.entries(spec.cost).map(([ck,cv])=>`${cv} ${ck}`).join(", ")} · ${spec.turns} turns` : html`<em>Free — unlocked automatically</em>`}
                      ${reqLabels.length ? html` · Needs: ${reqLabels.join(", ")}` : null}
                    </div>
                  </div>
                  <button disabled=${already||active||!canAfford||locked} onClick=${()=>build(k)}>${already?"Built":active?"Building":locked?"Locked":"Build"}</button>
                  ${(() => {
                    const up = upgradeMap[k];
                    if (!already || !up) return null;
                    const [uk, uspec] = up;
                    if (built.includes(uk)) return null;
                    const ubuilding = projects.some(p => p.key === uk);
                    const uafford = Object.entries(uspec.cost).every(([ck,cv]) =>
                      ck === "treasury" ? (d.treasury||0) >= cv : (stock[ck]||0) >= cv);
                    return html`<button class="small" style="margin-left:6px" title=${uspec.desc}
                      disabled=${ubuilding || !uafford} onClick=${() => build(uk)}>
                      ${ubuilding ? "Upgrading…" : "⬆ " + uspec.label}</button>`;
                  })()}
                </div>
              </div>`;
            })}
          </div>`;
        });
      })()}
    </div>`}

    ${sub === "labor" && html`<div>
      <div class="card">
        <div class="row" style="justify-content:space-between;align-items:center">
          <strong class="small">Labor Allocation</strong>
          <span class="muted small">Total: ${totalLabor} / ${pop}</span>
        </div>
        ${Object.entries(labor).map(([k,v]) => html`<div class="kdash-labor" key=${k}>
          <label class="kdash-lab-name">${k}</label>
          <input type="range" min="0" max=${pop} value=${laborDraft[k] ?? v}
            onInput=${(e)=>setLaborDraft({...laborDraft,[k]:e.target.value})} />
          <span class="kdash-lab-val">${laborDraft[k] ?? v}</span>
        </div>`)}
        <div class="row" style="margin-top:8px">
          <button class="primary" onClick=${commitLabor}>Apply labor</button>
          <button onClick=${autoLabor} title="Smart allocation based on the realm's needs">⚡ Auto-allocate</button>
          <button onClick=${()=>{setLaborDraft({});setAutoMsg("");}}>Reset</button>
        </div>
        ${autoMsg ? html`<div class="small" style="color:var(--ember-2);margin-top:6px">⚡ ${autoMsg}</div>` : null}
        ${totalLabor > pop ? html`<div class="small" style="color:var(--bad);margin-top:6px">Total exceeds population — will be scaled down.</div>` : null}
      </div>

      <div class="card">
        <div class="row" style="justify-content:space-between;align-items:center">
          <strong class="small">Crews & Teams</strong>
          <span class="muted small">${crews.length} crews · ${crewTotal} assigned</span>
        </div>
        ${crews.length ? crews.map((c, i) => html`<div class="kdash-crew" key=${i}>
          <input class="kdash-crew-name" value=${c.name}
            onInput=${(e) => editCrew(i, "name", e.target.value)} />
          <input class="kdash-crew-size" type="number" min="0" value=${c.size}
            onInput=${(e) => editCrew(i, "size", e.target.value)} />
          <input class="kdash-crew-role" placeholder="role / task" value=${c.role || ""}
            onInput=${(e) => editCrew(i, "role", e.target.value)} />
          <button class="small kdash-crew-x" title="remove crew" onClick=${() => removeCrew(i)}>✕</button>
        </div>`) : html`<div class="muted small">No crews yet. The council can stand one up in play, or add one here.</div>`}
        <div class="row" style="margin-top:8px">
          <button class="primary" disabled=${crewDraft === null} onClick=${commitCrews}>Apply crews</button>
          <button onClick=${addCrew}>+ Add crew</button>
          ${crewDraft !== null ? html`<button onClick=${() => setCrewDraft(null)}>Reset</button>` : null}
        </div>
        <div class="small muted" style="margin-top:4px">Changes you apply here are seen by the council in play.</div>
      </div>
    </div>`}

    ${sub === "chronicle" && html`<div>
      <div class="card">
        ${kchron.length ? kchron.map(c => html`<div class="kdash-chron" key=${c.id}>
          <div class="kdash-chron-date">${c.in_world_date || ""}</div>
          <div>${c.content}</div>
          ${(c.tags||[]).length ? html`<div class="chips" style="margin-top:4px">${c.tags.map(t=>html`<span class="chip">${t}</span>`)}</div>` : null}
        </div>`) : html`<div class="muted small">No kingdom chronicle entries yet.</div>`}
      </div>
    </div>`}
  </div>`;
}

function GMPane({ world, reload, refresh, toast }) {
  const [name, setName] = useState("");
  const [adv, setAdv] = useState(1);
  const [unit, setUnit] = useState("hours");
  return html`<div class="pane">
    <h3>GM Controls</h3>
    <div class="card">
      <strong class="small">Safety net</strong>
      <div class="row">
        <button onClick=${async () => { const r = await post("/api/session/undo"); toast(r.ok ? "Undid last turn" : (r.detail || "nothing to undo"), r.ok ? "info" : "warn"); reload(); refresh(); }}>↶ Undo last turn</button>
        <button onClick=${async () => { await post("/api/session/backup", { label: "manual" }); toast("Backup saved", "info"); }}>Backup</button>
        <a href="/api/session/export"><button>Export DB</button></a>
      </div>
    </div>
    <div class="card">
      <strong class="small">New hero</strong>
      <div class="row">
        <input placeholder="name" value=${name} onInput=${(e) => setName(e.target.value)} />
        <button class="primary" onClick=${async () => {
          await post("/api/pcs", { name, abilities: { str: 12, dex: 14, con: 13, int: 10, wis: 11, cha: 12 } });
          setName(""); refresh(); reload(); toast("Hero created", "info");
        }}>Create</button>
      </div>
    </div>
    <div class="card">
      <strong class="small">Advance time</strong>
      <div class="row">
        <input style="width:70px" type="number" value=${adv} onInput=${(e) => setAdv(+e.target.value)} />
        <select value=${unit} onChange=${(e) => setUnit(e.target.value)}>
          ${["hours", "days", "weeks", "months", "seasons"].map((u) => html`<option>${u}</option>`)}
        </select>
        <button onClick=${async () => { const r = await post("/api/world/advance", { amount: adv, unit }); (r.fired_events || []).forEach((e) => toast(e, "info")); reload(); }}>Advance</button>
      </div>
    </div>
    <div class="card">
      <strong class="small">World</strong>
      <div class="row">
        <button onClick=${async () => { await post("/api/world/bootstrap", {}); reload(); }}>Bootstrap start</button>
        <button onClick=${async () => { await post("/api/world/faction-tick"); reload(); }}>Faction tick</button>
      </div>
    </div>
  </div>`;
}

// ------------------------------------------------------------------------- app
function App() {
  const [health, setHealth] = useState(null);
  const [world, setWorld] = useState(null);
  const [combat, setCombat] = useState(null);
  const [conn, setConn] = useState("connecting");
  const [sideOpen, setSideOpen] = useState(false);
  const [model, setModel] = useState(null);
  const { toasts, add } = useToasts();
  const reload = useCallback(async () => {
    const w = await api("/api/world"); setWorld(w);
    const c = await api("/api/combat"); setCombat(c.encounter || null);
  }, []);
  useEffect(() => {
    api("/api/health").then((h) => { setHealth(h); if (!model) setModel(h.narration_model); });
    reload();
    post("/api/warmup");  // begin loading the model as soon as the page opens
  }, []);

  return html`
    <${Header} health=${health} conn=${conn} model=${model} onMenu=${() => setSideOpen((o) => !o)} />
    <main>
      <${Play} onStateChange=${reload} onCombat=${setCombat} toast=${add}
        reportConn=${setConn} onModel=${setModel} />
      <${Sidebar} world=${world} combat=${combat} reload=${reload} toast=${add}
        open=${sideOpen} onClose=${() => setSideOpen(false)} />
    </main>
    ${sideOpen ? html`<div class="side-backdrop" onClick=${() => setSideOpen(false)}></div>` : null}
    <${Toasts} toasts=${toasts} />`;
}

render(html`<${App} />`, document.getElementById("app"));
