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
const rows = document.querySelector("#applicationRows");
const searchInput = document.querySelector("#searchInput");
const statusFilter = document.querySelector("#statusFilter");
const resultCount = document.querySelector("#resultCount");
const toast = document.querySelector("#toast");

const money = (value) => `$${value.toLocaleString("en-US")}`;
const dti = (application) => (application.debt + application.payment) / application.income;
const statusLabel = (application) => application.reviewed ? "Reviewed" : application.status === "ready" ? "Ready to review" : "Needs attention";

function applyApiApplication(application) {
  return { ...application, initials: application.name.split(" ").map((part) => part[0]).join(""), color: application.id % 3 === 1 ? "#d7f36b" : application.id % 3 === 2 ? "#f6d36b" : "#f47762", reviewed: application.status === "reviewed" };
}

async function loadApplications(showMessage = false) {
  try {
    const response = await fetch("/api/applications");
    if (!response.ok) throw new Error(`API ${response.status}`);
    const liveApplications = await response.json();
    if (!liveApplications.length) throw new Error("No applications returned");
    applications = liveApplications.map(applyApiApplication);
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
      <td><div class="applicant-cell"><span class="applicant-avatar" style="background:${application.color}">${application.initials}</span><span class="applicant-name"><strong>${application.name}</strong><small>APP-${String(application.id).padStart(4, "0")}</small></span></div></td>
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
  document.querySelector(".review-panel").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2600);
}

searchInput.addEventListener("input", renderRows);
statusFilter.addEventListener("change", renderRows);
document.querySelector("#clearFilters").addEventListener("click", () => { searchInput.value = ""; statusFilter.value = "all"; renderRows(); });
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
document.querySelector("#moreActions").addEventListener("click", async () => {
  if (!apiConnected) { showToast("Start the API to search the knowledge base"); return; }
  try {
    const response = await fetch("/api/knowledge/search?q=loan+review");
    const results = await response.json();
    showToast(results.length ? `Found ${results.length} knowledge notes` : "No knowledge notes found");
  } catch (error) { showToast("Knowledge search unavailable"); }
});

lucide.createIcons();
renderRows();
renderSelected();
loadApplications();
