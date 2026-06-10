import { Plugin } from '@nocobase/server';
import { jwtAuthMiddleware, requireRoles, type QumanityJwtUser } from '../shared/auth';

export class VendorsPlugin extends Plugin {
  async load() {
    const auth = jwtAuthMiddleware();

    this.app.get('/api/vendors', auth, async (ctx) => {
      const { tehsil_id, category, include_pending } = ctx.query as Record<string, string>;
      const where: Record<string, unknown> = {};

      if (include_pending !== '1') {
        where.verification_status = 'verified';
      }
      if (tehsil_id) where.tehsil_id = tehsil_id;
      if (category) where.business_type = category;

      const vendors = await this.app.db.getRepository('vendors').find({
        filter: where,
        appends: ['products'],
        sort: ['-average_rating'],
      });
      ctx.body = vendors;
    });

    this.app.get('/api/vendors/:id', auth, async (ctx) => {
      const vendor = await this.app.db.getRepository('vendors').findOne({
        filter: { vendor_id: ctx.params.id },
        appends: ['products'],
      });
      if (!vendor) ctx.throw(404, 'Vendor not found');
      ctx.body = vendor;
    });

    // Flask → CRM sync on vendor registration
    this.app.post('/api/vendors/sync', auth, async (ctx) => {
      const body = ctx.request.body;
      const repo = this.app.db.getRepository('vendors');
      const existing = await repo.findOne({ filter: { vendor_id: body.vendor_id } });

      if (existing) {
        await repo.update({
          filter: { vendor_id: body.vendor_id },
          values: body,
        });
      } else {
        await repo.create({ values: { ...body, verification_status: 'pending' } });
      }
      ctx.body = { success: true };
    });

    this.app.post(
      '/api/vendors/verify',
      auth,
      requireRoles('manager', 'admin'),
      async (ctx) => {
        const user = ctx.state.user as QumanityJwtUser;
        const { vendor_id, status } = ctx.request.body;

        if (!['verified', 'rejected', 'pending'].includes(status)) {
          ctx.throw(400, 'Invalid status');
        }

        await this.app.db.getRepository('vendors').update({
          filter: { vendor_id },
          values: {
            verification_status: status,
            verified_by: user.private_id,
            verified_at: new Date(),
          },
        });
        ctx.body = { success: true };
      },
    );

    // Pending verification queue for managers
    this.app.get(
      '/api/vendors/pending',
      auth,
      requireRoles('manager', 'admin'),
      async (ctx) => {
        const user = ctx.state.user as QumanityJwtUser;
        const where: Record<string, unknown> = { verification_status: 'pending' };
        if (user.tehsil_id) where.tehsil_id = user.tehsil_id;

        const vendors = await this.app.db.getRepository('vendors').find({
          filter: where,
          sort: ['-verified_at'],
        });
        ctx.body = vendors;
      },
    );
  }
}

export default VendorsPlugin;
