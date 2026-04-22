import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { createChatSocket, sendLog } from '../api/client';

export default function ChatPanel({ userId, token, sessionId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [ws, setWs] = useState(null);
  const bottomRef = useRef(null);

  // When sessionId changes, reconnect websocket and load that session's messages
  useEffect(() => {
    if (!userId) return;
    setMessages([]);
    setIsTyping(false);

    // Load existing messages for this session
    if (sessionId && token) {
      fetch(`http://localhost:8000/chat/sessions/${userId}/${sessionId}/messages`, {
        headers: { Authorization: `Bearer ${token}` }
      })
        .then(r => r.json())
        .then(data => {
          if (data.messages && data.messages.length > 0) {
            const mapped = data.messages.map(m => ({
              role: m.role === 'assistant' ? 'bot' : m.role,
              content: m.content
            }));
            setMessages(mapped);
          }
        })
        .catch(() => {});
    }

    const socket = createChatSocket(
      userId,
      (data) => {
        if (data.type === 'typing') {
          setIsTyping(true);
        } else if (data.type === 'message' || data.type === 'error') {
          setIsTyping(false);
          setMessages((prev) => [...prev, { role: 'bot', content: data.content }]);
          sendLog('info', 'ChatPanel', 'MESSAGE_RECEIVED', `type=${data.type} length=${data.content?.length}`);
        }
      },
      (err) => {
        setIsTyping(false);
        sendLog('error', 'ChatPanel', 'WS_ERROR', String(err));
      }
    );
    setWs(socket);
    return () => { socket.close(); };
  }, [userId, sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const sendMessage = (text) => {
    const msg = text || input.trim();
    if (!msg || !ws || ws.readyState !== WebSocket.OPEN) return;
    setMessages((prev) => [...prev, { role: 'user', content: msg }]);
    ws.send(JSON.stringify({ message: msg, token, session_id: sessionId }));
    sendLog('info', 'ChatPanel', 'MESSAGE_SENT', `session_id=${sessionId} length=${msg.length}`);
    setInput('');
    setIsTyping(true);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  if (messages.length === 0 && !isTyping) {
    return (
      <div className="chat-container">
        <div className="chat-welcome">
          <span className="welcome-icon">🤖</span>
          <h2>Welcome to AI Loan &amp; Credit Advisor</h2>
          <p>Ask me about loan eligibility, EMI calculations, credit improvement, or government schemes like PMAY and MUDRA.</p>
          <div className="quick-actions" style={{ maxWidth: 400 }}>
            <button className="quick-action-btn" onClick={() => sendMessage('Can I get a home loan of ₹50 lakhs?')}>🏠 Home Loan Check</button>
            <button className="quick-action-btn" onClick={() => sendMessage('Am I eligible for PMAY?')}>📋 PMAY Eligibility</button>
            <button className="quick-action-btn" onClick={() => sendMessage('How can I improve my credit score?')}>💡 Credit Tips</button>
            <button className="quick-action-btn" onClick={() => sendMessage('What is the interest rate for personal loans?')}>💰 Rate Check</button>
          </div>
        </div>
        <div className="chat-input-area">
          <input className="input-field" placeholder="Type your message..." value={input}
            onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown} id="chat-input" />
          <button className="btn btn-primary" onClick={() => sendMessage()} id="chat-send-btn">
            Send ➤
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-container">
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`chat-message ${msg.role}`}>
            <div className={`message-avatar ${msg.role === 'user' ? 'user-avatar' : 'bot-avatar'}`}>
              {msg.role === 'user' ? '👤' : '🤖'}
            </div>
            <div className={`message-bubble ${msg.role === 'user' ? 'user-bubble' : 'bot-bubble'}`}>
              {msg.role === 'bot' ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              ) : (
                msg.content
              )}
            </div>
          </div>
        ))}

        {isTyping && (
          <div className="chat-message bot">
            <div className="message-avatar bot-avatar">🤖</div>
            <div className="message-bubble bot-bubble">
              <div className="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef}></div>
      </div>

      <div className="chat-input-area">
        <input className="input-field" placeholder="Type your message..." value={input}
          onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown} id="chat-input" />
        <button className="btn btn-primary" onClick={() => sendMessage()} disabled={isTyping} id="chat-send-btn">
          {isTyping ? '⏳' : 'Send ➤'}
        </button>
      </div>
    </div>
  );
}
