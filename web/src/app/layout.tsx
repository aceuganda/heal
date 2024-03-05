import { Metadata } from "next";
import "./globals.css";


import { Inter } from "next/font/google";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata:Metadata = {
  manifest: "/manifest.json",
  title: "HEAL",
  description: "Transforming Pandemic Preparedness in Uganda",
};

export const dynamic = "force-dynamic";


export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        className={`${inter.variable} font-sans text-default bg-background`}
      >
        {children}
      </body>
    </html>
  );
}
