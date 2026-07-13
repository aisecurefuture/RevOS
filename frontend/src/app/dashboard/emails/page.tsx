"use client";

import { useCallback, useEffect, useState } from "react";

import { NoBrandCta } from "@/components/NoBrandCta";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";
import { emailsApi } from "@/lib/resources";
import type { EmailMessage } from "@/lib/types";

const STATUS_STYLES: Record<string, string> = {
  sent: "bg-green-100 text-green-700",
  delivered: "bg-green-100 text-green-700",
  opened: "bg-emerald-100 text-emerald-700",
  clicked: "bg-emerald-100 text-emerald-700",
  pending_approval: "bg-amber-100 text-amber-700",
  suppressed: "bg-red-100 text-red-700",
  failed: "bg-red-100 text-red-700",
  bounced: "bg-red-100 text-red-700",
};

export default function EmailsPage() {
  const { user } = useAuth();
  const { selectedBrandId, brands } = useBrand();
  const isAdmin = user?.role === "admin" || user?.role === "owner";

  const [messages, setMessages] = useState<EmailMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [html, setHtml] = useState("<p>Hello from RevOS 👋</p>");
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (selectedBrandId) params.brand_id = selectedBrandId;
      setMessages(await emailsApi.list(params));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load emails");
    } finally {
      setLoading(false);
    }
  }, [selectedBrandId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function sendTest(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedBrandId) return;
    setError(null);
    setNotice(null);
    setSending(true);
    try {
      const msg = await emailsApi.test({
        brand_id: selectedBrandId,
        to_email: to,
        subject,
        html_body: html,
      });
      setNotice(
        msg.test_mode
          ? "Recorded in test mode (no real delivery — configure Resend to send)."
          : "Test email sent.",
      );
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Send failed");
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <PageHeader title="Email" description="Test sends, message log, and delivery status." />

      {error ? (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}
      {notice ? (
        <div className="mb-4 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700">{notice}</div>
      ) : null}

      {isAdmin ? (
        <Card className="mb-6">
          <CardTitle>Send a test email</CardTitle>
          {selectedBrandId ? (
            <form onSubmit={sendTest} className="space-y-3">
              <div className="flex flex-wrap gap-3">
                <input
                  required
                  type="email"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                  placeholder="you@example.com"
                  className="grow rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none"
                />
                <input
                  required
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Subject"
                  className="grow rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none"
                />
              </div>
              <textarea
                value={html}
                onChange={(e) => setHtml(e.target.value)}
                rows={3}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs focus:border-brand focus:outline-none"
              />
              <Button type="submit" disabled={sending}>
                {sending ? "Sending…" : "Send test"}
              </Button>
            </form>
          ) : (
            brands.length === 0 ? (
              <NoBrandCta feature="Email sending" />
            ) : (
              <p className="text-sm text-slate-500">Select a brand in the top bar to send a test.</p>
            )
          )}
        </Card>
      ) : null}

      {loading ? (
        <Spinner />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">To</th>
                <th className="px-4 py-3">Subject</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Opens</th>
              </tr>
            </thead>
            <tbody>
              {messages.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                    No emails yet.
                  </td>
                </tr>
              ) : (
                messages.map((m) => (
                  <tr key={m.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 text-slate-700">{m.to_email}</td>
                    <td className="px-4 py-3 text-slate-500">{m.subject}</td>
                    <td className="px-4 py-3 text-slate-400">{m.category}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[m.status] ?? "bg-slate-100 text-slate-500"}`}
                      >
                        {m.status.replace(/_/g, " ")}
                        {m.test_mode ? " · test" : ""}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-500">{m.open_count}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
