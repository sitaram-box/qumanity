import { Plugin } from '@nocobase/server';
import { jwtAuthMiddleware } from '../shared/auth';

export class RatingsPlugin extends Plugin {
  async load() {
    const auth = jwtAuthMiddleware();

    this.app.post('/api/ratings', auth, async (ctx) => {
      const body = ctx.request.body;
      const repo = this.app.db.getRepository('ratings');
      const rating = await repo.create({ values: body });

      // Update vendor or delivery agent aggregate rating
      if (body.rated_private_id && body.rating_value) {
        const vendorRepo = this.app.db.getRepository('vendors');
        const vendor = await vendorRepo.findOne({
          filter: { vendor_id: body.rated_private_id },
        });
        if (vendor) {
          const total = (vendor.get('total_ratings') || 0) + 1;
          const avg =
            ((vendor.get('average_rating') || 0) * (total - 1) + body.rating_value) / total;
          await vendorRepo.update({
            filter: { vendor_id: body.rated_private_id },
            values: { average_rating: avg, total_ratings: total },
          });
        }
      }

      ctx.body = rating;
    });

    this.app.get('/api/ratings', auth, async (ctx) => {
      const { order_id, rated_private_id } = ctx.query as Record<string, string>;
      const where: Record<string, unknown> = {};
      if (order_id) where.order_id = order_id;
      if (rated_private_id) where.rated_private_id = rated_private_id;

      const ratings = await this.app.db.getRepository('ratings').find({
        filter: where,
        sort: ['-created_at'],
      });
      ctx.body = ratings;
    });
  }
}

export default RatingsPlugin;
