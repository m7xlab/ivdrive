import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { ThemeProvider } from "@/lib/theme-provider";
import { FeedbackProvider } from "@/components/ui/feedback";
import { QueryProvider } from "@/lib/query-provider";

export const metadata: Metadata = {
  title: "iVDrive",
  description:
    "Premium electric vehicle monitoring for Volkswagen Group EVs",
  icons: { icon: "/logo.png" },
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "iVDrive",
  },
};

const analyticsUrl = process.env.SITE_ANALYTICS_URL;
const analyticsKey = process.env.SITE_ANALYTICS_KEY;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* App Router layout: the pages-directory font rule does not apply; fonts are allowed by the CSP in next.config.ts */}
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
        />
        {analyticsUrl && analyticsKey && (
          <script
            defer
            src={analyticsUrl}
            data-website-id={analyticsKey}
          />
        )}
      </head>
      <body className="antialiased" suppressHydrationWarning>
        <ThemeProvider>
          <AuthProvider>
            <FeedbackProvider>
              <QueryProvider>{children}</QueryProvider>
            </FeedbackProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
