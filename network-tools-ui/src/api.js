// src/api.js
const API_BASE = import.meta.env.VITE_API_BASE;

export async function fetchHistory() {
  const res = await fetch(`${API_BASE}/api/history`);
  if (!res.ok) throw new Error("Failed to load history");
  return res.json();
}

export async function sendMessage(message) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error("Chat failed");
  return res.json();
}

export async function generateReportAndDownload() {
  const res = await fetch(`${API_BASE}/api/report`, { method: "POST" });
  if (!res.ok) throw new Error("Report generation failed");
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "security_report.pdf";
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
