import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'IFC Site Generator | Swiss Terrain to BIM',
  description: 'Generate IFC files from Swiss cadastral data with terrain, buildings, roads, and more.',
  keywords: ['IFC', 'BIM', 'terrain', 'Switzerland', 'cadastral', 'architecture', 'construction'],
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="bg-sketch-paper text-sketch-black antialiased">
        <div className="min-h-screen bg-grid-sketch">
          {children}
        </div>
      </body>
    </html>
  )
}
