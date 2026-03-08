import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Zyon AI Chat",
  description: "AI-powered chat assistant",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
