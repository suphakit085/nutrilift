import type { Metadata } from "next";
import { Chakra_Petch, IBM_Plex_Mono, Noto_Sans_Thai } from "next/font/google";
import "./globals.css";

const notoThai = Noto_Sans_Thai({
  subsets: ["thai", "latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-thai",
  display: "swap",
});

// Technical/geometric, not the generic-SaaS default - used for headings and
// section labels so the app reads as a performance tool, not a wellness blog.
const chakraPetch = Chakra_Petch({
  subsets: ["thai", "latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
  display: "swap",
});

// Every kcal/gram/BMR/TDEE number in the app renders in this face. The
// product's actual selling point is "numbers you can verify," not "friendly
// wellness app" - a monospace numeral is a data-readout, not decoration.
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "NutriLift - แชตบอทโภชนาการสำหรับเวทเทรนนิ่ง",
  description:
    "แชตบอทให้ความรู้ด้านโภชนาการสำหรับผู้ฝึกเวทเทรนนิ่ง คำนวณพลังงานและสารอาหารเฉพาะบุคคล พร้อมแหล่งอ้างอิง",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="th">
      <body
        className={`${notoThai.variable} ${chakraPetch.variable} ${plexMono.variable} font-sans antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
