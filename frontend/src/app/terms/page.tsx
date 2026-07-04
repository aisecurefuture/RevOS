import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Service — RevOS360",
};

const EFFECTIVE_DATE = "July 4, 2026";
const CONTACT_EMAIL = "legal@revos360.com";

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-white">
      {/* Nav */}
      <header className="border-b border-slate-200 px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <Link href="/">
            <img src="/logo.svg" alt="RevOS360" width={120} height={27} />
          </Link>
          <Link href="/login" className="text-sm text-slate-500 hover:text-slate-900">
            Sign in
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1 className="mb-2 text-3xl font-bold text-slate-900">Terms of Service</h1>
        <p className="mb-10 text-sm text-slate-500">Effective date: {EFFECTIVE_DATE}</p>

        <div className="prose prose-slate max-w-none space-y-8 text-slate-700">

          <section>
            <h2 className="text-xl font-semibold text-slate-900">1. Acceptance of Terms</h2>
            <p>
              By accessing or using RevOS360 ("the Service"), you agree to be bound by these
              Terms of Service ("Terms"). If you are using the Service on behalf of an
              organization, you represent that you have authority to bind that organization
              to these Terms.
            </p>
            <p>
              If you do not agree to these Terms, do not use the Service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">2. Description of Service</h2>
            <p>
              RevOS360 is a business-to-business marketing and sales automation platform that
              provides tools for contact management, email marketing, social media publishing,
              content approval workflows, and sales pipeline management. The Service is
              accessible at <strong>app.revos360.com</strong>.
            </p>
            <p>
              We reserve the right to modify, suspend, or discontinue any part of the Service
              at any time with reasonable notice to active subscribers.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">3. Account Registration</h2>
            <ul className="list-disc space-y-1 pl-6">
              <li>You must provide accurate and complete registration information.</li>
              <li>You are responsible for maintaining the confidentiality of your login
                credentials and for all activity that occurs under your account.</li>
              <li>You must be at least 18 years old to use the Service.</li>
              <li>One person or legal entity may not maintain more than one free trial
                account. Creating multiple accounts to circumvent trial limits is prohibited.</li>
              <li>You must notify us immediately at{" "}
                <a href={`mailto:${CONTACT_EMAIL}`} className="text-blue-600 hover:underline">{CONTACT_EMAIL}</a>{" "}
                of any unauthorized use of your account.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">4. Subscription and Billing</h2>
            <h3 className="mt-4 font-semibold text-slate-800">4.1 Plans and Pricing</h3>
            <p>
              RevOS360 offers a 14-day free trial followed by paid subscription plans (Pro and
              Agency). Current pricing is displayed at the time of purchase and in your account
              billing section. We reserve the right to change pricing with 30 days' advance
              notice to active subscribers.
            </p>

            <h3 className="mt-4 font-semibold text-slate-800">4.2 Payment</h3>
            <p>
              Subscriptions are billed in advance on a monthly or annual basis through Stripe.
              By providing a payment method, you authorize us to charge applicable fees. All
              fees are in USD and non-refundable except as required by law or as described in
              Section 4.4.
            </p>

            <h3 className="mt-4 font-semibold text-slate-800">4.3 Auto-Renewal</h3>
            <p>
              Subscriptions automatically renew at the end of each billing period unless
              cancelled before the renewal date. You may cancel at any time from your account
              settings; your access continues until the end of the paid period.
            </p>

            <h3 className="mt-4 font-semibold text-slate-800">4.4 Refunds</h3>
            <p>
              We do not offer refunds for partial billing periods. If you experience a
              significant service outage (greater than 24 consecutive hours) caused by our
              infrastructure, contact us within 14 days for a pro-rated credit.
            </p>

            <h3 className="mt-4 font-semibold text-slate-800">4.5 Trial Period</h3>
            <p>
              The 14-day free trial gives you agency-level access to evaluate the Service.
              No credit card is required to start a trial. At the end of the trial, access
              is restricted until a paid plan is selected.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">5. Acceptable Use</h2>
            <p>You agree not to use the Service to:</p>
            <ul className="list-disc space-y-1 pl-6">
              <li>Send unsolicited bulk email (spam) or any communication to recipients who
                have not opted in</li>
              <li>Scrape, harvest, or collect email addresses or other personal data without
                the subject's consent</li>
              <li>Violate any applicable law, regulation, or third-party rights</li>
              <li>Post or transmit content that is unlawful, defamatory, obscene, or
                infringing of intellectual property rights</li>
              <li>Attempt to gain unauthorized access to any system, account, or data</li>
              <li>Reverse-engineer, decompile, or attempt to extract source code from the Service</li>
              <li>Use the Service to facilitate deceptive, fraudulent, or misleading content</li>
              <li>Circumvent any rate limits, access controls, or plan limits</li>
              <li>Resell or white-label the Service without written authorization</li>
            </ul>
            <p className="mt-3">
              We reserve the right to suspend or terminate accounts that violate these
              restrictions without prior notice.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">6. Social Platform Compliance</h2>
            <p>
              When using the social publishing features of RevOS360, you agree to comply with
              the terms of service and community standards of each connected platform, including
              but not limited to:
            </p>
            <ul className="list-disc space-y-1 pl-6">
              <li>Meta Platform Terms (developers.facebook.com/terms)</li>
              <li>Instagram Platform Policy (help.instagram.com/581066165581870)</li>
              <li>LinkedIn API Terms of Use</li>
              <li>YouTube Terms of Service</li>
              <li>X (Twitter) Developer Agreement</li>
            </ul>
            <p className="mt-3">
              You represent that you have all rights and permissions required to publish content
              to any connected social account and that such content does not infringe the rights
              of any third party. You are solely responsible for the content you publish through
              the Service.
            </p>
            <p className="mt-3">
              RevOS360 enforces an <strong>approval-first</strong> policy: no content is
              automatically published to any social platform without an explicit human approval
              action within the platform. You acknowledge that this is a workflow tool and not
              an autonomous posting service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">7. Your Data</h2>
            <p>
              You retain ownership of all data, content, and contacts you import or create in
              RevOS360. By using the Service, you grant us a limited license to store, process,
              and display your data solely as necessary to provide the Service.
            </p>
            <p>
              We do not sell, rent, or use your data for our own marketing purposes. See our{" "}
              <Link href="/privacy" className="text-blue-600 hover:underline">Privacy Policy</Link>{" "}
              for full details on how we handle your data.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">8. Intellectual Property</h2>
            <p>
              The RevOS360 platform, including its software, design, and documentation, is owned
              by RevOS360 and protected by copyright, trademark, and other intellectual property
              laws. These Terms do not grant you any right, title, or interest in the Service
              beyond the limited license to use it as described herein.
            </p>
            <p>
              You may not use the RevOS360 name, logo, or brand identity without our prior
              written consent.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">9. Disclaimer of Warranties</h2>
            <p>
              THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND,
              EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO WARRANTIES OF MERCHANTABILITY,
              FITNESS FOR A PARTICULAR PURPOSE, OR NON-INFRINGEMENT.
            </p>
            <p>
              We do not warrant that the Service will be uninterrupted, error-free, or free of
              viruses or other harmful components. Social platform integrations depend on
              third-party APIs that are outside our control and may change or become unavailable.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">10. Limitation of Liability</h2>
            <p>
              TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, REVOS360 SHALL NOT BE LIABLE
              FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES,
              INCLUDING LOST PROFITS, LOST DATA, OR BUSINESS INTERRUPTION, ARISING FROM YOUR
              USE OF OR INABILITY TO USE THE SERVICE.
            </p>
            <p>
              OUR TOTAL CUMULATIVE LIABILITY TO YOU FOR ANY CLAIM ARISING FROM OR RELATED TO
              THESE TERMS OR THE SERVICE SHALL NOT EXCEED THE GREATER OF (A) THE TOTAL FEES
              YOU PAID TO US IN THE 12 MONTHS PRECEDING THE CLAIM OR (B) $100 USD.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">11. Indemnification</h2>
            <p>
              You agree to indemnify, defend, and hold harmless RevOS360 and its officers,
              employees, and agents from any claims, damages, losses, liabilities, costs, and
              expenses (including reasonable legal fees) arising from: (a) your use of the
              Service; (b) your violation of these Terms; (c) content you publish through the
              Service; or (d) your violation of any third-party rights.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">12. Termination</h2>
            <p>
              You may cancel your account at any time from your account settings. We may
              suspend or terminate your account immediately if we determine that you have
              violated these Terms, engaged in fraudulent activity, or pose a risk to the
              Service or other users.
            </p>
            <p>
              Upon termination, your right to use the Service ceases immediately. We will
              retain your data for 30 days after termination (except where a shorter period
              is required for compliance reasons) to allow for account recovery. After that
              period, your data will be permanently deleted.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">13. Governing Law</h2>
            <p>
              These Terms are governed by the laws of the State of Illinois, United States,
              without regard to its conflict-of-law provisions. Any disputes arising from
              these Terms shall be resolved exclusively in the state or federal courts located
              in Cook County, Illinois, and you consent to personal jurisdiction in those courts.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">14. Changes to These Terms</h2>
            <p>
              We may update these Terms from time to time. When we make material changes, we
              will notify you by email and update the effective date above. Continued use of
              the Service after the effective date constitutes acceptance of the updated Terms.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">15. Contact</h2>
            <p>
              For legal inquiries or questions about these Terms:{" "}
              <a href={`mailto:${CONTACT_EMAIL}`} className="text-blue-600 hover:underline">{CONTACT_EMAIL}</a>
            </p>
          </section>

        </div>

        {/* Footer links */}
        <div className="mt-16 border-t border-slate-100 pt-6 text-center text-sm text-slate-400">
          <Link href="/privacy" className="hover:text-slate-600">Privacy Policy</Link>
          <span className="mx-2">·</span>
          <Link href="/" className="hover:text-slate-600">revos360.com</Link>
        </div>
      </main>
    </div>
  );
}
