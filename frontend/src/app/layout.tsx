import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PersonalTutor",
  description: "Personalized AI tutoring on top of DeepTutor.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
