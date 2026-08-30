import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Dograh Rebuild",
  description: "Voice agent platform rebuild",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
