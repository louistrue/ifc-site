# IFC Site Generator - Web UI

A sketch-style web interface for generating IFC site models from Swiss cadastral data.

## Tech Stack

- **Next.js 14** - React framework with App Router
- **Tailwind CSS** - Utility-first styling
- **Framer Motion** - Animations
- **Lucide Icons** - Icon library

## Design

The UI features a hand-drawn "sketch" aesthetic with:
- Black, grey, and white color palette
- Technical/blueprint-inspired elements
- Hand-drawn style borders and shadows
- Monospace typography (JetBrains Mono, Space Mono)
- Handwritten accents (Caveat font)

## Development

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

## Environment Variables

Create a `.env.local` file:

```env
NEXT_PUBLIC_API_URL=http://localhost:8080
```

For production, set `NEXT_PUBLIC_API_URL` to your deployed API endpoint.

## Deployment to Vercel

1. Push to GitHub
2. Import project in Vercel
3. Set environment variable:
   - `NEXT_PUBLIC_API_URL` = your API URL
4. Deploy

The `vercel.json` is pre-configured for optimal deployment.

## Project Structure

```
web/
├── app/
│   ├── globals.css      # Global styles & sketch design system
│   ├── layout.tsx       # Root layout
│   └── page.tsx         # Main page
├── components/
│   ├── Header.tsx       # Navigation header
│   ├── GeneratorForm.tsx # Main form component
│   ├── FeatureToggle.tsx # Feature checkbox component
│   └── JobTracker.tsx   # Job status component
├── lib/
│   └── api.ts           # API client
└── public/              # Static assets
```
