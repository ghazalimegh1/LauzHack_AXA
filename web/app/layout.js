import { Inter } from "next/font/google";
import "./globals.css";

// Inter is downloaded once when the site is built and then served by our own server,
// so the live demo does not depend on a font website.
const inter = Inter({ subsets: ["latin"], display: "swap" });

export const metadata = {
  title: "Site Check",
  description: "Film your site. See what a storm would hit first, and what to do about it.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
