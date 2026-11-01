(() => {
  "use strict";

  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  let motion = !reduced.matches;
  let traceTimer = null;
  let traceIndex = 0;
  let emhaTimer = null;
  let emhaIndex = 0;
  let toastTimer = null;
  let matrixMetric = "asr";
  let selectedAgent = 0;
  let selectedModel = 0;

  document.documentElement.classList.add("js");

  function toast(message) {
    const node = $("#toast");
    if (!node) return;
    node.textContent = message;
    node.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => node.classList.remove("show"), 2800);
  }

  /* Motion --------------------------------------------------------------- */
  const motionToggle = $("#motion-toggle");
  const motionLabel = $("#motion-label");

  function setMotion(on) {
    motion = on;
    document.body.classList.toggle("motion-off", !on);
    if (motionToggle) {
      motionToggle.setAttribute("aria-pressed", String(on));
      motionToggle.setAttribute("aria-label", on ? "Turn page animation off" : "Turn page animation on");
    }
    if (motionLabel) motionLabel.textContent = on ? "Motion on" : "Motion off";
    $$("svg").forEach((svg) => {
      try {
        if (on) svg.unpauseAnimations();
        else svg.pauseAnimations();
      } catch (_) { /* static SVG */ }
    });
    if (!on) {
      stopTrace();
      stopEmha();
      $$(".reveal").forEach((el) => el.classList.add("visible"));
    }
  }

  if (motionToggle) motionToggle.addEventListener("click", () => setMotion(!motion));
  setMotion(motion);
  if (reduced.addEventListener) {
    reduced.addEventListener("change", (event) => { if (event.matches) setMotion(false); });
  }

  /* Menu ----------------------------------------------------------------- */
  const menuToggle = $("#menu-toggle");
  const mainNav = $("#main-nav");

  function closeMenu() {
    if (!mainNav || !menuToggle) return;
    mainNav.classList.remove("open");
    menuToggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("menu-open");
  }

  if (menuToggle && mainNav) {
    menuToggle.addEventListener("click", () => {
      const open = mainNav.classList.toggle("open");
      menuToggle.setAttribute("aria-expanded", String(open));
      document.body.classList.toggle("menu-open", open);
    });
    $$("a", mainNav).forEach((link) => link.addEventListener("click", closeMenu));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && mainNav.classList.contains("open")) {
        closeMenu();
        menuToggle.focus();
      }
    });
    window.addEventListener("resize", () => {
      if (window.innerWidth > 900) closeMenu();
    });
  }

  /* Reveals -------------------------------------------------------------- */
  const reveals = $$(".reveal");
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: "0px 0px -4% 0px" });
    reveals.forEach((el) => observer.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add("visible"));
  }

  /* Read progress -------------------------------------------------------- */
  const progress = $("#read-progress");
  function updateProgress() {
    if (!progress) return;
    const range = document.documentElement.scrollHeight - window.innerHeight;
    progress.style.width = (range > 0 ? Math.max(0, Math.min(100, (100 * window.scrollY) / range)) : 0) + "%";
  }
  window.addEventListener("scroll", updateProgress, { passive: true });
  window.addEventListener("resize", updateProgress);
  updateProgress();

  /* Active chapter ------------------------------------------------------- */
  if ("IntersectionObserver" in window && mainNav) {
    const navLinks = $$("a", mainNav);
    const chapterObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        navLinks.forEach((link) => {
          link.classList.toggle("active", link.getAttribute("href") === "#" + entry.target.id);
        });
      });
    }, { rootMargin: "-18% 0px -64% 0px" });
    ["question", "arena", "search", "horizon", "evidence", "use"].forEach((id) => {
      const section = document.getElementById(id);
      if (section) chapterObserver.observe(section);
    });
  }

  /* Chapter 01: trace ---------------------------------------------------- */
  const trace = [
    ["Task", "Task starts, boundary is clear.", "The agent receives a benign objective. The hidden safety contract stays fixed for the whole run."],
    ["Change", "Authorized state changes.", "Within the adapter’s allowed surfaces, target-visible material changes. The objective and evaluator do not move."],
    ["Read", "Evolved state enters context.", "The agent reads the modified material. Consuming evolved state is not yet a violation."],
    ["Record", "A judgment is written down.", "The agent summarizes, plans, or stores a conclusion that later steps may reuse."],
    ["Reuse", "An earlier conclusion travels.", "The task continues. Modified state combines with the existing workflow and accumulates influence."],
    ["Action", "A later action crosses the line.", "In this illustrative path, a subsequent action violates the fixed safety boundary. First read and first unsafe action can be far apart."],
    ["Evaluate", "The trace is judged.", "The evaluator reads the execution trace and resulting state. Confirmed feedback guides later search; the task and evaluator remain unchanged."]
  ];

  const traceRail = $("#trace-rail");
  const traceTitle = $("#trace-title");
  const traceDesc = $("#trace-desc");
  const traceSlider = $("#trace-slider");
  const traceCount = $("#trace-count");
  const traceFill = $("#trace-fill");
  const tracePlay = $("#trace-play");
  const traceNodes = traceRail ? $$(".trace-node", traceRail) : [];

  function setTrace(index) {
    traceIndex = Math.max(0, Math.min(trace.length - 1, index));
    if (traceTitle) traceTitle.textContent = trace[traceIndex][1];
    if (traceDesc) traceDesc.textContent = trace[traceIndex][2];
    if (traceSlider) traceSlider.value = String(traceIndex);
    if (traceCount) traceCount.textContent = String(traceIndex + 1).padStart(2, "0") + " / 07";
    traceNodes.forEach((node, i) => {
      node.classList.toggle("seen", i <= traceIndex);
      node.classList.toggle("current", i === traceIndex);
      node.setAttribute("aria-pressed", String(i === traceIndex));
    });
    if (traceRail && traceFill && traceNodes.length) {
      const first = traceNodes[0].offsetLeft + traceNodes[0].offsetWidth / 2;
      const current = traceNodes[traceIndex].offsetLeft + traceNodes[traceIndex].offsetWidth / 2;
      traceFill.style.left = first + "px";
      traceFill.style.width = Math.max(0, current - first) + "px";
    }
  }

  function stopTrace() {
    clearInterval(traceTimer);
    traceTimer = null;
    if (tracePlay) {
      tracePlay.textContent = "▶";
      tracePlay.setAttribute("aria-pressed", "false");
      tracePlay.setAttribute("aria-label", "Play task demonstration");
    }
  }

  if (traceRail && traceNodes.length) {
    traceNodes.forEach((node, i) => {
      node.addEventListener("click", () => { stopTrace(); setTrace(i); });
      node.addEventListener("keydown", (event) => {
        let next = null;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (i + 1) % traceNodes.length;
        if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (i - 1 + traceNodes.length) % traceNodes.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = traceNodes.length - 1;
        if (next === null) return;
        event.preventDefault();
        stopTrace();
        setTrace(next);
        traceNodes[next].focus();
      });
    });
    setTrace(0);
    window.addEventListener("resize", () => setTrace(traceIndex));
  }

  if (tracePlay) {
    tracePlay.addEventListener("click", () => {
      if (traceTimer) { stopTrace(); return; }
      if (!motion) setMotion(true);
      if (traceIndex === trace.length - 1) setTrace(0);
      tracePlay.textContent = "Ⅱ";
      tracePlay.setAttribute("aria-pressed", "true");
      tracePlay.setAttribute("aria-label", "Pause task demonstration");
      traceTimer = setInterval(() => {
        if (traceIndex >= trace.length - 1) { stopTrace(); return; }
        setTrace(traceIndex + 1);
      }, 2600);
    });
  }

  if (traceSlider) {
    traceSlider.addEventListener("input", (event) => {
      stopTrace();
      setTrace(Number(event.target.value));
    });
  }

  /* Chapter 02: surfaces ------------------------------------------------- */
  const surfaceTabs = $$(".surface-tab");
  const surfacePanels = $$(".surface-panel");

  function setSurface(index) {
    surfaceTabs.forEach((tab, i) => {
      const active = i === index;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    surfacePanels.forEach((panel, i) => {
      const active = i === index;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
  }

  if (surfaceTabs.length) {
    surfaceTabs.forEach((tab, i) => tab.addEventListener("click", () => setSurface(i)));
    const tablist = $("#surface-tabs");
    if (tablist) {
      tablist.addEventListener("keydown", (event) => {
        const current = surfaceTabs.indexOf(document.activeElement);
        if (current < 0) return;
        let next = null;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (current + 1) % surfaceTabs.length;
        if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (current - 1 + surfaceTabs.length) % surfaceTabs.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = surfaceTabs.length - 1;
        if (next === null) return;
        event.preventDefault();
        setSurface(next);
        surfaceTabs[next].focus();
      });
    }
    setSurface(0);
  }

  /* Chapter 03: EMHA ----------------------------------------------------- */
  const emhaFigure = $("#emha-figure");
  const emhaSteps = $$(".emha-step");
  const emhaStageLabel = $("#emha-stage-label");
  const emhaCounter = $("#emha-counter");
  const emhaPlay = $("#emha-play");
  const emhaNext = $("#emha-next");
  const emhaNote = $("#emha-control-note");
  const emhaStages = ["RETRIEVE", "SELECT", "EXECUTE", "EVOLVE"];

  function setEmha(index) {
    emhaIndex = ((index % emhaSteps.length) + emhaSteps.length) % emhaSteps.length;
    emhaSteps.forEach((step, i) => {
      const active = i === emhaIndex;
      step.classList.toggle("active", active);
      step.setAttribute("aria-expanded", String(active));
    });
    if (emhaFigure) emhaFigure.dataset.step = String(emhaIndex + 1);
    if (emhaStageLabel) emhaStageLabel.textContent = String(emhaIndex + 1).padStart(2, "0") + " / " + emhaStages[emhaIndex];
    if (emhaCounter) emhaCounter.textContent = String(emhaIndex + 1).padStart(2, "0") + " / 04";
    $$("[data-hnode]").forEach((node) => {
      node.classList.toggle("node-active", Number(node.dataset.hnode) <= emhaIndex + 1);
    });
  }

  function stopEmha() {
    clearInterval(emhaTimer);
    emhaTimer = null;
    if (emhaPlay) {
      emhaPlay.textContent = "▶";
      emhaPlay.setAttribute("aria-pressed", "false");
      emhaPlay.setAttribute("aria-label", "Play EMHA search demonstration");
    }
    if (emhaNote) emhaNote.textContent = "Click a step, or play the loop";
  }

  if (emhaSteps.length) {
    emhaSteps.forEach((step, i) => step.addEventListener("click", () => { stopEmha(); setEmha(i); }));
    setEmha(0);
  }

  if (emhaPlay) {
    emhaPlay.addEventListener("click", () => {
      if (emhaTimer) { stopEmha(); return; }
      if (!motion) setMotion(true);
      emhaPlay.textContent = "Ⅱ";
      emhaPlay.setAttribute("aria-pressed", "true");
      emhaPlay.setAttribute("aria-label", "Pause EMHA search demonstration");
      if (emhaNote) emhaNote.textContent = "Following the feedback loop";
      emhaTimer = setInterval(() => setEmha((emhaIndex + 1) % emhaSteps.length), 3200);
    });
  }

  if (emhaNext) {
    emhaNext.addEventListener("click", () => { stopEmha(); setEmha(emhaIndex + 1); });
  }

  /* Chapter 04: complexity ----------------------------------------------- */
  const benchmarks = ["InjecAgent", "ToolEmu", "AgentDojo", "AgentHarm", "ASB", "DTap", "OpenART"];
  const complexity = [
    { label: "Tool calls", title: "Tool calls", values: [1, 3, 2, 3.5, 2, 15, 97], max: 100, insight: "Median number of agent-issued tool calls per task; each call counts as one operation." },
    { label: "Dependency depth", title: "Longest sequential dependency chain", values: [1, 2.5, 2, 3, 2, 2, 32], max: 35, insight: "Deeper dependency chains give an early state more chances to influence later decisions." },
    { label: "Parallel width", title: "Largest independent operation set", values: [1, 1, 1, 1.5, 1, 1.5, 12.5], max: 14, insight: "Parallel width describes workflow branching; branches can recombine and combine state effects." },
    { label: "State objects", title: "State objects accessed", values: [1, 3, 1, 3.5, 2, 2.5, 96.5], max: 100, insight: "More state objects mean evaluation has to track a wider set of persistent state." },
    { label: "File formats", title: "Persistent file format types", values: [0, 0, 0, 0, 0, 1, 7.5], max: 8, insight: "Cross-format material runs through the task. These are task-level medians, so fractional values are possible." }
  ];
  const complexityTabs = $$(".complexity-tab");
  const complexityBars = $$("#complexity-bars .bar-row");
  const complexityTitle = $("#complexity-chart-title");
  const complexityInsight = $("#complexity-insight");
  const complexityAxis = $("#complexity-axis");

  function formatNumber(value) {
    return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(1)));
  }

  function setComplexity(index) {
    const data = complexity[index];
    if (!data) return;
    complexityTabs.forEach((tab, i) => {
      const active = i === index;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    const panel = $("#complexity-panel");
    if (panel) panel.setAttribute("aria-labelledby", "complexity-tab-" + index);
    if (complexityTitle) complexityTitle.textContent = data.title;
    if (complexityInsight) {
      complexityInsight.innerHTML = "<strong>" + data.values[6] + "</strong><span>" + data.insight + "</span>";
    }
    complexityBars.forEach((row, i) => {
      const value = data.values[i];
      const bar = $(".bar", row);
      const label = $(".bar-value", row);
      if (bar) bar.style.width = Math.max(0, Math.min(100, (100 * value) / data.max)) + "%";
      if (label) label.textContent = formatNumber(value);
      row.setAttribute("aria-label", benchmarks[i] + ": " + formatNumber(value));
    });
    if (complexityAxis) {
      complexityAxis.innerHTML = [0, data.max / 2, data.max].map((value) => "<span>" + formatNumber(value) + "</span>").join("");
    }
  }

  if (complexityTabs.length) {
    complexityTabs.forEach((tab, i) => tab.addEventListener("click", () => setComplexity(i)));
    const tablist = $("#complexity-tabs");
    if (tablist) {
      tablist.addEventListener("keydown", (event) => {
        const current = complexityTabs.indexOf(document.activeElement);
        if (current < 0) return;
        let next = null;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (current + 1) % complexityTabs.length;
        if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (current - 1 + complexityTabs.length) % complexityTabs.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = complexityTabs.length - 1;
        if (next === null) return;
        event.preventDefault();
        setComplexity(next);
        complexityTabs[next].focus();
      });
    }
    setComplexity(0);
  }

  /* Chapter 05: matrix --------------------------------------------------- */
  const matrixCells = $$(".matrix-cell");
  const matrixModels = $$("#matrix thead th").slice(1).map((th) => th.textContent.trim());
  const matrixAsrButton = $("#metric-asr");
  const matrixCompButton = $("#metric-comp");
  const matrixHint = $("#matrix-hint");
  const matrixLegend = $("#matrix-legend");
  const legendDescription = $("#legend-description");
  const selectionAgent = $("#selection-agent");
  const selectionModel = $("#selection-model");
  const selectionAsr = $("#selection-asr");
  const selectionComp = $("#selection-comp");

  const colorStops = {
    asr: [[229, 228, 208], [158, 174, 140]],
    comp: [[224, 232, 214], [139, 167, 140]]
  };

  function cellColor(value, metric) {
    const [low, high] = colorStops[metric];
    const t = Math.max(0, Math.min(1, value / 100));
    return "rgb(" + low.map((channel, i) => Math.round(channel + (high[i] - channel) * t)).join(",") + ")";
  }

  function updateMatrix() {
    const isAsr = matrixMetric === "asr";
    if (matrixAsrButton) matrixAsrButton.setAttribute("aria-pressed", String(isAsr));
    if (matrixCompButton) matrixCompButton.setAttribute("aria-pressed", String(!isAsr));
    if (matrixHint) matrixHint.textContent = isAsr ? "Higher ASR means the attack is more likely to succeed ↗" : "Higher completion means stronger benign capability ↗";
    if (legendDescription) legendDescription.textContent = isAsr ? "Darker means higher attack success" : "Darker means higher benign completion";

    matrixCells.forEach((cell) => {
      const value = Number(cell.dataset[matrixMetric]);
      const shown = isAsr ? value.toFixed(1) : value.toFixed(2);
      cell.textContent = shown;
      cell.style.setProperty("--cell-color", cellColor(value, matrixMetric));
      const agent = cell.closest("tr")?.querySelector("th")?.textContent || "";
      const model = matrixModels[Number(cell.dataset.model)] || "";
      cell.setAttribute("aria-label", agent + ", " + model + ", " + (isAsr ? "Strict ASR " : "benign completion ") + shown + " percent");
      const selected = Number(cell.dataset.agent) === selectedAgent && Number(cell.dataset.model) === selectedModel;
      cell.classList.toggle("selected", selected);
      cell.setAttribute("aria-pressed", String(selected));
    });

    $$("#matrix tfoot td").forEach((cell) => {
      const value = Number(cell.dataset[matrixMetric]);
      cell.textContent = isAsr ? value.toFixed(1) : value.toFixed(2);
    });

    if (matrixLegend) {
      matrixLegend.innerHTML = [0, 20, 40, 60, 80, 100]
        .map((value) => '<i style="background:' + cellColor(value, matrixMetric) + '"></i>')
        .join("");
    }
  }

  function selectCell(agent, model) {
    selectedAgent = agent;
    selectedModel = model;
    const cell = $('.matrix-cell[data-agent="' + agent + '"][data-model="' + model + '"]');
    if (!cell) return;
    if (selectionAgent) selectionAgent.textContent = cell.closest("tr")?.querySelector("th")?.textContent || "";
    if (selectionModel) selectionModel.textContent = matrixModels[model] || "";
    if (selectionAsr) selectionAsr.textContent = Number(cell.dataset.asr).toFixed(1) + "%";
    if (selectionComp) selectionComp.textContent = Number(cell.dataset.comp).toFixed(2) + "%";
    matrixCells.forEach((item) => {
      const selected = Number(item.dataset.agent) === agent && Number(item.dataset.model) === model;
      item.classList.toggle("selected", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
  }

  if (matrixCells.length) {
    matrixCells.forEach((cell) => {
      cell.addEventListener("click", () => selectCell(Number(cell.dataset.agent), Number(cell.dataset.model)));
    });

    const matrix = $("#matrix");
    if (matrix) {
      matrix.addEventListener("keydown", (event) => {
        const cell = event.target.closest(".matrix-cell");
        if (!cell) return;
        let agent = Number(cell.dataset.agent);
        let model = Number(cell.dataset.model);
        if (event.key === "ArrowRight") model = Math.min(4, model + 1);
        else if (event.key === "ArrowLeft") model = Math.max(0, model - 1);
        else if (event.key === "ArrowDown") agent = Math.min(14, agent + 1);
        else if (event.key === "ArrowUp") agent = Math.max(0, agent - 1);
        else if (event.key === "Home") model = 0;
        else if (event.key === "End") model = 4;
        else return;
        event.preventDefault();
        selectCell(agent, model);
        $('.matrix-cell[data-agent="' + agent + '"][data-model="' + model + '"]')?.focus();
      });
    }
  }

  if (matrixAsrButton) matrixAsrButton.addEventListener("click", () => { matrixMetric = "asr"; updateMatrix(); });
  if (matrixCompButton) matrixCompButton.addEventListener("click", () => { matrixMetric = "comp"; updateMatrix(); });

  if (matrixCells.length) {
    updateMatrix();
    selectCell(0, 0);
  }

  /* Citation ------------------------------------------------------------- */
  const copyButton = $("#copy-citation");
  const citation = $("#citation-content");
  if (copyButton && citation) {
    copyButton.addEventListener("click", async () => {
      const text = citation.textContent;
      try {
        await navigator.clipboard.writeText(text);
        toast("BibTeX copied");
      } catch (_) {
        const helper = document.createElement("textarea");
        helper.value = text;
        helper.setAttribute("readonly", "");
        helper.style.position = "fixed";
        helper.style.opacity = "0";
        document.body.appendChild(helper);
        helper.select();
        try { document.execCommand("copy"); toast("BibTeX copied"); }
        catch (error) { toast("Select the BibTeX below and copy it"); }
        helper.remove();
      }
    });
  }

  /* Housekeeping --------------------------------------------------------- */
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopTrace();
      stopEmha();
    }
  });
})();