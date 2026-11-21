import "./globals.css";

export const metadata = {
  title: "Frugal Site Check",
  description: "Film a short walk around your business site and learn what a storm would hit first.",
  icons: { icon: "/axa-logo.png", apple: "/axa-logo.png" },
};

export const viewport = { width: "device-width", initialScale: 1, themeColor: "#00008F" };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@500;600;700&family=Source+Sans+3:wght@400;600&family=Spline+Sans+Mono:wght@500&display=swap"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
