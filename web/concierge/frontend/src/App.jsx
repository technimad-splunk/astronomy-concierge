import { useEffect, useMemo, useRef, useState } from "react";

const apiBase = (import.meta.env.VITE_CONCIERGE_API_URL || "").trim();

function buildApiUrl(path) {
  if (apiBase) {
    return `${apiBase.replace(/\/$/, "")}${path}`;
  }
  return path;
}

function parseEventData(raw, fallback) {
  if (!raw) {
    return fallback;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

// Shared shopper id, kept in the `concierge_session` cookie on host `localhost`.
// Cookies on localhost ignore the port, so this value is shared with the
// Astronomy Shop storefront tab (:8080) — where an injected bridge script keeps
// the same cookie in sync with the storefront's localStorage session. Using it
// as the cart id makes carts shared across the storefront and concierge tabs.
const SHOPPER_COOKIE = "concierge_session";

function readShopperCookie() {
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + SHOPPER_COOKIE + "=([^;]*)")
  );
  return match ? decodeURIComponent(match[1]) : "";
}

function writeShopperCookie(value) {
  document.cookie = `${SHOPPER_COOKIE}=${encodeURIComponent(value)}; path=/; SameSite=Lax`;
}

// Resolve the shared shopper id: prefer an existing cookie (typically set from
// the storefront's real session); otherwise mint one and publish it so a
// storefront tab opened later adopts the same id.
function resolveShopperId() {
  const existing = readShopperCookie();
  if (existing) {
    return existing;
  }
  const minted =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `concierge-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  writeShopperCookie(minted);
  return minted;
}

function App() {
  const [conversationId, setConversationId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [shopperId, setShopperId] = useState(() => resolveShopperId());
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState("");
  const chatWindowRef = useRef(null);

  const canSend = useMemo(
    () => !isStreaming && input.trim().length > 0,
    [input, isStreaming]
  );

  useEffect(() => {
    const chatWindow = chatWindowRef.current;
    if (!chatWindow) {
      return;
    }
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }, [messages, isStreaming]);

  const appendToken = (assistantId, token) => {
    if (!token) {
      return;
    }
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === assistantId ? { ...msg, content: `${msg.content}${token}` } : msg
      )
    );
  };

  const sendMessage = () => {
    const text = input.trim();
    if (!text || isStreaming) {
      return;
    }
    setError("");
    setInput("");
    const userId = crypto.randomUUID();
    const assistantId = crypto.randomUUID();

    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: text },
      { id: assistantId, role: "assistant", content: "" },
    ]);

    // Re-read the cookie each send: a storefront tab opened (or its session
    // changed) after this page loaded may have updated the shared shopper id.
    const currentShopperId = readShopperCookie() || shopperId || resolveShopperId();
    if (currentShopperId !== shopperId) {
      setShopperId(currentShopperId);
    }

    const params = new URLSearchParams({ message: text });
    if (conversationId) {
      params.set("conversation_id", conversationId);
    }
    if (currentShopperId) {
      params.set("cart_user_id", currentShopperId);
    }
    const streamUrl = `${buildApiUrl("/chat/stream")}?${params.toString()}`;

    setIsStreaming(true);
    const source = new EventSource(streamUrl);

    source.addEventListener("conversation", (event) => {
      const data = parseEventData(event.data, {});
      if (data.conversation_id) {
        setConversationId(data.conversation_id);
      }
      if (data.session_id) {
        setSessionId(data.session_id);
      }
    });

    source.addEventListener("token", (event) => {
      const data = parseEventData(event.data, {});
      appendToken(assistantId, data.token || "");
    });

    source.addEventListener("done", (event) => {
      const data = parseEventData(event.data, {});
      if (data.reply) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantId ? { ...msg, content: data.reply } : msg
          )
        );
      }
      if (data.conversation_id) {
        setConversationId(data.conversation_id);
      }
      if (data.session_id) {
        setSessionId(data.session_id);
      }
      setIsStreaming(false);
      source.close();
    });

    source.addEventListener("error", (event) => {
      const data = parseEventData(event.data, {});
      setError(data.detail || "Streaming request failed.");
      setIsStreaming(false);
      source.close();
    });
  };

  const onSubmit = (event) => {
    event.preventDefault();
    sendMessage();
  };

  const handleComposerKeyDown = (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) {
      return;
    }
    event.preventDefault();
    sendMessage();
  };

  const clearConversation = () => {
    if (isStreaming) {
      return;
    }
    setConversationId("");
    setSessionId("");
    setMessages([]);
    setError("");
  };

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="app-brand">
            <img
              className="app-brand-logo"
              src="/images/opentelemetry-demo-logo.png"
              alt="Astronomy Shop"
            />
            <h1>Astronomy Concierge</h1>
          </div>
        </div>
      </header>

      <section className="meta-panel" aria-label="session metadata">
        <span>
          <strong>Conversation:</strong> {conversationId || "new conversation"}
        </span>
        <span>
          <strong>Session:</strong> {sessionId || "not started"}
        </span>
        <span>
          <strong>Cart shopper:</strong> {shopperId || "not set"}
        </span>
      </section>

      <section ref={chatWindowRef} className="chat-window" aria-live="polite">
        {messages.length === 0 ? (
          <p className="empty-state">
            Ask for recommendations, policies, or cart actions.
          </p>
        ) : (
          messages.map((msg) => (
            <article key={msg.id} className={`bubble bubble-${msg.role}`}>
              <p className="bubble-role">{msg.role === "user" ? "You" : "Concierge"}</p>
              <p className="bubble-content">{msg.content || "..."}</p>
            </article>
          ))
        )}
      </section>

      {error ? <p className="error-banner">{error}</p> : null}

      <form className="composer" onSubmit={onSubmit}>
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleComposerKeyDown}
          placeholder="Ask about products, shipping, returns, or cart actions..."
          rows={3}
          disabled={isStreaming}
        />
        <p className="composer-helper">
          Press Enter to send · Shift+Enter for a new line.
        </p>
        <div className="composer-actions">
          <button type="button" onClick={clearConversation} disabled={isStreaming}>
            New conversation
          </button>
          <button type="submit" disabled={!canSend}>
            {isStreaming ? "Streaming..." : "Send"}
          </button>
        </div>
      </form>
    </main>
  );
}

export default App;
