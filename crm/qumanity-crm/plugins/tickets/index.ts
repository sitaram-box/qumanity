import axios from 'axios';
import { Plugin } from '@nocobase/server';
import {
  generateTicketId,
  jwtAuthMiddleware,
  requireRoles,
  ticketScopeWhere,
  type QumanityJwtUser,
} from '../shared/auth';

export class TicketsPlugin extends Plugin {
  async load() {
    const auth = jwtAuthMiddleware();

    this.app.resourceManager.use(auth, { tag: 'qumanity-jwt' });

    // ── Agent stats ────────────────────────────────────────────────────────
    this.app.get('/api/agents/stats', auth, async (ctx) => {
      const user = ctx.state.user as QumanityJwtUser;
      const repo = this.app.db.getRepository('tickets');
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      const closedToday = await repo.count({
        filter: {
          assigned_to: user.private_id,
          status: 'closed',
          resolved_at: { $gte: today.toISOString() },
        },
      });

      const closedAll = await repo.find({
        filter: {
          assigned_to: user.private_id,
          status: 'closed',
          resolution_time_seconds: { $not: null },
        },
        fields: ['resolution_time_seconds'],
      });

      const avgSeconds =
        closedAll.length > 0
          ? closedAll.reduce((s, t) => s + (t.get('resolution_time_seconds') || 0), 0) /
            closedAll.length
          : 0;

      ctx.body = {
        resolvedToday: closedToday,
        avgResolutionTime: Math.round((avgSeconds / 3600) * 10) / 10,
      };
    });

    // ── List tickets (role-scoped) ─────────────────────────────────────────
    this.app.get('/api/tickets', auth, async (ctx) => {
      const user = ctx.state.user as QumanityJwtUser;
      const { status, priority } = ctx.query as Record<string, string>;
      const where: Record<string, unknown> = { ...ticketScopeWhere(user) };
      if (status && status !== 'all') where.status = status;
      if (priority && priority !== 'all') where.priority = priority;

      const tickets = await this.app.db.getRepository('tickets').find({
        filter: where,
        sort: ['-created_at'],
      });
      ctx.body = tickets;
    });

    // ── Ticket detail ──────────────────────────────────────────────────────
    this.app.get('/api/tickets/:id', auth, async (ctx) => {
      const ticket = await this.app.db.getRepository('tickets').findOne({
        filter: { ticket_id: ctx.params.id },
        appends: ['comments'],
      });
      if (!ticket) ctx.throw(404, 'Ticket not found');
      ctx.body = ticket;
    });

    // ── Create ticket ──────────────────────────────────────────────────────
    this.app.post('/api/tickets', auth, async (ctx) => {
      const user = ctx.state.user as QumanityJwtUser;
      const { subject, description, category, priority, created_by_type } = ctx.request.body;

      const ticket = await this.app.db.getRepository('tickets').create({
        values: {
          ticket_id: generateTicketId(),
          subject,
          description,
          category,
          priority: priority || 'medium',
          created_by: user.private_id,
          created_by_name: user.name || user.private_id,
          created_by_type: created_by_type || 'citizen',
          tehsil_id: user.tehsil_id,
          district_id: user.district_id,
          state_id: user.state_id,
          status: 'open',
        },
      });
      ctx.body = ticket;
    });

    // ── Add comment ────────────────────────────────────────────────────────
    this.app.post('/api/tickets/:id/comments', auth, async (ctx) => {
      const user = ctx.state.user as QumanityJwtUser;
      const { message, is_internal } = ctx.request.body;

      const comment = await this.app.db.getRepository('ticket_comments').create({
        values: {
          ticket_id: ctx.params.id,
          author_id: user.private_id,
          author_name: user.name || user.private_id,
          author_role: user.role === 'citizen' ? 'citizen' : user.role,
          message,
          is_internal: Boolean(is_internal),
        },
      });
      ctx.body = comment;
    });

    // ── Assign ticket ──────────────────────────────────────────────────────
    this.app.post(
      '/api/tickets/:id/assign',
      auth,
      requireRoles('manager', 'admin'),
      async (ctx) => {
        const { agent_id, agent_name } = ctx.request.body;
        await this.app.db.getRepository('tickets').update({
          filter: { ticket_id: ctx.params.id },
          values: {
            assigned_to: agent_id,
            assigned_to_name: agent_name,
            status: 'in_progress',
          },
        });
        ctx.body = { success: true };
      },
    );

    // ── Close ticket + webhook to Flask ──────────────────────────────────
    this.app.post('/api/tickets/:id/close', auth, async (ctx) => {
      const user = ctx.state.user as QumanityJwtUser;
      const { resolution_notes, satisfaction_rating } = ctx.request.body;
      const resolvedAt = new Date();

      const repo = this.app.db.getRepository('tickets');
      const ticket = await repo.findOne({ filter: { ticket_id: ctx.params.id } });
      if (!ticket) ctx.throw(404, 'Ticket not found');

      const createdAt = new Date(ticket.get('created_at'));
      const resolutionTimeSeconds = Math.floor(
        (resolvedAt.getTime() - createdAt.getTime()) / 1000,
      );

      await repo.update({
        filter: { ticket_id: ctx.params.id },
        values: {
          status: 'closed',
          resolved_at: resolvedAt,
          resolution_time_seconds: resolutionTimeSeconds,
          satisfaction_rating: satisfaction_rating ?? null,
        },
      });

      if (resolution_notes) {
        await this.app.db.getRepository('ticket_comments').create({
          values: {
            ticket_id: ctx.params.id,
            author_id: user.private_id,
            author_name: user.name || user.private_id,
            author_role: user.role,
            message: resolution_notes,
            is_internal: false,
          },
        });
      }

      const qumanityUrl = process.env.QUMANITY_API_URL || 'http://localhost:5000/api';
      try {
        await axios.post(
          `${qumanityUrl}/webhooks/ticket-closed`,
          {
            ticket_id: ctx.params.id,
            resolution_notes,
            satisfaction_rating,
          },
          {
            headers: {
              'X-Webhook-Secret': process.env.QUMANITY_WEBHOOK_SECRET || '',
            },
          },
        );
      } catch (err) {
        this.app.logger.warn('[tickets] webhook failed: %s', (err as Error).message);
      }

      ctx.body = { success: true, resolution_time_seconds: resolutionTimeSeconds };
    });

    // ── Manager: team performance ─────────────────────────────────────────
    this.app.get(
      '/api/manager/team-performance',
      auth,
      requireRoles('manager', 'leader', 'admin'),
      async (ctx) => {
        const { tehsil_id } = ctx.query as Record<string, string>;
        const filter: Record<string, unknown> = { status: 'closed' };
        if (tehsil_id) filter.tehsil_id = tehsil_id;

        const tickets = await this.app.db.getRepository('tickets').find({ filter });
        const byAgent: Record<
          string,
          { agent_id: string; agent_name: string; count: number; totalSec: number; ratings: number[] }
        > = {};

        for (const t of tickets) {
          const aid = t.get('assigned_to');
          if (!aid) continue;
          if (!byAgent[aid]) {
            byAgent[aid] = {
              agent_id: aid,
              agent_name: t.get('assigned_to_name') || aid,
              count: 0,
              totalSec: 0,
              ratings: [],
            };
          }
          byAgent[aid].count += 1;
          byAgent[aid].totalSec += t.get('resolution_time_seconds') || 0;
          const r = t.get('satisfaction_rating');
          if (r) byAgent[aid].ratings.push(r);
        }

        ctx.body = Object.values(byAgent).map((a) => ({
          agent_id: a.agent_id,
          agent_name: a.agent_name,
          tickets_resolved: a.count,
          avg_resolution_time: a.count ? Math.round(a.totalSec / a.count / 3600 * 10) / 10 : 0,
          satisfaction_score: a.ratings.length
            ? Math.round((a.ratings.reduce((s, v) => s + v, 0) / a.ratings.length) * 10) / 10
            : 0,
        }));
      },
    );

    // ── Manager: scoped tickets ───────────────────────────────────────────
    this.app.get(
      '/api/manager/tickets',
      auth,
      requireRoles('manager', 'leader', 'admin'),
      async (ctx) => {
        const user = ctx.state.user as QumanityJwtUser;
        const { tehsil_id, unassigned } = ctx.query as Record<string, string>;
        const where: Record<string, unknown> = { ...ticketScopeWhere(user) };
        if (tehsil_id) where.tehsil_id = tehsil_id;
        if (unassigned === '1') {
          where.assigned_to = null;
          where.status = { $in: ['open', 'in_progress'] };
        }

        const tickets = await this.app.db.getRepository('tickets').find({
          filter: where,
          sort: ['-created_at'],
        });
        ctx.body = tickets;
      },
    );

    // ── Manager: CSV export ─────────────────────────────────────────────────
    this.app.get(
      '/api/manager/export-report',
      auth,
      requireRoles('manager', 'leader', 'admin'),
      async (ctx) => {
        const user = ctx.state.user as QumanityJwtUser;
        const tickets = await this.app.db.getRepository('tickets').find({
          filter: ticketScopeWhere(user),
          sort: ['-created_at'],
        });

        const header =
          'ticket_id,subject,category,priority,status,assigned_to,created_by,tehsil_id,created_at,resolved_at,satisfaction_rating\n';
        const rows = tickets
          .map((t) =>
            [
              t.get('ticket_id'),
              JSON.stringify(t.get('subject') || ''),
              t.get('category'),
              t.get('priority'),
              t.get('status'),
              t.get('assigned_to'),
              t.get('created_by'),
              t.get('tehsil_id'),
              t.get('created_at'),
              t.get('resolved_at'),
              t.get('satisfaction_rating'),
            ].join(','),
          )
          .join('\n');

        ctx.set('Content-Type', 'text/csv');
        ctx.set('Content-Disposition', 'attachment; filename=ticket_report.csv');
        ctx.body = header + rows;
      },
    );
  }
}

export default TicketsPlugin;
