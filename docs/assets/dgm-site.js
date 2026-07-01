const proof = {
  scorePath: [
    { label: "Base", solved: 5, note: "initial agent" },
    { label: "Breakthrough 1", solved: 6, note: "abc387_c" },
    { label: "Breakthrough 2", solved: 7, note: "abc388_e" },
    { label: "Best", solved: 8, note: "abc389_d" },
  ],
  cards: [
    {
      label: "Benchmark",
      value: "LiveCodeBench",
      detail: "12 code-generation-lite problems with private scored tests",
    },
    {
      label: "Run boundary",
      value: "GCP VM",
      detail: "disposable worker, artifact sync, verified teardown",
    },
    {
      label: "Provider",
      value: "OpenRouter",
      detail: "qwen/qwen3-coder, 30.76M total tokens",
    },
    {
      label: "Improvements",
      value: "5",
      detail: "parent-relative score improvements in the archive",
    },
  ],
};

function renderChart() {
  const target = document.querySelector("#score-chart");
  if (!target) return;

  const width = 720;
  const height = 330;
  const padding = { top: 28, right: 34, bottom: 54, left: 54 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const maxSolved = 12;
  const xStep = plotWidth / (proof.scorePath.length - 1);

  const points = proof.scorePath.map((point, index) => {
    const x = padding.left + index * xStep;
    const y = padding.top + plotHeight - (point.solved / maxSolved) * plotHeight;
    return { ...point, x, y };
  });

  const line = points.map((point) => `${point.x},${point.y}`).join(" ");
  const grid = [0, 3, 6, 9, 12]
    .map((tick) => {
      const y = padding.top + plotHeight - (tick / maxSolved) * plotHeight;
      return `
        <line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="#d9e1ea" stroke-width="1" />
        <text x="18" y="${y + 5}" fill="#536274" font-size="13">${tick}</text>
      `;
    })
    .join("");

  const markers = points
    .map(
      (point) => `
        <g>
          <circle cx="${point.x}" cy="${point.y}" r="8" fill="#26706a" stroke="#ffffff" stroke-width="3" />
          <text x="${point.x}" y="${height - 24}" text-anchor="middle" fill="#536274" font-size="13">${point.label}</text>
          <text x="${point.x}" y="${point.y - 18}" text-anchor="middle" fill="#17202a" font-size="15" font-weight="760">${point.solved}/12</text>
        </g>
      `
    )
    .join("");

  target.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" aria-hidden="true">
      <rect x="0" y="0" width="${width}" height="${height}" rx="8" fill="#ffffff" />
      ${grid}
      <polyline points="${line}" fill="none" stroke="#345f91" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" />
      ${markers}
      <text x="${padding.left}" y="24" fill="#536274" font-size="13">Solved problems</text>
    </svg>
  `;
}

function renderCards() {
  const target = document.querySelector("#proof-grid");
  if (!target) return;

  target.innerHTML = proof.cards
    .map(
      (card) => `
        <article class="proof-card">
          <span>${card.label}</span>
          <strong>${card.value}</strong>
          <p>${card.detail}</p>
        </article>
      `
    )
    .join("");
}

renderChart();
renderCards();
