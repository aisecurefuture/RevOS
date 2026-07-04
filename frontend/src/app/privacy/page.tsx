import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy — RevOS360",
};

const EFFECTIVE_DATE = "July 4, 2026";
const CONTACT_EMAIL = "privacy@revos360.com";

export default function PrivacyPage() {
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
        <h1 className="mb-2 text-3xl font-bold text-slate-900">Privacy Policy</h1>
        <p className="mb-10 text-sm text-slate-500">Effective date: {EFFECTIVE_DATE}</p>

        <div className="prose prose-slate max-w-none space-y-8 text-slate-700">

          <section>
            <h2 className="text-xl font-semibold text-slate-900">1. Introduction</h2>
            <p>
              RevOS360 ("RevOS", "we", "us", or "our") operates the RevOS360 marketing and sales
              automation platform, accessible at <strong>app.revos360.com</strong> and via our
              API at <strong>api.revos360.com</strong>. This Privacy Policy explains how we
              collect, use, store, and protect information when you use our services.
            </p>
            <p>
              By creating an account or using RevOS360, you agree to this policy. If you do not
              agree, please do not use our services.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">2. Information We Collect</h2>

            <h3 className="mt-4 font-semibold text-slate-800">2.1 Account Information</h3>
            <p>When you register, we collect your name, email address, and password (stored as
              a salted cryptographic hash — we never store your plaintext password). Account owners
              may also provide a company name, timezone, and profile avatar URL.</p>

            <h3 className="mt-4 font-semibold text-slate-800">2.2 Billing Information</h3>
            <p>Subscription payments are processed by <strong>Stripe, Inc.</strong> We never
              receive or store your full credit card number. Stripe provides us with a customer
              identifier, subscription status, and last-four card digits for display purposes.
              Stripe's privacy policy is available at stripe.com/privacy.</p>

            <h3 className="mt-4 font-semibold text-slate-800">2.3 Social Platform Credentials</h3>
            <p>When you connect a Facebook Page or Instagram Business Account, you authorize
              our Meta developer application to act on your behalf. We receive an OAuth access
              token from Meta. This token is <strong>never stored in our primary database</strong>;
              instead it is encrypted and stored in an isolated secrets vault (OpenBao / HashiCorp
              Vault KV v2). The token is used solely to perform actions you explicitly request and
              approve within RevOS360 (e.g., publishing a post you have reviewed and approved).</p>

            <h3 className="mt-4 font-semibold text-slate-800">2.4 Contact and CRM Data</h3>
            <p>You may import contacts, leads, and company records into RevOS360. This data
              belongs to you. We store it in your account's isolated workspace and do not share,
              sell, or use it for our own marketing or advertising purposes.</p>

            <h3 className="mt-4 font-semibold text-slate-800">2.5 Usage and Log Data</h3>
            <p>We collect server-side logs including IP addresses, browser user-agent strings,
              request timestamps, and feature usage events. This data is used for security
              monitoring, debugging, and product improvement. Log records are retained for
              90 days and then automatically purged.</p>

            <h3 className="mt-4 font-semibold text-slate-800">2.6 Cookies and Session Tokens</h3>
            <p>We use HTTP-only session cookies to maintain your authenticated session and a
              double-submit CSRF token cookie to prevent cross-site request forgery. We do not
              use third-party advertising cookies or tracking pixels.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">3. How We Use Your Information</h2>
            <ul className="list-disc space-y-1 pl-6">
              <li>To provide and operate the RevOS360 platform</li>
              <li>To authenticate your identity and secure your account</li>
              <li>To process subscription billing through Stripe</li>
              <li>To connect to social platforms you authorize and carry out actions you approve</li>
              <li>To send transactional emails (account verification, password reset, billing receipts)</li>
              <li>To detect and prevent fraud, abuse, and security threats</li>
              <li>To improve the platform based on aggregate, anonymized usage patterns</li>
            </ul>
            <p className="mt-3">
              We do <strong>not</strong> sell your personal information to third parties. We do not
              use your contact data, social connections, or CRM data for our own advertising.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">4. Social Platform Integrations (Meta / Facebook / Instagram)</h2>
            <p>
              RevOS360 integrates with the Meta Graph API to allow you to schedule and publish
              content to Facebook Pages and Instagram Business Accounts that you own or manage.
            </p>
            <ul className="list-disc space-y-2 pl-6">
              <li>
                <strong>Access requested:</strong> Meta's developer platform uses a use-case-based
                permission system — developers select functional use cases and Meta grants the
                underlying permissions automatically. We have requested all use cases available
                to our app type that are necessary to provide social publishing features. These
                cover managing Facebook Pages, reading page engagement, and publishing content
                to Instagram Business Accounts. Certain use cases are restricted by Meta
                and were not available for us to request. We do not request or receive access
                to personal profiles, private messages, or ad accounts.
              </li>
              <li>
                <strong>What we access:</strong> We access your Facebook Pages and linked
                Instagram Business Accounts to publish content you have explicitly drafted
                and approved inside RevOS360. We do not read private messages, friend lists,
                personal timelines, or any data beyond what is needed for the above purpose.
              </li>
              <li>
                <strong>Token storage:</strong> OAuth access tokens are stored exclusively in an
                encrypted secrets vault, isolated from our main application database. Tokens are
                never logged or transmitted in plaintext.
              </li>
              <li>
                <strong>Approval-first posting:</strong> No content is posted to any social
                platform without your explicit approval action within the platform. We do not
                auto-post without human sign-off.
              </li>
              <li>
                <strong>Disconnecting:</strong> You may revoke RevOS360's access to your
                social accounts at any time from your RevOS360 settings page or directly
                from your Facebook App Settings at facebook.com/settings?tab=applications.
                Upon disconnection, we delete the stored token from our vault immediately.
              </li>
              <li>
                <strong>Data deletion:</strong> You may request deletion of all data associated
                with your social connections by contacting us at <a href={`mailto:${CONTACT_EMAIL}`} className="text-blue-600 hover:underline">{CONTACT_EMAIL}</a>.
                We will remove your tokens and any associated metadata within 30 days.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">5. Data Storage and Security</h2>
            <ul className="list-disc space-y-2 pl-6">
              <li>Application data is stored in a PostgreSQL database hosted on dedicated
                infrastructure in the European Union (Hetzner, Frankfurt region).</li>
              <li>OAuth tokens and other sensitive credentials are stored in OpenBao (a
                HashiCorp Vault-compatible secrets manager) with encryption at rest.</li>
              <li>All data in transit is encrypted using TLS 1.2 or higher.</li>
              <li>Passwords are hashed using bcrypt with a per-user salt.</li>
              <li>Accounts support optional two-factor authentication (TOTP).</li>
              <li>We perform automated backups and store them encrypted with AES-256.</li>
            </ul>
            <p className="mt-3">
              Despite these measures, no system is 100% secure. If you believe your account
              has been compromised, contact us immediately at{" "}
              <a href={`mailto:${CONTACT_EMAIL}`} className="text-blue-600 hover:underline">{CONTACT_EMAIL}</a>.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">6. Data Retention</h2>
            <ul className="list-disc space-y-1 pl-6">
              <li>Account data is retained while your account is active.</li>
              <li>After account deletion, your personal data is purged within 30 days, except
                where retention is required by law (e.g., billing records retained 7 years
                for tax compliance).</li>
              <li>Server logs are retained for 90 days.</li>
              <li>Social OAuth tokens are deleted immediately upon disconnection or account deletion.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">7. Your Rights</h2>
            <p>Depending on your location, you may have the following rights:</p>
            <ul className="list-disc space-y-1 pl-6">
              <li><strong>Access:</strong> Request a copy of the personal data we hold about you.</li>
              <li><strong>Correction:</strong> Request correction of inaccurate or incomplete data.</li>
              <li><strong>Deletion:</strong> Request deletion of your account and personal data.</li>
              <li><strong>Portability:</strong> Request an export of your data in a machine-readable format.</li>
              <li><strong>Objection:</strong> Object to processing of your data in certain circumstances.</li>
              <li><strong>Restriction:</strong> Request restriction of processing in certain circumstances.</li>
            </ul>
            <p className="mt-3">
              To exercise any of these rights, email{" "}
              <a href={`mailto:${CONTACT_EMAIL}`} className="text-blue-600 hover:underline">{CONTACT_EMAIL}</a>.
              We will respond within 30 days.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">8. Third-Party Services</h2>
            <p>RevOS360 uses the following third-party services, each with their own privacy policies:</p>
            <ul className="list-disc space-y-1 pl-6">
              <li><strong>Stripe</strong> — payment processing (stripe.com/privacy)</li>
              <li><strong>Meta / Facebook</strong> — social platform integration (facebook.com/policy)</li>
              <li><strong>Resend</strong> — transactional email delivery (resend.com/legal/privacy-policy)</li>
              <li><strong>Hetzner</strong> — infrastructure hosting (hetzner.com/legal/privacy-policy)</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">9. Children's Privacy</h2>
            <p>
              RevOS360 is a business-to-business service intended for users who are at least
              18 years old. We do not knowingly collect personal information from children
              under 13. If you believe a child has provided us with personal information,
              contact us and we will delete it promptly.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">10. Changes to This Policy</h2>
            <p>
              We may update this Privacy Policy from time to time. When we make material
              changes, we will notify you by email and update the effective date at the top
              of this page. Your continued use of RevOS360 after the effective date constitutes
              your acceptance of the updated policy.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-slate-900">11. Contact Us</h2>
            <p>For privacy-related questions, data requests, or to report a concern:</p>
            <p className="mt-2">
              <strong>Email:</strong>{" "}
              <a href={`mailto:${CONTACT_EMAIL}`} className="text-blue-600 hover:underline">{CONTACT_EMAIL}</a>
            </p>
            <p>
              <strong>Subject line:</strong> Privacy Request — [your name or account email]
            </p>
          </section>

        </div>

        {/* Footer links */}
        <div className="mt-16 border-t border-slate-100 pt-6 text-center text-sm text-slate-400">
          <Link href="/terms" className="hover:text-slate-600">Terms of Service</Link>
          <span className="mx-2">·</span>
          <Link href="/" className="hover:text-slate-600">revos360.com</Link>
        </div>
      </main>
    </div>
  );
}
