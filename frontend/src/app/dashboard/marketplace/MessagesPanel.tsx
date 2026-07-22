"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { workspaceApi } from "@/lib/resources";
import type { Collaboration, CollaborationMessage } from "@/lib/types";

export function MessagesPanel({
  collab, role,
}: { collab: Collaboration; role: "creator" | "brand" }) {
  const myAccountId = role === "creator" ? collab.creator_account_id : collab.brand_account_id;

  const [messages, setMessages] = useState<CollaborationMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [reportingId, setReportingId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setMessages(await workspaceApi.listMessages(collab.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load messages");
    } finally {
      setLoading(false);
    }
  }, [collab.id]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages.length]);

  const ended = collab.state === "ended";

  async function send() {
    const body = draft.trim();
    if (!body || sending) return;
    setSending(true);
    setError(null);
    try {
      await workspaceApi.sendMessage(collab.id, body);
      setDraft("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to send");
    } finally {
      setSending(false);
    }
  }

  async function report(messageId: string) {
    const reason = window.prompt("Why are you reporting this message?");
    if (!reason || !reason.trim()) return;
    setReportingId(messageId);
    try {
      await workspaceApi.reportMessage(collab.id, messageId, reason.trim());
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to report");
    } finally {
      setReportingId(null);
    }
  }

  return (
    <Card>
      <CardTitle>Messages</CardTitle>
      {error ? <div className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      {loading ? (
        <Spinner />
      ) : (
        <div className="mb-3 max-h-80 space-y-2 overflow-y-auto rounded-lg border border-slate-100 bg-slate-50 p-3">
          {messages.length === 0 ? (
            <p className="text-sm text-slate-400">No messages yet — say hello.</p>
          ) : (
            messages.map((m) => {
              const mine = m.sender_account_id === myAccountId;
              return (
                <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                    mine ? "bg-brand text-white" : "bg-white text-slate-700 border border-slate-200"
                  }`}>
                    <p className="whitespace-pre-wrap">{m.body}</p>
                    <div className={`mt-1 flex items-center gap-2 text-xs ${mine ? "text-white/70" : "text-slate-400"}`}>
                      <span>{new Date(m.created_at).toLocaleString()}</span>
                      {m.is_flagged ? <span className="font-medium">· reported</span> : null}
                      {!mine ? (
                        <button
                          type="button"
                          onClick={() => void report(m.id)}
                          disabled={reportingId === m.id || m.is_flagged}
                          className="underline hover:no-underline disabled:opacity-50"
                        >
                          {m.is_flagged ? "reported" : "report"}
                        </button>
                      ) : null}
                    </div>
                  </div>
                </div>
              );
            })
          )}
          <div ref={bottomRef} />
        </div>
      )}

      {ended ? (
        <p className="text-xs text-slate-400">
          This collaboration has ended — messaging is closed.
        </p>
      ) : (
        <div className="flex gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            rows={2}
            placeholder="Write a message…"
            className="grow rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
          />
          <Button onClick={() => void send()} disabled={sending || !draft.trim()}>
            {sending ? "Sending…" : "Send"}
          </Button>
        </div>
      )}
    </Card>
  );
}
