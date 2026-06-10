-- Village Employment & Local Commerce System (VELCS)
-- Run in Supabase SQL Editor. Enable extensions first.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";

-- ─── Enums ───────────────────────────────────────────────────────────────────

CREATE TYPE user_role AS ENUM (
  'customer',
  'service_provider',
  'product_seller',
  'delivery_agent',
  'employment_seeker',
  'village_council',
  'super_admin'
);

CREATE TYPE verification_status AS ENUM ('pending', 'approved', 'rejected', 'resubmitted');
CREATE TYPE application_type AS ENUM (
  'employment_seeker',
  'service_provider',
  'product_seller',
  'delivery_agent'
);
CREATE TYPE order_status AS ENUM (
  'pending',
  'confirmed',
  'in_escrow',
  'in_delivery',
  'delivered',
  'completed',
  'cancelled',
  'disputed'
);
CREATE TYPE delivery_status AS ENUM (
  'pending',
  'notified',
  'accepted',
  'picked_up',
  'en_route',
  'delivered',
  'cancelled'
);
CREATE TYPE transaction_type AS ENUM (
  'credit',
  'debit',
  'escrow_hold',
  'escrow_release',
  'refund',
  'bonus'
);
CREATE TYPE chat_type AS ENUM ('customer_provider', 'customer_agent', 'order_negotiation');
CREATE TYPE dispute_status AS ENUM ('open', 'investigating', 'resolved', 'dismissed');

-- ─── Villages (imported from indiaq.db) ─────────────────────────────────────

CREATE TABLE villages (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  state_name TEXT,
  district_name TEXT,
  tehsil_name TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  geom GEOGRAPHY(POINT, 4326),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_villages_name ON villages USING gin (to_tsvector('simple', name));
CREATE INDEX idx_villages_geom ON villages USING GIST (geom);

-- ─── Profiles (extends auth.users) ──────────────────────────────────────────

CREATE TABLE profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  phone TEXT UNIQUE,
  full_name TEXT NOT NULL DEFAULT '',
  avatar_url TEXT,
  village_id TEXT REFERENCES villages(id),
  roles user_role[] NOT NULL DEFAULT ARRAY['customer']::user_role[],
  aadhaar_hash TEXT,
  aadhaar_verified BOOLEAN DEFAULT FALSE,
  is_verified BOOLEAN DEFAULT FALSE,
  trust_score INTEGER DEFAULT 0 CHECK (trust_score >= 0 AND trust_score <= 100),
  trust_summary TEXT,
  is_online BOOLEAN DEFAULT FALSE,
  last_seen_at TIMESTAMPTZ,
  preferred_language TEXT DEFAULT 'hi',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_profiles_village ON profiles(village_id);
CREATE INDEX idx_profiles_roles ON profiles USING GIN (roles);

-- ─── Categories ─────────────────────────────────────────────────────────────

CREATE TABLE categories (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  slug TEXT UNIQUE NOT NULL,
  name_en TEXT NOT NULL,
  name_hi TEXT,
  icon TEXT,
  kind TEXT NOT NULL CHECK (kind IN ('service', 'product', 'delivery', 'employment')),
  parent_id UUID REFERENCES categories(id) ON DELETE SET NULL,
  sort_order INTEGER DEFAULT 0,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_categories_kind ON categories(kind);
CREATE INDEX idx_categories_parent ON categories(parent_id);

-- ─── Verification Applications ──────────────────────────────────────────────

CREATE TABLE verification_applications (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  application_type application_type NOT NULL,
  village_id TEXT NOT NULL REFERENCES villages(id),
  status verification_status DEFAULT 'pending',
  payload JSONB NOT NULL DEFAULT '{}',
  documents JSONB DEFAULT '[]',
  reviewer_id UUID REFERENCES profiles(id),
  reviewer_notes TEXT,
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_verifications_status ON verification_applications(status);
CREATE INDEX idx_verifications_user ON verification_applications(user_id);
CREATE INDEX idx_verifications_village ON verification_applications(village_id);

-- ─── Employment Seekers ───────────────────────────────────────────────────────

CREATE TABLE employment_seekers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID UNIQUE NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  category_id UUID REFERENCES categories(id),
  subcategory_id UUID REFERENCES categories(id),
  skills TEXT[] DEFAULT '{}',
  expected_income INTEGER,
  experience_years INTEGER DEFAULT 0,
  availability JSONB DEFAULT '{}',
  work_radius_km INTEGER DEFAULT 5,
  is_available_now BOOLEAN DEFAULT FALSE,
  verification_id UUID REFERENCES verification_applications(id),
  is_active BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Service Providers ────────────────────────────────────────────────────────

CREATE TABLE service_providers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID UNIQUE NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  category_id UUID REFERENCES categories(id),
  subcategory_id UUID REFERENCES categories(id),
  title TEXT NOT NULL,
  description TEXT,
  pricing_type TEXT DEFAULT 'fixed' CHECK (pricing_type IN ('fixed', 'hourly', 'negotiable')),
  price_min INTEGER,
  price_max INTEGER,
  experience_years INTEGER DEFAULT 0,
  working_hours JSONB DEFAULT '{}',
  service_area_km INTEGER DEFAULT 5,
  home_service BOOLEAN DEFAULT TRUE,
  emergency_available BOOLEAN DEFAULT FALSE,
  is_available_now BOOLEAN DEFAULT FALSE,
  avg_rating NUMERIC(3,2) DEFAULT 0,
  review_count INTEGER DEFAULT 0,
  verification_id UUID REFERENCES verification_applications(id),
  is_active BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_service_providers_category ON service_providers(category_id);
CREATE INDEX idx_service_providers_active ON service_providers(is_active) WHERE is_active = TRUE;

-- ─── Product Sellers ──────────────────────────────────────────────────────────

CREATE TABLE product_sellers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID UNIQUE NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  shop_name TEXT NOT NULL,
  category_id UUID REFERENCES categories(id),
  description TEXT,
  pickup_available BOOLEAN DEFAULT TRUE,
  delivery_available BOOLEAN DEFAULT TRUE,
  avg_rating NUMERIC(3,2) DEFAULT 0,
  review_count INTEGER DEFAULT 0,
  verification_id UUID REFERENCES verification_applications(id),
  is_active BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Products ─────────────────────────────────────────────────────────────────

CREATE TABLE products (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  seller_id UUID NOT NULL REFERENCES product_sellers(id) ON DELETE CASCADE,
  category_id UUID REFERENCES categories(id),
  name TEXT NOT NULL,
  description TEXT,
  price INTEGER NOT NULL,
  quantity INTEGER DEFAULT 1,
  unit TEXT DEFAULT 'piece',
  image_urls TEXT[] DEFAULT '{}',
  freshness_info TEXT,
  expiry_date DATE,
  is_available BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_products_seller ON products(seller_id);
CREATE INDEX idx_products_category ON products(category_id);

-- ─── Delivery Agents ──────────────────────────────────────────────────────────

CREATE TABLE delivery_agents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID UNIQUE NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  vehicle_type TEXT,
  service_radius_km INTEGER DEFAULT 10,
  is_available BOOLEAN DEFAULT FALSE,
  current_lat DOUBLE PRECISION,
  current_lng DOUBLE PRECISION,
  geom GEOGRAPHY(POINT, 4326),
  avg_rating NUMERIC(3,2) DEFAULT 0,
  review_count INTEGER DEFAULT 0,
  total_deliveries INTEGER DEFAULT 0,
  verification_id UUID REFERENCES verification_applications(id),
  is_active BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_delivery_agents_geom ON delivery_agents USING GIST (geom);

-- ─── Orders ───────────────────────────────────────────────────────────────────

CREATE TABLE orders (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  customer_id UUID NOT NULL REFERENCES profiles(id),
  provider_id UUID REFERENCES profiles(id),
  seller_id UUID REFERENCES product_sellers(id),
  service_provider_id UUID REFERENCES service_providers(id),
  order_type TEXT NOT NULL CHECK (order_type IN ('service', 'product')),
  status order_status DEFAULT 'pending',
  total_qoins INTEGER NOT NULL DEFAULT 0,
  delivery_qoins INTEGER DEFAULT 0,
  notes TEXT,
  delivery_address TEXT,
  delivery_lat DOUBLE PRECISION,
  delivery_lng DOUBLE PRECISION,
  otp_code TEXT,
  otp_verified BOOLEAN DEFAULT FALSE,
  escrow_transaction_id UUID,
  village_id TEXT REFERENCES villages(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE order_items (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_id UUID REFERENCES products(id),
  quantity INTEGER DEFAULT 1,
  unit_price INTEGER NOT NULL,
  subtotal INTEGER NOT NULL
);

-- ─── Delivery Tasks ───────────────────────────────────────────────────────────

CREATE TABLE delivery_tasks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  order_id UUID UNIQUE NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  agent_id UUID REFERENCES delivery_agents(id),
  status delivery_status DEFAULT 'pending',
  pickup_lat DOUBLE PRECISION,
  pickup_lng DOUBLE PRECISION,
  drop_lat DOUBLE PRECISION,
  drop_lng DOUBLE PRECISION,
  estimated_minutes INTEGER,
  distance_km NUMERIC(6,2),
  accepted_at TIMESTAMPTZ,
  picked_up_at TIMESTAMPTZ,
  delivered_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_delivery_tasks_status ON delivery_tasks(status);
CREATE INDEX idx_delivery_tasks_agent ON delivery_tasks(agent_id);

-- ─── Chats & Messages ─────────────────────────────────────────────────────────

CREATE TABLE chats (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  chat_type chat_type NOT NULL,
  order_id UUID REFERENCES orders(id),
  participant_ids UUID[] NOT NULL,
  last_message_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  sender_id UUID NOT NULL REFERENCES profiles(id),
  content TEXT,
  image_url TEXT,
  quotation JSONB,
  is_read BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_chat ON messages(chat_id, created_at DESC);

-- ─── Wallets & Transactions ───────────────────────────────────────────────────

CREATE TABLE wallets (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID UNIQUE NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE transactions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  wallet_id UUID NOT NULL REFERENCES wallets(id),
  user_id UUID NOT NULL REFERENCES profiles(id),
  type transaction_type NOT NULL,
  amount INTEGER NOT NULL,
  balance_after INTEGER NOT NULL,
  order_id UUID REFERENCES orders(id),
  counterparty_id UUID REFERENCES profiles(id),
  description TEXT,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_transactions_user ON transactions(user_id, created_at DESC);
CREATE INDEX idx_transactions_order ON transactions(order_id);

-- ─── Reviews ──────────────────────────────────────────────────────────────────

CREATE TABLE reviews (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  reviewer_id UUID NOT NULL REFERENCES profiles(id),
  reviewee_id UUID NOT NULL REFERENCES profiles(id),
  order_id UUID REFERENCES orders(id),
  review_type TEXT NOT NULL CHECK (review_type IN (
    'service_provider', 'product_seller', 'delivery_agent', 'employment_seeker'
  )),
  rating_overall NUMERIC(2,1) NOT NULL CHECK (rating_overall >= 1 AND rating_overall <= 5),
  rating_skill NUMERIC(2,1),
  rating_behaviour NUMERIC(2,1),
  rating_punctuality NUMERIC(2,1),
  rating_freshness NUMERIC(2,1),
  rating_pricing NUMERIC(2,1),
  rating_speed NUMERIC(2,1),
  rating_packaging NUMERIC(2,1),
  rating_professionalism NUMERIC(2,1),
  comment TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reviews_reviewee ON reviews(reviewee_id);

-- ─── Disputes ─────────────────────────────────────────────────────────────────

CREATE TABLE disputes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  order_id UUID NOT NULL REFERENCES orders(id),
  raised_by UUID NOT NULL REFERENCES profiles(id),
  against_id UUID NOT NULL REFERENCES profiles(id),
  reason TEXT NOT NULL,
  status dispute_status DEFAULT 'open',
  resolution TEXT,
  resolved_by UUID REFERENCES profiles(id),
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Village Economy Stats (materialized periodically) ────────────────────────

CREATE TABLE village_economy_snapshots (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  village_id TEXT NOT NULL REFERENCES villages(id),
  total_qoins_circulation INTEGER DEFAULT 0,
  total_spent INTEGER DEFAULT 0,
  spending_by_category JSONB DEFAULT '{}',
  active_providers INTEGER DEFAULT 0,
  active_sellers INTEGER DEFAULT 0,
  snapshot_date DATE DEFAULT CURRENT_DATE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Fraud Flags ──────────────────────────────────────────────────────────────

CREATE TABLE fraud_flags (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES profiles(id),
  flagged_by UUID REFERENCES profiles(id),
  reason TEXT NOT NULL,
  severity TEXT DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high')),
  is_resolved BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Functions & Triggers ─────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER profiles_updated_at BEFORE UPDATE ON profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER service_providers_updated_at BEFORE UPDATE ON service_providers
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER product_sellers_updated_at BEFORE UPDATE ON product_sellers
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER orders_updated_at BEFORE UPDATE ON orders
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Auto-create wallet on profile insert
CREATE OR REPLACE FUNCTION create_wallet_for_profile()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO wallets (user_id, balance) VALUES (NEW.id, 100);
  INSERT INTO transactions (wallet_id, user_id, type, amount, balance_after, description)
  SELECT w.id, NEW.id, 'bonus', 100, 100, 'Welcome bonus — 100 Qoins'
  FROM wallets w WHERE w.user_id = NEW.id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_profile_created AFTER INSERT ON profiles
  FOR EACH ROW EXECUTE FUNCTION create_wallet_for_profile();

-- ─── Row Level Security ───────────────────────────────────────────────────────

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE chats ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_applications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Profiles are viewable by authenticated users"
  ON profiles FOR SELECT TO authenticated USING (true);

CREATE POLICY "Users can update own profile"
  ON profiles FOR UPDATE TO authenticated USING (auth.uid() = id);

CREATE POLICY "Users can insert own profile"
  ON profiles FOR INSERT TO authenticated WITH CHECK (auth.uid() = id);

CREATE POLICY "Users view own wallet"
  ON wallets FOR SELECT TO authenticated USING (user_id = auth.uid());

CREATE POLICY "Users view own transactions"
  ON transactions FOR SELECT TO authenticated USING (user_id = auth.uid());

CREATE POLICY "Chat participants can read messages"
  ON messages FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM chats c
      WHERE c.id = chat_id AND auth.uid() = ANY(c.participant_ids)
    )
  );

CREATE POLICY "Chat participants can send messages"
  ON messages FOR INSERT TO authenticated
  WITH CHECK (
    sender_id = auth.uid() AND
    EXISTS (
      SELECT 1 FROM chats c
      WHERE c.id = chat_id AND auth.uid() = ANY(c.participant_ids)
    )
  );

CREATE POLICY "Users view own chats"
  ON chats FOR SELECT TO authenticated
  USING (auth.uid() = ANY(participant_ids));

CREATE POLICY "Users view own orders"
  ON orders FOR SELECT TO authenticated
  USING (
    customer_id = auth.uid() OR provider_id = auth.uid()
  );

CREATE POLICY "Users view own verifications"
  ON verification_applications FOR SELECT TO authenticated
  USING (user_id = auth.uid());

CREATE POLICY "Users create own verifications"
  ON verification_applications FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

-- Public read for marketplace listings
ALTER TABLE service_providers ENABLE ROW LEVEL SECURITY;
ALTER TABLE product_sellers ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE villages ENABLE ROW LEVEL SECURITY;
ALTER TABLE employment_seekers ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read active services" ON service_providers
  FOR SELECT USING (is_active = true);
CREATE POLICY "Public read active sellers" ON product_sellers
  FOR SELECT USING (is_active = true);
CREATE POLICY "Public read available products" ON products
  FOR SELECT USING (is_available = true);
CREATE POLICY "Public read categories" ON categories FOR SELECT USING (is_active = true);
CREATE POLICY "Public read villages" ON villages FOR SELECT USING (true);
CREATE POLICY "Public read active employment" ON employment_seekers
  FOR SELECT USING (is_active = true);
CREATE POLICY "Public read reviews" ON reviews FOR SELECT USING (true);

-- Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE messages;
ALTER PUBLICATION supabase_realtime ADD TABLE delivery_tasks;
ALTER PUBLICATION supabase_realtime ADD TABLE orders;
