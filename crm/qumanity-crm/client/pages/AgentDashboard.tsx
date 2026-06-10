import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';

interface Ticket {
  ticket_id: string;
  subject: string;
  category: string;
  priority: string;
  status: string;
  created_by_name: string;
  created_at: string;
}

interface AgentStats {
  resolvedToday: number;
  avgResolutionTime: number;
}

const API = '/api';

function authHeaders() {
  return { Authorization: `Bearer ${localStorage.getItem('qumanity_token') || ''}` };
}

const AgentDashboard: React.FC = () => {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<AgentStats>({ resolvedToday: 0, avgResolutionTime: 0 });
  const [statusFilter, setStatusFilter] = useState('all');
  const [priorityFilter, setPriorityFilter] = useState('all');

  const fetchTickets = useCallback(async () => {
    try {
      const params: Record<string, string> = {};
      if (statusFilter !== 'all') params.status = statusFilter;
      if (priorityFilter !== 'all') params.priority = priorityFilter;
      const response = await axios.get(`${API}/tickets`, { headers: authHeaders(), params });
      setTickets(response.data?.data ?? response.data ?? []);
    } catch (error) {
      console.error('Failed to fetch tickets:', error);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, priorityFilter]);

  const fetchStats = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/agents/stats`, { headers: authHeaders() });
      setStats(response.data);
    } catch (error) {
      console.error('Failed to fetch stats:', error);
    }
  }, []);

  useEffect(() => {
    fetchTickets();
    fetchStats();
  }, [fetchTickets, fetchStats]);

  const filtered = useMemo(() => tickets, [tickets]);

  if (loading) return <div className="qb-crm-loading">Loading tickets…</div>;

  return (
    <div className="agent-dashboard qb-crm-page">
      <header className="qb-crm-header">
        <h1>Agent Dashboard</h1>
        <p>Tickets assigned to you</p>
      </header>

      <div className="stats-cards qb-crm-stats">
        <div className="stat-card qb-crm-card">
          <h3>Resolved Today</h3>
          <p className="stat-value">{stats.resolvedToday}</p>
        </div>
        <div className="stat-card qb-crm-card">
          <h3>Avg Resolution Time</h3>
          <p className="stat-value">{stats.avgResolutionTime} hrs</p>
        </div>
      </div>

      <div className="ticket-filters qb-crm-filters">
        <select
          id="status-filter"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label="Filter by status"
        >
          <option value="all">All Status</option>
          <option value="open">Open</option>
          <option value="in_progress">In Progress</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
        </select>
        <select
          id="priority-filter"
          value={priorityFilter}
          onChange={(e) => setPriorityFilter(e.target.value)}
          aria-label="Filter by priority"
        >
          <option value="all">All Priorities</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="urgent">Urgent</option>
        </select>
      </div>

      <table className="ticket-table qb-crm-table">
        <thead>
          <tr>
            <th>Ticket ID</th>
            <th>Subject</th>
            <th>Customer</th>
            <th>Priority</th>
            <th>Status</th>
            <th>Created</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((ticket) => (
            <tr key={ticket.ticket_id}>
              <td>{ticket.ticket_id}</td>
              <td>{ticket.subject}</td>
              <td>{ticket.created_by_name}</td>
              <td>
                <span className={`priority-${ticket.priority}`}>{ticket.priority}</span>
              </td>
              <td>
                <span className={`status-${ticket.status}`}>{ticket.status}</span>
              </td>
              <td>{new Date(ticket.created_at).toLocaleDateString()}</td>
              <td>
                <a className="qb-btn qb-btn-primary" href={`/crm/tickets/${ticket.ticket_id}`}>
                  View
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default AgentDashboard;
