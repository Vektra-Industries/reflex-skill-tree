const TIER_COLOR = ["var(--seed)", "var(--novice)", "var(--adept)", "var(--expert)", "var(--master)"];
const TIER_NAME = ["Seed", "Novice", "Adept", "Expert", "Master"];
const NODE_W = 150, NODE_H = 46, COL_GAP = 40, ROW_GAP = 70, BRANCH_GAP = 60;

function nodesOf(tree) {
  const out = {};
  for (const [bid, branch] of Object.entries(tree.branches || {})) {
    for (const [nid, raw] of Object.entries(branch.nodes || {})) {
      out[nid] = Object.assign({ id: nid, branch: bid }, raw);
    }
  }
  return out;
}

function render(tree) {
  const emptyEl = document.getElementById("empty");
  if (emptyEl) emptyEl.style.display = "none";
  const nodes = nodesOf(tree);
  const nodeIds = Object.keys(nodes);
  const statsEl = document.getElementById("stats");
  if (statsEl) {
    statsEl.textContent =
      `${nodeIds.length} node(s) · ${Object.keys(tree.branches || {}).length} branch(es) · ${tree.points || 0}pt unspent`;
  }

  // Longest-path-from-root depth per node, within its own branch, using
  // prerequisites (AND) + prerequisites_any (OR) edges together for layout
  // purposes only (both just mean "draw an edge here").
  function depthOf(nid, seen) {
    seen = seen || new Set();
    if (seen.has(nid)) return 0; // cycle guard, shouldn't happen in a valid tree
    seen.add(nid);
    const n = nodes[nid];
    if (!n) return 0;
    const prereqs = [...(n.prerequisites || []), ...(n.prerequisites_any || [])];
    if (prereqs.length === 0) return 0;
    return 1 + Math.max(...prereqs.map((p) => (nodes[p] ? depthOf(p, new Set(seen)) : 0)));
  }

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.innerHTML = `<defs><marker id="arrow" markerWidth="8" markerHeight="8"
    refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#4b5563"/></marker></defs>`;

  let yCursor = 10;
  let maxX = 600;
  const positions = {}; // nid -> {x, y}

  for (const [bid, branch] of Object.entries(tree.branches || {})) {
    const branchNodeIds = nodeIds.filter((nid) => nodes[nid].branch === bid);
    if (branchNodeIds.length === 0) continue;
    const byDepth = {};
    for (const nid of branchNodeIds) {
      const d = depthOf(nid);
      (byDepth[d] = byDepth[d] || []).push(nid);
    }
    const maxDepth = Math.max(...Object.keys(byDepth).map(Number));
    const branchHeight = (maxDepth + 1) * ROW_GAP + 30;

    const title = document.createElementNS(svgNS, "text");
    title.setAttribute("x", 10);
    title.setAttribute("y", yCursor + 14);
    title.setAttribute("class", "branch-title");
    const level = (tree.branch_usage || {})[bid] !== undefined
      ? Math.floor((tree.branch_usage[bid] || 0) / 5) : 0;
    title.textContent = `${branch.title || bid}  (usage level ${level})`;
    svg.appendChild(title);

    for (const [depthStr, idsAtDepth] of Object.entries(byDepth)) {
      const depth = Number(depthStr);
      idsAtDepth.forEach((nid, i) => {
        const x = 10 + i * (NODE_W + COL_GAP);
        const y = yCursor + 30 + depth * ROW_GAP;
        positions[nid] = { x, y };
        maxX = Math.max(maxX, x + NODE_W + 20);
      });
    }
    yCursor += branchHeight + BRANCH_GAP;
  }

  // edges first so nodes draw on top
  for (const nid of nodeIds) {
    const n = nodes[nid];
    const to = positions[nid];
    if (!to) continue;
    for (const p of n.prerequisites || []) {
      const from = positions[p];
      if (!from) continue;
      drawEdge(svg, from, to, "edge");
    }
    for (const p of n.prerequisites_any || []) {
      const from = positions[p];
      if (!from) continue;
      drawEdge(svg, from, to, "edge-any");
    }
  }

  for (const nid of nodeIds) {
    const n = nodes[nid];
    const pos = positions[nid];
    if (!pos) continue;
    const g = document.createElementNS(svgNS, "g");
    g.setAttribute("data-node-id", nid);
    const rect = document.createElementNS(svgNS, "rect");
    rect.setAttribute("x", pos.x);
    rect.setAttribute("y", pos.y);
    rect.setAttribute("width", NODE_W);
    rect.setAttribute("height", NODE_H);
    rect.setAttribute("rx", 6);
    rect.setAttribute("fill", TIER_COLOR[n.tier || 0]);
    rect.setAttribute("stroke", n.allocated ? "#fff" : "#1f2937");
    rect.setAttribute("class", "node-box" + (n.allocated ? " allocated" : ""));
    g.appendChild(rect);

    const title = document.createElementNS(svgNS, "text");
    title.setAttribute("x", pos.x + 8);
    title.setAttribute("y", pos.y + 18);
    title.setAttribute("class", "node-title");
    title.textContent = truncate(n.title || nid, 20);
    g.appendChild(title);

    const tierText = document.createElementNS(svgNS, "text");
    tierText.setAttribute("x", pos.x + 8);
    tierText.setAttribute("y", pos.y + 34);
    tierText.setAttribute("class", "node-tier");
    const reps = (n.practice && n.practice.reps) || 0;
    tierText.textContent = `T${n.tier || 0} ${TIER_NAME[n.tier || 0]} · ${reps} reps`;
    g.appendChild(tierText);

    const titleEl = document.createElementNS(svgNS, "title");
    titleEl.textContent = `${nid}\n${n.description || ""}`;
    g.appendChild(titleEl);

    svg.appendChild(g);
  }

  svg.setAttribute("width", maxX);
  svg.setAttribute("height", yCursor + 20);
  const wrap = document.getElementById("canvas-wrap");
  wrap.innerHTML = "";
  wrap.appendChild(svg);
  return svg;
}

function drawEdge(svg, from, to, cls) {
  const svgNS = "http://www.w3.org/2000/svg";
  const path = document.createElementNS(svgNS, "path");
  const x1 = from.x + NODE_W / 2, y1 = from.y + NODE_H;
  const x2 = to.x + NODE_W / 2, y2 = to.y;
  const midY = (y1 + y2) / 2;
  path.setAttribute("d", `M${x1},${y1} C${x1},${midY} ${x2},${midY} ${x2},${y2}`);
  path.setAttribute("class", cls);
  svg.appendChild(path);
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function wireFileInput() {
  const fileInput = document.getElementById("file");
  if (!fileInput) return;
  fileInput.addEventListener("change", (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const data = JSON.parse(reader.result);
        render(data);
      } catch (err) {
        const emptyEl = document.getElementById("empty");
        emptyEl.textContent = "Could not parse that file as JSON: " + err.message;
        emptyEl.style.display = "block";
      }
    };
    reader.readAsText(f);
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { nodesOf, render, drawEdge, truncate };
}
