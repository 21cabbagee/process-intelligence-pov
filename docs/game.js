// Tiny gamification layer shared by both project sites: XP, levels, achievements,
// toasts and confetti. Progress lives in this browser only (localStorage, best effort).
(function () {
  const LEVELS = [0, 60, 150, 280, 450, 700, 1000];
  const reduced = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function toast(title, desc, icon = "✨", xp) {
    const box = $("toasts");
    if (!box) return;
    const t = document.createElement("div");
    t.className = "toast";
    t.innerHTML = `<div class="t-icon">${icon}</div><div><div class="t-title">${esc(title)}${xp ? ` <span class="t-xp">+${xp} XP</span>` : ""}</div><div class="t-desc">${esc(desc)}</div></div>`;
    box.appendChild(t);
    setTimeout(() => t.classList.add("out"), 3800);
    setTimeout(() => t.remove(), 4300);
  }

  function confetti(amount = 120) {
    if (reduced()) return;
    const c = $("confetti");
    if (!c) return;
    const ctx = c.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    c.width = innerWidth * dpr; c.height = innerHeight * dpr;
    ctx.scale(dpr, dpr);
    const css = getComputedStyle(document.documentElement);
    const colors = ["--accent", "--accent-2", "--ok", "--warn", "--pink"].map((v) => css.getPropertyValue(v).trim() || "#888");
    const parts = Array.from({ length: amount }, () => ({
      x: innerWidth / 2 + (Math.random() - 0.5) * 200, y: innerHeight * 0.35,
      vx: (Math.random() - 0.5) * 14, vy: -Math.random() * 12 - 4,
      r: Math.random() * 6 + 3, a: Math.random() * Math.PI, va: (Math.random() - 0.5) * 0.3,
      c: colors[(Math.random() * colors.length) | 0],
    }));
    let frame = 0;
    (function tick() {
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      parts.forEach((p) => {
        p.vy += 0.35; p.vx *= 0.99; p.x += p.vx; p.y += p.vy; p.a += p.va;
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.a); ctx.fillStyle = p.c;
        ctx.globalAlpha = Math.max(0, 1 - frame / 110); ctx.fillRect(-p.r / 2, -p.r / 4, p.r, p.r / 2); ctx.restore();
      });
      if (++frame < 110) requestAnimationFrame(tick); else ctx.clearRect(0, 0, innerWidth, innerHeight);
    })();
  }

  function floatXP(n) {
    const anchor = $("hudXp");
    if (!anchor || reduced()) return;
    const r = anchor.getBoundingClientRect();
    const f = document.createElement("div");
    f.className = "xp-float";
    f.textContent = `+${n} XP`;
    f.style.left = r.left + "px"; f.style.top = r.bottom + 4 + "px";
    document.body.appendChild(f);
    setTimeout(() => f.remove(), 1200);
  }

  function create(opts) {
    const key = opts.storageKey;
    const fresh = () => ({ xp: 0, unlocked: {}, progress: {} });
    let st = fresh();
    try { const s = JSON.parse(localStorage.getItem(key)); if (s && typeof s.xp === "number") st = { ...fresh(), ...s }; } catch (e) { /* storage unavailable */ }
    const save = () => { try { localStorage.setItem(key, JSON.stringify(st)); } catch (e) { /* ignore */ } };
    const ach = opts.achievements;
    const byId = Object.fromEntries(ach.map((a) => [a.id, a]));
    const levelOf = (xp) => LEVELS.reduce((l, t, i) => (xp >= t ? i : l), 0);

    function render() {
      const l = levelOf(st.xp);
      const lo = LEVELS[l], hi = LEVELS[l + 1];
      const pct = hi ? ((st.xp - lo) / (hi - lo)) * 100 : 100;
      const n = Object.keys(st.unlocked).filter((k) => byId[k]).length;
      if ($("hudLevel")) $("hudLevel").textContent = `Lv ${l + 1} · ${opts.levelNames[Math.min(l, opts.levelNames.length - 1)]}`;
      if ($("hudBar")) $("hudBar").style.width = pct + "%";
      if ($("hudXp")) $("hudXp").textContent = hi ? `${st.xp} / ${hi} XP` : `${st.xp} XP · max`;
      if ($("hudBadges")) $("hudBadges").innerHTML = `🏆 <b>${n}</b>/${ach.length}`;
      document.querySelectorAll("[data-achievements]").forEach((el) => {
        el.innerHTML = ach.map((a) => {
          const got = !!st.unlocked[a.id];
          const prog = a.goal ? Math.min(a.goal, (st.progress[a.id] || []).length) : null;
          return `<div class="ach ${got ? "got" : ""}">
            <div class="ach-icon">${got ? a.icon : "🔒"}</div>
            <div class="ach-body"><div class="ach-title">${esc(a.title)} <span class="ach-xp">${a.xp} XP</span></div>
            <div class="ach-desc">${esc(got ? a.desc : a.hint || a.desc)}</div>
            ${a.goal ? `<div class="ach-prog"><i style="width:${(prog / a.goal) * 100}%"></i></div><div class="ach-count">${prog}/${a.goal}</div>` : ""}</div></div>`;
        }).join("");
      });
      opts.onRender && opts.onRender(st);
    }

    function addXP(n) {
      const before = levelOf(st.xp);
      st.xp += n; save(); floatXP(n);
      const after = levelOf(st.xp);
      if (after > before) {
        setTimeout(() => { toast("Level up!", `You reached level ${after + 1}: ${opts.levelNames[Math.min(after, opts.levelNames.length - 1)]}`, "⬆️"); confetti(180); }, 600);
      }
      render();
    }

    function unlock(id) {
      if (st.unlocked[id] || !byId[id]) return false;
      st.unlocked[id] = Date.now();
      const a = byId[id];
      toast(a.title, a.desc, a.icon, a.xp);
      confetti(70);
      addXP(a.xp);
      const master = ach.find((x) => x.master);
      if (master && !st.unlocked[master.id] && ach.every((x) => x.master || st.unlocked[x.id])) setTimeout(() => unlock(master.id), 900);
      return true;
    }

    function progress(id, item) {
      const list = (st.progress[id] = st.progress[id] || []);
      if (!list.includes(item)) { list.push(item); save(); }
      if (byId[id] && byId[id].goal && list.length >= byId[id].goal) unlock(id); else render();
      return list.length;
    }

    function reset() { st = fresh(); save(); render(); toast("Progress reset", "Fresh start. Good luck!", "🔄"); }

    // drawer wiring
    const drawer = $("drawer");
    const open = (v) => { if (!drawer) return; drawer.classList.toggle("open", v); drawer.setAttribute("aria-hidden", String(!v)); };
    $("hudBadges") && $("hudBadges").addEventListener("click", () => open(!drawer.classList.contains("open")));
    drawer && drawer.addEventListener("click", (e) => {
      if (e.target.closest("[data-close]")) open(false);
      if (e.target.closest("[data-reset]")) reset();
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") open(false); });

    render();
    return { addXP, unlock, progress, reset, render, has: (id) => !!st.unlocked[id], state: () => st };
  }

  window.Game = { create, toast, confetti };
})();
