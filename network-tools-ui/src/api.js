export async function fetchHistory() {
  const res = await fetch("http://127.0.0.1:8001/api/history");
  if (!res.ok) throw new Error("Failed to fetch history");
  return res.json();
}

export async function sendMessage(message) {
  const res = await fetch("http://127.0.0.1:8001/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error("Message failed");
  return res.json();
}

export async function generateReportAndDownload() {
  const res = await fetch("http://127.0.0.1:8001/api/report", { method: "POST" });
  if (!res.ok) throw new Error("Failed to generate report");
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "session_report.pdf";
  link.click();
}

export async function clearChatHistory() {
  const res = await fetch("http://127.0.0.1:8001/api/history/clear", { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to clear chat history");
  return res.json();
}