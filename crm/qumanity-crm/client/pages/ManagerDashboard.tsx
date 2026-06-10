import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

interface AgentPerformance {
  agent_id: string;
  agent_name: string;
  tickets_resolved: number;
  avg_resolution_time: number;
  satisfaction_score: number;
}

interface Ticket {
  ticket_id: string;
  subject: string;
  priority: string;
  status: string;
  created_at: string;
}

interface VendorPending {
  vendor_id: string;
  business_name: string;
  business_type: string;
  tehsil_id: string;
}

const API = '/api';

function authHeaders() {
  return { Authorization: `Bearer ${localStorage.getItem('qumanity_token') || ''}` };
}

const ManagerDashboard: React.FC = () => {
  const [agents, setAgents] = useState<AgentPerformance[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [pendingVendors, setPendingVendors] = useState<VendorPending[]>([]);
  const [selectedTehsil, setSelectedTehsil] = useState('');
  const [loading, setLoading] = useState(true);

  const fetchTeamPerformance = useCallback(async () => {
    const response = await axios.get(`${API}/manager/team-performance`, {
      headers: authHeaders(),
      params: selectedTehsil ? { tehsil_id: selectedTehsil } : {},
    });
    setAgents(response.data ?? []);
  }, [selectedTehsil]);

  const fetchTickets = useCallback(async () => {
    const response = await axios.get(`${API}/manager/tickets`, {
      headers: authHeaders(),
      params: {
        unassigned: '1',
        ...(selectedTehsil ? { tehsil_id: selectedTehsil } : {}),
      },
    });
    setTickets(response.data?.data ?? response.data ?? []);
  }, [selectedTehsil]);

  const fetchPendingVendors = useCallback(async () => {
    const response = await axios.get(`${API}/vendors/pending`, { headers: authHeaders() });
    setPendingVendors(response.data?.data ?? response.data ?? []);
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      await Promise.all([fetchTeamPerformance(), fetchTickets(), fetchPendingVendors()]);
      setLoading(false);
    })();
  }, [fetchTeamPerformance, fetchTickets, fetchPendingVendors]);

  const exportReport = async () => {
    const response = await axios.get(`${API}/manager/export-report`, {
      headers: authHeaders(),
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'ticket_report.csv');
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const verifyVendor = async (vendorId: string, status: 'verified' | 'rejected') => {
    await axios.post(
      `${API}/vendors/verify`,
      { vendor_id: vendorId, status },
      { headers: authHeaders() },
    );
    fetchPendingVendors();
  };

  if (loading) return <div className="qb-crm-loading">Loading manager dashboard…</div>;

  return (
    <div className="manager-dashboard qb-crm-page">
      <div className="dashboard-header qb-crm-header">
        <div>
          <h1>Manager Dashboard</h1>
          <p>Tehsil / district oversight</p>
        </div>
        <button type="button" className="qb-btn qb-btn-primary" onClick={exportReport}>
          Export Report (CSV)
        </button>
      </div>

      <div className="filter-section qb-crm-filters">
        <label htmlFor="tehsil-select">Tehsil filter</label>
        <input
          id="tehsil-select"
          type="text"
          placeholder="Tehsil location ID (optional)"
          value={selectedTehsil}
          onChange={(e) => setSelectedTehsil(e.target.value)}
        />
      </div>

      <section className="team-performance qb-crm-section">
        <h2>Agent Performance</h2>
        <table className="qb-crm-table">
          <thead>
            <tr>
              <th>Agent Name</th>
              <th>Tickets Resolved</th>
              <th>Avg Resolution Time (hrs)</th>
              <th>Satisfaction Score</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((agent) => (
              <tr key={agent.agent_id}>
                <td>{agent.agent_name}</td>
                <td>{agent.tickets_resolved}</td>
                <td>{agent.avg_resolution_time}</td>
                <td>{agent.satisfaction_score}/5</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="pending-tickets qb-crm-section">
        <h2>Unassigned / Pending Tickets</h2>
        <table className="qb-crm-table">
          <thead>
            <tr>
              <th>Ticket ID</th>
              <th>Subject</th>
              <th>Priority</th>
              <th>Created</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((ticket) => (
              <tr key={ticket.ticket_id}>
                <td>{ticket.ticket_id}</td>
                <td>{ticket.subject}</td>
                <td>{ticket.priority}</td>
                <td>{new Date(ticket.created_at).toLocaleDateString()}</td>
                <td>
                  <a className="qb-btn qb-btn-secondary" href={`/crm/tickets/${ticket.ticket_id}`}>
                    Assign
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="vendor-verification qb-crm-section">
        <h2>Vendor Verification Requests</h2>
        <table className="qb-crm-table">
          <thead>
            <tr>
              <th>Vendor ID</th>
              <th>Business</th>
              <th>Type</th>
              <th>Tehsil</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {pendingVendors.map((v) => (
              <tr key={v.vendor_id}>
                <td>{v.vendor_id}</td>
                <td>{v.business_name}</td>
                <td>{v.business_type}</td>
                <td>{v.tehsil_id}</td>
                <td>
                  <button
                    type="button"
                    className="qb-btn qb-btn-primary"
                    onClick={() => verifyVendor(v.vendor_id, 'verified')}
                  >
                    Verify
                  </button>{' '}
                  <button
                    type="button"
                    className="qb-btn qb-btn-danger"
                    onClick={() => verifyVendor(v.vendor_id, 'rejected')}
                  >
                    Reject
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
};

export default ManagerDashboard;
