function storedValue(key, fallback = "") {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function storeValue(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // The review still works when a browser disables storage for file pages.
  }
}

const state = {
  status: "proposed",
  cursor: null,
  selectedText: null,
  config: null,
  loading: false,
  criteria: storedValue("yime-review-criteria", "standard"),
  affixAnalysis: null,
  affixPayload: null,
  familyDiscoveryModel: null,
  automaticScreening: null,
  lengthGroups: [],
};

const $ = (selector) => document.querySelector(selector);
const number = (value) => new Intl.NumberFormat("zh-CN").format(value || 0);
const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:8765" : "";
const LAUNCH_COMMAND =
  ".\\venv312\\Scripts\\python.exe tools\\review_unencoded_candidates.py";

const classLabels = {
  single_character: "单字",
  lexical_candidate: "词汇候选",
  fixed_expression: "固定表达",
  person_name: "人名",
  place_name: "地名",
  organization_name: "机构名",
  domain_term: "领域词",
  semi_fixed_construction: "半固定构式",
  productive_phrase: "能产短语",
  syntactic_fragment: "句法片段",
  noise: "噪声",
  context_dependent: "依赖语境",
  unknown: "未知材料",
};

const statusLabels = {
  proposed: "待审",
  approved: "已准入 / 已动态归类",
  rejected: "已拒绝",
  deferred: "暂缓",
};

const bccCategoryLabels = {
  modern_chinese: "现代汉语",
  news: "新闻",
  dialogue: "对话",
  literature: "文学",
  classical_chinese: "古汉语",
  multi_domain: "综合",
};

const affixSuggestionLabels = {
  dynamic_composition_candidate: "动态组合候选",
  proper_name_rule_candidate: "专名规则候选",
  domain_rule_candidate: "领域规则候选",
  frame_composition_candidate: "框式动态组合候选",
  short_form_exception: "两字组合例外",
  ambiguous_split: "存在多种拆分",
  reading_evidence_required: "至少一侧缺注音",
};

const tailSemanticLabels = {
  person_name: "人名",
  business_name: "商号 / 企业字号",
  product_name: "品名 / 商品名",
  currency_measurement: "货币计量",
  other_proper_name: "其他专名",
  fixed_lexical_item: "固定词 · 保留待编码",
  noise: "噪声 · 不予编码",
  uncertain: "无法判定 · 保留人工审查",
};

const coverageStatusLabels = {
  atomic_gated: "整体已注音",
  composition_covered: "递归组合覆盖",
  empty_optional: "可空槽位",
  short_form_exception: "两字例外",
  ambiguous_split: "多种拆分",
  reading_evidence_required: "缺少注音",
};

const automaticCategoryLabels = {
  auto_covered: "可安全自动归类",
  rule_conflict: "规则分类冲突",
  negative_example_excluded: "规则反例排除",
  short_form_exception: "两字组合例外",
  ambiguous_split: "拆分存在歧义",
  unclassified_composition: "组合可覆盖但缺规则",
  reading_evidence_required: "需要补充读音证据",
};

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (error) {
    throw new Error(
      window.location.protocol === "file:"
        ? `未连接到本地审查服务。请在仓库根目录运行：${LAUNCH_COMMAND}`
        : "本地审查服务暂不可用，请确认服务仍在运行。",
      { cause: error },
    );
  }
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : { error: `服务返回了非 JSON 响应（HTTP ${response.status}）` };
  if (!response.ok) throw new Error(payload.error || "请求失败");
  return payload;
}

function setConnection(connected, detail = "") {
  const panel = $("#connection-panel");
  panel.classList.toggle("connected", connected);
  panel.classList.toggle("disconnected", !connected);
  $("#connection-title").textContent = connected
    ? "已连接本地审查数据"
    : "尚未连接本地审查数据";
  $("#connection-detail").textContent = detail || (
    connected
      ? "候选覆盖库与统一来源库已就绪；判决只写 input_model.sqlite3。"
      : `请在仓库根目录运行：${LAUNCH_COMMAND}`
  );
}

function customCriteria() {
  return {
    name: $("#custom-criteria-name").value.trim(),
    goal: $("#custom-criteria-goal").value,
    rules: $("#custom-criteria-rules").value.trim(),
  };
}

function persistCriteria() {
  storeValue("yime-review-criteria", state.criteria);
  storeValue("yime-review-custom-criteria", JSON.stringify(customCriteria()));
}

function selectCriteria(value) {
  state.criteria = value;
  document.querySelectorAll(".criteria-tab").forEach((tab) => {
    const active = tab.dataset.criteria === value;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".criteria-content").forEach((panel) => {
    panel.hidden = panel.id !== `criteria-${value}`;
  });
  const labels = {
    standard: "国家 / 国际基本规范",
    academic: "学界语料标注准则",
    reviewer: $("#custom-criteria-name").value.trim() || "审查者自定标准",
  };
  $("#criteria-selection").textContent = `当前：${labels[value]}`;
  persistCriteria();
}

function restoreCustomCriteria() {
  try {
    const stored = JSON.parse(
      storedValue("yime-review-custom-criteria", "{}"),
    );
    if (stored.name) $("#custom-criteria-name").value = stored.name;
    if (["runtime", "evaluation", "discovery"].includes(stored.goal)) {
      $("#custom-criteria-goal").value = stored.goal;
    }
    if (stored.rules) $("#custom-criteria-rules").value = stored.rules;
  } catch {
    try {
      localStorage.removeItem("yime-review-custom-criteria");
    } catch {
      // Ignore unavailable storage.
    }
  }
}

async function loadSummary() {
  const summary = await api("/api/summary");
  state.lengthGroups = summary.length_groups || [];
  $("#metric-total").textContent = number(summary.unencoded_total);
  $("#metric-proposed").textContent = number(summary.status_counts.proposed);
  $("#metric-families").textContent = number(summary.rule_family_count);
  $("#metric-two-character-dynamic").textContent = number(
    summary.two_character_dynamic_reachability,
  );
  $("#metric-closed").textContent = number(
    summary.status_counts.rejected + summary.status_counts.deferred,
  );
  renderLengthFilter();
}

function renderLengthFilter() {
  const select = $("#length-filter");
  const selected = select.value;
  select.innerHTML = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "全部字数";
  select.append(all);
  state.lengthGroups.forEach((group) => {
    const option = document.createElement("option");
    option.value = String(group.text_length);
    option.textContent = `${group.label}（${number(group.count)}）`;
    select.append(option);
  });
  if ([...select.options].some((option) => option.value === selected)) {
    select.value = selected;
  }
}

function renderQueueItem(item) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "queue-item";
  if (state.selectedText === item.text) button.classList.add("active");
  button.dataset.text = item.text;

  const title = document.createElement("span");
  title.className = "queue-text";
  title.textContent = item.text;

  const frequency = document.createElement("span");
  frequency.className = "queue-frequency";
  frequency.textContent = item.bcc_frequency
    ? `BCC ${number(item.bcc_frequency)}`
    : "无 BCC 频次";

  const meta = document.createElement("span");
  meta.className = "queue-meta";
  meta.textContent =
    `${item.text_length_label}组 · ${classLabels[item.candidate_class] || item.candidate_class}`;

  const warning = document.createElement("span");
  warning.className = "queue-meta";
  if (item.has_source_rejection) {
    warning.classList.add("queue-warning");
    warning.textContent = "有来源拒绝记录";
  } else if (item.context_count) {
    warning.textContent = `${item.context_count} 条上下文`;
  } else {
    warning.textContent = "缺少上下文";
  }

  const bccCategories = document.createElement("span");
  bccCategories.className = "queue-meta queue-bcc-categories";
  const categoryLabels = (item.bcc_categories || []).map(
    (category) => bccCategoryLabels[category] || category,
  );
  bccCategories.textContent = categoryLabels.length
    ? `BCC 分类：${categoryLabels.join("、")}`
    : "BCC 分类：无";

  button.append(title, frequency, meta, warning, bccCategories);
  button.addEventListener("click", () => selectCandidate(item.text));
  return button;
}

async function loadQueue({ append = false } = {}) {
  if (state.loading) return;
  state.loading = true;
  const queue = $("#queue");
  if (!append) {
    queue.innerHTML = '<div class="queue-empty">正在读取审查队列…</div>';
    state.cursor = null;
  }
  const params = new URLSearchParams({
    status: state.status,
    query: $("#search-input").value.trim(),
    minimum_frequency: $("#frequency-filter").value,
    text_length: $("#length-filter").value,
    limit: "50",
  });
  if (append && state.cursor) params.set("cursor", state.cursor);

  try {
    const payload = await api(`/api/queue?${params}`);
    if (!append) queue.innerHTML = "";
    payload.items.forEach((item) => queue.append(renderQueueItem(item)));
    if (!queue.children.length) {
      queue.innerHTML = '<div class="queue-empty">当前筛选条件下没有待处理字串。</div>';
    }
    state.cursor = payload.next_cursor;
    $("#load-more").hidden = !state.cursor;
  } catch (error) {
    queue.innerHTML = `<div class="queue-empty">${error.message}</div>`;
  } finally {
    state.loading = false;
  }
}

function addBadge(text) {
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = text;
  $("#candidate-badges").append(badge);
}

function renderHistory(detail) {
  const target = $("#history-content");
  target.innerHTML = "";
  const rejections = detail.source.rejection_reasons || [];
  rejections.forEach((reason) => {
    const item = document.createElement("div");
    item.className = "history-item";
    item.innerHTML = "<strong>来源拒绝</strong><br>";
    item.append(document.createTextNode(reason));
    target.append(item);
  });
  detail.audit_events.forEach((event) => {
    const item = document.createElement("div");
    item.className = "history-item";
    const status = event.payload.decision_status || event.event_type;
    item.innerHTML = `<strong>${statusLabels[status] || status}</strong> · ${event.assessor}<br>`;
    item.append(document.createTextNode(
      `${event.payload.rationale || "无理由"} · ${new Date(event.created_at_utc).toLocaleString("zh-CN")}`,
    ));
    target.append(item);
  });
  if (!target.children.length) {
    target.innerHTML = '<div class="history-item">暂无来源拒绝或改判记录。</div>';
  }
}

async function selectCandidate(text) {
  state.selectedText = text;
  document.querySelectorAll(".queue-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.text === text);
  });
  $("#empty-state").hidden = true;
  $("#candidate-detail").hidden = false;
  $("#candidate-text").textContent = "读取中…";
  $("#action-message").textContent = "";

  try {
    const detail = await api(`/api/candidate?text=${encodeURIComponent(text)}`);
    $("#candidate-kicker").textContent =
      `${detail.text_length_label}组 · 未进入已编码候选`;
    $("#candidate-text").textContent = detail.text;
    $("#candidate-frequency").textContent = number(detail.bcc_frequency);
    $("#candidate-badges").innerHTML = "";
    addBadge(classLabels[detail.candidate_class] || detail.candidate_class);
    if (detail.dynamic_reachable) {
      addBadge("动态可达证据 · 未判去留");
    }
    if (detail.blocking_reason === "missing_trusted_mandarin_reading") {
      addBadge("暂无可信普通话读音来源 · 未予编码");
      $("#gate-title").textContent = "当前暂无可信普通话读音来源，暂未予编码";
      $("#gate-detail").textContent =
        "字串包含尚无可信普通话读音来源的码点。当前不标注拼音、不进入正式编码链，但不判为噪声或永久拒绝；保留原始证据，等待专家或未来来源复核。";
    } else {
      addBadge("无门禁合格注音");
      $("#gate-title").textContent = "当前不能进入已编码运行候选";
      $("#gate-detail").textContent =
        "缺少通过来源门禁的完整注音（拼音）。其中一部分只有汉字字串与 BCC 频次，另一部分可能有被门禁拒绝的来源注音。准入只确认候选价值，后续仍须补充真实注音来源并走正式编码链。";
    }
    if (detail.has_source_rejection) addBadge("有来源拒绝");
    if (detail.evidence.rule_family_id) {
      addBadge(`规则族：${detail.evidence.rule_family_id}`);
    }

    $("#source-categories").textContent =
      detail.source.categories.length ? detail.source.categories.join("、") : "无合规来源分类";
    $("#context-count").textContent = `${detail.contexts.length} 条`;
    $("#rejection-count").textContent = `${detail.source.rejection_reasons.length} 条`;
    $("#class-select").value = detail.candidate_class;
    if (["static_keep", "model_only"].includes(detail.integration_policy)) {
      $("#policy-select").value = detail.integration_policy;
    }
    $("#rationale-input").value =
      detail.decision_status === "proposed" ? "" : detail.rationale;
    $("#assessor-input").value =
      detail.assessor.startsWith("baseline:") ? "human:local-reviewer" : detail.assessor;

    const status = $("#current-status");
    status.textContent = statusLabels[detail.decision_status] || detail.decision_status;
    status.className = `status-pill ${detail.decision_status}`;
    renderHistory(detail);
  } catch (error) {
    $("#candidate-text").textContent = text;
    showMessage(error.message, true);
  }
}

function showMessage(message, isError = false) {
  const target = $("#action-message");
  target.textContent = message;
  target.classList.toggle("error", isError);
}

function setDecisionButtons(disabled) {
  document.querySelectorAll(".decision").forEach((button) => {
    button.disabled = disabled;
  });
}

function refinementValues() {
  return $("#affix-refinement-input").value
    .split(/[\r\n,，、]+/)
    .map((value) => value.trim())
    .filter(Boolean);
}

function updateDiscoveryMode() {
  const frame = $("#affix-direction").value === "frame";
  $("#affix-root-field").hidden = frame;
  $("#affix-refinement-field").hidden = frame;
  $("#construction-template-field").hidden = !frame;
  $("#tail-classification-actions").hidden = frame;
  $("#tail-classification-heading").textContent = frame ? "语义分类（不适用）" : "语义分类";
  $("#run-affix-analysis").textContent = frame ? "分析框式" : "开始筛选";
}

function appendReadingCell(row, item, side) {
  const part = item[`${side}_part`];
  const gated = item[`${side}_has_gated_reading`];
  const reading = item[`${side}_reading`];
  const cell = document.createElement("td");
  cell.className = gated ? "gate-ok" : "gate-missing";
  cell.textContent = part;
  const hint = document.createElement("span");
  hint.className = "reading-hint";
  hint.textContent = gated && reading ? reading.marked : "无门禁合格注音";
  cell.append(hint);
  row.append(cell);
}

function renderAffixAnalysis(payload) {
  const summary = $("#affix-summary");
  summary.innerHTML = "";
  const total = document.createElement("span");
  total.textContent = `命中 ${number(payload.total_matches)} 项`;
  summary.append(total);
  const isFrame = payload.kind === "frame_template";
  if (isFrame) {
    [
      `递归覆盖 ${number(payload.composition_covered)} 项`,
      `两字例外 ${number(payload.short_form_exceptions)} 项`,
      `多解 ${number(payload.ambiguous_matches)} 项`,
    ].forEach((label) => {
      const chip = document.createElement("span");
      chip.textContent = label;
      summary.append(chip);
    });
    $("#analysis-match-heading").textContent = "模板";
    $("#analysis-left-heading").textContent = "匹配结构";
    $("#analysis-right-heading").textContent = "槽位递归";
    $("#analysis-status-heading").textContent = "覆盖状态";
  } else {
    const gated = document.createElement("span");
    gated.textContent = `两侧均已注音 ${number(payload.both_parts_gated)} 项`;
    summary.append(gated);
    payload.anchor_counts.forEach((item) => {
      const chip = document.createElement("span");
      chip.textContent =
        `${item.anchor}：${number(item.matched)} 项／两侧合格 ${number(item.both_parts_gated)}`;
      summary.append(chip);
    });
    $("#analysis-match-heading").textContent = "层级命中";
    $("#analysis-left-heading").textContent = "左部";
    $("#analysis-right-heading").textContent = "右部";
    $("#analysis-status-heading").textContent = "两侧核验";
  }
  summary.hidden = false;

  const body = $("#affix-result-body");
  body.innerHTML = "";
  payload.items.forEach((item) => {
    const eligibleSuggestions = new Set([
      "dynamic_composition_candidate",
      "proper_name_rule_candidate",
      "domain_rule_candidate",
      "frame_composition_candidate",
    ]);
    const eligible = eligibleSuggestions.has(item.suggestion);
    const row = document.createElement("tr");
    const selectCell = document.createElement("td");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "affix-result-check";
    checkbox.dataset.text = item.text;
    checkbox.dataset.bothGated = String(eligible);
    selectCell.append(checkbox);

    const textCell = document.createElement("td");
    const textButton = document.createElement("button");
    textButton.type = "button";
    textButton.className = "affix-candidate-link";
    textButton.textContent = item.text;
    textButton.addEventListener("click", async () => {
      await selectCandidate(item.text);
      $("#detail-panel").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    textCell.append(textButton);

    const gateCell = document.createElement("td");
    gateCell.className = eligible ? "gate-ok" : "gate-missing";
    const frequencyCell = document.createElement("td");
    frequencyCell.textContent = number(item.bcc_frequency);
    const suggestionCell = document.createElement("td");
    suggestionCell.textContent =
      affixSuggestionLabels[item.suggestion] || item.suggestion;
    const classificationCell = document.createElement("td");
    if (isFrame) {
      classificationCell.textContent = "—";
    } else {
      const classificationSelect = document.createElement("select");
      classificationSelect.className = "tail-classification-select";
      classificationSelect.dataset.text = item.text;
      classificationSelect.dataset.matchedAnchor = item.matched_anchor;
      const emptyOption = document.createElement("option");
      emptyOption.value = "";
      emptyOption.textContent = "未分类";
      classificationSelect.append(emptyOption);
      Object.entries(tailSemanticLabels).forEach(([value, label]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        classificationSelect.append(option);
      });
      classificationSelect.value =
        item.tail_classification?.semantic_class || "";
      classificationSelect.title = item.tail_classification
        ? `已由 ${item.tail_classification.assessor} 保存`
        : "尚未保存";
      classificationCell.append(classificationSelect);
    }

    row.append(selectCell, textCell);
    if (isFrame) {
      const templateCell = document.createElement("td");
      templateCell.textContent = payload.template;
      const structureCell = document.createElement("td");
      structureCell.textContent = item.components
        .map((component) => {
          if (component.type === "slot") {
            return `{${component.name}}=${component.text || "∅"}`;
          }
          return component.text;
        })
        .join(" · ");
      const recursionCell = document.createElement("td");
      item.components
        .filter((component) => component.type === "slot")
        .forEach((component) => {
          const line = document.createElement("span");
          line.className = "reading-hint";
          const parts = component.parts.length ? component.parts.join(" + ") : "∅";
          line.textContent =
            `${component.name}: ${parts} · ` +
            (coverageStatusLabels[component.coverage_status] || component.coverage_status);
          recursionCell.append(line);
        });
      gateCell.textContent =
        coverageStatusLabels[
          item.suggestion === "short_form_exception"
            ? "short_form_exception"
            : item.suggestion === "ambiguous_split"
              ? "ambiguous_split"
              : item.suggestion === "reading_evidence_required"
                ? "reading_evidence_required"
                : "composition_covered"
        ];
      row.append(templateCell, structureCell, recursionCell);
    } else {
      const anchorCell = document.createElement("td");
      anchorCell.textContent = item.matched_anchor;
      row.append(anchorCell);
      appendReadingCell(row, item, "left");
      appendReadingCell(row, item, "right");
      gateCell.textContent = item.both_parts_gated ? "✓ 前后均合格" : "! 尚不完整";
    }
    row.append(gateCell, frequencyCell, suggestionCell, classificationCell);
    body.append(row);
  });
  if (!payload.items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 9;
    cell.className = "queue-empty";
    cell.textContent = "当前层级筛选没有命中候选。";
    row.append(cell);
    body.append(row);
  }
  $("#affix-results").hidden = false;
}

async function runAffixAnalysis() {
  const direction = $("#affix-direction").value;
  const rootAnchor = $("#affix-root").value.trim();
  const template = $("#construction-template-input").value.trim();
  if (direction === "frame" ? !template : !rootAnchor) {
    $("#affix-message").textContent =
      direction === "frame" ? "请先填写框式模板。" : "请先填写第一层筛选项。";
    $("#affix-message").classList.add("error");
    return;
  }
  const refinements = refinementValues();
  const commonParams = {
    intended_class: $("#affix-class-select").value,
    minimum_frequency: $("#affix-minimum-frequency").value,
    only_unencoded: String($("#affix-only-unencoded").checked),
    limit: "300",
  };
  const params = new URLSearchParams(commonParams);
  let endpoint;
  if (direction === "frame") {
    params.set("template", template);
    endpoint = "/api/construction-analysis";
  } else {
    params.set("direction", direction);
    params.set("root_anchor", rootAnchor);
    refinements.forEach((value) => params.append("refinement", value));
    endpoint = "/api/affix-analysis";
  }
  $("#run-affix-analysis").disabled = true;
  $("#affix-message").classList.remove("error");
  $("#affix-message").textContent = "正在执行层级筛选并核验两侧注音…";
  try {
    const payload = await api(`${endpoint}?${params}`);
    state.affixPayload = payload;
    state.affixAnalysis = payload.kind === "frame_template"
      ? {
          kind: "frame_template",
          template: payload.template,
        }
      : {
          kind: "affix_hierarchy",
          direction: payload.direction,
          root_anchor: payload.root_anchor,
          refinements: payload.refinements,
        };
    renderAffixAnalysis(payload);
    $("#affix-message").textContent = payload.truncated
      ? "结果较多，当前显示前 300 项；可提高最低频次继续收窄。"
      : "筛选完成。此处只提供可审计建议，没有写入任何判决。";
  } catch (error) {
    $("#affix-message").textContent = error.message;
    $("#affix-message").classList.add("error");
  } finally {
    $("#run-affix-analysis").disabled = false;
  }
}

function selectedTailClassifications() {
  return Array.from(document.querySelectorAll(".tail-classification-select"))
    .filter((select) => select.value)
    .map((select) => ({
      text: select.dataset.text,
      matched_anchor: select.dataset.matchedAnchor,
      semantic_class: select.value,
      note: "",
    }));
}

async function saveTailClassifications() {
  const payload = state.affixPayload;
  const assessor = $("#tail-assessor-input").value.trim();
  if (!payload || payload.kind === "frame_template") return;
  const classifications = selectedTailClassifications();
  if (!classifications.length) {
    $("#affix-message").textContent = "请至少为一个候选选择语义分类。";
    $("#affix-message").classList.add("error");
    return;
  }
  if (!assessor) {
    $("#affix-message").textContent = "请填写分类审查者。";
    $("#affix-message").classList.add("error");
    return;
  }
  $("#affix-message").classList.remove("error");
  $("#affix-message").textContent = "正在保存语义分类；此步骤不写候选去留判决…";
  try {
    const result = await api("/api/tail-classifications", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Yime-Review": "1",
      },
      body: JSON.stringify({
        direction: payload.direction,
        root_anchor: payload.root_anchor,
        classifications,
        assessor,
      }),
    });
    $("#affix-message").textContent =
      `已保存 ${number(result.saved_count)} 项分类；尚未运行去留判定。`;
  } catch (error) {
    $("#affix-message").textContent = error.message;
    $("#affix-message").classList.add("error");
  }
}

async function applyTailClassifications() {
  const payload = state.affixPayload;
  const assessor = $("#tail-assessor-input").value.trim();
  if (!payload || payload.kind === "frame_template") return;
  if (!assessor) {
    $("#affix-message").textContent = "请填写分类审查者。";
    $("#affix-message").classList.add("error");
    return;
  }
  $("#affix-message").classList.remove("error");
  $("#affix-message").textContent =
    "正在按已保存分类、组件注音和结构门禁计算去留…";
  try {
    const result = await api("/api/tail-classifications/apply", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Yime-Review": "1",
      },
      body: JSON.stringify({
        direction: payload.direction,
        root_anchor: payload.root_anchor,
        assessor,
        maximum_items: 5000,
      }),
    });
    const counts = result.disposition_counts;
    $("#affix-message").textContent =
      `已处理 ${number(result.applied_count)} 项：` +
      `移出静态待编码 ${number(counts.exclude_from_static_encoding)}，` +
      `保留待编码 ${number(counts.keep_for_encoding_review)}，` +
      `拒绝 ${number(counts.reject)}，` +
      `继续人工审查 ${number(
        (counts.reading_or_structure_review || 0) + (counts.manual_review || 0),
      )}。`;
    await Promise.all([loadSummary(), loadQueue()]);
  } catch (error) {
    $("#affix-message").textContent = error.message;
    $("#affix-message").classList.add("error");
  }
}

function addAutoMetric(target, label, value) {
  const card = document.createElement("article");
  const caption = document.createElement("span");
  caption.textContent = label;
  const numberNode = document.createElement("strong");
  numberNode.textContent = value;
  card.append(caption, numberNode);
  target.append(card);
}

function renderAutomaticScreening(payload) {
  const summary = $("#auto-screening-summary");
  summary.innerHTML = "";
  addAutoMetric(summary, "待筛查总数", number(payload.pending_total));
  addAutoMetric(summary, "已登记筛查规则", number(payload.registered_rule_count));
  addAutoMetric(
    summary,
    "安全自动命中",
    number(payload.category_counts.auto_covered),
  );
  addAutoMetric(
    summary,
    "自动覆盖率",
    `${(payload.automatic_coverage_rate * 100).toFixed(1)}%`,
  );
  addAutoMetric(
    summary,
    "规则冲突",
    number(payload.category_counts.rule_conflict),
  );
  addAutoMetric(
    summary,
    "两字例外",
    number(payload.category_counts.short_form_exception),
  );
  addAutoMetric(
    summary,
    "组合已覆盖但缺规则",
    number(payload.category_counts.unclassified_composition),
  );
  addAutoMetric(
    summary,
    "缺读音 / 其他残余",
    number(
      payload.category_counts.reading_evidence_required +
      payload.category_counts.ambiguous_split,
    ),
  );
  summary.hidden = false;

  const body = $("#auto-screening-result-body");
  body.innerHTML = "";
  payload.items.forEach((item) => {
    const row = document.createElement("tr");
    const textCell = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "affix-candidate-link";
    button.textContent = item.text;
    button.addEventListener("click", () => selectCandidate(item.text));
    textCell.append(button);
    const frequencyCell = document.createElement("td");
    frequencyCell.textContent = number(item.bcc_frequency);
    const categoryCell = document.createElement("td");
    categoryCell.textContent =
      automaticCategoryLabels[item.category] || item.category;
    categoryCell.className =
      item.category === "auto_covered" ? "gate-ok" : "gate-missing";
    const familyCell = document.createElement("td");
    familyCell.textContent = item.selected_family_title || "—";
    const classCell = document.createElement("td");
    classCell.textContent = item.candidate_class
      ? classLabels[item.candidate_class] || item.candidate_class
      : "—";
    row.append(textCell, frequencyCell, categoryCell, familyCell, classCell);
    body.append(row);
  });
  $("#auto-screening-results").hidden = false;

  const clusterPanel = $("#residual-clusters");
  const clusterList = $("#residual-cluster-list");
  clusterList.innerHTML = "";
  payload.residual_clusters.forEach((cluster) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "residual-cluster-button";
    const direction = cluster.direction === "prefix" ? "正序" : "逆序";
    button.textContent =
      `${direction}「${cluster.anchor}」 · ${number(cluster.count)} 项`;
    button.title = cluster.examples.join("、");
    button.addEventListener("click", () => {
      $("#affix-direction").value = cluster.direction;
      updateDiscoveryMode();
      $("#affix-root").value = cluster.anchor;
      $("#affix-minimum-frequency").value =
        $("#auto-minimum-frequency").value;
      $(".affix-explorer").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    clusterList.append(button);
  });
  clusterPanel.hidden = !payload.residual_clusters.length;
  $("#apply-auto-screening").disabled =
    payload.category_counts.auto_covered < 1;
}

async function previewAutomaticScreening() {
  const params = new URLSearchParams({
    minimum_frequency: $("#auto-minimum-frequency").value,
    limit: "300",
  });
  $("#preview-auto-screening").disabled = true;
  $("#apply-auto-screening").disabled = true;
  $("#auto-screening-message").classList.remove("error");
  $("#auto-screening-message").textContent =
    "正在应用已登记规则、检查冲突并聚类剩余项…";
  try {
    const payload = await api(`/api/automatic-screening?${params}`);
    state.automaticScreening = payload;
    renderAutomaticScreening(payload);
    $("#auto-screening-message").textContent = payload.truncated
      ? "预览显示前 300 项；汇总数字已覆盖当前频次范围内的全部待筛查项。"
      : "预览完成，尚未写入任何判决。";
  } catch (error) {
    $("#auto-screening-message").textContent = error.message;
    $("#auto-screening-message").classList.add("error");
  } finally {
    $("#preview-auto-screening").disabled = false;
  }
}

async function applyAutomaticScreening() {
  if (
    !state.automaticScreening ||
    state.automaticScreening.category_counts.auto_covered < 1
  ) return;
  const count = state.automaticScreening.category_counts.auto_covered;
  const confirmed = window.confirm(
    `将最多应用 ${$("#auto-maximum-items").value} 项无冲突命中（当前共有 ${count} 项）。` +
    "它们只写入 model_only 覆盖层，不进入运行词库。是否继续？",
  );
  if (!confirmed) return;
  $("#apply-auto-screening").disabled = true;
  $("#preview-auto-screening").disabled = true;
  $("#auto-screening-message").textContent = "正在记录安全自动命中…";
  try {
    const result = await api("/api/automatic-screening/apply", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Yime-Review": "1",
      },
      body: JSON.stringify({
        assessor: $("#auto-assessor-input").value.trim(),
        minimum_frequency: Number($("#auto-minimum-frequency").value),
        maximum_items: Number($("#auto-maximum-items").value),
      }),
    });
    await Promise.all([loadSummary(), loadQueue()]);
    await previewAutomaticScreening();
    $("#auto-screening-message").textContent =
      `已应用 ${number(result.applied_count)} 项；运行词库没有被修改。`;
  } catch (error) {
    $("#auto-screening-message").textContent = error.message;
    $("#auto-screening-message").classList.add("error");
  } finally {
    $("#preview-auto-screening").disabled = false;
  }
}

function selectedAffixExamples(onlyGated) {
  return Array.from(document.querySelectorAll(".affix-result-check:checked"))
    .filter((item) => !onlyGated || item.dataset.bothGated === "true")
    .map((item) => item.dataset.text);
}

function mergeExampleTextarea(selector, values) {
  const existing = exampleLines(selector);
  $(selector).value = Array.from(new Set([...existing, ...values])).join("\n");
}

async function transferAffixExamples(role) {
  const onlyGated = role === "positive";
  const selected = selectedAffixExamples(onlyGated);
  if (!selected.length) {
    $("#affix-message").textContent = onlyGated
      ? "请至少勾选一个左右两侧均已注音的结果。"
      : "请至少勾选一个结果。";
    $("#affix-message").classList.add("error");
    return;
  }
  const selector =
    role === "positive" ? "#family-positive-input" : "#family-negative-input";
  mergeExampleTextarea(selector, selected);
  if (role === "positive") state.familyDiscoveryModel = state.affixAnalysis;
  $("#family-class-select").value = $("#affix-class-select").value;
  const directionLabel =
    state.affixAnalysis.direction === "suffix" ? "以…结尾的逆序" : "以…开头的正序";
  if (!$("#family-pattern-input").value.trim()) {
    if (state.affixAnalysis.kind === "frame_template") {
      $("#family-pattern-input").value =
        `框式构式：${state.affixAnalysis.template}；各槽位整体合格即停止，否则递归到已注音原子；两字在双方单字均有注音时动态覆盖，缺音时进入例外审查。`;
    } else {
      const refinements = state.affixAnalysis.refinements.length
        ? `，并按 ${state.affixAnalysis.refinements.join("、")} 采用最长项细分`
        : "";
      $("#family-pattern-input").value =
        `${directionLabel}构式：第一层为 ${state.affixAnalysis.root_anchor}${refinements}；拆分后左右两侧须有来源门禁合格注音。`;
    }
  }
  $("#affix-message").classList.remove("error");
  $("#affix-message").textContent =
    `已把 ${selected.length} 项加入规则族${role === "positive" ? "正例" : "反例"}。`;
  if (
    role === "positive" &&
    selected.length &&
    (!state.selectedText || !selected.includes(state.selectedText))
  ) {
    await selectCandidate(selected[0]);
  }
}

function exampleLines(selector) {
  return $(selector).value
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);
}

function showFamilyMessage(message, isError = false) {
  const target = $("#family-message");
  target.textContent = message;
  target.classList.toggle("error", isError);
}

async function registerRuleFamily() {
  if (!state.selectedText) return;
  const payload = {
    family_id: $("#family-id-input").value.trim(),
    title: $("#family-title-input").value.trim(),
    pattern_description: $("#family-pattern-input").value.trim(),
    applicability_notes: $("#family-scope-input").value.trim(),
    representative: state.selectedText,
    positive_examples: exampleLines("#family-positive-input"),
    negative_examples: exampleLines("#family-negative-input"),
    candidate_class: $("#family-class-select").value,
    rationale: $("#family-rationale-input").value.trim(),
    assessor: $("#family-assessor-input").value.trim(),
    review_standard: state.criteria,
    custom_criteria: state.criteria === "reviewer" ? customCriteria() : null,
    discovery_model: state.familyDiscoveryModel,
  };
  if (!payload.family_id || !payload.title || !payload.pattern_description ||
      !payload.rationale || !payload.negative_examples.length) {
    showFamilyMessage("请填写规则族 ID、名称、结构规则、至少一个反例和登记依据。", true);
    return;
  }
  if (state.criteria === "reviewer") {
    const criteria = customCriteria();
    if (!criteria.name || !criteria.rules) {
      showFamilyMessage("请先补全当前自定审查标准。", true);
      return;
    }
  }
  setDecisionButtons(true);
  showFamilyMessage("正在登记规则族…");
  try {
    const family = await api("/api/rule-family", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Yime-Review": "1",
      },
      body: JSON.stringify(payload),
    });
    showFamilyMessage(
      `已登记 ${family.family_id}；正例仅进入模型评测层，仍未成为运行时规则。`,
    );
    state.familyDiscoveryModel = null;
    await Promise.all([loadSummary(), loadQueue()]);
    await selectCandidate(state.selectedText);
  } catch (error) {
    showFamilyMessage(error.message, true);
  } finally {
    setDecisionButtons(false);
  }
}

async function decide(action) {
  if (!state.selectedText) return;
  const rationale = $("#rationale-input").value.trim();
  if (!rationale) {
    showMessage("请先点击常用理由或填写判决依据。", true);
    $("#rationale-input").focus();
    return;
  }
  if (state.criteria === "reviewer") {
    const criteria = customCriteria();
    if (!criteria.name || !criteria.rules) {
      showMessage("请先填写自定标准名称和至少一条判据。", true);
      $("#custom-criteria-rules").focus();
      return;
    }
  }
  setDecisionButtons(true);
  showMessage("正在记录判决…");
  try {
    const detail = await api("/api/decision", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Yime-Review": "1",
      },
      body: JSON.stringify({
        text: state.selectedText,
        action,
        candidate_class: $("#class-select").value,
        integration_policy: $("#policy-select").value,
        rationale,
        assessor: $("#assessor-input").value,
        review_standard: state.criteria,
        custom_criteria: state.criteria === "reviewer" ? customCriteria() : null,
      }),
    });
    const label = statusLabels[detail.decision_status] || detail.decision_status;
    showMessage(`已记录：${label}。运行词库没有被修改。`);
    await Promise.all([loadSummary(), loadQueue()]);
    await selectCandidate(detail.text);
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    setDecisionButtons(false);
  }
}

async function initialize() {
  try {
    state.config = await api("/api/config");
    const select = $("#class-select");
    select.innerHTML = "";
    state.config.candidate_classes.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = classLabels[value] || value;
      select.append(option);
    });
    await Promise.all([loadSummary(), loadQueue()]);
    setConnection(
      true,
      window.location.protocol === "file:"
        ? "页面由本地文件打开，已安全连接 127.0.0.1:8765；判决只写候选覆盖库。"
        : "",
    );
  } catch (error) {
    $("#queue").innerHTML = `<div class="queue-empty">${error.message}</div>`;
    setConnection(false, error.message);
  }
}

document.querySelectorAll(".status-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".status-tab").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    state.status = tab.dataset.status;
    state.selectedText = null;
    loadQueue();
  });
});

let searchTimer;
$("#search-input").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadQueue(), 250);
});
$("#frequency-filter").addEventListener("change", () => loadQueue());
$("#length-filter").addEventListener("change", () => loadQueue());
$("#refresh-button").addEventListener("click", () => Promise.all([loadSummary(), loadQueue()]));
$("#load-more").addEventListener("click", () => loadQueue({ append: true }));
$("#preview-auto-screening").addEventListener("click", () => previewAutomaticScreening());
$("#apply-auto-screening").addEventListener("click", () => applyAutomaticScreening());
$("#affix-direction").addEventListener("change", () => updateDiscoveryMode());
$("#run-affix-analysis").addEventListener("click", () => runAffixAnalysis());
$("#affix-to-positive").addEventListener("click", () => transferAffixExamples("positive"));
$("#affix-to-negative").addEventListener("click", () => transferAffixExamples("negative"));
$("#save-tail-classifications").addEventListener("click", () =>
  saveTailClassifications(),
);
$("#apply-tail-classifications").addEventListener("click", () =>
  applyTailClassifications(),
);
$("#register-family-button").addEventListener("click", () => registerRuleFamily());
$("#approve-button").addEventListener("click", () => decide("approve"));
$("#reject-button").addEventListener("click", () => decide("reject"));
$("#defer-button").addEventListener("click", () => decide("defer"));
document.querySelectorAll("[data-reason]").forEach((button) => {
  button.addEventListener("click", () => {
    $("#rationale-input").value = button.dataset.reason;
    if (button.dataset.class) $("#class-select").value = button.dataset.class;
    if (button.dataset.policy) $("#policy-select").value = button.dataset.policy;
    if (button.dataset.openFamily) {
      $("#family-class-select").value = "productive_phrase";
      $("#family-pattern-input").focus();
    }
    showMessage("");
  });
});

document.querySelectorAll(".criteria-tab").forEach((tab) => {
  tab.addEventListener("click", () => selectCriteria(tab.dataset.criteria));
});
["#custom-criteria-name", "#custom-criteria-goal", "#custom-criteria-rules"].forEach(
  (selector) => {
    $(selector).addEventListener("input", () => {
      persistCriteria();
      if (state.criteria === "reviewer") selectCriteria("reviewer");
    });
  },
);
$("#retry-connection").addEventListener("click", () => initialize());
$("#copy-launch-command").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(LAUNCH_COMMAND);
    $("#connection-detail").textContent = "启动命令已复制。请在仓库根目录的 PowerShell 中运行。";
  } catch {
    $("#connection-detail").textContent = `请复制并运行：${LAUNCH_COMMAND}`;
  }
});

restoreCustomCriteria();
updateDiscoveryMode();
selectCriteria(["standard", "academic", "reviewer"].includes(state.criteria)
  ? state.criteria
  : "standard");
initialize();
