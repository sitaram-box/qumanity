import OpenAI from "openai";
import { marketplaceSearch } from "@/lib/geo";
import type { AIRecommendation } from "@/lib/types";

const SYSTEM_PROMPT = `You are the Village Employment & Local Commerce assistant for rural India.
Help customers find local service providers, products, and workers in their village.
Understand Hindi and English. Be concise and friendly.
When users ask for services/products, extract: type (service/product/employment), category keywords, price preference, urgency.
Respond in JSON when asked to search, but also give a friendly Hindi-English summary.`;

const CATEGORY_KEYWORDS: Record<string, string> = {
  plumber: "plumber",
  प्लंबर: "plumber",
  electrician: "electrician",
  vegetables: "vegetables",
  सब्जी: "vegetables",
  tuition: "tuition",
  ट्यूशन: "tuition",
  labour: "construction",
  मजदूर: "construction",
  milk: "milk",
  दूध: "milk",
  delivery: "product-delivery",
  rickshaw: "rickshaw",
  auto: "auto",
};

function detectCategory(message: string): string | undefined {
  const lower = message.toLowerCase();
  for (const [key, slug] of Object.entries(CATEGORY_KEYWORDS)) {
    if (lower.includes(key)) return slug;
  }
  if (lower.includes("cheapest") || lower.includes("sasta")) return undefined;
  if (lower.includes("plumber")) return "plumber";
  if (lower.includes("vegetable")) return "vegetables";
  if (lower.includes("tuition") || lower.includes("teacher")) return "tuition";
  if (lower.includes("labour") || lower.includes("labor")) return "construction";
  return undefined;
}

function detectType(message: string): "service" | "product" | "employment" | "all" {
  const lower = message.toLowerCase();
  if (lower.includes("vegetable") || lower.includes("milk") || lower.includes("product") || lower.includes("deliver"))
    return "product";
  if (lower.includes("labour") || lower.includes("employment") || lower.includes("job") || lower.includes("काम"))
    return "employment";
  if (lower.includes("service") || lower.includes("plumber") || lower.includes("repair") || lower.includes("tuition"))
    return "service";
  return "all";
}

export async function processAIQuery(
  message: string,
  villageId?: string,
  lat?: number,
  lng?: number
): Promise<{ reply: string; recommendations: AIRecommendation[] }> {
  const categorySlug = detectCategory(message);
  const type = detectType(message);
  const wantsCheapest =
    message.toLowerCase().includes("cheapest") || message.toLowerCase().includes("sasta");

  const results = await marketplaceSearch({
    query: message,
    categorySlug,
    villageId,
    lat,
    lng,
    type,
    availableNow: message.toLowerCase().includes("urgent") || message.toLowerCase().includes("emergency"),
    limit: 8,
  });

  let sorted = [...results];
  if (wantsCheapest) {
    sorted.sort((a, b) => {
      const pa = parseInt(a.priceRange.replace(/\D/g, "") || "99999");
      const pb = parseInt(b.priceRange.replace(/\D/g, "") || "99999");
      return pa - pb;
    });
  }

  const recommendations: AIRecommendation[] = sorted.map((r) => ({
    ...r,
    reason: r.verified ? "Verified by Village Council" : "Local provider",
  }));

  let aiSummary = "";
  const apiKey = process.env.OPENAI_API_KEY;

  if (apiKey && !apiKey.startsWith("sk-your")) {
    try {
      const openai = new OpenAI({ apiKey });
      const completion = await openai.chat.completions.create({
        model: "gpt-4o-mini",
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          {
            role: "user",
            content: `User query: "${message}"
Found ${recommendations.length} results: ${JSON.stringify(recommendations.slice(0, 5))}
Give a 2-3 sentence helpful reply in simple Hindi-English mix.`,
          },
        ],
        max_tokens: 200,
      });
      aiSummary = completion.choices[0]?.message?.content ?? "";
    } catch {
      aiSummary = "";
    }
  }

  if (!aiSummary) {
    if (recommendations.length === 0) {
      aiSummary =
        "Maaf kijiye, abhi aapke gaanv mein yeh service uplabdh nahi hai. Kripya Verification ke baad providers register karein.";
    } else {
      aiSummary = `Maine ${recommendations.length} options dhundhe hain. Sabse accha: ${recommendations[0].name} (${recommendations[0].priceRange}). Neeche list dekhein aur select karein.`;
    }
  }

  return { reply: aiSummary, recommendations };
}

export async function generateTrustSummary(reviews: { comment: string | null; rating_overall: number }[]) {
  if (reviews.length === 0) return "No reviews yet.";
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey || apiKey.startsWith("sk-your")) {
    const avg = reviews.reduce((s, r) => s + r.rating_overall, 0) / reviews.length;
    return `Trusted local provider with ${reviews.length} reviews (${avg.toFixed(1)}★ average).`;
  }
  try {
    const openai = new OpenAI({ apiKey });
    const completion = await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [
        {
          role: "user",
          content: `Summarize these village service reviews in 1 sentence (Hindi-English): ${JSON.stringify(reviews.slice(0, 10))}`,
        },
      ],
      max_tokens: 80,
    });
    return completion.choices[0]?.message?.content ?? "Well-reviewed local provider.";
  } catch {
    return "Well-reviewed local provider.";
  }
}
