// Industry taxonomy for brand onboarding personalization.
//
// This drives (1) the grouped/searchable industry picker, (2) the
// "Recommended for you" feature panel, and (3) the product tour's emphasis.
// It is PERSONALIZATION ONLY — never a gate. Every feature stays reachable
// regardless of industry; recommendations only change what we surface first.
//
// `value` is the stored slug (Brand.industry). Categories map to a recommended
// feature set; a few industries override with a specialization. "Other" is
// always available as free text so nobody is ever excluded.

export type IndustryCategory =
  | "trades"
  | "professional"
  | "healthcare"
  | "real_estate"
  | "finance"
  | "creators"
  | "public"
  | "marketing"
  | "technology"
  | "business"
  | "other";

export interface Industry {
  value: string;
  label: string;
  category: IndustryCategory;
  /** Regulated professions — onboarding nudges them toward Brand Book
   * disclaimers/guardrails. We never imply auto-compliance. */
  regulated?: boolean;
  /** Optional per-industry recommended-feature override (nav hrefs). */
  recommends?: string[];
}

export interface IndustryGroup {
  category: IndustryCategory;
  label: string;
  industries: Industry[];
}

// Feature keys are dashboard hrefs so the recommendation panel + tour can link
// straight to them.
export const F = {
  brands: "/dashboard/brands",
  brandBook: "/dashboard/brand-book",
  personas: "/dashboard/personas",
  offers: "/dashboard/offers",
  leads: "/dashboard/leads",
  forms: "/dashboard/forms",
  crm: "/dashboard/crm",
  campaigns: "/dashboard/campaigns",
  emails: "/dashboard/emails",
  sequences: "/dashboard/sequences",
  content: "/dashboard/content",
  media: "/dashboard/media",
  pitchVideos: "/dashboard/pitch-videos",
  social: "/dashboard/social",
  scheduler: "/dashboard/scheduler",
  analytics: "/dashboard/analytics",
  approvals: "/dashboard/approvals",
} as const;

// Default recommended features per category (3-5 each, most-useful first).
export const CATEGORY_RECOMMENDS: Record<IndustryCategory, string[]> = {
  trades: [F.leads, F.forms, F.scheduler, F.crm, F.media],
  professional: [F.scheduler, F.forms, F.crm, F.emails, F.brandBook],
  healthcare: [F.scheduler, F.forms, F.emails, F.brandBook, F.content],
  real_estate: [F.leads, F.media, F.sequences, F.scheduler, F.social],
  finance: [F.brandBook, F.pitchVideos, F.crm, F.emails, F.analytics],
  creators: [F.brandBook, F.content, F.social, F.media, F.personas],
  public: [F.personas, F.pitchVideos, F.social, F.content, F.brandBook],
  marketing: [F.brands, F.content, F.social, F.approvals, F.analytics],
  technology: [F.pitchVideos, F.brandBook, F.content, F.social, F.leads],
  business: [F.offers, F.social, F.media, F.emails, F.campaigns],
  other: [F.brandBook, F.content, F.social, F.emails, F.approvals],
};

export const CATEGORY_LABELS: Record<IndustryCategory, string> = {
  trades: "Trades & Home Services",
  professional: "Professional Services",
  healthcare: "Healthcare",
  real_estate: "Real Estate & Property",
  finance: "Finance & Investment",
  creators: "Creators & Artists",
  public: "Public Figures",
  marketing: "Marketing & Media",
  technology: "Technology",
  business: "Business & Retail",
  other: "Other",
};

function ind(
  value: string, label: string, category: IndustryCategory,
  extra?: Partial<Industry>,
): Industry {
  return { value, label, category, ...extra };
}

export const INDUSTRIES: Industry[] = [
  // Trades & home services
  ind("general_contractor", "General Contractor", "trades"),
  ind("electrician", "Electrician", "trades"),
  ind("plumber", "Plumber", "trades"),
  ind("carpenter", "Carpenter", "trades"),
  ind("builder", "Builder", "trades"),
  ind("hvac_technician", "HVAC Technician", "trades"),
  ind("landscaper", "Landscaper", "trades"),
  ind("roofer", "Roofer", "trades"),
  ind("handyman", "Handyman", "trades"),
  ind("cleaning_service", "Cleaning Service", "trades"),

  // Professional services
  ind("lawyer", "Lawyer", "professional", { regulated: true }),
  ind("accountant", "Accountant", "professional", { regulated: true }),
  ind("financial_advisor", "Financial Advisor", "professional", { regulated: true }),
  ind("insurance_agent", "Insurance Agent", "professional", { regulated: true }),
  ind("consultant", "Consultant", "professional"),
  ind("bookkeeper", "Bookkeeper", "professional"),

  // Healthcare
  ind("doctor", "Doctor", "healthcare", { regulated: true }),
  ind("dentist", "Dentist", "healthcare", { regulated: true }),
  ind("chiropractor", "Chiropractor", "healthcare", { regulated: true }),
  ind("optometrist", "Eye Doctor (Optometrist)", "healthcare", { regulated: true }),
  ind("veterinarian", "Veterinarian", "healthcare", { regulated: true }),
  ind("therapist", "Therapist / Counselor", "healthcare", { regulated: true }),
  ind("nutritionist", "Nutritionist / Dietitian", "healthcare"),
  ind("physical_therapist", "Physical Therapist", "healthcare", { regulated: true }),

  // Real estate & property
  ind("real_estate_agent", "Real Estate Agent", "real_estate"),
  ind("property_manager", "Property Manager", "real_estate"),
  ind("mortgage_broker", "Mortgage Broker", "real_estate", { regulated: true }),
  ind("interior_designer", "Interior Designer", "real_estate"),

  // Finance & investment
  ind("banker", "Banker", "finance", { regulated: true }),
  ind("investor", "Investor", "finance", { regulated: true }),
  ind("wealth_manager", "Wealth Manager", "finance", { regulated: true }),

  // Creators & artists
  ind("artist", "Artist", "creators"),
  ind("musician", "Musical Artist / Musician", "creators"),
  ind("painter", "Painter / Visual Artist", "creators"),
  ind("actor", "Actor", "creators"),
  ind("author", "Author", "creators", { recommends: [F.brandBook, F.pitchVideos, F.content, F.social, F.emails] }),
  ind("photographer", "Photographer", "creators"),
  ind("content_creator", "Content Creator / Influencer", "creators"),
  ind("podcaster", "Podcaster", "creators"),
  ind("filmmaker", "Filmmaker", "creators"),
  ind("designer", "Designer", "creators"),

  // Public figures
  ind("public_figure", "Public Figure", "public"),
  ind("philanthropist", "Philanthropist", "public"),
  ind("speaker_coach", "Speaker / Coach", "public"),
  ind("politician", "Politician", "public", { regulated: true }),

  // Marketing & media
  ind("marketing_agency", "Marketing Agency", "marketing"),
  ind("marketing_strategist", "Marketing Strategist", "marketing"),
  ind("brand_manager", "Brand Manager", "marketing"),
  ind("social_media_manager", "Social Media Manager", "marketing"),
  ind("pr_communications", "PR / Communications", "marketing"),

  // Technology
  ind("software_engineer", "Software Engineer", "technology"),
  ind("ai_engineer", "AI Engineer", "technology"),
  ind("entrepreneur", "Entrepreneur / Startup Founder", "technology"),
  ind("product_manager", "Product Manager", "technology"),
  ind("it_services", "IT Services", "technology"),

  // Business & retail
  ind("retail_business", "Retail Business", "business"),
  ind("ecommerce", "E-commerce Store", "business"),
  ind("restaurant", "Restaurant / Food Service", "business"),
  ind("fitness", "Fitness / Gym", "business"),
  ind("salon_spa", "Salon / Spa", "business"),
  ind("freelancer", "Freelancer", "business"),
  ind("small_business", "Small Business", "business"),
];

export const INDUSTRY_GROUPS: IndustryGroup[] = (
  Object.keys(CATEGORY_LABELS) as IndustryCategory[]
)
  .filter((c) => c !== "other")
  .map((category) => ({
    category,
    label: CATEGORY_LABELS[category],
    industries: INDUSTRIES.filter((i) => i.category === category),
  }))
  .filter((g) => g.industries.length > 0);

const BY_VALUE = new Map(INDUSTRIES.map((i) => [i.value, i]));

export function findIndustry(value: string | null | undefined): Industry | null {
  if (!value) return null;
  return BY_VALUE.get(value) ?? null;
}

/** Recommended feature hrefs for a stored industry value (handles custom
 * "Other" free text → the balanced default set). */
export function recommendedFeatures(value: string | null | undefined): string[] {
  const found = findIndustry(value);
  if (found?.recommends) return found.recommends;
  if (found) return CATEGORY_RECOMMENDS[found.category];
  return CATEGORY_RECOMMENDS.other;
}

export function isRegulated(value: string | null | undefined): boolean {
  return !!findIndustry(value)?.regulated;
}
