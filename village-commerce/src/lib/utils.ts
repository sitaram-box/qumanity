import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatQoins(amount: number): string {
  return `${amount.toLocaleString("en-IN")} Qoins`;
}

export function formatRating(rating: number): string {
  return rating.toFixed(1);
}

export function priceRange(min: number | null, max: number | null): string {
  if (min == null && max == null) return "Negotiable";
  if (min != null && max != null && min !== max) return `₹${min}–₹${max}`;
  return `₹${min ?? max}`;
}

export function haversineKm(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number
): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function formatDistance(km: number): string {
  if (km < 1) return `${Math.round(km * 1000)} m`;
  return `${km.toFixed(1)} km`;
}

export function generateOtp(): string {
  return String(Math.floor(100000 + Math.random() * 900000));
}

export function hasRole(roles: string[], role: string): boolean {
  return roles.includes(role);
}

export function isCouncil(roles: string[]): boolean {
  return roles.includes("village_council") || roles.includes("super_admin");
}
