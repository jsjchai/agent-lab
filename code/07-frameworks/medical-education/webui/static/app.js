/* ==========================================================================
   医疗教学 Agent · 可视化
   原生 JS，无任何外部依赖。后端接口：
     GET /api/health
     GET /api/run?example=langgraph|crewai&topic=...&model=...  (text/event-stream)
   ========================================================================== */
(function () {
  'use strict';

  /* ------------------------------------------------------------------ 常量 */
  var DEFAULT_MODELS = ['mock', 'qwen2.5:7b', 'qwen3:8b'];
  var DEFAULT_TOPICS = {
    langgraph: '社区获得性肺炎（CAP）',
    crewai: '急性胸痛（STEMI 鉴别）'
  };
  var EXAMPLES = ['langgraph', 'crewai'];
  var NODES = ['plan', 'draft_case', 'design_questions', 'review', 'revise', 'finalize'];
  var STATE_KEYS = ['objectives', 'case_text', 'questions'];
  var TASKS = ['design', 'clinic', 'assess', 'summary'];
  var TASK_LABELS = { design: '教学设计', clinic: '临床要点', assess: '考核评价', summary: '汇总整合' };
  var FOLD_PLACEHOLDERS = {
    objectives: 'plan 节点会先生成教学目标。',
    case_text: 'draft_case 节点生成教学病例；revise 会覆盖为修订版。',
    questions: 'design_questions 节点生成分层问题。'
  };
  var IDLE_REVIEW = '点击「运行」，看看评审为什么把教案打回。';
  var IDLE_LG_FINAL = '运行结束后，这里会显示完整教案（Markdown 渲染）。';
  var IDLE_CREW_FINAL = '点击「运行」，看看四位角色如何接力产出一份完整教案。';

  /* ------------------------------------------------------------------ 状态 */
  var state = {
    example: 'langgraph',
    runExample: 'langgraph',
    model: 'mock',
    topics: { langgraph: DEFAULT_TOPICS.langgraph, crewai: DEFAULT_TOPICS.crewai },
    running: false,
    finished: false,
    source: null,
    startedAt: 0,
    timerId: null,
    reviewCount: 0
  };

  /* -------------------------------------------------------------------- DOM */
  var el = {
    statusDot: document.getElementById('statusDot'),
    statusText: document.getElementById('statusText'),
    timer: document.getElementById('timer'),
    errorBar: document.getElementById('errorBar'),
    errorText: document.getElementById('errorText'),
    errorClose: document.getElementById('errorClose'),
    tabs: Array.prototype.slice.call(document.querySelectorAll('.tab')),
    viewLg: document.getElementById('view-langgraph'),
    viewCrew: document.getElementById('view-crewai'),
    flow: document.getElementById('flow'),
    reviewList: document.getElementById('reviewList'),
    lgFinal: document.getElementById('lgFinal'),
    crewFinal: document.getElementById('crewFinal'),
    crewList: document.getElementById('crewList'),
    modelSelect: document.getElementById('modelSelect'),
    topicInput: document.getElementById('topicInput'),
    runBtn: document.getElementById('runBtn'),
    resetBtn: document.getElementById('resetBtn'),
    ticker: document.getElementById('ticker'),
    logText: document.getElementById('logText')
  };

  /* ---- markdown-renderer:start ---- */
  /* 迷你 Markdown 渲染器（约 120 行）：先整体转义，再生成标签，避免 XSS。
     支持：# ~ ###### 标题、**粗体**、`行内代码`、无序/有序列表、
     ``` 代码块、> 引用、| 管道表格（含分隔行）、空行分段、--- 分隔线。 */
  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderInline(text) {
    var out = escapeHtml(text);
    out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    return out;
  }

  /* 中文排版：段内折行直接拼接，英文单词之间保留一个空格。 */
  function joinTextLines(lines) {
    var out = '';
    for (var i = 0; i < lines.length; i += 1) {
      var line = lines[i];
      if (!out) { out = line; continue; }
      var prev = out.charAt(out.length - 1);
      var next = line.charAt(0);
      var asciiPrev = /[A-Za-z0-9)\].,;:!?'"]/.test(prev);
      var asciiNext = /[A-Za-z0-9([]/.test(next);
      out += (asciiPrev && asciiNext) ? ' ' + line : line;
    }
    return out;
  }

  var TABLE_SEPARATOR = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/;

  function isTableSeparator(line) {
    return TABLE_SEPARATOR.test(line);
  }

  function splitTableRow(line) {
    var value = line.trim();
    if (value.charAt(0) === '|') { value = value.slice(1); }
    if (value.charAt(value.length - 1) === '|') { value = value.slice(0, -1); }
    return value.split('|').map(function (cell) { return cell.trim(); });
  }

  function listKind(line) {
    if (/^\s*[-*+]\s+/.test(line)) { return 'ul'; }
    if (/^\s*\d+[.)]\s+/.test(line)) { return 'ol'; }
    return '';
  }

  function isBlockStart(lines, index) {
    var trimmed = lines[index].trim();
    if (!trimmed) { return true; }
    if (/^```/.test(trimmed)) { return true; }
    if (/^#{1,6}\s+/.test(trimmed)) { return true; }
    if (trimmed.charAt(0) === '>') { return true; }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) { return true; }
    if (listKind(trimmed)) { return true; }
    if (trimmed.indexOf('|') !== -1 && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      return true;
    }
    return false;
  }

  function renderTable(headers, rows) {
    var head = '<thead><tr>' + headers.map(function (cell) {
      return '<th>' + renderInline(cell) + '</th>';
    }).join('') + '</tr></thead>';
    var body = rows.map(function (row) {
      var cells = [];
      for (var c = 0; c < headers.length; c += 1) {
        cells.push('<td>' + renderInline(row[c] || '') + '</td>');
      }
      return '<tr>' + cells.join('') + '</tr>';
    }).join('');
    return '<div class="table-wrap"><table>' + head + '<tbody>' + body + '</tbody></table></div>';
  }

  function renderMarkdown(source) {
    var lines = String(source == null ? '' : source).replace(/\r\n?/g, '\n').split('\n');
    var html = [];
    var i = 0;

    while (i < lines.length) {
      var line = lines[i];
      var trimmed = line.trim();

      if (!trimmed) { i += 1; continue; }

      /* 代码块 */
      if (/^```/.test(trimmed)) {
        var codeLines = [];
        i += 1;
        while (i < lines.length && !/^```\s*$/.test(lines[i].trim())) {
          codeLines.push(lines[i]);
          i += 1;
        }
        if (i < lines.length) { i += 1; }
        html.push('<pre><code>' + escapeHtml(codeLines.join('\n')) + '</code></pre>');
        continue;
      }

      /* 表格：当前行含 |，且下一行是 |---|---| 分隔行 */
      if (trimmed.indexOf('|') !== -1 && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
        var headers = splitTableRow(line);
        i += 2;
        var rows = [];
        while (i < lines.length && lines[i].trim() && lines[i].indexOf('|') !== -1) {
          rows.push(splitTableRow(lines[i]));
          i += 1;
        }
        html.push(renderTable(headers, rows));
        continue;
      }

      /* 标题 */
      var heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        var level = heading[1].length;
        html.push('<h' + level + '>' + renderInline(heading[2]) + '</h' + level + '>');
        i += 1;
        continue;
      }

      /* 分隔线 */
      if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
        html.push('<hr>');
        i += 1;
        continue;
      }

      /* 引用 */
      if (trimmed.charAt(0) === '>') {
        var quoteLines = [];
        while (i < lines.length && lines[i].trim().charAt(0) === '>') {
          quoteLines.push(lines[i].trim().replace(/^>\s?/, ''));
          i += 1;
        }
        /* 引用内的换行保留为 <br>：> 行通常是元信息，拼成一段会粘在一起 */
        html.push('<blockquote><p>' + quoteLines.map(renderInline).join('<br>') + '</p></blockquote>');
        continue;
      }

      /* 无序 / 有序列表（支持缩进续行） */
      var kind = listKind(trimmed);
      if (kind) {
        var items = [];
        var itemRe = kind === 'ol' ? /^\s*\d+[.)]\s+(.*)$/ : /^\s*[-*+]\s+(.*)$/;
        while (i < lines.length) {
          var current = lines[i].trim();
          if (itemRe.test(current)) {
            items.push(current.replace(itemRe, '$1'));
            i += 1;
            continue;
          }
          if (items.length && /^\s{2,}\S/.test(lines[i]) && !isBlockStart(lines, i)) {
            items[items.length - 1] += ' ' + current;
            i += 1;
            continue;
          }
          if (!current) {
            var lookahead = i + 1;
            while (lookahead < lines.length && !lines[lookahead].trim()) { lookahead += 1; }
            var continues = lookahead < lines.length && (kind === 'ol'
              ? /^\d+[.)]\s+/.test(lines[lookahead].trim())
              : /^[-*+]\s+/.test(lines[lookahead].trim()));
            if (continues) { i = lookahead; continue; }
          }
          break;
        }
        html.push('<' + kind + '>' + items.map(function (item) {
          return '<li>' + renderInline(item) + '</li>';
        }).join('') + '</' + kind + '>');
        continue;
      }

      /* 普通段落 */
      var paragraph = [];
      while (i < lines.length) {
        var paraLine = lines[i].trim();
        if (!paraLine) { break; }
        if (paragraph.length && isBlockStart(lines, i)) { break; }
        paragraph.push(paraLine);
        i += 1;
      }
      if (!paragraph.length) { paragraph.push(trimmed); i += 1; }
      html.push('<p>' + renderInline(joinTextLines(paragraph)) + '</p>');
    }

    return html.join('\n');
  }
  /* ---- markdown-renderer:end ---- */

  /* -------------------------------------------------------------- 通用 UI */
  function setStatus(kind, text) {
    el.statusDot.className = 'status-dot ' + kind;
    el.statusText.textContent = text;
  }

  function log(text) {
    if (!text) { return; }
    el.ticker.hidden = false;
    el.logText.textContent = text;
  }

  function showError(message) {
    el.errorText.textContent = message || '运行出错，请重试。';
    el.errorBar.hidden = false;
  }

  function hideError() {
    el.errorBar.hidden = true;
    el.errorText.textContent = '';
  }

  function pad2(value) {
    return value < 10 ? '0' + value : String(value);
  }

  function formatClock(ms) {
    var total = Math.max(0, ms) / 1000;
    var minutes = Math.floor(total / 60);
    var seconds = Math.floor(total % 60);
    var tenth = Math.floor((total * 10) % 10);
    return pad2(minutes) + ':' + pad2(seconds) + '.' + tenth;
  }

  function tick() {
    el.timer.textContent = formatClock(Date.now() - state.startedAt);
  }

  function startTimer() {
    stopTimer();
    state.startedAt = Date.now();
    el.timer.textContent = '00:00.0';
    state.timerId = window.setInterval(tick, 100);
  }

  function stopTimer() {
    if (state.timerId) {
      window.clearInterval(state.timerId);
      state.timerId = null;
    }
  }

  function setNodeState(name, next) {
    var node = el.flow.querySelector('[data-node="' + name + '"]');
    if (!node) { return; }
    node.classList.remove('pending', 'running', 'done');
    node.classList.add(next);
  }

  function setFold(key, value) {
    var body = document.querySelector('[data-body="' + key + '"]');
    var fold = document.querySelector('.fold[data-key="' + key + '"]');
    if (!body || !fold) { return; }
    var status = fold.querySelector('.fold-status');
    var wasReady = fold.classList.contains('has-content');
    var text = typeof value === 'string' ? value : '';
    if (text.trim()) {
      body.innerHTML = renderMarkdown(text);
    } else {
      body.innerHTML = '<p class="empty-hint">该节点暂未返回内容。</p>';
    }
    fold.classList.add('has-content');
    fold.open = true;
    status.textContent = wasReady ? '已更新' : '已生成';
    status.className = 'fold-status ready';
  }

  function addReview(data) {
    var existingHint = el.reviewList.querySelector('.empty-hint');
    if (existingHint) { el.reviewList.innerHTML = ''; }

    state.reviewCount += 1;
    var round = Number(data.round);
    if (!isFinite(round) || round < 1) { round = state.reviewCount; }
    var score = Number(data.score);
    if (!isFinite(score)) { score = 0; }
    var passed = data.verdict === 'pass';
    var issues = Array.isArray(data.issues) ? data.issues.filter(function (issue) {
      return typeof issue === 'string' && issue.trim();
    }) : [];

    var card = document.createElement('article');
    card.className = 'review-card ' + (passed ? 'pass' : 'revise');
    var html = '';
    html += '<div class="review-top">';
    html += '<div class="score-block"><span class="score">' + Math.round(score) + '</span>';
    html += '<span class="score-unit">/ 100</span></div>';
    html += '<div class="review-meta"><span class="badge ' + (passed ? 'pass' : 'revise') + '">';
    html += (passed ? '通过' : '需修订') + '</span>';
    html += '<span class="round">第 ' + round + ' 轮评审</span></div></div>';
    html += '<div class="review-issues"><h4>评审意见</h4>';
    if (issues.length) {
      html += '<ul>' + issues.map(function (issue) {
        return '<li>' + escapeHtml(issue) + '</li>';
      }).join('') + '</ul>';
    } else {
      html += '<p class="no-issues">未列出必须修改的问题。</p>';
    }
    html += '</div>';
    card.innerHTML = html;
    el.reviewList.appendChild(card);
  }

  function refreshClip(card) {
    if (!card || card.classList.contains('expanded')) { return; }
    var output = card.querySelector('[data-output]');
    var button = card.querySelector('[data-expand]');
    if (!output || !button) { return; }
    var clipped = output.scrollHeight > output.clientHeight + 1;
    card.classList.toggle('is-clipped', clipped);
    button.hidden = !clipped;
    if (!clipped) {
      card.classList.remove('expanded');
      button.textContent = '展开全文';
    }
  }

  function setTaskState(task, next, output) {
    var card = el.crewList.querySelector('.agent-card[data-task="' + task + '"]');
    if (!card) { return; }
    var pill = card.querySelector('[data-state]');
    var outputBox = card.querySelector('[data-output]');
    var expand = card.querySelector('[data-expand]');

    if (next === 'running') {
      card.classList.remove('is-done', 'is-clipped', 'expanded');
      card.classList.add('is-running');
      pill.className = 'agent-state running';
      pill.innerHTML = '<i class="state-dot"></i>进行中';
      outputBox.innerHTML = '<p class="empty-hint">正在生成…</p>';
      expand.hidden = true;
      expand.textContent = '展开全文';
      return;
    }

    card.classList.remove('is-running');
    card.classList.add('is-done');
    pill.className = 'agent-state done';
    pill.innerHTML = '<i class="state-dot"></i>完成';
    var text = typeof output === 'string' && output.trim()
      ? output.trim()
      : '（该任务未推送文本产出，请见右侧完整教案。）';
    // 角色卡里也渲染 Markdown：直接放原文会出现满屏 | 和 **，和右侧教案观感割裂
    outputBox.innerHTML = renderMarkdown(text);
    expand.hidden = true;
    expand.textContent = '展开全文';
    window.requestAnimationFrame(function () { refreshClip(card); });
  }

  function refreshVisibleClips() {
    var cards = el.crewList.querySelectorAll('.agent-card.is-done');
    Array.prototype.forEach.call(cards, function (card) {
      window.requestAnimationFrame(function () { refreshClip(card); });
    });
  }

  function setFinal(example, markdown) {
    var target = example === 'langgraph' ? el.lgFinal : el.crewFinal;
    if (!target) { return; }
    if (typeof markdown === 'string' && markdown.trim()) {
      target.innerHTML = renderMarkdown(markdown);
    } else {
      target.innerHTML = '<p class="empty-hint">运行结束，但没有收到最终 Markdown 内容。</p>';
    }
    target.scrollTop = 0;
  }

  /* ------------------------------------------------------------ 视图与重置 */
  function switchView(example) {
    if (EXAMPLES.indexOf(example) === -1) { return; }
    state.example = example;
    el.tabs.forEach(function (tab) {
      var active = tab.getAttribute('data-example') === example;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    el.viewLg.classList.toggle('hidden', example !== 'langgraph');
    el.viewCrew.classList.toggle('hidden', example !== 'crewai');
    el.topicInput.value = state.topics[example] || DEFAULT_TOPICS[example];
    if (example === 'crewai') { refreshVisibleClips(); }
  }

  function resetLanggraphView() {
    NODES.forEach(function (name) { setNodeState(name, 'pending'); });
    el.reviewList.innerHTML = '<p class="empty-hint">' + IDLE_REVIEW + '</p>';
    STATE_KEYS.forEach(function (key) {
      var body = document.querySelector('[data-body="' + key + '"]');
      var fold = document.querySelector('.fold[data-key="' + key + '"]');
      if (!body || !fold) { return; }
      var status = fold.querySelector('.fold-status');
      fold.classList.remove('has-content');
      fold.open = key === 'objectives';
      status.className = 'fold-status';
      status.textContent = '待生成';
      body.innerHTML = '<p class="empty-hint">' + FOLD_PLACEHOLDERS[key] + '</p>';
    });
    el.lgFinal.innerHTML = '<p class="empty-hint">' + IDLE_LG_FINAL + '</p>';
  }

  function resetCrewView() {
    TASKS.forEach(function (task) {
      var card = el.crewList.querySelector('.agent-card[data-task="' + task + '"]');
      if (!card) { return; }
      card.classList.remove('is-running', 'is-done', 'is-clipped', 'expanded');
      var pill = card.querySelector('[data-state]');
      pill.className = 'agent-state waiting';
      pill.innerHTML = '<i class="state-dot"></i>等待';
      card.querySelector('[data-output]').innerHTML = '<p class="empty-hint">等待任务开始…</p>';
      var expand = card.querySelector('[data-expand]');
      expand.hidden = true;
      expand.textContent = '展开全文';
    });
    el.crewFinal.innerHTML = '<p class="empty-hint">' + IDLE_CREW_FINAL + '</p>';
  }

  function resetCurrentView() {
    if (state.example === 'langgraph') {
      resetLanggraphView();
    } else {
      resetCrewView();
    }
  }

  /* ---------------------------------------------------------------- 运行控制 */
  function closeStream() {
    if (state.source) {
      try { state.source.close(); } catch (err) { /* ignore */ }
      state.source = null;
    }
  }

  function startRun() {
    if (state.running) { return; }
    var example = state.example;
    var topic = el.topicInput.value.trim() || DEFAULT_TOPICS[example];
    state.topics[example] = topic;
    state.model = el.modelSelect.value || 'mock';
    state.runExample = example;
    state.reviewCount = 0;
    state.finished = false;
    state.running = true;

    hideError();
    resetCurrentView();
    setStatus('running', '运行中');
    el.runBtn.disabled = true;
    el.runBtn.textContent = '运行中…';
    startTimer();
    log('开始运行：' + (example === 'langgraph' ? 'LangGraph · 评审回环' : 'CrewAI · 多角色协作')
      + ' ｜ ' + topic + ' ｜ ' + state.model);

    var url = '/api/run?example=' + encodeURIComponent(example)
      + '&topic=' + encodeURIComponent(topic)
      + '&model=' + encodeURIComponent(state.model);

    try {
      var source = new EventSource(url);
      state.source = source;
      source.onmessage = function (event) { handleRawMessage(event.data); };
      source.onerror = function () {
        if (!state.running || state.finished) { return; }
        failRun('与后端连接中断。请确认 webui/server.py 已启动（默认 127.0.0.1:7861），然后重试。');
      };
    } catch (err) {
      failRun('无法创建 SSE 连接：' + (err && err.message ? err.message : '未知错误'));
    }
  }

  function handleRawMessage(raw) {
    if (typeof raw !== 'string' || !raw.trim()) { return; }
    var data;
    try {
      data = JSON.parse(raw);
    } catch (err) {
      return;
    }
    if (!data || typeof data !== 'object') { return; }
    handleEvent(data);
  }

  function handleEvent(data) {
    switch (data.type) {
      case 'start':
        if (typeof data.example === 'string' && EXAMPLES.indexOf(data.example) !== -1) {
          state.runExample = data.example;
          if (data.example !== state.example) { switchView(data.example); }
        }
        log('开始：' + (data.topic || '') + (data.model ? ' ｜ 模型 ' + data.model : ''));
        break;

      case 'node':
        if (typeof data.node === 'string' && NODES.indexOf(data.node) !== -1) {
          setNodeState(data.node, data.phase === 'start' ? 'running' : 'done');
          log('节点 ' + data.node + (data.phase === 'start' ? ' 开始' : ' 完成'));
        }
        break;

      case 'state':
        if (STATE_KEYS.indexOf(data.key) !== -1) {
          setFold(data.key, data.value);
          log('收到节点产出：' + data.key);
        }
        break;

      case 'review':
        addReview(data);
        log('评审第 ' + (Number(data.round) || state.reviewCount) + ' 轮：'
          + data.score + ' 分（' + (data.verdict === 'pass' ? '通过' : '需修订') + '）');
        break;

      case 'task':
        if (TASKS.indexOf(data.task) !== -1) {
          if (data.phase === 'start') {
            setTaskState(data.task, 'running');
            log('任务开始：' + TASK_LABELS[data.task]);
          } else {
            setTaskState(data.task, 'done', data.output);
            log('任务完成：' + TASK_LABELS[data.task]);
          }
        }
        break;

      case 'log':
        if (typeof data.text === 'string') { log(data.text); }
        break;

      case 'done':
        finishRun(data);
        break;

      case 'error':
        failRun(typeof data.message === 'string' && data.message
          ? data.message
          : '运行出错，请查看后端日志。');
        break;

      default:
        break;
    }
  }

  function finishRun(data) {
    if (state.finished) { return; }
    state.finished = true;
    state.running = false;
    closeStream();
    stopTimer();

    var example = state.runExample;
    var seconds = parseFloat(data.elapsed);
    var measured = (Date.now() - state.startedAt) / 1000;
    if (!isFinite(seconds) || seconds < measured) {
      /* mock 子进程极快，后端 elapsed 可能为 0；取较大值，避免总耗时显示 0.0s。 */
      seconds = measured;
    }
    el.timer.textContent = seconds.toFixed(1) + 's';

    if (example === 'langgraph') {
      NODES.forEach(function (name) { setNodeState(name, 'done'); });
      setFinal('langgraph', data.markdown);
    } else {
      TASKS.forEach(function (task) {
        var card = el.crewList.querySelector('.agent-card[data-task="' + task + '"]');
        if (card && !card.classList.contains('is-done')) {
          setTaskState(task, 'done', '（该任务未推送文本产出，请见右侧完整教案。）');
        }
      });
      setFinal('crewai', data.markdown);
    }

    setStatus('done', '完成');
    el.runBtn.disabled = false;
    el.runBtn.textContent = '▶ 运行';
    log('运行完成，总耗时 ' + seconds.toFixed(1) + ' 秒');
  }

  function failRun(message) {
    if (state.finished) { return; }
    state.finished = true;
    state.running = false;
    closeStream();
    stopTimer();

    /* 保留已收到的内容，只把"执行中"回退为待执行，避免动画一直转。 */
    Array.prototype.forEach.call(el.flow.querySelectorAll('.flow-node.running'), function (node) {
      node.classList.remove('running');
      node.classList.add('pending');
    });
    Array.prototype.forEach.call(el.crewList.querySelectorAll('.agent-card.is-running'), function (card) {
      card.classList.remove('is-running');
      var pill = card.querySelector('[data-state]');
      pill.className = 'agent-state waiting';
      pill.innerHTML = '<i class="state-dot"></i>等待';
    });

    setStatus('error', '出错');
    el.runBtn.disabled = false;
    el.runBtn.textContent = '▶ 运行';
    showError(message);
    log('出错：' + message);
  }

  function handleReset() {
    if (state.running) {
      closeStream();
      state.running = false;
      state.finished = false;
      var target = state.runExample;
      if (target === 'langgraph') { resetLanggraphView(); } else { resetCrewView(); }
    } else {
      resetCurrentView();
    }
    stopTimer();
    el.timer.textContent = '00:00.0';
    el.runBtn.disabled = false;
    el.runBtn.textContent = '▶ 运行';
    setStatus('idle', '就绪');
    hideError();
    state.reviewCount = 0;
    el.ticker.hidden = true;
    el.logText.textContent = '';
  }

  /* ------------------------------------------------------------------ 模型 */
  function populateModels(models, selected) {
    el.modelSelect.innerHTML = '';
    models.forEach(function (model) {
      var option = document.createElement('option');
      option.value = model;
      option.textContent = model;
      el.modelSelect.appendChild(option);
    });
    var pick = models.indexOf(selected) !== -1 ? selected : models[0];
    el.modelSelect.value = pick;
    state.model = pick;
  }

  function initModels() {
    populateModels(DEFAULT_MODELS, 'mock');
    if (typeof window.fetch !== 'function') { return; }
    window.fetch('/api/health', { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) { throw new Error('health ' + response.status); }
        return response.json();
      })
      .then(function (data) {
        var models = Array.isArray(data && data.models) ? data.models.filter(function (model) {
          return typeof model === 'string' && model.trim();
        }) : [];
        if (!models.length) { models = DEFAULT_MODELS.slice(); }
        var def = data && typeof data.default === 'string' && models.indexOf(data.default) !== -1
          ? data.default
          : models[0];
        populateModels(models, def);
      })
      .catch(function () {
        log('未连接后端，已使用内置模型列表（mock / qwen2.5:7b / qwen3:8b）');
      });
  }

  /* ------------------------------------------------------------------ 事件 */
  function bindEvents() {
    el.tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        switchView(tab.getAttribute('data-example'));
      });
    });

    el.topicInput.addEventListener('input', function () {
      state.topics[state.example] = el.topicInput.value;
    });

    el.topicInput.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        startRun();
      }
    });

    el.runBtn.addEventListener('click', startRun);
    el.resetBtn.addEventListener('click', handleReset);
    el.errorClose.addEventListener('click', hideError);

    el.crewList.addEventListener('click', function (event) {
      var button = event.target.closest ? event.target.closest('[data-expand]') : null;
      if (!button) { return; }
      var card = button.closest('.agent-card');
      if (!card) { return; }
      var expanded = card.classList.toggle('expanded');
      button.textContent = expanded ? '收起' : '展开全文';
      if (!expanded) {
        window.requestAnimationFrame(function () { refreshClip(card); });
      }
    });
  }

  /* ------------------------------------------------------------------ 启动 */
  bindEvents();
  resetLanggraphView();
  resetCrewView();
  setStatus('idle', '就绪');
  initModels();
})();
