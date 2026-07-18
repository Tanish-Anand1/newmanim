import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vivacity Studio",
  description: "Async Manim video generation"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
