// Small helpers for reading Claude's answers. Pure, no page access.
export function adStatus(ad) {
  const s = ad.effective_status;
  if (s === "ACTIVE") return ["on", "On"];
  if (s === "IN_PROCESS" || s === "PENDING_REVIEW") return ["review", "In review"];
  if (s === "DISAPPROVED" || s === "WITH_ISSUES") return ["bad", "Rejected"];
  if (s === "ARCHIVED") return ["", "Archived"];
  return ["", "Off"];
}

const squash = (text) => String(text || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

// A report as an intro and its "## " sections. The opening line usually repeats the answer shown
// above it, so a near-copy is dropped.
export function reportParts(body, summary) {
  const sections = [];
  const intro = [];
  let at = null;
  String(body || "").replace(/\r\n/g, "\n").split("\n").forEach((line) => {
    const h = line.match(/^##\s+(.*)$/);
    if (h) { at = { title: h[1].trim(), body: [] }; sections.push(at); return; }
    (at ? at.body : intro).push(line);
  });
  let lead = intro.join("\n").trim();
  const first = squash(lead.split("\n\n")[0]);
  const said = squash(summary);
  if (first && said && (said.includes(first) || first.includes(said))) lead = lead.split("\n\n").slice(1).join("\n\n").trim();
  return { intro: lead, sections: sections.map((s) => ({ title: s.title, body: s.body.join("\n").trim() })) };
}
