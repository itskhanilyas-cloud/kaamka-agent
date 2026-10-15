// Kaam Ka AI dashboard. No framework, no build step.
// All data is rendered with textContent (never innerHTML), because AI output is untrusted.

const $view = document.getElementById("view");
const state = { overview: null };

// ---------- helpers ----------
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

async function api(path, opts = {}) {
  const res = await fetch("/api" + path, {
    method: opts.method || "GET",
    headers: opts.body ? { "Content-Type": "application/json" } : {},
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    credentials: "same-origin",
  });
  if (res.status === 401) { location.href = "/.auth/login/aad?post_login_redirect_uri=/"; throw new Error("Please sign in"); }
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) throw new Error((data && (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))) || res.statusText);
  return data;
}

// In-page confirmation sheet. Native confirm()/prompt() are blocked or hidden in some
// embedded browsers and app webviews, which made buttons look dead.
function ask(message, { ok = "Yes", danger = false, input = null } = {}) {
  return new Promise((resolve) => {
    const prev = document.activeElement;
    const field = input ? h("textarea", { rows: 3, placeholder: input, "aria-label": input }) : null;
    const close = (val) => { overlay.remove(); document.removeEventListener("keydown", onKey); prev?.focus?.(); resolve(val); };
    const onKey = (e) => { if (e.key === "Escape") close(input ? null : false); };
    const okBtn = h("button", { class: danger ? "bad" : "good", onclick: () => close(input ? field.value.trim() : true) }, ok);
    const overlay = h("div", { class: "sheet-backdrop", onclick: (e) => { if (e.target === overlay) close(input ? null : false); } },
      h("div", { class: "sheet", role: "dialog", "aria-modal": "true", "aria-label": message },
        h("p", {}, message), field,
        h("div", { class: "row" }, okBtn, h("button", { class: "secondary", onclick: () => close(input ? null : false) }, "Cancel"))));
    document.body.append(overlay);
    document.addEventListener("keydown", onKey);
    (field || okBtn).focus();
  });
}

function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 2600);
}

const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const when = (s) => (s ? new Date(s).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "");
const STATUS_LABEL = { draft: "Draft", pending_approval: "Waiting for you", approved: "Approved", scheduled: "Scheduled",
  published: "Published", rejected: "Rejected", failed: "Failed" };
const FORMAT_LABEL = { IMAGE: "Image", CAROUSEL: "Carousel", REELS: "Reel", STORIES: "Story" };
const PILLARS = [["tool_test", "Tool test"], ["workflow", "Workflow"], ["prompts", "Prompts"], ["news", "AI news"], ["career", "Career"]];

function errorBox(e) { return h("div", { class: "error", role: "alert" }, e.message || String(e)); }
function page(title, sub, ...body) { return [h("h1", {}, title), sub ? h("p", { class: "sub" }, sub) : null, ...body]; }
function statusTag(p) {
  const cls = p.status === "published" || p.status === "approved" || p.status === "scheduled" ? "tag ok"
    : p.status === "rejected" || p.status === "failed" ? "tag bad" : "tag";
  return h("span", { class: cls }, STATUS_LABEL[p.status] || p.status);
}
function mockTag(isMock) { return isMock ? h("span", { class: "tag mock", title: "Practice output, not from the AI model" }, "MOCK") : null; }

function segmented(options, value, onChange) {
  const wrap = h("div", { class: "seg", role: "group" });
  const render = (v) => {
    wrap.replaceChildren(...options.map(([val, label]) =>
      h("button", { type: "button", "aria-pressed": String(val === v), onclick: () => { render(val); onChange(val); } }, label)));
  };
  render(value);
  return wrap;
}

// ---------- content preview (used by Studio, Approvals, Post detail) ----------
function contentPreview(content, mediaType, caption, media) {
  const c = content || {};
  const parts = [];
  const video = (media || []).find((m) => m.kind === "video");
  const shots = (media || []).filter((m) => m.kind === "slide" || (mediaType === "REELS" && m.kind === "cover"));
  if (c.hook && !shots.length) parts.push(h("p", { class: "hook" }, c.hook));
  if (video) {
    const cover = shots[0];
    parts.push(h("video", { class: "reel", src: video.url, controls: true, playsinline: true, muted: true, preload: "metadata",
      poster: cover ? cover.url : null, "aria-label": "Reel video" }));
  } else if (shots.length) {
    parts.push(h("div", { class: "slides", "aria-label": "Post images" },
      shots.map((m, i) => h("img", { class: mediaType === "REELS" ? "shot tall" : "shot", src: m.url, loading: "lazy",
        alt: `${mediaType === "REELS" ? "Reel cover" : "Slide " + (i + 1)}${c.slides?.[i]?.title ? ": " + c.slides[i].title : c.hook ? ": " + c.hook : ""}` }))));
    if (mediaType === "REELS") parts.push(h("p", { class: "meta" }, "Cover only so far. Upload the Reel's MP4 below."));
  } else if (mediaType === "CAROUSEL" && Array.isArray(c.slides)) {
    parts.push(h("div", { class: "slides", "aria-label": "Carousel slides" },
      c.slides.map((s, i) => h("div", { class: "slide" }, h("b", {}, s.title || ""), h("span", {}, s.body || ""), h("small", {}, `${i + 1} / ${c.slides.length}`)))));
  }
  if (mediaType === "REELS" && Array.isArray(c.script)) {
    parts.push(h("div", {}, c.script.map((s) =>
      h("div", { class: "scene" }, h("b", {}, `${s.seconds || ""}s · `), s.visual || "",
        s.voiceover ? h("div", {}, "🎙 ", s.voiceover) : null, s.on_screen_text ? h("div", { class: "meta" }, "Text: ", s.on_screen_text) : null))));
  }
  parts.push(h("div", { class: "preview" }, caption ?? c.caption ?? ""));
  return parts;
}

function qualityBlock(q) {
  if (!q) return null;
  const failed = q.checks.filter((c) => !c.passed);
  return h("div", {},
    h("p", {}, h("span", { class: "score" }, `Quality ${q.score}/100`), " ",
      q.blocked ? h("span", { class: "tag bad" }, "Needs edits") : h("span", { class: "tag ok" }, "Passes checks")),
    failed.length ? h("ul", { class: "checks" }, failed.map((c) => h("li", { class: "x" }, `✗ ${c.reason}${c.blocking ? " (must fix)" : ""}`))) : null);
}

// ---------- views ----------
async function viewHome() {
  const o = await api("/overview");
  state.overview = o;
  const s = o.posts_by_status;
  const pct = Math.min(100, (o.spent_this_month_inr / o.monthly_budget_inr) * 100);
  return page("Overview", "Your content pipeline at a glance.",
    o.pending_approvals ? h("a", { href: "#/approvals", class: "card", style: "display:block;text-decoration:none;color:inherit;border-color:var(--saffron)" },
      h("b", {}, `${o.pending_approvals} post${o.pending_approvals > 1 ? "s" : ""} waiting for your approval →`)) : null,
    h("div", { class: "grid four" },
      [["Drafts", s.draft], ["Waiting", s.pending_approval], ["Scheduled", s.approved + s.scheduled], ["Published", s.published]]
        .map(([k, v]) => h("div", { class: "stat" }, h("div", { class: "k" }, k), h("div", { class: "v" }, v)))),
    h("div", { class: "card" },
      h("h2", {}, "Spending this month"),
      h("p", {}, h("b", {}, inr(o.spent_this_month_inr)), ` of ${inr(o.monthly_budget_inr)} cap`),
      h("div", { class: `meter ${pct > 80 ? "hot" : ""}`, role: "progressbar", "aria-valuenow": Math.round(pct), "aria-valuemin": 0, "aria-valuemax": 100 },
        h("i", { style: `width:${pct}%` })),
      h("p", { class: "meta", style: "margin-top:8px" }, "AI calls are refused before they would exceed the cap.")),
    h("div", { class: "card" },
      h("h2", {}, "Status"),
      h("ul", { class: "list" },
        h("li", {}, "Instagram: ", h("b", {}, o.instagram_connected ? "Connected" : "Not connected yet"), h("div", { class: "meta" }, o.data_note)),
        h("li", {}, "AI writer: ", h("b", {}, o.text_provider === "mock" ? "Practice mode (mock)" : "Azure OpenAI")),
        h("li", {}, "Auto-publish: ", h("b", {}, o.auto_publish.enabled ? "On" : "Off"), h("div", { class: "meta" }, "Every post needs your approval while this is off.")))),
    h("a", { href: "#/studio" }, h("button", { class: "full" }, "✦ Create new content")));
}

async function viewStudio() {
  const form = { idea: "", media_type: "CAROUSEL", pillar: "workflow", variants: 3, has_affiliate_link: false, test_notes: "" };
  const results = h("div", { "aria-live": "polite" });
  const btn = h("button", { class: "full", type: "submit" }, "Generate drafts");

  const submit = async (ev) => {
    ev.preventDefault();
    btn.disabled = true; btn.replaceChildren(h("span", { class: "spinner" }), "Writing…");
    results.replaceChildren();
    try {
      const r = await api("/studio/generate", { method: "POST", body: form });
      results.replaceChildren(...[
        h("h2", { style: "margin-top:20px" }, `${r.drafts.length} draft${r.drafts.length > 1 ? "s" : ""}, best first`),
        r.provider === "mock" ? h("div", { class: "note" }, "Practice mode: these are placeholders, not real AI writing. Real drafts start once the app runs in Azure.") : null,
        ...r.drafts.map((d, i) => h("article", { class: "card" },
          h("div", { class: "row" }, h("span", { class: "tag" }, `Option ${i + 1}`), mockTag(d.is_mock)),
          contentPreview(d.variant, form.media_type, null, d.media),
          d.render_error ? errorBox(new Error("Images: " + d.render_error)) : null,
          qualityBlock(d.quality),
          h("a", { href: `#/post/${d.post_id}` }, h("button", { class: "secondary full", style: "margin-top:8px" }, "Open draft to edit & submit"))))].filter(Boolean));
      results.querySelector("h2")?.scrollIntoView({ behavior: "smooth" });
    } catch (e) { results.replaceChildren(errorBox(e)); }
    btn.disabled = false; btn.replaceChildren("Generate drafts");
  };

  return page("Content Studio", "Describe an idea; get scored drafts in the Kaam Ka AI voice. Nothing is posted.",
    h("form", { class: "card", onsubmit: submit },
      h("label", { for: "idea" }, "Idea"),
      h("textarea", { id: "idea", required: true, minlength: 5, maxlength: 500, placeholder: "e.g. 3 free AI tools that turn lecture recordings into notes",
        oninput: (e) => (form.idea = e.target.value) }),
      h("label", {}, "Format"),
      segmented([["IMAGE", "Image"], ["CAROUSEL", "Carousel"], ["REELS", "Reel"]], form.media_type, (v) => (form.media_type = v)),
      h("label", { for: "pillar" }, "Content pillar"),
      h("select", { id: "pillar", onchange: (e) => (form.pillar = e.target.value) },
        PILLARS.map(([v, l]) => h("option", { value: v, selected: v === form.pillar }, l))),
      h("label", {}, "How many options"),
      segmented([[1, "1"], [2, "2"], [3, "3"], [4, "4"]], form.variants, (v) => (form.variants = v)),
      h("label", { for: "notes" }, "Your test notes (optional)"),
      h("textarea", { id: "notes", style: "min-height:80px", placeholder: "What actually happened when you tried it. Leave empty and the AI won't claim any results.",
        oninput: (e) => (form.test_notes = e.target.value) }),
      h("label", { class: "check" }, h("input", { type: "checkbox", onchange: (e) => (form.has_affiliate_link = e.target.checked) }), "This post has an affiliate link"),
      h("div", { style: "margin-top:16px" }, btn)),
    results);
}

async function viewApprovals() {
  const items = await api("/approvals?status=pending");
  const list = h("div");
  const render = (rows) => {
    list.replaceChildren(...(rows.length ? rows.map((r) => {
      const p = r.post;
      const actions = h("div", { class: "row", style: "margin-top:10px" },
        h("button", { class: "good", onclick: () => decide(r.id, true) }, "Approve"),
        h("button", { class: "bad", onclick: () => decide(r.id, false) }, "Reject"),
        p ? h("a", { href: `#/post/${p.id}` }, h("button", { class: "secondary" }, "Edit")) : null);
      return h("article", { class: "card" },
        h("div", { class: "row" }, h("span", { class: "tag" }, r.kind.replace("_", " ")), p ? h("span", { class: "tag" }, FORMAT_LABEL[p.media_type]) : null, p ? mockTag(p.is_mock) : null),
        p ? contentPreview(p.content, p.media_type, p.caption, p.media) : h("pre", { class: "preview" }, JSON.stringify(r.payload, null, 2)),
        p?.scheduled_at ? h("p", { class: "meta" }, "Goes out: ", when(p.scheduled_at)) : p ? h("p", { class: "meta" }, "After you approve, it goes out when you press \u201cPublish approved posts now\u201d.") : null,
        h("p", { class: "meta" }, `Requested by ${r.requested_by} · ${when(r.created_at)}`),
        actions);
    }) : [h("div", { class: "card empty" }, "Nothing waiting for you. ", h("a", { href: "#/studio" }, "Create content"))]));
  };
  const decide = async (id, approve) => {
    let note = null;
    if (!approve) { note = await ask("Why reject? (optional, helps future drafts)", { ok: "Reject", danger: true, input: "Reason (optional)" }); if (note === null) return; note = note || null; }
    else if (!(await ask("Approve this post for publishing?", { ok: "Approve" }))) return;
    try {
      await api(`/approvals/${id}/decision`, { method: "POST", body: { approve, note } });
      toast(approve ? "Approved" : "Rejected");
      refreshBadge(); route();  // reload the whole view so the "Publish approved posts now" card appears
    } catch (e) { toast(e.message); }
  };
  render(items);
  const approved = await api("/posts?status=approved");
  const runNow = async (btn) => {
    if (!(await ask(`Publish ${approved.length} approved post${approved.length > 1 ? "s" : ""} to Instagram now? It will be public on your account. (Maximum 3 a day.)`, { ok: "Publish now" }))) return;
    btn.disabled = true; btn.replaceChildren(h("span", { class: "spinner" }), "Publishing…");
    try {
      const r = await api("/publish/run", { method: "POST" });
      toast(r.dry_run ? "Test mode: nothing will be posted" : "Publishing started. Photos take about a minute, Reels up to 5. Check Posts.");
      setTimeout(route, 4000);
    } catch (e) { toast(e.message); btn.disabled = false; btn.replaceChildren("Publish approved posts now"); }
  };
  const publishCard = approved.length ? h("div", { class: "card", style: "border-color:var(--green)" },
    h("p", {}, h("b", {}, `${approved.length} approved post${approved.length > 1 ? "s" : ""} ready to go.`)),
    h("p", { class: "meta" }, "These have no publish time, so they go out when you press this. Posts you gave a time go out by themselves at that time (checked every 15 minutes)."),
    h("button", { class: "good", onclick: (e) => runNow(e.currentTarget) }, "Publish approved posts now")) : null;
  return page("Approval Center", "Nothing is published, sent or spent without your OK here.", publishCard, list);
}

async function viewPosts(params) {
  const filters = [["draft", "Drafts"], ["pending_approval", "Waiting"], ["scheduled", "Scheduled"], ["approved", "Approved"], ["published", "Published"], ["rejected", "Rejected"], ["failed", "Failed"]];
  const current = params.get("status") || "draft";
  const posts = await api(`/posts?status=${current}`);
  return page("Posts", "Every draft and post, by status.",
    h("div", { class: "slides", style: "gap:6px;margin-bottom:12px" },
      filters.map(([v, l]) => h("a", { href: `#/posts?status=${v}` }, h("button", { class: v === current ? "" : "secondary", style: "white-space:nowrap" }, l)))),
    h("div", { class: "card" }, posts.length ? h("ul", { class: "list" }, posts.map((p) =>
      h("li", {}, h("a", { href: `#/post/${p.id}`, style: "text-decoration:none;color:inherit;display:block" },
        h("div", { class: "row" }, statusTag(p), h("span", { class: "tag" }, FORMAT_LABEL[p.media_type]), mockTag(p.is_mock),
          p.quality ? h("span", { class: "meta" }, `Quality ${p.quality.score}`) : null),
        h("p", { style: "margin:6px 0 0;font-weight:600" }, (p.content?.hook || p.caption || "(no caption)").slice(0, 90)),
        h("p", { class: "meta" }, p.scheduled_at ? `Scheduled ${when(p.scheduled_at)}` : p.published_at ? `Published ${when(p.published_at)}` : "")))))
      : h("p", { class: "empty" }, "No posts here.")));
}

async function viewPost(id) {
  const all = await api("/posts");
  const p = all.find((x) => x.id === id);
  if (!p) return page("Post not found", null);
  const editable = ["draft", "rejected", "failed", "approved"].includes(p.status);
  const edits = { caption: p.caption, scheduled_at: p.scheduled_at, has_affiliate_link: p.has_affiliate_link };
  const c = p.content || {};
  const draft = { hook: c.hook || "", slides: (c.slides || []).map((s) => ({ title: s.title || "", body: s.body || "" })) };
  let contentDirty = false;
  const body = () => (contentDirty ? { ...edits, ...(p.media_type === "CAROUSEL" ? { slides: draft.slides } : { hook: draft.hook }) } : edits);
  const rerender = async () => {
    try { await api(`/posts/${id}/render`, { method: "POST" }); toast("Images updated"); route(); } catch (e) { toast(e.message); }
  };
  const slideEditor = p.media_type === "CAROUSEL"
    ? draft.slides.map((s, i) => h("div", { class: "slide-edit" },
        h("label", { for: `st${i}` }, `Slide ${i + 1} title`),
        h("input", { id: `st${i}`, type: "text", maxlength: 200, value: s.title, oninput: (e) => { s.title = e.target.value; contentDirty = true; } }),
        h("label", { for: `sb${i}` }, `Slide ${i + 1} text`),
        h("textarea", { id: `sb${i}`, style: "min-height:80px", maxlength: 600, oninput: (e) => { s.body = e.target.value; contentDirty = true; } }, s.body)))
    : [h("label", { for: "hook" }, p.media_type === "REELS" ? "Cover headline" : "Image headline"),
       h("input", { id: "hook", type: "text", maxlength: 200, value: draft.hook, oninput: (e) => { draft.hook = e.target.value; contentDirty = true; } })];
  const toLocal = (s) => (s ? new Date(new Date(s).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "");

  const upload = async (input) => {
    const f = input.files[0];
    if (!f) return;
    if (f.size > 100 * 1024 * 1024) { toast("Video is larger than 100 MB"); return; }
    input.disabled = true; toast("Uploading video…");
    try {
      const res = await fetch(`/api/posts/${id}/video`, { method: "POST", body: f, headers: { "Content-Type": "video/mp4" }, credentials: "same-origin" });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.detail || res.statusText);
      toast("Video added"); route();
    } catch (e) { toast(e.message); input.disabled = false; }
  };
  const save = async () => {
    try { await api(`/posts/${id}`, { method: "PATCH", body: body() }); toast(contentDirty ? "Saved and images updated" : "Saved"); route(); } catch (e) { toast(e.message); }
  };
  const submit = async () => {
    try { await api(`/posts/${id}`, { method: "PATCH", body: body() }); await api(`/posts/${id}/submit`, { method: "POST" });
      toast("Sent to Approval Center"); refreshBadge(); location.hash = "#/approvals"; }
    catch (e) { toast(e.message); }
  };

  return page(FORMAT_LABEL[p.media_type] + " post", null,
    h("div", { class: "row", style: "margin-bottom:10px" }, statusTag(p), mockTag(p.is_mock), p.generated_by && !p.is_mock ? h("span", { class: "meta" }, `Written by ${p.generated_by}`) : null),
    h("div", { class: "card" }, contentPreview(p.content, p.media_type, p.caption, p.media), qualityBlock(p.quality),
      editable && !p.media.length ? h("button", { class: "secondary", style: "margin-top:8px", onclick: rerender }, "Make images") : null),
    editable ? h("div", { class: "card" },
      h("h2", {}, "Edit"),
      h("details", { open: !p.media.length },
        h("summary", {}, p.media_type === "CAROUSEL" ? "Slide text (updates the images)" : "Headline (updates the image)"),
        slideEditor),
      p.media_type === "REELS" ? h("div", {},
        h("label", { for: "vid" }, p.media.some((m) => m.kind === "video") ? "Replace the video (MP4, 9:16, up to 100 MB)" : "Reel video (MP4, 9:16, up to 100 MB)"),
        h("input", { id: "vid", type: "file", accept: "video/mp4", onchange: (e) => upload(e.target) })) : null,
      h("label", { for: "cap" }, "Caption (with hashtags)"),
      h("textarea", { id: "cap", style: "min-height:200px", oninput: (e) => (edits.caption = e.target.value) }, p.caption),
      h("label", { for: "when" }, "Publish time (optional)"),
      h("input", { id: "when", type: "datetime-local", value: toLocal(p.scheduled_at),
        onchange: (e) => (edits.scheduled_at = e.target.value ? new Date(e.target.value).toISOString() : null) }),
      h("label", { class: "check" }, h("input", { type: "checkbox", checked: p.has_affiliate_link, onchange: (e) => (edits.has_affiliate_link = e.target.checked) }), "Has an affiliate link"),
      p.checks.length ? h("div", { class: "note", style: "margin-top:12px" }, h("b", {}, "Before it can be submitted:"),
        h("ul", { class: "checks" }, p.checks.map((c) => h("li", {}, "• " + c)))) : null,
      h("div", { class: "row", style: "margin-top:12px" },
        h("button", { class: "secondary", onclick: save }, "Save"),
        h("button", { onclick: submit, disabled: p.is_mock }, "Submit for approval")),
      p.is_mock ? h("p", { class: "meta", style: "margin-top:8px" }, "Practice drafts can't be submitted.") : null)
    : h("p", { class: "meta" }, p.status === "pending_approval" ? "Waiting in the Approval Center." : ""),
    p.last_error ? errorBox(new Error("Last error: " + p.last_error)) : null);
}

function viewMore() {
  return page("More", null, h("nav", { class: "card menu" },
    [["#/money", "Money", "Revenue, costs, profit"], ["#/settings", "Settings", "Auto-publish, budget, accounts"],
      ["#/analytics", "Results", "Views, reach, saves, followers"], ["#/audit", "Audit log", "Every important action"], ["#/trends", "Trend Lab", "Coming in Phase 8"]]
      .map(([href, l, d]) => h("a", { href }, l, h("span", {}, d)))));
}

async function viewMoney() {
  const s = await api("/revenue/summary");
  const form = { source: "affiliate", amount_inr: "", confirmed: false, evidence: "" };
  const add = async (ev) => {
    ev.preventDefault();
    try { await api("/revenue", { method: "POST", body: { ...form, amount_inr: Number(form.amount_inr) } }); toast("Recorded"); route(); }
    catch (e) { toast(e.message); }
  };
  return page("Money", "Confirmed money needs proof. Estimates are kept separate and never counted as earned.",
    h("div", { class: "grid" },
      h("div", { class: "stat" }, h("div", { class: "k" }, "Confirmed revenue"), h("div", { class: "v" }, inr(s.revenue_confirmed_inr))),
      h("div", { class: "stat" }, h("div", { class: "k" }, "Costs"), h("div", { class: "v" }, inr(s.costs_inr))),
      h("div", { class: "stat" }, h("div", { class: "k" }, "Confirmed profit"), h("div", { class: "v" }, inr(s.profit_confirmed_inr))),
      h("div", { class: "stat" }, h("div", { class: "k" }, "Estimated (not yet paid)"), h("div", { class: "v" }, inr(s.revenue_estimated_inr)))),
    Object.keys(s.by_source).length ? h("div", { class: "card" }, h("h2", {}, "By source"), h("ul", { class: "list" },
      Object.entries(s.by_source).map(([k, v]) => h("li", { class: "row", style: "justify-content:space-between" }, h("span", {}, k.replace("_", " ")),
        h("span", {}, inr(v.confirmed), v.estimated ? h("span", { class: "meta" }, ` + ${inr(v.estimated)} est.`) : null))))) : null,
    h("form", { class: "card", onsubmit: add },
      h("h2", {}, "Record income"),
      h("label", { for: "src" }, "Source"),
      h("select", { id: "src", onchange: (e) => (form.source = e.target.value) },
        [["affiliate", "Affiliate"], ["sponsorship", "Sponsorship"], ["digital_product", "Digital product"], ["referral", "Referral"], ["ads", "Ads"], ["other", "Other"]]
          .map(([v, l]) => h("option", { value: v }, l))),
      h("label", { for: "amt" }, "Amount (₹)"),
      h("input", { id: "amt", type: "number", min: "0", step: "0.01", required: true, inputmode: "decimal", oninput: (e) => (form.amount_inr = e.target.value) }),
      h("label", { class: "check" }, h("input", { type: "checkbox", onchange: (e) => (form.confirmed = e.target.checked) }), "Money received (confirmed)"),
      h("label", { for: "ev" }, "Proof (payout ID, statement or invoice)"),
      h("input", { id: "ev", type: "text", placeholder: "Required if confirmed", oninput: (e) => (form.evidence = e.target.value) }),
      h("div", { style: "margin-top:16px" }, h("button", { class: "full", type: "submit" }, "Record"))));
}

async function viewSettings() {
  const [o, pol, ig] = await Promise.all([api("/overview"), api("/policies/auto_publish"), api("/instagram/status")]);
  const flag = new URLSearchParams(location.hash.split("?")[1] || "").get("ig");
  const disconnect = async () => {
    if (!(await ask("Disconnect Instagram? Kaam Ka AI will stop being able to post until you connect again.", { ok: "Disconnect", danger: true }))) return;
    try { await api("/instagram/disconnect", { method: "POST" }); toast("Instagram disconnected"); route(); } catch (e) { toast(e.message); }
  };
  const igCard = h("div", { class: "card" }, h("h2", {}, "Instagram"),
    flag === "connected" ? h("div", { class: "note" }, "Connected. Kaam Ka AI can now publish posts you approve.") : null,
    flag === "declined" ? h("div", { class: "error" }, "Connection cancelled on Instagram. Nothing was changed.") : null,
    ig.connected
      ? [h("p", {}, "Connected as ", h("b", {}, "@" + ig.username), ig.account_type ? h("span", { class: "meta" }, ` (${ig.account_type.toLowerCase().replace("_", " ")})`) : null),
         h("p", { class: "meta" }, "Access renews automatically. Current access valid until ", when(ig.token_expires_at), "."),
         h("button", { class: "bad", onclick: disconnect }, "Disconnect")]
      : ig.configured
        ? [h("p", {}, "Not connected yet."),
           h("p", { class: "meta" }, "You'll sign in on Instagram's own page and approve: profile info, publishing, comments and insights. Direct messages are not requested."),
           h("a", { href: "/instagram/connect" }, h("button", {}, "Connect Instagram"))]
        : h("p", { class: "meta" }, "Waiting for the Instagram app settings to be added in Azure."));
  const toggle = async () => {
    const next = !pol.enabled;
    if (next && !(await ask("Turn on auto-publish? Approved post types could then publish without a per-post click. You can turn it off any time.", { ok: "Turn on" }))) return;
    try { await api("/policies/auto_publish", { method: "PUT", body: { value: { ...pol, enabled: next } } }); toast(next ? "Auto-publish on" : "Auto-publish off"); route(); }
    catch (e) { toast(e.message); }
  };
  return page("Settings", "Only you can change these. The agent can read them but never change them.",
    h("div", { class: "card" }, h("h2", {}, "Auto-publish"),
      h("p", {}, pol.enabled ? "On." : "Off: every post needs your approval."),
      h("p", { class: "meta" }, o.instagram_connected ? "Scheduled automatic posting is not switched on yet; publish approved posts from Approve." : "Not active until Instagram is connected."),
      h("button", { class: pol.enabled ? "bad" : "secondary", onclick: toggle }, pol.enabled ? "Turn off" : "Turn on")),
    h("div", { class: "card" }, h("h2", {}, "Budget"),
      h("p", {}, `Monthly cap ${inr(o.monthly_budget_inr)} · spent ${inr(o.spent_this_month_inr)}`),
      h("p", { class: "meta" }, "Change the cap with KA_MONTHLY_BUDGET_INR in Azure settings.")),
    igCard,
    h("div", { class: "card" }, h("h2", {}, "AI writer"),
      h("p", {}, h("b", {}, o.text_provider === "mock" ? "Practice mode" : "Azure OpenAI (text-main)"))));
}

async function viewAudit() {
  const rows = await api("/audit?limit=100");
  return page("Audit log", "Every approval, change, block and error. Secrets are hidden automatically.",
    h("div", { class: "card" }, rows.length ? h("ul", { class: "list" }, rows.map((r) =>
      h("li", {}, h("b", {}, r.event.replaceAll("_", " ")), h("div", { class: "meta" }, `${when(r.at)} · ${r.actor}${r.target ? " · " + r.target.slice(0, 8) : ""}`))))
      : h("p", { class: "empty" }, "No events yet.")));
}

async function viewAnalytics() {
  const a = await api("/analytics");
  const n = (v) => (v == null ? "–" : Number(v).toLocaleString("en-IN"));
  const pct = (v) => (v == null ? "–" : (v * 100).toFixed(1) + "%");
  const refresh = async (btn) => {
    btn.disabled = true; btn.replaceChildren(h("span", { class: "spinner" }), "Fetching from Instagram…");
    try { await api("/analytics/refresh", { method: "POST" }); setTimeout(route, 6000); }
    catch (e) { toast(e.message); btn.disabled = false; btn.replaceChildren("Refresh numbers now"); }
  };
  const t = a.totals;
  return page("Results", "Real numbers from Instagram only. Updated every 6 hours.",
    h("div", { class: "grid four" },
      [["Followers", a.followers], ["Views", t.views], ["Saves", t.saved], ["Shares", t.shares]]
        .map(([k, v]) => h("div", { class: "stat" }, h("div", { class: "k" }, k), h("div", { class: "v" }, n(v))))),
    h("div", { class: "card" }, h("h2", {}, "What the numbers say"),
      h("ul", { class: "list" }, a.lessons.map((l) => h("li", {}, l)))),
    a.posts.length ? a.posts.map((r) => h("a", { href: `#/post/${r.id}`, class: "card", style: "display:block;text-decoration:none;color:inherit" },
      h("div", { class: "row" }, h("span", { class: "tag" }, FORMAT_LABEL[r.format] || r.format), h("span", { class: "meta" }, when(r.published_at))),
      h("p", {}, h("b", {}, r.hook)),
      r.has_data
        ? h("div", { class: "grid four" },
            [["Views", n(r.views)], ["Reach", n(r.reach)], ["Saves", `${n(r.saved)} · ${pct(r.save_rate)}`], ["Shares", `${n(r.shares)} · ${pct(r.share_rate)}`]]
              .map(([k, v]) => h("div", { class: "stat" }, h("div", { class: "k" }, k), h("div", { class: "v small" }, v))))
        : h("p", { class: "meta" }, "No numbers yet. Instagram needs a little time after posting.")))
      : h("div", { class: "card empty" }, "Nothing published yet."),
    h("p", { class: "meta" }, a.last_synced_at ? `Last fetched ${when(a.last_synced_at)}.` : "Not fetched yet."),
    h("button", { class: "secondary", onclick: (e) => refresh(e.currentTarget) }, "Refresh numbers now"));
}

function viewComingSoon(title, text) { return page(title, null, h("div", { class: "card" }, h("p", {}, text))); }

// ---------- router ----------
const routes = {
  home: viewHome, studio: viewStudio, approvals: viewApprovals, posts: viewPosts, more: viewMore,
  money: viewMoney, settings: viewSettings, audit: viewAudit,
  trends: () => viewComingSoon("Trend Lab", "Ranked content ideas, researched from permitted sources and your own results, arrive in Phase 8."),
  analytics: viewAnalytics,
};
const TAB_OF = { money: "more", settings: "more", audit: "more", trends: "more", analytics: "more", post: "posts" };

async function route() {
  const [path, query] = (location.hash.slice(2) || "home").split("?");
  const [name, arg] = path.split("/");
  const params = new URLSearchParams(query || "");
  document.querySelectorAll(".nav a").forEach((a) => a.toggleAttribute("aria-current", false));
  const tab = document.querySelector(`.nav a[data-tab="${TAB_OF[name] || name}"]`);
  if (tab) tab.setAttribute("aria-current", "page");
  $view.replaceChildren(h("p", { class: "meta" }, h("span", { class: "spinner" }), "Loading…"));
  try {
    const out = name === "post" ? await viewPost(arg) : await (routes[name] || viewHome)(params);
    $view.replaceChildren(...[out].flat(Infinity).filter((x) => x != null && x !== false));
  } catch (e) { $view.replaceChildren(errorBox(e)); }
  $view.focus({ preventScroll: true }); window.scrollTo(0, 0);
}

async function refreshBadge() {
  try {
    const o = await api("/overview");
    const b = document.getElementById("badge");
    b.hidden = !o.pending_approvals; b.textContent = o.pending_approvals;
    const env = document.getElementById("env");
    env.textContent = o.environment === "production" ? "Live" : "Test mode";
    env.classList.toggle("prod", o.environment === "production");
  } catch { /* shown by the view */ }
}

window.addEventListener("hashchange", route);
route(); refreshBadge();
