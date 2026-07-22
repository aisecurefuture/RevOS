import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "RevOS — Revenue Operating System",
  description: "Approval-first marketing & sales automation platform.",
  icons: {
    icon: "/mark.svg",
    shortcut: "/mark.svg",
    apple: "/mark.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
