(function () {
  const historyEl = document.getElementById("compass-history-chart");
  const rangeSelect = document.getElementById("compass-range");
  const modeSelect = document.getElementById("compass-mode");
  const metaEl = document.getElementById("compass-history-meta");
  const toggles = document.querySelectorAll("#compass-series-toggles input[type=checkbox]");

  const seriesMeta = {
    alignment: { name: "Overall", color: "#0f6a5a" },
    weight: { name: "Weight score", color: "#5c6a75" },
    body_fat: { name: "Body fat score", color: "#b45309" },
    muscle: { name: "Muscle score", color: "#335c67" },
  };

  let chart = null;
  let lastPoints = [];

  function selectedSeries() {
    const keys = Array.from(toggles)
      .filter((el) => el.checked)
      .map((el) => el.dataset.series);
    // Draw overall last so it sits on top of component lines.
    return [
      ...keys.filter((k) => k !== "alignment"),
      ...(keys.includes("alignment") ? ["alignment"] : []),
    ];
  }

  function renderChart(points) {
    if (!historyEl || !window.echarts) return;
    if (!chart) chart = echarts.init(historyEl);
    const keys = selectedSeries();
    const series = keys.map((key) => {
      const isOverall = key === "alignment";
      return {
        name: seriesMeta[key].name,
        type: "line",
        zlevel: isOverall ? 2 : 1,
        z: isOverall ? 10 : 1,
        showSymbol: isOverall ? points.length < 60 : points.length < 40,
        symbolSize: isOverall ? 9 : 5,
        data: points
          .map((p) => [p.t, p[key]])
          .filter((row) => row[1] != null),
        lineStyle: {
          width: isOverall ? 4.5 : 1.35,
          color: seriesMeta[key].color,
          opacity: isOverall ? 1 : 0.45,
        },
        itemStyle: {
          color: seriesMeta[key].color,
          opacity: isOverall ? 1 : 0.5,
        },
        areaStyle: isOverall
          ? { color: "rgba(15, 106, 90, 0.14)", origin: "start" }
          : undefined,
        emphasis: {
          focus: isOverall ? "series" : "none",
          lineStyle: { width: isOverall ? 5.5 : 1.6 },
        },
        smooth: 0.15,
      };
    });
    chart.setOption(
      {
        animationDuration: 400,
        grid: { left: 48, right: 24, top: 48, bottom: 48 },
        tooltip: { trigger: "axis" },
        legend: { top: 8 },
        xAxis: { type: "time" },
        yAxis: { type: "value", min: 0, max: 100, scale: false, name: "Score" },
        series,
      },
      true
    );
  }

  async function loadHistory() {
    if (!rangeSelect || !modeSelect) return;
    const range = rangeSelect.value;
    const mode = modeSelect.value;
    const res = await fetch(
      `/api/compass-history/?range=${encodeURIComponent(range)}&mode=${encodeURIComponent(mode)}`
    );
    const data = await res.json();
    lastPoints = data.points || [];
    if (metaEl) {
      const modeLabel =
        mode === "today" ? "recalculated with today’s target" : "historical targets per date";
      metaEl.textContent = `${data.count || 0} scored points · ${modeLabel}`;
    }
    renderChart(lastPoints);
  }

  if (rangeSelect && modeSelect) {
    rangeSelect.addEventListener("change", loadHistory);
    modeSelect.addEventListener("change", loadHistory);
    toggles.forEach((el) => el.addEventListener("change", () => renderChart(lastPoints)));
    window.addEventListener("resize", () => chart && chart.resize());
    loadHistory();
  }

  const form = document.getElementById("compass-sim-form");
  const results = document.getElementById("sim-results");
  const resetBtn = document.getElementById("sim-reset");
  const latest = window.COMPASS_LATEST || {};

  function fillLatest() {
    const w = document.getElementById("sim-weight");
    const f = document.getElementById("sim-fat");
    const m = document.getElementById("sim-muscle");
    if (w) w.value = latest.weight_kg != null ? latest.weight_kg : "";
    if (f) f.value = latest.body_fat_percent != null ? latest.body_fat_percent : "";
    if (m) m.value = latest.muscle_percent != null ? latest.muscle_percent : "";
  }

  function renderList(el, items, mapper) {
    if (!el) return;
    el.innerHTML = "";
    if (!items || !items.length) {
      const li = document.createElement("li");
      li.className = "meta";
      li.textContent = "None";
      el.appendChild(li);
      return;
    }
    items.forEach((item) => {
      const li = document.createElement("li");
      li.innerHTML = mapper(item);
      el.appendChild(li);
    });
  }

  async function runSimulate(event) {
    if (event) event.preventDefault();
    const params = new URLSearchParams();
    const weight = document.getElementById("sim-weight")?.value;
    const fat = document.getElementById("sim-fat")?.value;
    const muscle = document.getElementById("sim-muscle")?.value;
    if (weight) params.set("weight_kg", weight);
    if (fat) params.set("body_fat_percent", fat);
    if (muscle) params.set("muscle_percent", muscle);
    const res = await fetch(`/api/compass-simulate/?${params.toString()}`);
    const data = await res.json();
    if (!results) return;
    results.hidden = false;
    const align = document.getElementById("sim-alignment");
    if (align) align.textContent = data.alignment != null ? data.alignment : "—";
    const tbody = document.getElementById("sim-components");
    if (tbody) {
      tbody.innerHTML = "";
      (data.components || []).forEach((c) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${c.label}</td><td class="num">${
          c.value != null ? c.value : "—"
        }</td><td class="num">${c.score != null ? c.score : "—"}</td>`;
        tbody.appendChild(tr);
      });
    }
    renderList(
      document.getElementById("sim-opportunities"),
      data.opportunities,
      (o) =>
        `<strong>${o.title}</strong> <span class="meta">gain ${o.alignment_gain} → ${
          o.simulated_alignment != null ? o.simulated_alignment : "—"
        }</span><br>${o.explanation}`
    );
    renderList(
      document.getElementById("sim-milestones"),
      data.milestones,
      (m) => `<strong>${m.title}</strong><br><span class="meta">${m.detail}</span>`
    );
    const guidanceEl = document.getElementById("sim-guidance");
    if (guidanceEl) {
      renderList(
        guidanceEl,
        data.guidance,
        (g) => `<strong>${g.title}</strong><br><span class="meta">${g.body}</span>`
      );
    }
  }

  if (form) {
    form.addEventListener("submit", runSimulate);
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        fillLatest();
        runSimulate();
      });
    }
    if (latest.weight_kg != null) runSimulate();
  }
})();
