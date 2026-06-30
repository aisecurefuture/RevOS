"""Seed the five default brands with their full marketing context.

Idempotent: a brand is skipped if its slug already exists. Each brand gets a
voice, audiences, buyer personas, offers (incl. a lead magnet), CTAs, content
pillars, and a consent-first newsletter form. CyberArmor and the book also get
a starter email sequence.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.brand import Audience, Brand, BrandType, BrandVoice, BuyerPersona
from app.models.campaign import Form, FormType
from app.models.content import CTA, Pillar
from app.models.email import EmailCategory, EmailTemplate
from app.models.offer import Offer, OfferStatus, OfferType
from app.models.sequence import Sequence, SequenceStatus, SequenceStep, SequenceType

BRANDS: list[dict] = [
    {
        "slug": "cyberarmor", "name": "CyberArmor.ai", "type": BrandType.company,
        "website": "https://cyberarmor.ai",
        "tagline": "AI security, runtime protection & AI trust",
        "description": "AI security platform: runtime protection, AI trust, URL/content "
                       "trust gate, AI governance, and security architecture.",
        "voice": {
            "tone": "authoritative, technical, plain-spoken, no FUD",
            "do_list": ["lead with the threat model", "be concrete", "respect the reader's expertise"],
            "dont_list": ["fear-monger", "hand-wave", "overclaim"],
            "value_props": ["runtime AI protection", "AI trust & governance", "security architecture"],
        },
        "audiences": [
            ("CISOs & security architects", "Security leaders evaluating AI risk"),
            ("Startup founders", "Founders shipping AI products who need to prove trust"),
            ("AI governance leaders", "Owners of AI policy, risk, and compliance"),
        ],
        "personas": [{
            "name": "CISO Carla", "role_title": "Chief Information Security Officer",
            "goals": ["reduce AI attack surface", "demonstrate AI governance"],
            "pain_points": ["no runtime visibility into AI", "board pressure on AI risk"],
            "objections": ["another tool to manage", "unproven category"],
        }],
        "offers": [
            {"name": "AI Security Checklist", "type": OfferType.lead_magnet,
             "asset_url": "https://cyberarmor.ai/checklist.pdf",
             "description": "A practical checklist for securing AI systems in production."},
            {"name": "Design Partner Program", "type": OfferType.service,
             "description": "Co-build AI runtime protection with the CyberArmor team."},
        ],
        "ctas": ["Request a demo", "Join the design partner program",
                 "Download the AI security checklist", "Schedule a consultation"],
        "pillars": ["AI runtime protection", "AI governance", "Threat intelligence",
                    "Security architecture"],
        "sequence": {
            "type": SequenceType.cyberarmor_buyer, "name": "CyberArmor buyer nurture",
            "steps": [
                ("Your AI security checklist", "<p>Thanks for grabbing the checklist — here's how "
                 "to use it.</p>", 0),
                ("The #1 AI security gap we see", "<p>Most teams have no runtime visibility into "
                 "their AI. Here's why that matters.</p>", 2880),
                ("See CyberArmor in action", "<p>Want a 20-minute walkthrough? "
                 "{{unsubscribe_url}}</p>", 4320),
            ],
        },
    },
    {
        "slug": "tradicore-usa", "name": "TradicoreUSA.com", "type": BrandType.company,
        "website": "https://tradicoreusa.com",
        "tagline": "Trade, logistics & sourcing for growing businesses",
        "description": "Trade, logistics, sourcing, and import/export platform for "
                       "small businesses and sourcing partners.",
        "voice": {"tone": "practical, trustworthy, helpful",
                  "do_list": ["be specific about timelines and costs"],
                  "dont_list": ["overpromise delivery"],
                  "value_props": ["reliable sourcing", "transparent logistics"]},
        "audiences": [
            ("Small businesses & retailers", "Businesses sourcing products to sell"),
            ("Logistics buyers", "Buyers needing freight & fulfillment"),
        ],
        "personas": [{
            "name": "Retailer Rosa", "role_title": "Small business owner",
            "goals": ["reliable supply", "predictable landed cost"],
            "pain_points": ["unreliable suppliers", "opaque shipping costs"]}],
        "offers": [
            {"name": "Sourcing Starter Guide", "type": OfferType.lead_magnet,
             "asset_url": "https://tradicoreusa.com/guide.pdf",
             "description": "How to source reliably and avoid costly mistakes."},
            {"name": "Sourcing & Logistics Service", "type": OfferType.service,
             "description": "End-to-end sourcing and logistics support."},
        ],
        "ctas": ["Request a quote", "Schedule a consultation", "Supplier inquiry"],
        "pillars": ["Sourcing", "Logistics", "Cost transparency"],
    },
    {
        "slug": "patrick-m-kelly-jr", "name": "PatrickMKellyJr.com", "type": BrandType.personal,
        "website": "https://patrickmkellyjr.com",
        "tagline": "AI security architect · author · speaker · advisor",
        "description": "Executive technical leader, AI security architect, author, "
                       "speaker, advisor, and founder.",
        "voice": {"tone": "credible, generous, forward-looking",
                  "do_list": ["share hard-won lessons", "be specific"],
                  "dont_list": ["humble-brag"],
                  "value_props": ["AI security expertise", "executive perspective"]},
        "audiences": [
            ("Executives & founders", "Leaders navigating AI risk and strategy"),
            ("Event organizers", "Conferences seeking an AI security speaker"),
            ("Readers", "People interested in safe AI and human agency"),
        ],
        "personas": [{
            "name": "Organizer Omar", "role_title": "Conference organizer",
            "goals": ["book a compelling AI security speaker"],
            "pain_points": ["generic speakers", "no practical takeaways"]}],
        "offers": [
            {"name": "Advisory Call", "type": OfferType.consulting,
             "description": "A focused advisory call on AI security & strategy."},
            {"name": "Speaking Engagement", "type": OfferType.service,
             "description": "Keynotes and workshops on AI security and trust."},
        ],
        "ctas": ["Book Patrick", "Hire Patrick", "Read the book", "Join the newsletter",
                 "Request an advisory call"],
        "pillars": ["AI security", "Leadership", "The book", "Speaking"],
    },
    {
        "slug": "first-golden-logistics", "name": "FirstGoldenLogistics.com",
        "type": BrandType.company, "website": "https://firstgoldenlogistics.com",
        "tagline": "Logistics, trade & supply chain partners",
        "description": "Logistics, trade, supply chain, and business development platform.",
        "voice": {"tone": "dependable, direct, partnership-minded",
                  "do_list": ["emphasize reliability"], "dont_list": ["use jargon"],
                  "value_props": ["dependable logistics", "trade partnerships"]},
        "audiences": [
            ("Importers & exporters", "Businesses moving goods across borders"),
            ("Manufacturers", "Manufacturers needing supply chain support"),
        ],
        "personas": [{
            "name": "Importer Ian", "role_title": "Operations lead",
            "goals": ["reliable freight", "fewer customs delays"],
            "pain_points": ["delays", "unclear status"]}],
        "offers": [
            {"name": "Logistics Quote", "type": OfferType.service,
             "description": "Get a tailored logistics quote."},
        ],
        "ctas": ["Request a logistics quote", "Partner inquiry", "Schedule a consultation"],
        "pillars": ["Freight", "Customs", "Partnerships"],
    },
    {
        "slug": "ai-secure-future", "name": "AI Secure Future", "type": BrandType.book,
        "website": "https://aisecurefuture.com",
        "tagline": "A book about safe AI, trust & human agency",
        "description": "A book and thought-leadership platform about safe AI, AI "
                       "security, trust, and human agency.",
        "voice": {"tone": "thoughtful, accessible, hopeful but honest",
                  "do_list": ["make it human", "avoid hype"], "dont_list": ["doom"],
                  "value_props": ["safe AI", "human agency", "practical trust"]},
        "audiences": [
            ("Business & technical leaders", "Leaders making AI decisions"),
            ("General readers", "Anyone curious about safe AI"),
            ("Parents & students", "People thinking about AI's role in life"),
        ],
        "personas": [{
            "name": "Reader Riya", "role_title": "Curious professional",
            "goals": ["understand AI risk", "feel agency over AI"],
            "pain_points": ["overwhelmed by hype", "unsure what to trust"]}],
        "offers": [
            {"name": "AI Secure Future (book)", "type": OfferType.book,
             "price_cents": 2499,
             "description": "The book on safe AI, trust, and human agency."},
            {"name": "Companion Checklist", "type": OfferType.lead_magnet,
             "asset_url": "https://aisecurefuture.com/companion.pdf",
             "description": "A companion checklist for readers."},
        ],
        "ctas": ["Buy the book", "Join the reader list", "Download the companion checklist",
                 "Book a speaking engagement"],
        "pillars": ["Safe AI", "Human agency", "Trust", "Book launch"],
        "sequence": {
            "type": SequenceType.book_launch, "name": "Book launch sequence",
            "steps": [
                ("Welcome to AI Secure Future", "<p>Thanks for joining the reader list!</p>", 0),
                ("A preview chapter", "<p>Here's a chapter to get you started.</p>", 2880),
                ("Launch day is here", "<p>The book is live. {{unsubscribe_url}}</p>", 5760),
            ],
        },
    },
]


async def _exists(db: AsyncSession, slug: str) -> bool:
    result = await db.execute(select(Brand).where(Brand.slug == slug))
    return result.scalar_one_or_none() is not None


async def seed_brands(db: AsyncSession) -> int:
    created = 0
    for cfg in BRANDS:
        if await _exists(db, cfg["slug"]):
            continue
        brand = Brand(
            name=cfg["name"], slug=cfg["slug"], brand_type=cfg["type"],
            website_url=cfg["website"], tagline=cfg["tagline"],
            description=cfg["description"], is_active=True,
            settings={"ctas": cfg["ctas"]},
        )
        db.add(brand)
        await db.flush()

        v = cfg["voice"]
        db.add(BrandVoice(brand_id=brand.id, tone=v["tone"], do_list=v["do_list"],
                          dont_list=v["dont_list"], value_props=v["value_props"]))
        for name, desc in cfg["audiences"]:
            db.add(Audience(brand_id=brand.id, name=name, description=desc))
        for p in cfg["personas"]:
            db.add(BuyerPersona(brand_id=brand.id, name=p["name"], role_title=p["role_title"],
                                goals=p.get("goals", []), pain_points=p.get("pain_points", []),
                                objections=p.get("objections", [])))
        for label in cfg["ctas"]:
            db.add(CTA(brand_id=brand.id, label=label))
        for pillar in cfg["pillars"]:
            db.add(Pillar(brand_id=brand.id, name=pillar))

        magnet_offer = None
        for o in cfg["offers"]:
            offer = Offer(
                brand_id=brand.id, offer_type=o["type"], name=o["name"],
                slug=o["name"].lower().replace(" ", "-").replace("(", "").replace(")", ""),
                description=o["description"], status=OfferStatus.active,
                price_cents=o.get("price_cents"), asset_url=o.get("asset_url"),
            )
            db.add(offer)
            await db.flush()
            if o["type"] == OfferType.lead_magnet and magnet_offer is None:
                magnet_offer = offer

        # A consent-first, double-opt-in newsletter / lead-magnet form.
        db.add(Form(
            brand_id=brand.id, name=f"{brand.name} newsletter",
            slug=f"{cfg['slug']}-newsletter",
            form_type=FormType.lead_magnet if magnet_offer else FormType.newsletter,
            consent_required=True, double_optin=True,
            consent_text="I agree to receive emails and can unsubscribe anytime.",
            lead_magnet_offer_id=magnet_offer.id if magnet_offer else None,
            tags_to_apply=[cfg["slug"]],
        ))

        seq_cfg = cfg.get("sequence")
        if seq_cfg:
            sequence = Sequence(
                brand_id=brand.id, name=seq_cfg["name"], slug=f"{cfg['slug']}-seq",
                sequence_type=seq_cfg["type"], status=SequenceStatus.draft,
                trigger="form_submit", stop_on_reply=True,
            )
            db.add(sequence)
            await db.flush()
            for i, (subject, html, delay) in enumerate(seq_cfg["steps"]):
                db.add(SequenceStep(sequence_id=sequence.id, order_index=i, name=subject,
                                    delay_minutes=delay, subject=subject, html_body=html))
            db.add(EmailTemplate(
                brand_id=brand.id, name=f"{brand.name} welcome",
                slug=f"{cfg['slug']}-welcome", category=EmailCategory.welcome,
                subject=seq_cfg["steps"][0][0], html_body=seq_cfg["steps"][0][1]))

        created += 1
    await db.flush()
    return created
