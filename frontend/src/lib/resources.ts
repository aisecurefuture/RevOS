// Typed wrappers around the brand/offer/campaign CRUD endpoints.

import { apiFetch, apiUpload } from "./api";
import type {
  Approval,
  Brand,
  Campaign,
  CollaborationRequest,
  Contact,
  ContactImportResult,
  Collaboration,
  CollaborationShare,
  ContentItem,
  CreatorDiscovery,
  Deal,
  Insights,
  AnalyticsOverview,
  EmailMessage,
  Form,
  IntegrationStatus,
  Lead,
  MatchCreator,
  MatchProduct,
  MediaAsset,
  MediaVariant,
  Offer,
  PipelineStage,
  ProductDiscovery,
  PublishResult,
  SharedBrandBook,
  Sequence,
  SocialCampaign,
  SocialPost,
  TickResult,
} from "./types";

export const brandsApi = {
  list: () => apiFetch<Brand[]>("/brands"),
  get: (id: string) => apiFetch<Brand>(`/brands/${id}`),
  create: (data: Record<string, unknown>) =>
    apiFetch<Brand>("/brands", { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: Record<string, unknown>) =>
    apiFetch<Brand>(`/brands/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: string) =>
    apiFetch<{ status: string }>(`/brands/${id}`, { method: "DELETE" }),
};

export const offersApi = {
  list: (brandId?: string | null) =>
    apiFetch<Offer[]>(`/offers${brandId ? `?brand_id=${brandId}` : ""}`),
  create: (data: Record<string, unknown>) =>
    apiFetch<Offer>("/offers", { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: Record<string, unknown>) =>
    apiFetch<Offer>(`/offers/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: string) =>
    apiFetch<{ status: string }>(`/offers/${id}`, { method: "DELETE" }),
};

export const campaignsApi = {
  list: (brandId?: string | null) =>
    apiFetch<Campaign[]>(`/campaigns${brandId ? `?brand_id=${brandId}` : ""}`),
  create: (data: Record<string, unknown>) =>
    apiFetch<Campaign>("/campaigns", { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: Record<string, unknown>) =>
    apiFetch<Campaign>(`/campaigns/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: string) =>
    apiFetch<{ status: string }>(`/campaigns/${id}`, { method: "DELETE" }),
};

export const formsApi = {
  list: (brandId?: string | null) =>
    apiFetch<Form[]>(`/forms${brandId ? `?brand_id=${brandId}` : ""}`),
  create: (data: Record<string, unknown>) =>
    apiFetch<Form>("/forms", { method: "POST", body: JSON.stringify(data) }),
  remove: (id: string) =>
    apiFetch<{ status: string }>(`/forms/${id}`, { method: "DELETE" }),
};

export const leadsApi = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<Lead[]>(`/leads${qs ? `?${qs}` : ""}`);
  },
  // Manually add a lead (and optionally a linked contact) with an opt-in attestation.
  create: (data: Record<string, unknown>) =>
    apiFetch<Lead>("/leads", { method: "POST", body: JSON.stringify(data) }),
  // CSV export downloads via the browser (cookie-authenticated, same-origin).
  async exportCsv(params: Record<string, string> = {}): Promise<void> {
    const qs = new URLSearchParams(params).toString();
    const resp = await fetch(`/api/leads/export${qs ? `?${qs}` : ""}`, {
      credentials: "same-origin",
    });
    if (!resp.ok) throw new Error("Export failed");
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "leads.csv";
    a.click();
    URL.revokeObjectURL(url);
  },
};

export const emailsApi = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<EmailMessage[]>(`/emails${qs ? `?${qs}` : ""}`);
  },
  test: (data: Record<string, unknown>) =>
    apiFetch<EmailMessage>("/emails/test", { method: "POST", body: JSON.stringify(data) }),
  preview: (data: Record<string, unknown>) =>
    apiFetch<{ subject: string; html: string }>("/emails/preview", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

export const campaignSendApi = {
  prepare: (campaignId: string, data: Record<string, unknown>) =>
    apiFetch<{ approval_id: string; recipient_count: number; preview_html: string }>(
      `/campaigns/${campaignId}/email/prepare`,
      { method: "POST", body: JSON.stringify(data) },
    ),
};

export const approvalsApi = {
  list: () => apiFetch<Approval[]>("/approvals"),
  pendingCount: () => apiFetch<{ pending: number }>("/approvals/count"),
  approve: (id: string) =>
    apiFetch<{ status: string; sent?: number }>(`/approvals/${id}/approve`, { method: "POST" }),
  reject: (id: string, reason?: string) =>
    apiFetch<{ status: string }>(`/approvals/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
};

export const socialCommentsApi = {
  status: () => apiFetch<{ enabled: boolean }>("/social-comments/status"),
  sync: () =>
    apiFetch<{ connections: number; drafts: number; errors: number }>("/social-comments/sync", { method: "POST" }),
  updateDraft: (commentId: string, replyText: string) =>
    apiFetch<{ drafted_reply: string | null }>(`/social-comments/${commentId}/draft`, {
      method: "POST",
      body: JSON.stringify({ reply_text: replyText }),
    }),
  like: (commentId: string) =>
    apiFetch<{ liked: boolean }>(`/social-comments/${commentId}/like`, { method: "POST" }),
  dismiss: (commentId: string) =>
    apiFetch<{ status: string }>(`/social-comments/${commentId}/dismiss`, { method: "POST" }),
};

export const sequencesApi = {
  list: (brandId?: string | null) =>
    apiFetch<Sequence[]>(`/sequences${brandId ? `?brand_id=${brandId}` : ""}`),
  get: (id: string) => apiFetch<Sequence>(`/sequences/${id}`),
  create: (data: Record<string, unknown>) =>
    apiFetch<Sequence>("/sequences", { method: "POST", body: JSON.stringify(data) }),
  addStep: (id: string, data: Record<string, unknown>) =>
    apiFetch<unknown>(`/sequences/${id}/steps`, { method: "POST", body: JSON.stringify(data) }),
  activate: (id: string) =>
    apiFetch<Sequence>(`/sequences/${id}/activate`, { method: "POST" }),
  pause: (id: string) => apiFetch<Sequence>(`/sequences/${id}/pause`, { method: "POST" }),
  tick: () => apiFetch<TickResult>("/sequences/tick", { method: "POST" }),
};

export const contactsApi = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<Contact[]>(`/contacts${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => apiFetch<Contact>(`/contacts/${id}`),
  update: (id: string, data: Record<string, unknown>) =>
    apiFetch<Contact>(`/contacts/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: string) =>
    apiFetch<{ status: string }>(`/contacts/${id}`, { method: "DELETE" }),
  importCsv: (file: File, brandId?: string | null) => {
    const fd = new FormData();
    fd.append("file", file);
    if (brandId) fd.append("brand_id", brandId);
    return apiUpload<ContactImportResult>("/contacts/import", fd);
  },
  async exportCsv(params: Record<string, string> = {}): Promise<void> {
    const qs = new URLSearchParams(params).toString();
    const resp = await fetch(`/api/contacts/export${qs ? `?${qs}` : ""}`, {
      credentials: "same-origin",
    });
    if (!resp.ok) throw new Error("Export failed");
    const url = URL.createObjectURL(await resp.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = "contacts.csv";
    a.click();
    URL.revokeObjectURL(url);
  },
};

export const dealsApi = {
  list: (brandId?: string | null) =>
    apiFetch<Deal[]>(`/deals${brandId ? `?brand_id=${brandId}` : ""}`),
  pipeline: (brandId?: string | null) =>
    apiFetch<PipelineStage[]>(`/deals/pipeline${brandId ? `?brand_id=${brandId}` : ""}`),
  create: (data: Record<string, unknown>) =>
    apiFetch<Deal>("/deals", { method: "POST", body: JSON.stringify(data) }),
  move: (id: string, stageId: string) =>
    apiFetch<Deal>(`/deals/${id}/move`, {
      method: "POST",
      body: JSON.stringify({ pipeline_stage_id: stageId }),
    }),
};

export const contentApi = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<ContentItem[]>(`/content${qs ? `?${qs}` : ""}`);
  },
  create: (data: Record<string, unknown>) =>
    apiFetch<ContentItem>("/content", { method: "POST", body: JSON.stringify(data) }),
  transition: (id: string, action: string) =>
    apiFetch<ContentItem>(`/content/${id}/${action}`, { method: "POST" }),
  ideas: (data: Record<string, unknown>) =>
    apiFetch<{ ideas: string[]; source: string }>("/content/ideas", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

export const socialApi = {
  status: () => apiFetch<{ adapters: Record<string, boolean> }>("/social/status"),
  campaigns: (brandId?: string | null) =>
    apiFetch<SocialCampaign[]>(`/social/campaigns${brandId ? `?brand_id=${brandId}` : ""}`),
  createCampaign: (data: Record<string, unknown>) =>
    apiFetch<SocialCampaign>("/social/campaigns", { method: "POST", body: JSON.stringify(data) }),
  posts: (brandId?: string | null) =>
    apiFetch<SocialPost[]>(`/social/posts${brandId ? `?brand_id=${brandId}` : ""}`),
  createPost: (data: Record<string, unknown>) =>
    apiFetch<SocialPost>("/social/posts", { method: "POST", body: JSON.stringify(data) }),
  uploadMedia: (file: File, brandId: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("brand_id", brandId);
    return apiUpload<{ media_url: string; kind: string; filename: string; mime_type: string | null }>(
      "/social/upload-media", fd,
    );
  },
  publish: (id: string) =>
    apiFetch<PublishResult>(`/social/posts/${id}/publish`, { method: "POST" }),
  submitForApproval: (id: string, connectionId?: string) =>
    apiFetch<{ approval_request_id: string; message: string }>(
      `/social/posts/${id}/submit${connectionId ? `?connection_id=${connectionId}` : ""}`,
      { method: "POST" },
    ),
};

export const mediaApi = {
  list: (brandId?: string | null) =>
    apiFetch<MediaAsset[]>(`/media${brandId ? `?brand_id=${brandId}` : ""}`),
  get: (id: string) => apiFetch<MediaAsset>(`/media/${id}`),
  upload: (file: File, brandId: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("brand_id", brandId);
    return apiUpload<MediaAsset>("/media", fd);
  },
  process: (id: string, platforms: string[], enhance: boolean) =>
    apiFetch<MediaVariant[]>(`/media/${id}/process`, {
      method: "POST",
      body: JSON.stringify({ platforms, enhance }),
    }),
  approveVariant: (id: string) =>
    apiFetch<MediaVariant>(`/media/variants/${id}/approve`, { method: "POST" }),
};

export const analyticsApi = {
  overview: (brandId?: string | null) =>
    apiFetch<AnalyticsOverview>(`/analytics/overview${brandId ? `?brand_id=${brandId}` : ""}`),
  revenue: (brandId?: string | null) =>
    apiFetch<{ offer: string; amount_cents: number }[]>(
      `/analytics/revenue${brandId ? `?brand_id=${brandId}` : ""}`,
    ),
  pipeline: (brandId?: string | null) =>
    apiFetch<{ stage: string; count: number; amount_cents: number }[]>(
      `/analytics/pipeline${brandId ? `?brand_id=${brandId}` : ""}`,
    ),
  funnel: (brandId?: string | null) =>
    apiFetch<{ stage: string; count: number }[]>(
      `/analytics/funnel${brandId ? `?brand_id=${brandId}` : ""}`,
    ),
  async exportCsv(brandId?: string | null): Promise<void> {
    const qs = brandId ? `?brand_id=${brandId}` : "";
    const resp = await fetch(`/api/analytics/export${qs}`, { credentials: "same-origin" });
    if (!resp.ok) throw new Error("Export failed");
    const url = URL.createObjectURL(await resp.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = "analytics.csv";
    a.click();
    URL.revokeObjectURL(url);
  },
};

export const integrationsApi = {
  status: () => apiFetch<IntegrationStatus>("/integrations/status"),
  async exportContacts(fmt: "csv" | "notion", brandId?: string | null): Promise<void> {
    const params = new URLSearchParams({ entity: "contacts", fmt });
    if (brandId) params.set("brand_id", brandId);
    const resp = await fetch(`/api/integrations/export?${params}`, { credentials: "same-origin" });
    if (!resp.ok) throw new Error("Export failed");
    const url = URL.createObjectURL(await resp.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = fmt === "notion" ? "contacts.md" : "contacts.csv";
    a.click();
    URL.revokeObjectURL(url);
  },
};

export const aiApi = {
  status: () => apiFetch<{ available: boolean; provider: string }>("/ai/status"),
  draftSocial: (brandId: string, platform: string, topic: string) =>
    apiFetch<{ text: string; source: string }>("/ai/draft-social", {
      method: "POST",
      body: JSON.stringify({ brand_id: brandId, platform, topic }),
    }),
  draftEmail: (brandId: string, goal: string) =>
    apiFetch<{ text: string; source: string }>("/ai/draft-email", {
      method: "POST",
      body: JSON.stringify({ brand_id: brandId, goal }),
    }),
};

function qs(params: Record<string, string | undefined>): string {
  const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v));
  const s = new URLSearchParams(clean as Record<string, string>).toString();
  return s ? `?${s}` : "";
}

export const marketplaceApi = {
  // Your own roster (for the "rank against" + request pickers, and management).
  myCreators: (params: Record<string, string | undefined> = {}) =>
    apiFetch<MatchCreator[]>(`/matching/creators${qs(params)}`),
  createCreator: (data: Record<string, unknown>) =>
    apiFetch<MatchCreator>("/matching/creators", { method: "POST", body: JSON.stringify(data) }),
  updateCreator: (id: string, data: Record<string, unknown>) =>
    apiFetch<MatchCreator>(`/matching/creators/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  myProducts: (params: Record<string, string | undefined> = {}) =>
    apiFetch<MatchProduct[]>(`/matching/products${qs(params)}`),
  createProduct: (data: Record<string, unknown>) =>
    apiFetch<MatchProduct>("/matching/products", { method: "POST", body: JSON.stringify(data) }),
  importOfferProduct: (data: Record<string, unknown>) =>
    apiFetch<MatchProduct>("/matching/products/import-offer", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateProduct: (id: string, data: Record<string, unknown>) =>
    apiFetch<MatchProduct>(`/matching/products/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  // Cross-tenant, consent-gated discovery.
  discoverCreators: (params: Record<string, string | undefined> = {}) =>
    apiFetch<CreatorDiscovery[]>(`/matching/discover/creators${qs(params)}`),
  discoverProducts: (params: Record<string, string | undefined> = {}) =>
    apiFetch<ProductDiscovery[]>(`/matching/discover/products${qs(params)}`),

  // Collaboration requests.
  createCollaboration: (data: Record<string, unknown>) =>
    apiFetch<CollaborationRequest>("/matching/collaborations", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  collaborations: (box: "incoming" | "outgoing", status?: string) =>
    apiFetch<CollaborationRequest[]>(`/matching/collaborations${qs({ box, status })}`),
  respond: (id: string, accept: boolean, note?: string) =>
    apiFetch<CollaborationRequest>(`/matching/collaborations/${id}/respond`, {
      method: "POST",
      body: JSON.stringify({ accept, note }),
    }),
  withdraw: (id: string) =>
    apiFetch<CollaborationRequest>(`/matching/collaborations/${id}/withdraw`, { method: "POST" }),

  // Insight dashboards (own subjects only).
  creatorInsights: (id: string) => apiFetch<Insights>(`/matching/creators/${id}/insights`),
  productInsights: (id: string) => apiFetch<Insights>(`/matching/products/${id}/insights`),
};

export const workspaceApi = {
  list: (state?: string) =>
    apiFetch<Collaboration[]>(`/matching/workspaces${state ? `?state=${state}` : ""}`),
  get: (id: string) => apiFetch<Collaboration>(`/matching/workspaces/${id}`),
  end: (id: string) =>
    apiFetch<Collaboration>(`/matching/workspaces/${id}/end`, { method: "POST" }),
  shares: (id: string) => apiFetch<CollaborationShare[]>(`/matching/workspaces/${id}/shares`),
  shareBrandBook: (id: string, brandId: string) =>
    apiFetch<CollaborationShare>(`/matching/workspaces/${id}/shares/brand-book`, {
      method: "POST",
      body: JSON.stringify({ brand_id: brandId }),
    }),
  revokeShare: (workspaceId: string, shareId: string) =>
    apiFetch<{ status: string }>(`/matching/workspaces/${workspaceId}/shares/${shareId}`, {
      method: "DELETE",
    }),
  readSharedBrandBook: (workspaceId: string, shareId: string) =>
    apiFetch<SharedBrandBook>(`/matching/workspaces/${workspaceId}/shares/${shareId}/brand-book`),
};
