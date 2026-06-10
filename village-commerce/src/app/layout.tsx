import type { Metadata, Viewport } from "next";
import { Navbar, Footer } from "@/components/Navbar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Village Employment & Local Commerce | Qumanity",
  description:
    "Digitising the unorganised sector in Indian villages — employment, services, products, Qoins payments, and Village Council verification.",
  manifest: "/manifest.json",
  appleWebApp: { capable: true, statusBarStyle: "default", title: "Village Commerce" },
};

export const viewport: Viewport = {
  themeColor: "#ff9933",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="hi">
      <body className="flex min-h-screen flex-col">
        <Navbar />
        <main className="flex-1">{children}</main>
        <Footer />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              if ('serviceWorker' in navigator) {
                window.addEventListener('load', () => {
                  navigator.serviceWorker.register('/sw.js').catch(() => {});
                });
              }
            `,
          }}
        />
      </body>
    </html>
  );
}
