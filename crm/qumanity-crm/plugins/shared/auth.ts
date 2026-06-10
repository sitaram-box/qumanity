/**
 * Shared JWT auth middleware for Qumanity CRM plugins.
 */
import jwt from 'jsonwebtoken';
import type { Context, Next } from '@nocobase/actions';

export interface QumanityJwtUser {
  private_id: string;
  name?: string;
  role: 'agent' | 'manager' | 'leader' | 'admin' | 'citizen';
  tehsil_id?: string;
  district_id?: string;
  state_id?: string;
  account_type?: string;
}

const PUBLIC_PATHS = new Set([
  '/api/health',
  '/api/orders/sync',
]);

export function jwtAuthMiddleware() {
  return async (ctx: Context, next: Next) => {
    const path = ctx.request.path || '';
    if (PUBLIC_PATHS.has(path)) {
      return next();
    }

    const authHeader = ctx.get('authorization') || '';
    const webhookSecret = ctx.get('x-webhook-secret');
    const expectedWebhook = process.env.QUMANITY_WEBHOOK_SECRET;

    if (webhookSecret && expectedWebhook && webhookSecret === expectedWebhook) {
      ctx.state.user = { private_id: 'system', role: 'admin', name: 'System' } as QumanityJwtUser;
      return next();
    }

    if (!authHeader.startsWith('Bearer ')) {
      ctx.throw(401, 'No token provided');
    }

    const token = authHeader.slice(7);
    try {
      const decoded = jwt.verify(token, process.env.JWT_SECRET || '') as QumanityJwtUser;
      ctx.state.user = decoded;
      await next();
    } catch {
      ctx.throw(401, 'Invalid token');
    }
  };
}

export function requireRoles(...roles: string[]) {
  return async (ctx: Context, next: Next) => {
    const user = ctx.state.user as QumanityJwtUser | undefined;
    if (!user || !roles.includes(user.role)) {
      ctx.throw(403, 'Insufficient permissions');
    }
    await next();
  };
}

export function ticketScopeWhere(user: QumanityJwtUser): Record<string, unknown> {
  if (user.role === 'admin') return {};
  if (user.role === 'leader') {
    return user.state_id ? { state_id: user.state_id } : {};
  }
  if (user.role === 'manager') {
    if (user.district_id) return { district_id: user.district_id };
    if (user.tehsil_id) return { tehsil_id: user.tehsil_id };
    return {};
  }
  if (user.role === 'agent') {
    return { assigned_to: user.private_id };
  }
  return { created_by: user.private_id };
}

export function generateTicketId(): string {
  const d = new Date();
  const date = d.toISOString().slice(0, 10).replace(/-/g, '');
  const seq = String(Math.floor(Math.random() * 900) + 100);
  return `TKT-${date}-${seq}`;
}
