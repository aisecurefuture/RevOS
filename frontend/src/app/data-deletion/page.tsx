import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Data Deletion — RevOS360",
};

export default function DataDeletionPage({
  searchParams,
}: {
  searchParams: { code?: string };
}) {
  const code = searchParams.code;

  return (
    <div className="min-h-screen bg-white">
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

      <main className="mx-auto max-w-2xl px-6 py-16 text-center">
        <div className="mb-6 flex justify-center">
          <span className="text-5xl">✓</span>
        </div>
        <h1 className="mb-4 text-2xl font-bold text-slate-900">
          Your data has been deleted
        </h1>
        <p className="mb-6 text-slate-600">
          All Facebook and Instagram connection data associated with your account
          has been removed from RevOS360&apos;s systems, including any stored
          access tokens.
        </p>

        {code && (
          <p className="mb-8 rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-500">
            Confirmation code: <span className="font-mono">{code}</span>
          </p>
        )}

        <div className="rounded-xl border border-slate-200 p-6 text-left text-sm text-slate-600 space-y-3">
          <p className="font-semibold text-slate-800">What was deleted</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>Facebook Page and Instagram Business Account connections</li>
            <li>OAuth access tokens stored in our encrypted secrets vault</li>
            <li>Associated metadata (page IDs, account handles)</li>
          </ul>
          <p className="font-semibold text-slate-800 pt-2">What was not affected</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>Your RevOS360 account and any non-social data remain intact</li>
            <li>Content you published through RevOS360 is not removed from Facebook or Instagram — to remove that, manage it directly in those platforms</li>
          </ul>
        </div>

        <p className="mt-8 text-sm text-slate-500">
          Questions?{" "}
          <a href="mailto:privacy@revos360.com" className="text-blue-600 hover:underline">
            privacy@revos360.com
          </a>
        </p>

        <div className="mt-8">
          <Link href="/" className="text-sm text-slate-400 hover:text-slate-600">
            ← Back to revos360.com
          </Link>
        </div>
      </main>
    </div>
  );
}
