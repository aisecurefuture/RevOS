"use client";

import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { useTour } from "@/lib/tour";

interface Faq {
  q: string;
  a: string;
}

// Concise, honest answers — note the regulated-industry one deliberately does
// NOT claim auto-compliance.
const FAQS: Faq[] = [
  {
    q: "Why does everything start with the Brand Book?",
    a: "The Brand Book is your source of truth — your voice, approved claims, facts, and guardrails. Every email, post, script, and video the platform generates is grounded in it, so output stays on-brand and accurate instead of being isolated AI guesses. Fill it in first and everything else gets better.",
  },
  {
    q: "What does “approval-first” mean?",
    a: "Nothing AI-generated is published on your behalf without your review. Drafts are created for you, then wait in Approvals until you approve them. You can turn on Autopilot to auto-publish content that passes every guardrail cleanly, but anything flagged still waits for a human.",
  },
  {
    q: "How do I connect my social accounts?",
    a: "Go to Settings → Social Connections and connect each network (LinkedIn, Instagram, Facebook, X, YouTube, TikTok, Threads) via its official login. Once connected you can publish and schedule posts, and everything still flows through approval first.",
  },
  {
    q: "How do I turn a slide deck into a video?",
    a: "Open Pitch Videos, upload a PowerPoint (.pptx) or paste a Deck Spec, pick a narration voice and style, and generate. The platform writes and narrates each scene and renders a brand-themed MP4. You can also create a consented on-camera avatar of yourself under Avatar Personas.",
  },
  {
    q: "Can I run more than one brand?",
    a: "Yes. Add each business, book, or client under Brands — a new brand is data, not a rebuild. Switch the active brand from the selector at the top; everything (content, CRM, analytics, approvals) scopes to it.",
  },
  {
    q: "Does the platform make my content legally compliant?",
    a: "No — and it's important to be clear about that. RevOS helps you set disclaimers and guardrails in the Brand Book and flags likely issues, but you are responsible for what you publish. If you're in a regulated field (medical, legal, financial, insurance), have qualified review where required. The tools assist compliance; they don't guarantee it.",
  },
  {
    q: "How do I invite my team?",
    a: "Go to Settings → Team to invite teammates by email and assign roles (owner, admin, editor, viewer). Roles control who can create, edit, approve, and publish.",
  },
  {
    q: "Where do the “Recommended for you” features come from?",
    a: "From the industry you set on your brand. Change it anytime by editing the brand under Brands, and the dashboard recommendations update. Recommendations only highlight useful starting points — every feature is always available from the sidebar.",
  },
];

function FaqItem({ faq }: { faq: Faq }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-slate-100 last:border-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 py-3 text-left text-sm font-medium text-slate-800"
        aria-expanded={open}
      >
        {faq.q}
        <span aria-hidden className={`shrink-0 text-slate-400 transition-transform ${open ? "rotate-90" : ""}`}>
          ›
        </span>
      </button>
      {open ? <p className="pb-4 text-sm text-slate-600">{faq.a}</p> : null}
    </div>
  );
}

export default function HelpPage() {
  const { startTour } = useTour();
  return (
    <>
      <PageHeader
        title="Help & FAQ"
        description="Answers to common questions — and a replay of the product tour whenever you want it."
      />

      <Card className="mb-4 flex flex-wrap items-center justify-between gap-3 border-brand/30 bg-brand/[0.03]">
        <div>
          <CardTitle>Take the product tour</CardTitle>
          <p className="text-xs text-slate-500">
            A 60-second walkthrough of how the app is organized and where to start.
          </p>
        </div>
        <Button onClick={startTour}>Replay tour</Button>
      </Card>

      <Card>
        <CardTitle>Frequently asked questions</CardTitle>
        <div>
          {FAQS.map((faq) => (
            <FaqItem key={faq.q} faq={faq} />
          ))}
        </div>
      </Card>

      <Card className="mt-4">
        <CardTitle>Still stuck?</CardTitle>
        <p className="text-sm text-slate-600">
          Email{" "}
          <a href="mailto:support@revos360.com" className="text-brand hover:underline">
            support@revos360.com
          </a>{" "}
          and we&apos;ll help. Include your brand name and what you were trying to do.
        </p>
      </Card>
    </>
  );
}
