import { ShieldCheck, Star, MapPin, Zap } from "lucide-react";
import { cn, formatRating } from "@/lib/utils";
import type { SearchResult } from "@/lib/types";

interface ListingCardProps {
  item: SearchResult;
  onSelect?: (item: SearchResult) => void;
}

export function VerifiedBadge({ className }: { className?: string }) {
  return (
    <span className={cn("badge-verified", className)}>
      <ShieldCheck className="h-3 w-3" />
      Verified
    </span>
  );
}

export function ListingCard({ item, onSelect }: ListingCardProps) {
  return (
    <article className="card flex flex-col gap-2 transition hover:shadow-md">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-lg font-bold text-soil">{item.name}</h3>
          <p className="text-sm capitalize text-soil/60">{item.type}</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          {item.verified && <VerifiedBadge />}
          {item.availableNow && (
            <span className="badge-available">
              <Zap className="h-3 w-3" />
              Available Now
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm text-soil/80">
        <span className="font-semibold text-saffron-dark">{item.priceRange}</span>
        {item.rating > 0 && (
          <span className="flex items-center gap-1">
            <Star className="h-4 w-4 fill-saffron text-saffron" />
            {formatRating(item.rating)}
          </span>
        )}
        <span className="flex items-center gap-1">
          <MapPin className="h-4 w-4" />
          {item.distance}
        </span>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-xs text-earth-green">Trust: {item.trustScore}/100</span>
        {item.deliveryAvailable && (
          <span className="text-xs font-medium text-earth-green">Delivery ✓</span>
        )}
      </div>

      {onSelect && (
        <button type="button" className="btn-primary mt-2 w-full !py-2" onClick={() => onSelect(item)}>
          Select & Chat
        </button>
      )}
    </article>
  );
}
