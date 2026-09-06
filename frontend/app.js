let applications = [
  {
    id: 1,
    name: "Maya Rao",
    initials: "MR",
    color: "#d7f36b",
    income: 90000,
    debt: 18000,
    payment: 22000,
    employment: 48,
    credit: 760,
    status: "ready",
    reviewed: false,
  },
  {
    id: 2,
    name: "Arjun Mehta",
    initials: "AM",
    color: "#f6d36b",
    income: 55000,
    debt: 24000,
    payment: 19000,
    employment: 14,
    credit: 670,
    status: "attention",
    reviewed: false,
  },
  {
    id: 3,
    name: "Kiran Das",
    initials: "KD",
    color: "#f47762",
    income: 42000,
    debt: 26000,
    payment: 18000,
    employment: 5,
    credit: 595,
    status: "attention",
    reviewed: false,
  },
];

let selectedId = 1;
let apiConnected = false;
let currentReviewer = "Reviewer";
const rows = document.querySelector("#applicationRows");
const searchInput = document.querySelector("#searchInput");
const statusFilter = document.querySelector("#statusFilter");
const resultCount = document.querySelector("#resultCount");
const toast = document.querySelector("#toast");

const money = (value) => `$${value.toLocaleString("en-US")}`;
const dti = (application) => (application.debt + application.payment) / application.income;
const statusLabel = (application) => application.reviewed ? "Reviewed" : application.status === "ready" ? "Ready to review" : "Needs attention";
const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);

function updateSummary(summary) {
  document.querySelector("#needsReviewMetric").textContent = String(summary.needs_review).padStart(2, "0");
  document.querySelector("#medianDtiMetric").textContent = `${(summary.median_dti * 100).toFixed(1)}%`;
  document.querySelector("#evidenceMetric").textContent = `${Math.round(summary.evidence_coverage * 100)}%`;
}

function applyApiApplication(application) {
  return { ...application, initials: application.name.split(" ").map((part) => part[0]).join(""), color: application.id % 3 === 1 ? "#d7f36b" : application.id % 3 === 2 ? "#f6d36b" : "#f47762", reviewed: application.status === "reviewed" };
}

async function loadApplications(showMessage = false) {
  try {
    const response = await fetch("/api/applications");
    if (!response.ok) throw new Error(`API ${response.status}`);
    const [liveApplications, summaryResponse] = await Promise.all([
      response.json(),
      fetch("/api/analytics/summary"),
    ]);
    if (!liveApplications.length) throw new Error("No applications returned");
    applications = liveApplications.map(applyApiApplication);
    if (summaryResponse.ok) updateSummary(await summaryResponse.json());
    apiConnected = true;
    document.querySelector(".live-status").innerHTML = '<span class="status-dot"></span>API connected';
    renderRows();
    renderSelected();
    if (showMessage) showToast("Queue refreshed from PostgreSQL");
  } catch (error) {
    apiConnected = false;
    document.querySelector(".live-status").innerHTML = '<span class="status-dot"></span>Demo mode';
    if (showMessage) showToast("API unavailable; showing local demo data");
  }
}

function renderRows() {
  const query = searchInput.value.trim().toLowerCase();
  const filter = statusFilter.value;
  const visible = applications.filter((application) => {
    const matchesQuery = !query || application.name.toLowerCase().includes(query) || String(application.id).includes(query);
    const matchesStatus = filter === "all" || application.status === filter;
    return matchesQuery && matchesStatus;
  });

  rows.innerHTML = visible.length ? visible.map((application) => `
    <tr class="${application.id === selectedId ? "selected" : ""}" data-id="${application.id}">
      <td><div class="applicant-cell"><span class="applicant-avatar" style="background:${application.color}">${escapeHtml(application.initials)}</span><span class="applicant-name"><strong>${escapeHtml(application.name)}</strong><small>APP-${String(application.id).padStart(4, "0")}</small></span></div></td>
      <td class="mono">${money(application.income)}</td>
      <td class="mono">${(dti(application) * 100).toFixed(1)}%</td>
      <td class="mono">${application.credit}</td>
      <td><span class="status-pill ${application.reviewed ? "reviewed" : application.status}"><i></i>${statusLabel(application)}</span></td>
      <td><button class="open-button" data-open="${application.id}" type="button">Open <i data-lucide="arrow-up-right"></i></button></td>
    </tr>
  `).join("") : `<tr><td colspan="6" class="empty-state">No applications match this view.</td></tr>`;

  resultCount.textContent = `Showing ${visible.length} application${visible.length === 1 ? "" : "s"}`;
  rows.querySelectorAll("[data-open]").forEach((button) => button.addEventListener("click", () => selectApplication(Number(button.dataset.open))));
  lucide.createIcons();
}

function renderSelected() {
  const application = applications.find((item) => item.id === selectedId);
  const dtiValue = dti(application);
  const indicators = [
    ["Debt-to-income", `${(dtiValue * 100).toFixed(1)}%`, "Passes below 40% threshold", dtiValue <= .4],
    ["Credit score", String(application.credit), "Passes 650 minimum", application.credit >= 650],
    ["Employment history", `${application.employment} months`, "Passes 12 month minimum", application.employment >= 12],
  ];
  const passed = indicators.filter((item) => item[3]).length;
  const ready = passed === indicators.length;

  document.querySelector("#selectedName").textContent = application.name;
  document.querySelector("#selectedId").textContent = `Application #${application.id}`;
  document.querySelector("#selectedStatus").textContent = application.reviewed ? "Reviewed" : ready ? "Ready" : "Needs attention";
  document.querySelector("#selectedStatus").style.background = application.reviewed ? "#edf0f1" : ready ? "#e3f3de" : "#fff0cf";
  document.querySelector("#selectedStatus").style.color = application.reviewed ? "#68767c" : ready ? "#377440" : "#8b661a";
  document.querySelector("#scoreValue").textContent = `${passed}/3`;
  document.querySelector("#scoreRing").style.borderColor = ready ? "#d7f36b" : "#f6d36b";
  document.querySelector("#riskTitle").textContent = ready ? "Strong evidence" : "Needs attention";
  document.querySelector("#riskCopy").textContent = ready ? "All configured affordability indicators are passing." : "Some indicators need a qualified reviewer’s attention.";
  document.querySelector("#detailList").innerHTML = indicators.map(([label, value, hint, pass]) => `<div class="detail-row"><span class="detail-label"><span>${label}</span><small>${hint}</small></span><strong class="detail-value ${pass ? "pass" : "flag"}">${value} ${pass ? "✓" : "!"}</strong></div>`).join("");
  document.querySelector("#markReviewed").innerHTML = application.reviewed ? '<i data-lucide="rotate-ccw"></i>Reopen review' : '<i data-lucide="check"></i>Mark reviewed';
  lucide.createIcons();
}

function selectApplication(id) {
  selectedId = id;
  renderRows();
  renderSelected();
  loadFeatureData();
  document.querySelector(".review-panel").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function selectedApplication() {
  return applications.find((item) => item.id === selectedId);
}

async function loadFeatureData() {
  const application = selectedApplication();
  if (!application) return;
  document.querySelector("#simIncome").value = application.income;
  document.querySelector("#simDebt").value = application.debt;
  document.querySelector("#simPayment").value = application.payment;
  if (!apiConnected) {
    renderFairness([{ cohort: "credit_650_plus", applications: 2, reviewed_rate: 0 }, { cohort: "credit_below_650", applications: 1, reviewed_rate: 0 }]);
    return;
  }
  try {
    const [debate, documents, audit, repayments, fairness] = await Promise.all([
      fetch(`/api/applications/${selectedId}/debate`).then((response) => response.json()),
      fetch(`/api/applications/${selectedId}/documents`).then((response) => response.json()),
      fetch(`/api/applications/${selectedId}/audit`).then((response) => response.json()),
      fetch("/api/monitoring/repayments").then((response) => response.json()),
      fetch("/api/analytics/fairness").then((response) => response.json()),
    ]);
    renderDebate(debate.specialists);
    renderDocuments(documents);
    renderAudit(audit);
    renderRepayments(repayments);
    renderFairness(fairness.groups);
  } catch (error) {
    showToast("Some monitoring data is unavailable");
  }
}

function renderDebate(specialists) {
  document.querySelector("#debateList").innerHTML = specialists.map((specialist) => `<div class="debate-row"><span class="agent-orb">${specialist.name[0]}</span><span><strong>${specialist.name}</strong><small>${specialist.reason}</small></span><b class="${specialist.position === "pass" ? "pass-text" : "flag-text"}">${specialist.position}</b></div>`).join("");
}

function renderDocuments(documents) {
  document.querySelector("#documentList").innerHTML = documents.length ? documents.map((document) => `<span><i data-lucide="file-text"></i>${document.file_name}<b>${document.status}</b></span>`).join("") : "<span>No documents uploaded in this session.</span>";
  lucide.createIcons();
}

function renderAudit(events) {
  document.querySelector("#auditList").innerHTML = events.length ? events.map((event) => `<div class="audit-row"><span class="audit-dot"></span><span><strong>${escapeHtml(event.event_type.replaceAll("_", " "))}</strong><small>${escapeHtml(event.note || "No note")} · ${escapeHtml(event.reviewer)}</small></span><time>${new Date(event.created_at).toLocaleString()}</time></div>`).join("") : "<span>No events recorded for this application.</span>";
}

function renderRepayments(items) {
  document.querySelector("#repaymentList").innerHTML = items.map((item) => `<div class="pulse-row"><span>${item.applicant_name}</span><b class="${item.health === "on_track" ? "on-track" : "watch"}">${item.health === "on_track" ? "On track" : "Watch"}</b><span>${item.amount_due ? Math.round((item.amount_paid / item.amount_due) * 100) : 0}%</span></div>`).join("");
}

function renderFairness(groups) {
  document.querySelector("#fairnessList").innerHTML = groups.map((group) => `<div class="fairness-row"><span>${group.cohort.replaceAll("_", " ")}</span><strong>${group.applications}</strong><span>${Math.round(group.reviewed_rate * 100)}% reviewed</span></div>`).join("");
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2600);
}

function showWorkspace(username) {
  currentReviewer = username;
  document.querySelector("#reviewerName").textContent = username;
  document.querySelector("#loginScreen").hidden = true;
  document.querySelector(".app-shell").hidden = false;
  renderRows();
  renderSelected();
  loadApplications();
  loadFeatureData();
}

async function signIn(event) {
  event.preventDefault();
  const error = document.querySelector("#loginError");
  error.textContent = "";
  try {
    const response = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: document.querySelector("#loginUsername").value.trim(), password: document.querySelector("#loginPassword").value }) });
    if (!response.ok) throw new Error("Invalid username or password");
    const user = await response.json();
    showWorkspace(user.username);
  } catch (signInError) {
    error.textContent = signInError.message;
  }
}

searchInput.addEventListener("input", renderRows);
statusFilter.addEventListener("change", renderRows);
document.querySelector("#clearFilters").addEventListener("click", () => { searchInput.value = ""; statusFilter.value = "all"; renderRows(); });
document.querySelector("#exportButton").addEventListener("click", () => {
  const query = searchInput.value.trim().toLowerCase();
  const filter = statusFilter.value;
  const visible = applications.filter((application) => (!query || application.name.toLowerCase().includes(query) || String(application.id).includes(query)) && (filter === "all" || application.status === filter));
  const csv = ["Application ID,Applicant,Monthly income,Monthly debt,Requested payment,DTI,Credit score,Employment months,Status", ...visible.map((application) => [application.id, application.name, application.income, application.debt, application.payment, `${(dti(application) * 100).toFixed(1)}%`, application.credit, application.employment, statusLabel(application)].map((value) => `"${String(value).replaceAll('"', '""')}"`).join(","))].join("\n");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  link.download = `clearline-applications-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
  showToast(`Exported ${visible.length} application${visible.length === 1 ? "" : "s"}`);
});
document.querySelector("#refreshButton").addEventListener("click", async (event) => { event.currentTarget.querySelector("svg")?.classList.add("spin"); await loadApplications(true); window.setTimeout(() => event.currentTarget.querySelector("svg")?.classList.remove("spin"), 500); });
document.querySelector("#markReviewed").addEventListener("click", async () => {
  const application = applications.find((item) => item.id === selectedId);
  const nextReviewed = !application.reviewed;
  if (apiConnected) {
    try {
      const response = await fetch(`/api/applications/${selectedId}/review?reviewed=${nextReviewed}`, { method: "POST" });
      if (!response.ok) throw new Error(`API ${response.status}`);
      Object.assign(application, applyApiApplication(await response.json()));
    } catch (error) {
      showToast("Could not save review state");
      return;
    }
  } else {
    application.reviewed = nextReviewed;
  }
  showToast(application.reviewed ? `${application.name} marked as reviewed` : `${application.name} reopened`);
  renderRows();
  renderSelected();
});
document.querySelector("#moreActions").addEventListener("click", () => {
  document.querySelector("#knowledgeModal").hidden = false;
  document.querySelector("#knowledgeQuery").focus();
});
document.querySelector("#closeKnowledge").addEventListener("click", () => { document.querySelector("#knowledgeModal").hidden = true; });
document.querySelector("#knowledgeForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = document.querySelector("#knowledgeQuery").value.trim();
  const resultsContainer = document.querySelector("#knowledgeResults");
  if (!apiConnected) { resultsContainer.innerHTML = "<span>Start the API to search the local knowledge base.</span>"; return; }
  resultsContainer.innerHTML = "<span>Searching...</span>";
  try {
    const response = await fetch(`/api/knowledge/search?q=${encodeURIComponent(query)}`);
    if (!response.ok) throw new Error("Search failed");
    const results = await response.json();
    resultsContainer.innerHTML = results.length ? results.map((result) => `<article class="knowledge-result"><strong>${escapeHtml(result.metadata?.source || "Knowledge note")}</strong><p>${escapeHtml(result.document)}</p></article>`).join("") : "<span>No matching knowledge notes found.</span>";
  } catch (error) { resultsContainer.innerHTML = "<span>Knowledge search is unavailable.</span>"; }
});
document.querySelector("#auditForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const noteInput = document.querySelector("#auditNote");
  const note = noteInput.value.trim();
  if (!note) return;
  if (!apiConnected) { showToast("Start the API to save reviewer notes"); return; }
  const response = await fetch(`/api/applications/${selectedId}/audit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ event_type: "reviewer_note", reviewer: currentReviewer, note }) });
  if (!response.ok) { showToast("Could not save reviewer note"); return; }
  noteInput.value = "";
  await loadFeatureData();
  showToast("Reviewer note added");
});
document.querySelector("#simulateButton").addEventListener("click", async () => {
  const payload = { monthly_income: Number(document.querySelector("#simIncome").value), monthly_debt: Number(document.querySelector("#simDebt").value), requested_payment: Number(document.querySelector("#simPayment").value) };
  let result;
  if (apiConnected) {
    const response = await fetch(`/api/applications/${selectedId}/simulate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!response.ok) { showToast("Simulation failed"); return; }
    result = await response.json();
  } else {
    result = { debt_to_income_ratio: (payload.monthly_debt + payload.requested_payment) / payload.monthly_income };
  }
  document.querySelector("#simDti").textContent = `${(result.debt_to_income_ratio * 100).toFixed(1)}%`;
  document.querySelector("#simStatus").textContent = result.debt_to_income_ratio <= .4 ? "Below the 40% indicator threshold" : "Above the 40% indicator threshold";
  showToast("What-if simulation complete; stored data unchanged");
});
document.querySelector("#debateButton").addEventListener("click", async () => { if (!apiConnected) { showToast("Start the API to run specialist review"); return; } await loadFeatureData(); showToast("Specialist perspectives refreshed"); });
document.querySelector("#aiReviewButton").addEventListener("click", async (event) => {
  if (!apiConnected) { showToast("Start PostgreSQL and the local AI model first"); return; }
  const button = event.currentTarget;
  const answer = document.querySelector("#aiAnswer");
  button.disabled = true;
  button.querySelector("svg")?.classList.add("spin");
  answer.hidden = false;
  answer.textContent = "The Manager agent is consulting the loan-risk specialist...";
  try {
    const response = await fetch(`/api/applications/${selectedId}/ai-review`, { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "AI review unavailable");
    answer.textContent = result.answer;
    showToast(`AI review completed with ${result.model}`);
  } catch (error) {
    answer.textContent = error.message;
    showToast("AI review unavailable");
  } finally {
    button.disabled = false;
    button.querySelector("svg")?.classList.remove("spin");
  }
});
document.querySelector("#documentInput").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (!apiConnected) { document.querySelector("#documentList").innerHTML = `<span><i data-lucide="file-text"></i>${file.name}<b>demo queued</b></span>`; lucide.createIcons(); showToast("Document queued in demo mode"); return; }
  const form = new FormData();
  form.append("document", file);
  const response = await fetch(`/api/applications/${selectedId}/documents`, { method: "POST", body: form });
  if (!response.ok) { showToast("Document upload failed"); return; }
  await loadFeatureData();
  showToast("Document uploaded; extraction queued");
});

lucide.createIcons();
document.querySelector("#loginForm").addEventListener("submit", signIn);
document.querySelector("#logoutButton").addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  document.querySelector(".app-shell").hidden = true;
  document.querySelector("#loginScreen").hidden = false;
  document.querySelector("#loginPassword").value = "";
});
document.querySelector(".app-shell").hidden = true;
fetch("/api/auth/me").then((response) => response.ok ? response.json() : Promise.reject()).then((user) => showWorkspace(user.username)).catch(() => document.querySelector("#loginUsername").focus());
