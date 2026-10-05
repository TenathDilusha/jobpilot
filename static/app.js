const $ = (id) => document.getElementById(id);

const state = { chat: [], questions: [], models: { normal: "Gemma", fast: "Gemma" } };

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function list(items) {
  return el("ul", {}, items.map((item) => el("li", {}, item)));
}

function box(title, ...children) {
  return el("div", { class: "box" }, el("h3", {}, title), ...children);
}

const fast = () => $("fast-mode").checked;
const modelName = () => (fast() ? state.models.fast : state.models.normal);

async function api(path, body) {
  let options = {};
  if (body instanceof FormData) options = { method: "POST", body };
  else if (body) {
    options = {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, fast: fast() }),
    };
  }
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

async function errorMessage(response) {
  const data = await response.json().catch(() => ({}));
  if (Array.isArray(data.detail)) return "Please fill in the required fields.";
  return data.detail || `Request failed (${response.status})`;
}

// Shows a live elapsed-time counter while a slow local model works.
async function run(button, target, loadingText, task) {
  if (button) button.disabled = true;
  const started = Date.now();
  const loading = el("p", { class: "loading" }, `${loadingText}…`);
  const timer = setInterval(() => {
    loading.textContent = `${loadingText}… ${Math.round((Date.now() - started) / 1000)}s`;
  }, 1000);
  target.replaceChildren(loading);
  try {
    target.replaceChildren(await task());
  } catch (err) {
    target.replaceChildren(el("p", { class: "error" }, err.message));
  } finally {
    clearInterval(timer);
    if (button) button.disabled = false;
  }
}

const cvText = () => $("cv-text").value.trim();
const jobText = () => $("job-text").value.trim();

function requireDocs(needJob = true) {
  if (!cvText()) throw new Error("Add your CV first (step 1).");
  if (needJob && !jobText()) throw new Error("Paste a job description first (step 2).");
}

// Tabs

function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
}
document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => showTab(tab.dataset.tab)));

// Health and fast mode

let health = null;

function renderStatus() {
  const status = $("status");
  const text = $("status-text");
  status.hidden = false;
  if (!health) {
    status.className = "status err";
    text.textContent = "Server unreachable";
    return;
  }
  const { ollama } = health;
  const available = fast() ? ollama.fast_model_available : ollama.model_available;
  if (!ollama.reachable) {
    status.className = "status err";
    text.textContent = "Ollama not running: start it with `ollama serve`";
  } else if (!available) {
    status.className = "status warn";
    text.textContent = `Run: ollama pull ${modelName()}`;
  } else {
    status.hidden = true;
  }
}

async function checkHealth() {
  try {
    health = await api("/api/health");
    state.models = { normal: health.ollama.model, fast: health.ollama.fast_model };
  } catch {
    health = null;
  }
  renderStatus();
}

$("fast-mode").checked = localStorage.getItem("fastMode") === "1";
$("fast-mode").addEventListener("change", () => {
  localStorage.setItem("fastMode", fast() ? "1" : "0");
  renderStatus();
});

// CV upload

function renderCvSkills(skills) {
  $("cv-skills").replaceChildren(...skills.map((s) => el("span", { class: "chip" }, s)));
}

$("cv-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  $("cv-skills").replaceChildren(el("span", { class: "loading" }, "Reading your CV…"));
  try {
    const { text, skills } = await api("/api/cv/parse", form);
    $("cv-text").value = text;
    renderCvSkills(skills);
  } catch (err) {
    $("cv-skills").replaceChildren(el("span", { class: "error" }, err.message));
  }
});

// Match & gaps

function scoreCard(value, label, alt = false) {
  return el("div", { class: `score${alt ? " alt" : ""}` }, el("div", { class: "value" }, value), el("div", { class: "label" }, label));
}

function renderKeywordMatch(km) {
  const value = km.score == null ? "—" : `${km.score}%`;
  return el("div", { class: "result" },
    box("Skills match",
      el("div", { class: "scores" }, scoreCard(value, `Keyword match: ${km.matched.length} of ${km.job_skills.length} skills the job lists`, true)),
      el("p", {}),
      el("div", { class: "chips" },
        km.matched.map((s) => el("span", { class: "chip match" }, `✓ ${s.skill}`)),
        km.missing.map((s) => el("span", { class: "chip missing" }, `✗ ${s.skill}`)),
      ),
    ),
  );
}

function renderGaps(ai) {
  return el("div", { class: "result" },
    el("div", { class: "scores" }, scoreCard(`${ai.fit_score}%`, `Overall fit, estimated by ${modelName()}`)),
    box("Summary", el("p", {}, ai.summary)),
    ai.strengths.length
      ? box("Your strengths for this job", list(ai.strengths.map((s) => [el("strong", {}, s.skill), " · “", s.evidence, "”"])))
      : null,
    box("Missing skills and how to close the gap",
      ai.missing_skills.map((g) => el("div", { class: `gap ${g.importance}` },
        el("strong", {}, g.skill), el("span", { class: "badge" }, g.importance),
        el("div", {}, g.why),
        el("div", {}, el("em", {}, "How to learn: "), g.how_to_learn),
      )),
    ),
    ai.cv_improvements.length ? box("Make your CV stronger for this job", list(ai.cv_improvements)) : null,
  );
}

function questionNodes() {
  return state.questions.map((q) => el("div", { class: "question" },
    el("div", {}, q.question, el("small", {}, `${q.category} · Tip: ${q.tip}`)),
    el("button", { class: "secondary", onclick: () => practice(q.question) }, "Practice"),
  ));
}

function renderQuestions(questions) {
  state.questions = questions;
  $("question-list").replaceChildren(box("Questions for this job", questionNodes()));
  return box("Interview questions they might ask", questionNodes());
}

function practice(question) {
  $("iv-question").value = question;
  $("iv-answer").value = "";
  $("iv-result").replaceChildren();
  showTab("interview");
  $("iv-answer").focus();
}

$("analyze-btn").addEventListener("click", async (e) => {
  const button = e.target;
  $("analyze-result").replaceChildren();
  $("questions-result").replaceChildren();
  try {
    requireDocs();
  } catch (err) {
    $("keyword-result").replaceChildren(el("p", { class: "error" }, err.message));
    return;
  }
  const docs = { cv_text: cvText(), job_description: jobText() };
  button.disabled = true;
  try {
    await run(null, $("keyword-result"), "Matching skills", async () => renderKeywordMatch(await api("/api/match", docs)));
    await run(null, $("analyze-result"), `${modelName()} is analysing your fit on this laptop`, async () =>
      renderGaps((await api("/api/analyze", docs)).ai));
    await run(null, $("questions-result"), `${modelName()} is preparing interview questions`, async () =>
      renderQuestions((await api("/api/interview/questions", docs)).questions));
  } finally {
    button.disabled = false;
  }
});

// Rewrite

$("rewrite-btn").addEventListener("click", (e) =>
  run(e.target, $("rewrite-result"), "Rewriting", async () => {
    const text = $("rewrite-text").value.trim();
    if (!text) throw new Error("Paste a project description to rewrite.");
    const r = await api("/api/rewrite", { text, target_role: $("rewrite-role").value, job_description: jobText() });
    const copyText = [r.rewritten, "", ...r.bullets.map((b) => `• ${b}`)].join("\n");
    return el("div", { class: "result" },
      box("Rewritten",
        el("button", { class: "secondary copy", onclick: (ev) => { navigator.clipboard.writeText(copyText); ev.target.textContent = "Copied"; } }, "Copy"),
        el("p", {}, r.rewritten)),
      box("CV bullet points", list(r.bullets)),
      box("Make it even better", list(r.notes)),
    );
  }));

// Interview practice

$("iv-btn").addEventListener("click", (e) =>
  run(e.target, $("iv-result"), "The interviewer is reviewing your answer", async () => {
    const question = $("iv-question").value.trim();
    const answer = $("iv-answer").value.trim();
    if (!question || !answer) throw new Error("Add a question and your answer.");
    const f = await api("/api/interview/feedback", { question, answer, cv_text: cvText(), job_description: jobText() });
    return el("div", { class: "result" },
      el("div", { class: "scores" }, scoreCard(`${f.score}/10`, "Interview readiness", true)),
      box("What worked", list(f.strengths)),
      box("How to improve", list(f.improvements)),
      box("A stronger answer", el("p", {}, f.better_answer)),
    );
  }));

// Chat (streamed token by token)

// Minimal markdown (bold, bullets) built from DOM nodes, so model output is never parsed as HTML.
function formatReply(text) {
  const inline = (line) => line.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? el("strong", {}, part) : part));
  const nodes = [];
  let bullets = null;
  for (const line of text.split("\n")) {
    const item = line.match(/^\s*[*-]\s+(.*)/);
    if (item) {
      if (!bullets) nodes.push((bullets = el("ul")));
      bullets.append(el("li", {}, inline(item[1])));
      continue;
    }
    bullets = null;
    if (line.trim()) nodes.push(el("p", {}, inline(line.replace(/^#+\s*/, ""))));
  }
  return nodes;
}

function addMessage(role, content) {
  const node = el("div", { class: `msg ${role}` }, content);
  $("chat-log").append(node);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
  return node;
}

async function sendChat(text) {
  if (!text) return;
  state.chat.push({ role: "user", content: text });
  addMessage("user", text);
  const pending = addMessage("assistant", `${modelName()} is thinking…`);
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: state.chat, cv_text: cvText(), job_description: jobText(), fast: fast() }),
    });
    if (!response.ok) throw new Error(await errorMessage(response));

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let reply = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      reply += decoder.decode(value, { stream: true });
      pending.replaceChildren(...formatReply(reply));
      $("chat-log").scrollTop = $("chat-log").scrollHeight;
    }
    state.chat.push({ role: "assistant", content: reply });
  } catch (err) {
    state.chat.pop();
    pending.textContent = err.message;
    pending.classList.add("error");
  }
}

$("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("chat-input").value.trim();
  $("chat-input").value = "";
  sendChat(text);
});
$("quick-prompts").addEventListener("click", (e) => {
  if (e.target.classList.contains("chip")) sendChat(e.target.textContent);
});

// Job search

function useJob(job) {
  const highlights = job.highlights.length ? `\n\n${job.highlights.map((h) => `- ${h}`).join("\n")}` : "";
  $("job-text").value = `${job.title} at ${job.company} (${job.location})\n\n${job.description}${highlights}`;
  showTab("analyze");
  $("job-text").scrollIntoView({ behavior: "smooth" });
}

function renderDemand(search, demand) {
  if (!demand.skills.length) return null;
  const hasCv = demand.skills[0].in_cv !== null;
  const max = demand.skills[0].count;
  const plan = el("div", {});
  const planButton = el("button", {
    class: "secondary",
    onclick: () => run(planButton, plan, `${modelName()} is building your learning plan`, async () => renderInsights(
      await api("/api/jobs/insights", { ...search, postings: demand.postings, skills: demand.skills, cv_text: cvText() }))),
  }, hasCv ? "What should I learn next?" : "Summarise what employers want");

  return box(`What employers are asking for right now (${demand.postings} live postings)`,
    hasCv ? el("p", { class: "hint" }, "Blue: already on your CV. Yellow: not on your CV yet.") : null,
    el("div", { class: "bars" }, demand.skills.map((s) => el("div", { class: "bar-row" },
      el("span", { class: "bar-label" }, s.skill),
      el("span", { class: "bar-track" },
        el("span", { class: `bar ${s.in_cv === true ? "have" : s.in_cv === false ? "need" : ""}`, style: `width: ${(100 * s.count) / max}%` })),
      el("span", { class: "bar-value" }, `${s.count} · ${s.share}%`),
    ))),
    el("div", { class: "actions" }, planButton),
    plan,
  );
}

function renderInsights(r) {
  return el("div", { class: "result" },
    el("p", {}, r.summary),
    r.learn_next.length
      ? box("Learn next", r.learn_next.map((s) => el("div", { class: "gap high" },
        el("strong", {}, s.skill), el("div", {}, s.why), el("div", {}, el("em", {}, "First step: "), s.first_step))))
      : null,
    r.lead_with.length ? box("Put these at the top of your CV", el("div", { class: "chips" }, r.lead_with.map((s) => el("span", { class: "chip match" }, s)))) : null,
  );
}

$("jobs-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const button = e.target.querySelector("button");
  run(button, $("jobs-result"), "Searching live job postings", async () => {
    const search = { query: $("jobs-query").value.trim(), location: $("jobs-location").value.trim() || "Sri Lanka" };
    const { jobs, demand } = await api("/api/jobs/search", { ...search, cv_text: cvText() });
    if (!jobs.length) return el("p", { class: "hint" }, "No postings found. Try a broader search.");
    return el("div", {}, renderDemand(search, demand), jobs.map((job) => el("article", { class: "job" },
      el("header", {},
        el("div", {}, el("h3", {}, job.title), el("div", { class: "meta" }, [job.company, job.location, job.via, job.posted].filter(Boolean).join(" · "))),
        job.match?.score != null ? el("span", { class: "pct" }, `${job.match.score}% match`) : null,
      ),
      job.match?.missing.length
        ? el("div", { class: "chips" }, job.match.missing.map((s) => el("span", { class: "chip missing" }, `✗ ${s.skill}`)))
        : null,
      el("div", { class: "actions" },
        el("button", { class: "secondary", onclick: () => useJob(job) }, "Use this job"),
        job.link ? el("a", { href: job.link, target: "_blank", rel: "noopener" }, "View posting ↗") : null,
      ),
    )));
  });
});

checkHealth();
