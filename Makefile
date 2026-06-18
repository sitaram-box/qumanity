# Railway / Razorpay test helpers for Qumanity

.PHONY: help railway-setup railway-set-vpa railway-restart

help:
	@echo "Railway commands:"
	@echo "  make railway-setup     - Full Razorpay test env setup (interactive)"
	@echo "  make railway-set-vpa   - Set success@razorpay and redeploy"
	@echo "  make railway-restart   - Redeploy Railway service"

railway-setup:
	bash scripts/setup_railway_env.sh

railway-set-vpa:
	bash scripts/setup_railway_env.sh --vpa-only

railway-restart:
	railway redeploy -y || railway restart
