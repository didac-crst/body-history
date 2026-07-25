(function () {
  const el = document.getElementById("chart");
  if (!el || !window.echarts) return;

  const chart = echarts.init(el);
  const metricSelect = document.getElementById("metric");
  const rangeSelect = document.getElementById("range");

  async function load() {
    const metric = metricSelect.value;
    const range = rangeSelect.value;
    const res = await fetch(`/api/chart-data/?metric=${encodeURIComponent(metric)}&range=${encodeURIComponent(range)}`);
    const data = await res.json();
    const raw = data.raw.map((p) => [p.t, p.v]);
    const trend = data.trend.map((p) => [p.t, p.v]);
    const series = [
      {
        name: "Raw",
        type: "scatter",
        data: raw,
        symbolSize: 7,
        itemStyle: { color: "#0f6a5a", opacity: 0.55 },
      },
      {
        name: "Trend",
        type: "line",
        data: trend,
        showSymbol: false,
        lineStyle: { width: 2.5, color: "#b45309" },
        smooth: 0.2,
      },
    ];
    if (data.target != null) {
      series.push({
        name: "Target",
        type: "line",
        markLine: {
          symbol: "none",
          label: { formatter: "target" },
          data: [{ yAxis: data.target }],
          lineStyle: { color: "#335c67", type: "dashed" },
        },
      });
    }
    chart.setOption(
      {
        animationDuration: 450,
        grid: { left: 48, right: 24, top: 40, bottom: 48 },
        tooltip: { trigger: "axis" },
        legend: { top: 8 },
        xAxis: { type: "time" },
        yAxis: { type: "value", scale: true },
        series,
      },
      true
    );
  }

  metricSelect.addEventListener("change", load);
  rangeSelect.addEventListener("change", load);
  window.addEventListener("resize", () => chart.resize());
  load();
})();
