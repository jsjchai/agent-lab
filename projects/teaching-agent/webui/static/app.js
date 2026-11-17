/* ==========================================================================
   Teaching Agent · 可视化 —— 纯原生 JS，无外部依赖。
   所有 API 均为同源相对路径 /api/...
   ========================================================================== */
"use strict";

/* ------------------------------------------------------------ 工具函数 */

function $(sel) { return document.querySelector(sel); }

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

async function api(path, options) {
  let res;
  try {
    res = await fetch(path, options);
  } catch (e) {
    throw new Error("网络请求失败：" + e.message + "（请确认后端正在运行）");
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* 非 JSON 响应 */ }
  if (!res.ok) {
    throw new Error((data && data.error) ? data.error : ("请求失败（HTTP " + res.status + "）"));
  }
  return data;
}

function postJSON(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function showError(msg) {
  $("#error-text").textContent = msg;
  $("#error-banner").hidden = false;
}
function hideError() { $("#error-banner").hidden = true; }

/* 按钮 loading 态：禁用 + 文案「处理中…」，结束后恢复 */
function setBusy(btn, busy, busyText) {
  if (!btn) return;
  if (busy) {
    btn.dataset.origText = btn.textContent;
    btn.textContent = busyText || "处理中…";
    btn.disabled = true;
  } else {
    btn.textContent = btn.dataset.origText || btn.textContent;
    btn.disabled = false;
  }
}

/* ------------------------------------------------------------ Tab 切换 */

document.querySelectorAll(".tab").forEach(function (btn) {
  btn.addEventListener("click", function () {
    document.querySelectorAll(".tab").forEach(function (b) {
      b.classList.toggle("active", b === btn);
      b.setAttribute("aria-selected", b === btn ? "true" : "false");
    });
    document.querySelectorAll(".tab-panel").forEach(function (p) {
      p.classList.toggle("active", p.id === "tab-" + btn.dataset.tab);
    });
    /* 面板只是隐藏，不销毁：切 Tab 不丢已跑出的结果 */
  });
});

/* ------------------------------------------------------------ 初始化 */

function currentModel() {
  const el = $("#model-select");
  return el ? el.value : "mock";
}

async function init() {
  try {
    const h = await api("/api/health");
    $("#llm-info").textContent = h.llm || "LLM 后端未知";
    $("#llm-info").classList.add("ok");
    const users = Array.isArray(h.users) && h.users.length ? h.users : ["u1", "u2", "u3"];
    ["#wf-user", "#rag-user"].forEach(function (sel) {
      const el = $(sel);
      el.innerHTML = users.map(function (u) {
        return '<option value="' + esc(u) + '">' + esc(u) + "</option>";
      }).join("");
    });
    const models = Array.isArray(h.models) && h.models.length ? h.models : ["mock"];
    $("#model-select").innerHTML = models.map(function (m) {
      const label = m === "mock" ? "mock（离线）" : m + "（Ollama）";
      return '<option value="' + esc(m) + '">' + esc(label) + "</option>";
    }).join("");
    $("#model-select").value = h.default_model || "mock";
    const syncBadge = function () {
      const m = $("#model-select").value;
      $("#llm-info").textContent = m === "mock" ? "LLM 后端：mock（离线，无需 API key）" : "LLM 后端：" + m + "（Ollama 本地）";
    };
    $("#model-select").addEventListener("change", syncBadge);
    syncBadge();
  } catch (e) {
    $("#llm-info").textContent = "后端连接失败";
    $("#llm-info").classList.add("bad");
    showError("健康检查失败：" + e.message);
  }
  loadEvalAndSecurity();
}

/* ============================================================
   Tab 1：活动创建工作流
   ============================================================ */

let wfData = null;      /* 最近一次 start/resume/status 的完整响应 */
let wfBusy = false;

const NODE_LABELS = {
  extract: "抽取", clarify: "澄清", gather: "收集", draft: "草稿",
  validate: "校验", fix: "修正", confirm: "确认", create: "创建", fail: "失败",
};
const MAIN_NODES = ["extract", "gather", "draft", "validate", "confirm", "create"];
const SLOT_LABELS = {
  activity_type: "活动类型", subject: "学科", grade: "年级", time_hint: "时间提示",
  date_text: "日期", audience: "参与对象", speaker_count: "主讲人数", speakers: "主讲人",
};
const DRAFT_LABELS = {
  title: "标题", activity_type: "活动类型", subject: "学科", grade: "年级",
  date_text: "日期", audience: "参与对象", speakers: "主讲人", duration_minutes: "时长（分钟）",
};

function fmtVal(v) {
  if (Array.isArray(v)) return v.join("、");
  return String(v);
}

/* ---- 流程图 ---- */

function currentNodeOf(data) {
  if (!data || data.done || !data.interrupt) return null;
  const t = data.interrupt.type;
  if (t === "clarification") return "extract";   /* extract↺clarify 回环处 */
  if (t === "confirmation") return "confirm";
  if (t === "validation_error") return "validate"; /* validate↺fix 回环处 */
  return null;
}

function isFailed(data) {
  const st = (data && data.state) || {};
  return !!(data && data.done && (st.status === "failed" || !st.activity_id));
}

function renderGraph(data) {
  const wrap = $("#flow-graph");
  const traceNodes = new Set(((data && data.trace) || []).map(function (t) { return t.node; }));
  const done = !!(data && data.done) && !isFailed(data);
  const current = currentNodeOf(data);
  const started = !!data;

  let html = '<div class="flow">';
  MAIN_NODES.forEach(function (name, i) {
    if (i > 0) html += '<div class="flow-arrow" aria-hidden="true">→</div>';

    let cls = "pending";
    if (done || traceNodes.has(name)) cls = "done";
    if (name === current) cls = "current";
    if (!started) cls = "pending";

    /* 回环标记：extract↺clarify、validate↺fix */
    let loop = "";
    if (name === "extract") {
      const active = current === "extract" || traceNodes.has("clarify");
      loop = '<div class="loop-badge' + (active ? " loop-active" : "") + '">↺ clarify 澄清</div>';
    } else if (name === "validate") {
      const active = current === "validate" || traceNodes.has("fix");
      loop = '<div class="loop-badge' + (active ? " loop-active" : "") + '">↺ fix 修正</div>';
    }

    const mark = cls === "done" ? "✓ " : (cls === "current" ? "● " : "");
    html += '<div class="flow-cell">' + loop +
      '<div class="flow-node node-' + cls + '" data-node="' + name + '">' +
      '<span class="node-mark">' + mark + "</span>" +
      '<span class="node-cn">' + NODE_LABELS[name] + "</span>" +
      '<span class="node-en">' + name + "</span>" +
      "</div></div>";
  });
  html += "</div>";

  if (traceNodes.has("fail")) {
    html += '<div class="fail-chip">✗ 流程进入 fail 节点（创建失败，详见交互区错误信息）</div>';
  }
  wrap.innerHTML = html;
}

/* ---- 中断交互区 ---- */

function renderInterrupt(data) {
  const area = $("#interrupt-area");

  if (!data) {
    area.innerHTML = '<p class="placeholder">尚未开始。点击上方「开始创建」后，这里会出现需要你回答的澄清问题或待确认的活动草稿。</p>';
    return;
  }

  if (data.done) {
    if (isFailed(data)) {
      area.innerHTML =
        '<div class="fail-card">' +
        '<div class="fail-title">✗ 活动创建失败</div>' +
        '<p>流程已进入 fail 节点（澄清/修正轮次达到上限，或校验始终未通过）。请点「重置」后重新发起，并在澄清时直接给出合法信息（如：11月20日，主讲人：张三、李四）。</p>' +
        "</div>";
      return;
    }
    const aid = (data.state && data.state.activity_id) || "（未知）";
    area.innerHTML =
      '<div class="success-card">' +
      '<div class="success-title">✓ 活动创建成功</div>' +
      '<p class="kv"><span class="kv-key">activity_id</span><code class="mono">' + esc(aid) + "</code></p>" +
      '<p class="success-note">凭证已一次性消费，重放会被拒绝（可切到「评测与安全」查看「凭证重放」测试）。</p>' +
      "</div>";
    return;
  }

  const it = data.interrupt;
  if (!it) {
    area.innerHTML = '<p class="placeholder">当前无中断，等待后端返回…</p>';
    return;
  }

  if (it.type === "clarification") {
    const qs = (it.questions || []).map(function (q) { return "<li>" + esc(q) + "</li>"; }).join("");
    area.innerHTML =
      '<div class="interrupt-panel panel-clarify">' +
      '<div class="panel-head"><span class="panel-tag tag-clarify">澄清</span>Agent 需要更多信息（第 ' +
      esc(((data.state && data.state.clarify_rounds) || 0) + 1) + " 轮）</div>" +
      '<ul class="question-list">' + qs + "</ul>" +
      '<textarea id="clarify-input" class="input textarea" rows="2" placeholder="请一次性回答以上问题，例如：11月20日，主讲人：张三、李四"></textarea>' +
      '<div class="btn-row"><button id="btn-clarify" class="btn btn-primary" type="button">提交补充</button></div>' +
      "</div>";
    $("#btn-clarify").addEventListener("click", function () {
      const v = $("#clarify-input").value.trim();
      if (!v) { showError("请先输入澄清答案再提交。"); return; }
      doResume(v, this);
    });
    $("#clarify-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) $("#btn-clarify").click();
    });
    return;
  }

  if (it.type === "confirmation") {
    area.innerHTML = confirmationHTML(it);
    bindConfirmation(it);
    return;
  }

  if (it.type === "validation_error") {
    const errs = (it.errors || []).map(function (e) { return "<li>" + esc(e) + "</li>"; }).join("");
    area.innerHTML =
      '<div class="interrupt-panel panel-error">' +
      '<div class="panel-head"><span class="panel-tag tag-error">校验未通过</span>请修正以下问题</div>' +
      '<ul class="error-list">' + errs + "</ul>" +
      '<textarea id="fix-input" class="input textarea" rows="2" placeholder="输入修正内容，例如：11月20日，主讲人：张三、李四"></textarea>' +
      '<div class="btn-row"><button id="btn-fix" class="btn btn-primary" type="button">提交修正</button></div>' +
      "</div>";
    $("#btn-fix").addEventListener("click", function () {
      const v = $("#fix-input").value.trim();
      if (!v) { showError("请先输入修正内容再提交。"); return; }
      doResume(v, this);
    });
    return;
  }

  area.innerHTML = '<p class="placeholder">未知中断类型：' + esc(it.type) + "</p>";
}

function confirmationHTML(it) {
  const draft = it.draft || {};
  const rows = Object.keys(DRAFT_LABELS).map(function (k) {
    return "<tr><th>" + esc(DRAFT_LABELS[k]) + "</th><td>" + esc(fmtVal(draft[k])) + "</td></tr>";
  }).join("");
  return '<div class="interrupt-panel panel-confirm">' +
    '<div class="panel-head"><span class="panel-tag tag-confirm">待确认</span>请核对活动草稿，确认后才会真正创建</div>' +
    '<table class="table draft-table"><tbody>' + rows + "</tbody></table>" +
    '<div class="btn-row">' +
    '<button id="btn-confirm" class="btn btn-primary" type="button">确认创建</button>' +
    '<button id="btn-cancel" class="btn btn-ghost" type="button">取消</button>' +
    "</div>" +
    '<p class="hint">确认将向后端提交一次性凭证（token），凭证用后即失效。</p>' +
    "</div>";
}

function bindConfirmation(it) {
  $("#btn-confirm").addEventListener("click", function () {
    doResume(it.token, this);
  });
  $("#btn-cancel").addEventListener("click", function () {
    /* 取消只是本地收起面板，不调用后端；任务仍在 Checkpoint 中 */
    $("#interrupt-area").innerHTML =
      '<div class="interrupt-panel">' +
      '<p class="placeholder">已取消本次确认。任务仍保留在后端 Checkpoint 中，可随时重新查看草稿，或点「重置」开始新任务。</p>' +
      '<div class="btn-row"><button id="btn-show-draft" class="btn btn-ghost" type="button">重新显示草稿</button></div>' +
      "</div>";
    $("#btn-show-draft").addEventListener("click", function () {
      $("#interrupt-area").innerHTML = confirmationHTML(it);
      bindConfirmation(it);
    });
  });
}

/* ---- 状态区 ---- */

function renderStatus(data) {
  const box = $("#wf-status");
  $("#task-id").textContent = (data && data.task_id) || "—";

  if (!data) {
    box.innerHTML = '<p class="placeholder">运行后这里会显示已抽取的槽位（slots）、缺项、澄清轮次等信息。</p>';
    return;
  }
  const st = data.state || {};
  const slots = st.slots || {};
  const keys = Object.keys(slots);

  let html = "";
  if (data.done && st.activity_id) {
    html += '<div class="success-card success-mini">' +
      '<div class="success-title">✓ 创建成功</div>' +
      '<p class="kv"><span class="kv-key">activity_id</span><code class="mono">' + esc(st.activity_id) + "</code></p>" +
      "</div>";
  }
  html += '<p class="kv"><span class="kv-key">状态</span><span>' +
    (isFailed(data) ? '<span class="chip chip-fail">failed</span>' : esc(st.status || (data.done ? "done" : "进行中"))) +
    "</span></p>";
  html += '<p class="kv"><span class="kv-key">澄清轮次</span><span>' + esc(st.clarify_rounds || 0) + "</span></p>";

  const missing = st.missing || [];
  html += '<p class="kv"><span class="kv-key">缺项</span><span>' +
    (missing.length
      ? missing.map(function (m) { return '<span class="chip chip-warn">' + esc(SLOT_LABELS[m] || m) + "</span>"; }).join(" ")
      : '<span class="chip chip-ok">无</span>') +
    "</span></p>";

  if (keys.length) {
    html += '<table class="table table-compact"><thead><tr><th>槽位</th><th>值</th></tr></thead><tbody>' +
      keys.map(function (k) {
        return "<tr><th>" + esc(SLOT_LABELS[k] || k) + '</th><td class="mono-small">' + esc(fmtVal(slots[k])) + "</td></tr>";
      }).join("") + "</tbody></table>";
  } else {
    html += '<p class="placeholder">暂无槽位。</p>';
  }
  box.innerHTML = html;
}

function renderWorkflow(data) {
  wfData = data;
  renderGraph(data);
  renderInterrupt(data);
  renderStatus(data);
}

/* ---- 工作流动作 ---- */

async function doStart() {
  if (wfBusy) return;
  const text = $("#wf-text").value.trim();
  if (!text) { showError("请先输入活动需求。"); return; }
  hideError();
  wfBusy = true;
  setBusy($("#btn-start"), true);
  $("#btn-reset").disabled = true;
  try {
    const data = await postJSON("/api/workflow/start", { user: $("#wf-user").value, text: text, model: currentModel() });
    renderWorkflow(data);
  } catch (e) {
    showError(e.message);
  } finally {
    wfBusy = false;
    setBusy($("#btn-start"), false);
    $("#btn-reset").disabled = false;
  }
}

async function doResume(value, btn) {
  if (wfBusy || !wfData || !wfData.task_id) return;
  hideError();
  wfBusy = true;
  setBusy(btn, true);
  try {
    const data = await postJSON("/api/workflow/resume", {
      task_id: wfData.task_id, user: $("#wf-user").value, value: value, model: currentModel(),
    });
    renderWorkflow(data);
  } catch (e) {
    showError(e.message);   /* 保留已有内容，仅恢复按钮 */
    setBusy(btn, false);
  } finally {
    wfBusy = false;
    if (btn && btn.isConnected && btn.disabled) setBusy(btn, false);
  }
}

async function doRestore() {
  if (wfBusy) return;
  const id = $("#restore-id").value.trim();
  if (!id) { showError("请输入要恢复的任务ID。"); return; }
  hideError();
  wfBusy = true;
  setBusy($("#btn-restore"), true);
  try {
    const data = await api("/api/workflow/status?task_id=" + encodeURIComponent(id) +
      "&user=" + encodeURIComponent($("#wf-user").value) + "&model=" + encodeURIComponent(currentModel()));
    renderWorkflow(data);
  } catch (e) {
    showError(e.message);
  } finally {
    wfBusy = false;
    setBusy($("#btn-restore"), false);
  }
}

function doReset() {
  if (wfBusy) return;
  hideError();
  wfData = null;
  $("#restore-id").value = "";
  renderWorkflow(null);
}

$("#btn-start").addEventListener("click", doStart);
$("#btn-reset").addEventListener("click", doReset);
$("#btn-restore").addEventListener("click", doRestore);
$("#wf-text").addEventListener("keydown", function (e) {
  if (e.key === "Enter") doStart();
});
$("#restore-id").addEventListener("keydown", function (e) {
  if (e.key === "Enter") doRestore();
});
$("#error-close").addEventListener("click", hideError);

/* ============================================================
   Tab 2：知识问答（RAG）
   ============================================================ */

let ragBusy = false;

async function doAsk() {
  if (ragBusy) return;
  const query = $("#rag-query").value.trim();
  if (!query) { showError("请先输入问题。"); return; }
  hideError();
  ragBusy = true;
  setBusy($("#btn-ask"), true);
  try {
    const data = await postJSON("/api/rag", { user: $("#rag-user").value, query: query, model: currentModel() });
    renderRag(data);
  } catch (e) {
    showError(e.message);
  } finally {
    ragBusy = false;
    setBusy($("#btn-ask"), false);
  }
}

function renderRag(data) {
  const box = $("#rag-result");
  const citations = data.citations || [];
  const chunks = data.chunks || [];
  const refused = citations.length === 0 && String(data.answer || "").indexOf("无法确认") !== -1;

  let html = '<div class="card">' +
    '<h2 class="card-title">回答 <span class="card-sub">用户 ' + esc($("#rag-user").value) +
    " · 租户 " + esc(data.user_tenant || "?") + "</span></h2>";

  if (refused) {
    html += '<div class="refusal-card"><div class="refusal-title">⚠ 无依据拒答</div>' +
      "<p>" + esc(data.answer) + "</p>" +
      '<p class="hint">当前用户的租户内没有可支撑该问题的知识片段，Agent 选择拒答而不是编造。可切换 u3（租户 t2）再试。</p></div>';
  } else {
    html += '<p class="rag-answer">' + esc(data.answer) + "</p>";
  }

  if (citations.length) {
    html += '<div class="cite-row"><span class="cite-label">引用：</span>' +
      citations.map(function (c) { return '<span class="badge badge-cite">' + esc(c) + "</span>"; }).join("") +
      "</div>";
  }
  html += "</div>";

  if (chunks.length) {
    html += '<div class="chunk-list">' + chunks.map(function (ch) {
      return '<div class="card chunk-card">' +
        '<div class="chunk-head"><span class="chunk-title">' + esc(ch.doc_title) + " · " + esc(ch.section) + "</span>" +
        '<span class="badge badge-tenant">' + esc(ch.tenant) + "</span></div>" +
        '<p class="chunk-id mono">' + esc(ch.chunk_id) + "</p>" +
        '<p class="chunk-text">' + esc(ch.text) + "</p>" +
        "</div>";
    }).join("") + "</div>";
  } else if (!refused) {
    html += '<div class="card"><p class="placeholder">未检索到知识片段。</p></div>';
  }

  box.innerHTML = html;
}

$("#btn-ask").addEventListener("click", doAsk);
$("#rag-query").addEventListener("keydown", function (e) {
  if (e.key === "Enter") doAsk();
});

/* ============================================================
   Tab 3：评测与安全
   ============================================================ */

async function loadEvalAndSecurity() {
  /* 两个接口独立加载，互不阻塞 */
  api("/api/eval").then(renderEval).catch(function (e) {
    $("#eval-area").innerHTML = '<p class="error-text">评测加载失败：' + esc(e.message) + "</p>";
  });
  api("/api/security").then(renderSecurity).catch(function (e) {
    $("#security-area").innerHTML = '<p class="error-text">安全测试加载失败：' + esc(e.message) + "</p>";
  });
}

function pct(v) { return (Number(v) * 100).toFixed(1) + "%"; }

function renderEval(data) {
  const metrics = data.metrics || {};
  const thresholds = data.thresholds || {};
  const rows = Object.keys(metrics).map(function (name) {
    const actual = Number(metrics[name]);
    const th = Number(thresholds[name]);
    const pass = actual >= th;
    return "<tr><th>" + esc(name) + "</th><td>" + pct(actual) + "</td><td>" + pct(th) + "</td>" +
      '<td class="' + (pass ? "pass" : "fail") + '">' + (pass ? "✅ 达标" : "❌ 未达标") + "</td></tr>";
  }).join("");

  $("#eval-area").innerHTML =
    '<table class="table"><thead><tr><th>指标</th><th>实测</th><th>门槛</th><th>结果</th></tr></thead>' +
    "<tbody>" + rows + "</tbody></table>";

  const details = data.details || [];
  if (details.length) {
    const d = $("#eval-details");
    d.hidden = false;
    $("#eval-details-summary").textContent = "用例明细（共 " + (data.total || details.length) + " 条，点击展开）";
    $("#eval-details-body").innerHTML =
      '<table class="table table-compact"><thead><tr><th>ID</th><th>类别</th><th>结果</th></tr></thead><tbody>' +
      details.map(function (c) {
        return "<tr><td class='mono-small'>" + esc(c.id) + "</td><td>" + esc(c.category) + "</td>" +
          '<td class="' + (c.ok ? "pass" : "fail") + '">' + (c.ok ? "✓" : "✗") + "</td></tr>";
      }).join("") + "</tbody></table>";
  }
}

function renderSecurity(data) {
  const tests = data.tests || [];
  const passed = tests.filter(function (t) { return t.passed; }).length;
  const allPass = passed === tests.length && tests.length > 0;

  let html = '<div class="security-summary ' + (allPass ? "sum-ok" : "sum-bad") + '">' +
    "<b>" + passed + "/" + tests.length + " 通过</b>" +
    (allPass ? " · 全部安全测试通过" : " · 存在未通过项") + "</div>";
  html += '<ul class="security-list">' + tests.map(function (t) {
    return '<li class="' + (t.passed ? "sec-pass" : "sec-fail") + '">' +
      '<span class="sec-mark">' + (t.passed ? "✓" : "✗") + "</span>" + esc(t.name) + "</li>";
  }).join("") + "</ul>";
  $("#security-area").innerHTML = html;
}

/* ------------------------------------------------------------ 启动 */

renderGraph(null);
init();