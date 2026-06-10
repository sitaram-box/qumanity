"use client";

import { useEffect, useState } from "react";
import { Star } from "lucide-react";
import { VerifiedBadge } from "@/components/ListingCard";

interface Review {
  id: string;
  review_type: string;
  rating_overall: number;
  rating_skill: number | null;
  rating_behaviour: number | null;
  rating_punctuality: number | null;
  comment: string | null;
  created_at: string;
  profiles: { full_name: string };
}

export default function ReviewsPage() {
  const [reviews, setReviews] = useState<Review[]>([]);

  useEffect(() => {
    fetch("/api/reviews")
      .then((r) => r.json())
      .then((d) => setReviews(d.reviews ?? []));
  }, []);

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="section-title mb-6">Ratings & Reviews</h1>

      {reviews.length === 0 ? (
        <div className="card py-12 text-center text-soil/60">No reviews yet</div>
      ) : (
        <ul className="space-y-4">
          {reviews.map((r) => (
            <li key={r.id} className="card">
              <div className="flex items-center justify-between">
                <p className="font-bold">{r.profiles?.full_name}</p>
                <div className="flex items-center gap-1">
                  <Star className="h-4 w-4 fill-saffron text-saffron" />
                  <span className="font-semibold">{r.rating_overall}</span>
                </div>
              </div>
              <p className="mt-1 text-xs capitalize text-soil/50">{r.review_type.replace(/_/g, " ")}</p>
              {r.comment && <p className="mt-2 text-sm text-soil/80">{r.comment}</p>}
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-soil/60">
                {r.rating_skill != null && <span>Skill: {r.rating_skill}★</span>}
                {r.rating_behaviour != null && <span>Behaviour: {r.rating_behaviour}★</span>}
                {r.rating_punctuality != null && <span>Punctuality: {r.rating_punctuality}★</span>}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="card mt-8">
        <h2 className="font-bold">Leave a Review</h2>
        <p className="mt-2 text-sm text-soil/70">
          After completing an order, rate your provider on skill, behaviour, and punctuality.
          AI generates a trust summary for verified profiles.
        </p>
        <VerifiedBadge className="mt-3" />
      </div>
    </div>
  );
}
