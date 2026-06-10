export type UserRole =
  | "customer"
  | "service_provider"
  | "product_seller"
  | "delivery_agent"
  | "employment_seeker"
  | "village_council"
  | "super_admin";

export type VerificationStatus = "pending" | "approved" | "rejected" | "resubmitted";
export type ApplicationType =
  | "employment_seeker"
  | "service_provider"
  | "product_seller"
  | "delivery_agent";

export type OrderStatus =
  | "pending"
  | "confirmed"
  | "in_escrow"
  | "in_delivery"
  | "delivered"
  | "completed"
  | "cancelled"
  | "disputed";

export type DeliveryStatus =
  | "pending"
  | "notified"
  | "accepted"
  | "picked_up"
  | "en_route"
  | "delivered"
  | "cancelled";

export interface Profile {
  id: string;
  phone: string | null;
  full_name: string;
  avatar_url: string | null;
  village_id: string | null;
  roles: UserRole[];
  is_verified: boolean;
  trust_score: number;
  trust_summary: string | null;
  is_online: boolean;
  preferred_language: string;
  created_at: string;
}

export interface Village {
  id: string;
  name: string;
  state_name: string | null;
  district_name: string | null;
  tehsil_name: string | null;
  latitude: number | null;
  longitude: number | null;
}

export interface Category {
  id: string;
  slug: string;
  name_en: string;
  name_hi: string | null;
  icon: string | null;
  kind: string;
  parent_id: string | null;
  sort_order: number;
}

export interface ServiceProvider {
  id: string;
  user_id: string;
  category_id: string | null;
  subcategory_id: string | null;
  title: string;
  description: string | null;
  pricing_type: string;
  price_min: number | null;
  price_max: number | null;
  experience_years: number;
  service_area_km: number;
  home_service: boolean;
  emergency_available: boolean;
  is_available_now: boolean;
  avg_rating: number;
  review_count: number;
  is_active: boolean;
  profiles?: Profile;
  categories?: Category;
}

export interface Product {
  id: string;
  seller_id: string;
  category_id: string | null;
  name: string;
  description: string | null;
  price: number;
  quantity: number;
  unit: string;
  image_urls: string[];
  freshness_info: string | null;
  is_available: boolean;
  product_sellers?: ProductSeller;
}

export interface ProductSeller {
  id: string;
  user_id: string;
  shop_name: string;
  category_id: string | null;
  description: string | null;
  pickup_available: boolean;
  delivery_available: boolean;
  avg_rating: number;
  review_count: number;
  is_active: boolean;
  profiles?: Profile;
}

export interface EmploymentSeeker {
  id: string;
  user_id: string;
  category_id: string | null;
  skills: string[];
  expected_income: number | null;
  experience_years: number;
  work_radius_km: number;
  is_available_now: boolean;
  is_active: boolean;
  profiles?: Profile;
}

export interface DeliveryAgent {
  id: string;
  user_id: string;
  vehicle_type: string | null;
  service_radius_km: number;
  is_available: boolean;
  avg_rating: number;
  total_deliveries: number;
  is_active: boolean;
  profiles?: Profile;
}

export interface Order {
  id: string;
  customer_id: string;
  provider_id: string | null;
  order_type: "service" | "product";
  status: OrderStatus;
  total_qoins: number;
  delivery_qoins: number;
  notes: string | null;
  village_id: string | null;
  created_at: string;
}

export interface Wallet {
  id: string;
  user_id: string;
  balance: number;
}

export interface Transaction {
  id: string;
  type: string;
  amount: number;
  balance_after: number;
  description: string | null;
  created_at: string;
}

export interface Chat {
  id: string;
  chat_type: string;
  order_id: string | null;
  participant_ids: string[];
  last_message_at: string | null;
}

export interface Message {
  id: string;
  chat_id: string;
  sender_id: string;
  content: string | null;
  image_url: string | null;
  quotation: Record<string, unknown> | null;
  is_read: boolean;
  created_at: string;
}

export interface Review {
  id: string;
  reviewer_id: string;
  reviewee_id: string;
  review_type: string;
  rating_overall: number;
  comment: string | null;
  created_at: string;
}

export interface VerificationApplication {
  id: string;
  user_id: string;
  application_type: ApplicationType;
  village_id: string;
  status: VerificationStatus;
  payload: Record<string, unknown>;
  reviewer_notes: string | null;
  created_at: string;
  profiles?: Profile;
}

export interface SearchResult {
  id: string;
  type: "service" | "product" | "employment";
  name: string;
  priceRange: string;
  rating: number;
  distance: string;
  verified: boolean;
  trustScore: number;
  deliveryAvailable: boolean;
  availableNow: boolean;
  userId: string;
}

export interface AIRecommendation extends SearchResult {
  reason?: string;
}
