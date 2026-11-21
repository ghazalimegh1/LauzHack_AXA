import { Inter_Tight, Source_Sans_3, Spline_Sans_Mono } from "next/font/google";
import "./globals.css";

// Three fonts, downloaded once at build time and served by our own server (no font
// website needed during the demo):
// - Source Sans: AXA XL's body font
// - Inter Tight: stands in for Dream Machines' paid headline font (Aeonik)
// - Spline Sans Mono: Dream Machines' own small uppercase labels
const body = Source_Sans_3({ subsets: ["latin"], variable: "--font-body", display: "swap" });
const head = Inter_Tight({ subsets: ["latin"], weight: ["500", "600"], variable: "--font-head", display: "swap" });
const mono = Spline_Sans_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });

export const metadata = {
  title: "Site Check",
  description: "Film your site. See what a storm would hit first, and what to do about it.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${body.variable} ${head.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
