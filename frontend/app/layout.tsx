import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

const geist = Geist({ variable: "--font-geist", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Vigilyx — AI Revenue Monitoring for Stripe",
  description:
    "Proactive anomaly detection for Stripe revenue. Catch drops, spikes, and refund surges before they become problems.",
  metadataBase: new URL("https://www.vigilyx.io"),
  alternates: {
    canonical: "/",
  },
  robots: {
    index: true,
    follow: true,
  },
  openGraph: {
    title: "Vigilyx — AI Revenue Monitoring for Stripe",
    description:
      "Proactive anomaly detection for Stripe revenue. Catch drops, spikes, and refund surges before they become problems.",
    url: "https://www.vigilyx.io",
    siteName: "Vigilyx",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "Vigilyx" }],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Vigilyx — AI Revenue Monitoring for Stripe",
    description:
      "Proactive anomaly detection for Stripe revenue. Catch drops, spikes, and refund surges before they become problems.",
    images: ["/og-image.png"],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geist.variable} antialiased bg-gray-950 text-gray-100 min-h-screen`}>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
