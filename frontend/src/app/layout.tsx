import type { Metadata } from "next";
import { Noto_Sans } from "next/font/google";
import "./globals.css";
import AppHeader from "@/components/app-header";
import { Providers } from "./providers";

const notoSans = Noto_Sans({
  variable: "--font-noto",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"]
});

export const metadata: Metadata = {
  title: "RateEngine",
  description: "Advanced Freight Quoting System",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${notoSans.variable} font-sans antialiased bg-background text-foreground`}>
        <Providers>
          <div className="flex flex-col h-screen overflow-hidden">
            <AppHeader />
            <main className="flex-1 overflow-y-auto p-6">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
