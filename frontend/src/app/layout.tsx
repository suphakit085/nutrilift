import type { Metadata } from "next";
import { Noto_Sans_Thai } from "next/font/google";
import "./globals.css";

const notoThai = Noto_Sans_Thai({
  subsets: ["thai", "latin"],
  variable: "--font-thai",
  display: "swap",
});

export const metadata: Metadata = {
  title: "โค้ชนัท - แชตบอทโภชนาการสำหรับเวทเทรนนิ่ง",
  description:
    "แชตบอทให้ความรู้ด้านโภชนาการสำหรับผู้ฝึกเวทเทรนนิ่ง คำนวณพลังงานและสารอาหารเฉพาะบุคคล พร้อมแหล่งอ้างอิง",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="th">
      <body className={`${notoThai.variable} font-sans antialiased`}>
        {children}
      </body>
    </html>
  );
}
