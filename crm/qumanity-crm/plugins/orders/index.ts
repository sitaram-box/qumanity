import { Plugin } from '@nocobase/server';
import { jwtAuthMiddleware, requireRoles, type QumanityJwtUser } from '../shared/auth';

export class OrdersPlugin extends Plugin {
  async load() {
    const auth = jwtAuthMiddleware();

    this.app.get('/api/orders', auth, async (ctx) => {
      const user = ctx.state.user as QumanityJwtUser;
      const { tehsil_id, status } = ctx.query as Record<string, string>;
      const where: Record<string, unknown> = {};

      if (user.role === 'agent' || user.role === 'manager') {
        if (tehsil_id) where.buyer_tehsil_id = tehsil_id;
        else if (user.tehsil_id) where.buyer_tehsil_id = user.tehsil_id;
      } else if (user.role === 'citizen') {
        where.buyer_private_id = user.private_id;
      }
      if (status) where.order_status = status;

      const orders = await this.app.db.getRepository('orders').find({
        filter: where,
        sort: ['-created_at'],
      });
      ctx.body = orders;
    });

    // Flask → CRM order sync (also accepts webhook secret)
    this.app.post('/api/orders', auth, async (ctx) => {
      const order = ctx.request.body;
      const repo = this.app.db.getRepository('orders');
      const existing = await repo.findOne({ filter: { order_id: order.order_id } });

      if (!existing) {
        await repo.create({ values: order });
      }
      ctx.body = { success: true };
    });

    this.app.post(
      '/api/orders/:id/assign-delivery',
      auth,
      requireRoles('manager', 'admin', 'agent'),
      async (ctx) => {
        const { delivery_agent_id, delivery_agent_name } = ctx.request.body;
        await this.app.db.getRepository('orders').update({
          filter: { order_id: ctx.params.id },
          values: {
            delivery_agent_id,
            delivery_agent_name,
            order_status: 'confirmed',
          },
        });
        ctx.body = { success: true };
      },
    );

    this.app.post('/api/orders/:id/status', auth, async (ctx) => {
      const { status } = ctx.request.body;
      const updateData: Record<string, unknown> = { order_status: status };

      if (status === 'delivered') {
        updateData.delivered_at = new Date();
      }

      await this.app.db.getRepository('orders').update({
        filter: { order_id: ctx.params.id },
        values: updateData,
      });
      ctx.body = { success: true };
    });
  }
}

export default OrdersPlugin;
