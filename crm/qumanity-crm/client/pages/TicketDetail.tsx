import React, { useEffect, useState } from 'react';
import axios from 'axios';

interface Comment {
  id: number;
  author_name: string;
  author_role: string;
  message: string;
  is_internal: boolean;
  created_at: string;
}

interface TicketDetail {
  ticket_id: string;
  subject: string;
  description: string;
  category: string;
  priority: string;
  status: string;
  created_by_name: string;
  assigned_to_name?: string;
  comments?: Comment[];
}

const API = '/api';

function authHeaders() {
  return { Authorization: `Bearer ${localStorage.getItem('qumanity_token') || ''}` };
}

const TicketDetailPage: React.FC<{ ticketId: string }> = ({ ticketId }) => {
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [reply, setReply] = useState('');
  const [internalNote, setInternalNote] = useState(false);
  const [resolutionNotes, setResolutionNotes] = useState('');
  const [satisfaction, setSatisfaction] = useState(5);

  const load = async () => {
    const res = await axios.get(`${API}/tickets/${ticketId}`, { headers: authHeaders() });
    setTicket(res.data?.data ?? res.data);
  };

  useEffect(() => {
    load();
  }, [ticketId]);

  const sendReply = async () => {
    await axios.post(
      `${API}/tickets/${ticketId}/comments`,
      { message: reply, is_internal: internalNote },
      { headers: authHeaders() },
    );
    setReply('');
    load();
  };

  const closeTicket = async () => {
    await axios.post(
      `${API}/tickets/${ticketId}/close`,
      { resolution_notes: resolutionNotes, satisfaction_rating: satisfaction },
      { headers: authHeaders() },
    );
    load();
  };

  if (!ticket) return <div className="qb-crm-loading">Loading ticket…</div>;

  const comments = ticket.comments || [];

  return (
    <div className="ticket-detail qb-crm-page">
      <header className="qb-crm-header">
        <h1>{ticket.ticket_id}</h1>
        <p>{ticket.subject}</p>
        <span className={`status-${ticket.status}`}>{ticket.status}</span>
      </header>

      <section className="qb-crm-card">
        <p><strong>Customer:</strong> {ticket.created_by_name}</p>
        <p><strong>Category:</strong> {ticket.category}</p>
        <p><strong>Priority:</strong> {ticket.priority}</p>
        <p><strong>Assigned:</strong> {ticket.assigned_to_name || 'Unassigned'}</p>
        <p>{ticket.description}</p>
      </section>

      <section className="qb-crm-section">
        <h2>Timeline</h2>
        <ul className="qb-crm-timeline">
          {comments.map((c) => (
            <li key={c.id} className={c.is_internal ? 'internal' : ''}>
              <strong>{c.author_name}</strong> ({c.author_role})
              {c.is_internal && ' — internal note'}
              <p>{c.message}</p>
              <small>{new Date(c.created_at).toLocaleString()}</small>
            </li>
          ))}
        </ul>
      </section>

      {ticket.status !== 'closed' && (
        <>
          <section className="qb-crm-section">
            <h2>Reply</h2>
            <textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={4} />
            <label>
              <input
                type="checkbox"
                checked={internalNote}
                onChange={(e) => setInternalNote(e.target.checked)}
              />{' '}
              Internal note (agent only)
            </label>
            <button type="button" className="qb-btn qb-btn-secondary" onClick={sendReply}>
              Send Reply
            </button>
          </section>

          <section className="qb-crm-section">
            <h2>Close Ticket</h2>
            <textarea
              value={resolutionNotes}
              onChange={(e) => setResolutionNotes(e.target.value)}
              placeholder="Resolution notes"
              rows={3}
            />
            <label>
              Satisfaction (1–5):{' '}
              <input
                type="number"
                min={1}
                max={5}
                value={satisfaction}
                onChange={(e) => setSatisfaction(Number(e.target.value))}
              />
            </label>
            <button type="button" className="qb-btn qb-btn-primary" onClick={closeTicket}>
              Close Ticket
            </button>
          </section>
        </>
      )}
    </div>
  );
};

export default TicketDetailPage;
