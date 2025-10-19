// src/App.jsx
import { useEffect, useState } from "react";
import { fetchHistory, sendMessage, generateReportAndDownload } from "./api";
import "./app.css";

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [reporting, setReporting] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchHistory();
        setMessages(data.messages || []);
      } catch (e) {
        console.error(e);
      }
    })();
  }, []);

  const onSend = async () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    setLoading(true);
    try {
      setMessages((m) => [...m, { role: "user", content: text }]);
      const { reply } = await sendMessage(text);
      setMessages((m) => [...m, { role: "assistant", content: reply }]);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const onGenerateReport = async () => {
    setReporting(true);
    try {
      await generateReportAndDownload();
    } catch (e) {
      console.error(e);
    } finally {
      setReporting(false);
    }
  };

  return (
    <div className="container">
      <header>
        <h2>Network Tools Assistant</h2>
        <button onClick={onGenerateReport} disabled={reporting}>
          {reporting ? "Generating..." : "Generate Report (PDF)"}
        </button>
      </header>

      <div className="chat">
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">{m.content}</div>
          </div>
        ))}
      </div>

      <div className="composer">
        <input
          placeholder="Ask something..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" ? onSend() : null}
        />
        <button onClick={onSend} disabled={loading}>
          {loading ? "Sending..." : "Send"}
        </button>
      </div>
    </div>
  );
}