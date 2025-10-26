import { useEffect, useState } from "react";
import { fetchHistory, sendMessage, generateReportAndDownload, clearChatHistory } from "./api";
import "./app.css";

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [clearing, setClearing] = useState(false);

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

  const onClearChat = async () => {
    setClearing(true);
    try {
      await clearChatHistory();
      setMessages([]);
    } catch (e) {
      console.error(e);
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="container network-grid">
      <header className="app-header glass">
        <div className="title">
          <svg
            className="title-icon"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              fill="currentColor"
              d="M3 7h18v2H3V7zm2 4h14v2H5v-2zm4 4h6v2H9v-2z"
            />
          </svg>
          <h2>Network Tools Assistant</h2>
        </div>

        <div className="header-actions">
          <div className={`status-pill ${loading ? "busy" : "ok"}`}>
            <span className="dot" />
            <span className="label">{loading ? "Processing" : "Agent Online"}</span>
          </div>

          <button onClick={onGenerateReport} disabled={reporting}>
            {reporting ? "Generating..." : "Generate Report"}
          </button>

          <button onClick={onClearChat} disabled={clearing}>
            {clearing ? "Clearing..." : "Delete Chat History"}
          </button>
        </div>
      </header>

      <div className="chat">
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === "assistant" && (
              <div className="avatar server" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24">
                  <path
                    fill="currentColor"
                    d="M4 6h16v4H4V6zm0 8h16v4H4v-4zM6 7h4v2H6V7zm0 8h4v2H6v-2z"
                  />
                </svg>
              </div>
            )}
            <div className={`bubble glass ${m.role}`}>
              <div className="meta">{m.role === "user" ? "You" : "Agent"}</div>
              <div className="content">{m.content}</div>
            </div>
            {m.role === "user" && (
              <div className="avatar user" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24">
                  <path
                    fill="currentColor"
                    d="M12 12a5 5 0 1 0-5-5a5 5 0 0 0 5 5Zm0 2c-4.418 0-8 2.239-8 5v1h16v-1c0-2.761-3.582-5-8-5Z"
                  />
                </svg>
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="msg assistant">
            <div className="avatar server" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24">
                <path
                  fill="currentColor"
                  d="M4 6h16v4H4V6zm0 8h16v4H4v-4zM6 7h4v2H6V7zm0 8h4v2H6v-2z"
                />
              </svg>
            </div>
            <div className="bubble glass typing">
              <span className="dot d1" />
              <span className="dot d2" />
              <span className="dot d3" />
            </div>
          </div>
        )}
      </div>

      <div className="composer glass">
        <input
          placeholder="Ask something..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => (e.key === "Enter" ? onSend() : null)}
        />
        <button onClick={onSend} disabled={loading}>
          {loading ? "Sending..." : "Send"}
        </button>
      </div>
    </div>
  );
}
