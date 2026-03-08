import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { ThemeProvider } from "@/lib/theme-provider";

const inter = Inter({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

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
      <body className={`${inter.variable} antialiased`}>
        {analyticsUrl && analyticsKey && (
          <Script
            src={analyticsUrl}
            data-website-id={analyticsKey}
            strategy="afterInteractive"
          />
        )}
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
