'use client'

import { motion } from 'framer-motion'
import {
  Mountain,
  Building2,
  TreePine,
  Droplets,
  Car,
  Train,
  Satellite,
  ArrowDown,
  Terminal,
  Globe,
  Zap,
} from 'lucide-react'
import Header from '@/components/Header'
import GeneratorForm from '@/components/GeneratorForm'

const features = [
  { icon: Mountain, label: 'Terrain', desc: 'Swiss elevation data' },
  { icon: Building2, label: 'Buildings', desc: 'CityGML 3D models' },
  { icon: Car, label: 'Roads', desc: 'SwissTLM3D network' },
  { icon: TreePine, label: 'Forest', desc: 'Vegetation coverage' },
  { icon: Droplets, label: 'Water', desc: 'Lakes & rivers' },
  { icon: Train, label: 'Railways', desc: 'Rail infrastructure' },
  { icon: Satellite, label: 'Imagery', desc: 'SWISSIMAGE overlay' },
]

export default function Home() {
  return (
    <div className="min-h-screen">
      <Header />

      {/* Hero Section */}
      <section className="relative overflow-hidden">
        {/* Decorative elements */}
        <div className="absolute inset-0 pointer-events-none">
          {/* Grid overlay */}
          <svg
            className="absolute inset-0 w-full h-full opacity-20"
            xmlns="http://www.w3.org/2000/svg"
          >
            <defs>
              <pattern
                id="hero-grid"
                width="60"
                height="60"
                patternUnits="userSpaceOnUse"
              >
                <path
                  d="M 60 0 L 0 0 0 60"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="0.5"
                  className="text-sketch-gray"
                />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#hero-grid)" />
          </svg>

          {/* Sketch decorations */}
          <motion.div
            className="absolute top-20 right-[10%] w-32 h-32 border-2 border-sketch-pale"
            style={{ transform: 'rotate(15deg)' }}
            animate={{ rotate: [15, 20, 15] }}
            transition={{ duration: 8, repeat: Infinity }}
          />
          <motion.div
            className="absolute bottom-40 left-[5%] w-24 h-24 border-2 border-dashed border-sketch-pale"
            animate={{ scale: [1, 1.1, 1] }}
            transition={{ duration: 6, repeat: Infinity }}
          />
        </div>

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 lg:py-32">
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
            {/* Left: Text */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
            >
              <motion.div
                className="sketch-badge-dark mb-6"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.2 }}
              >
                Swiss Cadastral Data → IFC
              </motion.div>

              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-tech font-bold leading-tight mb-6">
                <span className="block">Site Models</span>
                <span className="block text-sketch-gray">
                  <span className="handwritten text-5xl sm:text-6xl lg:text-7xl">sketched</span> to BIM
                </span>
              </h1>

              <p className="text-lg text-sketch-gray mb-8 max-w-xl leading-relaxed">
                Generate IFC files from Swiss cadastral data. Terrain, buildings,
                roads, vegetation — all combined into a single BIM model ready for
                your architectural workflow.
              </p>

              {/* Feature pills */}
              <div className="flex flex-wrap gap-2 mb-8">
                {features.map((f, i) => (
                  <motion.div
                    key={f.label}
                    className="flex items-center gap-2 px-3 py-2 bg-sketch-white border border-sketch-pale"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 + i * 0.05 }}
                  >
                    <f.icon size={14} className="text-sketch-gray" />
                    <span className="text-xs font-mono">{f.label}</span>
                  </motion.div>
                ))}
              </div>

              <motion.a
                href="#generator"
                className="inline-flex items-center gap-2 sketch-btn-primary"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.6 }}
              >
                Start Generating
                <ArrowDown size={16} />
              </motion.a>
            </motion.div>

            {/* Right: Visual */}
            <motion.div
              className="relative"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
            >
              {/* Sketch illustration */}
              <div className="relative aspect-square max-w-md mx-auto">
                <svg
                  viewBox="0 0 400 400"
                  className="w-full h-full"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  {/* Ground grid */}
                  <motion.g
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.5, duration: 0.8 }}
                  >
                    {[...Array(8)].map((_, i) => (
                      <line
                        key={`h-${i}`}
                        x1="50"
                        y1={250 + i * 15}
                        x2="350"
                        y2={250 + i * 15}
                        stroke="#d4d4d4"
                        strokeWidth="0.5"
                      />
                    ))}
                    {[...Array(8)].map((_, i) => (
                      <line
                        key={`v-${i}`}
                        x1={50 + i * 42}
                        y1="250"
                        x2={100 + i * 42}
                        y2="350"
                        stroke="#d4d4d4"
                        strokeWidth="0.5"
                      />
                    ))}
                  </motion.g>

                  {/* Terrain */}
                  <motion.path
                    d="M50 280 Q100 250 150 270 T250 260 T350 280 L350 350 L50 350 Z"
                    fill="#f5f5f5"
                    stroke="#1a1a1a"
                    strokeWidth="2"
                    initial={{ pathLength: 0, fillOpacity: 0 }}
                    animate={{ pathLength: 1, fillOpacity: 1 }}
                    transition={{ duration: 1.5, delay: 0.3 }}
                  />

                  {/* Building 1 */}
                  <motion.g
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 1, duration: 0.5 }}
                  >
                    <rect
                      x="120"
                      y="180"
                      width="60"
                      height="80"
                      fill="#fafafa"
                      stroke="#1a1a1a"
                      strokeWidth="2"
                    />
                    <rect
                      x="130"
                      y="200"
                      width="15"
                      height="20"
                      fill="none"
                      stroke="#4a4a4a"
                      strokeWidth="1"
                    />
                    <rect
                      x="155"
                      y="200"
                      width="15"
                      height="20"
                      fill="none"
                      stroke="#4a4a4a"
                      strokeWidth="1"
                    />
                    <rect
                      x="130"
                      y="230"
                      width="15"
                      height="30"
                      fill="none"
                      stroke="#4a4a4a"
                      strokeWidth="1"
                    />
                  </motion.g>

                  {/* Building 2 */}
                  <motion.g
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 1.2, duration: 0.5 }}
                  >
                    <rect
                      x="220"
                      y="200"
                      width="80"
                      height="60"
                      fill="#fafafa"
                      stroke="#1a1a1a"
                      strokeWidth="2"
                    />
                    <polygon
                      points="220,200 260,170 300,200"
                      fill="#fafafa"
                      stroke="#1a1a1a"
                      strokeWidth="2"
                    />
                  </motion.g>

                  {/* Trees */}
                  <motion.g
                    initial={{ opacity: 0, scale: 0 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 1.4, duration: 0.4 }}
                  >
                    <circle cx="90" cy="245" r="15" fill="#6b6b6b" opacity="0.3" />
                    <line
                      x1="90"
                      y1="260"
                      x2="90"
                      y2="280"
                      stroke="#4a4a4a"
                      strokeWidth="2"
                    />
                  </motion.g>

                  <motion.g
                    initial={{ opacity: 0, scale: 0 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 1.5, duration: 0.4 }}
                  >
                    <circle cx="340" cy="235" r="12" fill="#6b6b6b" opacity="0.3" />
                    <line
                      x1="340"
                      y1="247"
                      x2="340"
                      y2="265"
                      stroke="#4a4a4a"
                      strokeWidth="2"
                    />
                  </motion.g>

                  {/* Road */}
                  <motion.path
                    d="M50 290 Q150 285 200 295 T350 285"
                    fill="none"
                    stroke="#4a4a4a"
                    strokeWidth="8"
                    strokeLinecap="round"
                    initial={{ pathLength: 0 }}
                    animate={{ pathLength: 1 }}
                    transition={{ delay: 1.6, duration: 0.8 }}
                  />
                  <motion.path
                    d="M50 290 Q150 285 200 295 T350 285"
                    fill="none"
                    stroke="#fafafa"
                    strokeWidth="1"
                    strokeDasharray="10 10"
                    initial={{ pathLength: 0 }}
                    animate={{ pathLength: 1 }}
                    transition={{ delay: 1.8, duration: 0.8 }}
                  />

                  {/* Labels */}
                  <motion.g
                    className="font-mono"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 2 }}
                  >
                    <text
                      x="60"
                      y="100"
                      className="text-[10px] fill-sketch-gray"
                      fontFamily="monospace"
                    >
                      {'// IFC SITE MODEL'}
                    </text>
                    <text
                      x="60"
                      y="115"
                      className="text-[10px] fill-sketch-gray"
                      fontFamily="monospace"
                    >
                      {'// EGRID: CH999979659148'}
                    </text>
                  </motion.g>

                  {/* Dimension lines */}
                  <motion.g
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 2.2 }}
                  >
                    <line
                      x1="50"
                      y1="370"
                      x2="350"
                      y2="370"
                      stroke="#9a9a9a"
                      strokeWidth="1"
                    />
                    <line
                      x1="50"
                      y1="365"
                      x2="50"
                      y2="375"
                      stroke="#9a9a9a"
                      strokeWidth="1"
                    />
                    <line
                      x1="350"
                      y1="365"
                      x2="350"
                      y2="375"
                      stroke="#9a9a9a"
                      strokeWidth="1"
                    />
                    <text
                      x="200"
                      y="385"
                      textAnchor="middle"
                      className="text-[10px] fill-sketch-gray"
                      fontFamily="monospace"
                    >
                      500m radius
                    </text>
                  </motion.g>
                </svg>

                {/* Floating badges */}
                <motion.div
                  className="absolute top-4 right-4 sketch-badge"
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 2.5 }}
                >
                  <span className="text-green-600 mr-1">●</span> API Ready
                </motion.div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="border-y-2 border-sketch-black bg-sketch-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {[
              { value: '7+', label: 'Data Layers' },
              { value: 'IFC 4', label: 'Format' },
              { value: 'glTF', label: 'Export' },
              { value: '∞', label: 'Locations' },
            ].map((stat, i) => (
              <motion.div
                key={stat.label}
                className="text-center"
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                viewport={{ once: true }}
              >
                <p className="text-3xl md:text-4xl font-tech font-bold">
                  {stat.value}
                </p>
                <p className="tech-label mt-1">{stat.label}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Generator Section */}
      <section id="generator" className="py-20 lg:py-32">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div
            className="text-center mb-12"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <h2 className="text-3xl sm:text-4xl font-tech font-bold mb-4">
              Generate Your Model
            </h2>
            <p className="text-sketch-gray">
              Enter a Swiss EGRID or address to create your IFC site model
            </p>
          </motion.div>

          <GeneratorForm />
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-20 lg:py-32 bg-sketch-white border-t-2 border-sketch-black">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div
            className="text-center mb-16"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <h2 className="text-3xl sm:text-4xl font-tech font-bold mb-4">
              Available Interfaces
            </h2>
            <p className="text-sketch-gray max-w-2xl mx-auto">
              Use the REST API for integration or the CLI for local generation
            </p>
          </motion.div>

          <div className="grid md:grid-cols-2 gap-8">
            {/* REST API Card */}
            <motion.div
              className="sketch-card"
              initial={{ opacity: 0, x: -20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="p-3 bg-sketch-paper border-2 border-sketch-black">
                  <Globe size={24} />
                </div>
                <div>
                  <h3 className="font-tech font-bold text-lg">REST API</h3>
                  <p className="text-xs text-sketch-gray">HTTP endpoints</p>
                </div>
              </div>
              <pre className="bg-sketch-paper p-4 text-sm overflow-x-auto border border-sketch-pale">
{`POST /jobs
{
  "egrid": "CH999979659148",
  "include_all": true,
  "radius": 500
}`}
              </pre>
              <div className="mt-4 flex flex-wrap gap-2">
                <span className="sketch-badge">Async Jobs</span>
                <span className="sketch-badge">Rate Limited</span>
                <span className="sketch-badge">glTF Export</span>
              </div>
            </motion.div>

            {/* CLI Card */}
            <motion.div
              className="sketch-card"
              initial={{ opacity: 0, x: 20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="p-3 bg-sketch-paper border-2 border-sketch-black">
                  <Terminal size={24} />
                </div>
                <div>
                  <h3 className="font-tech font-bold text-lg">CLI</h3>
                  <p className="text-xs text-sketch-gray">Command line</p>
                </div>
              </div>
              <pre className="bg-sketch-paper p-4 text-sm overflow-x-auto border border-sketch-pale">
{`python -m src.cli \\
  --address "Bundesplatz 3" \\
  --all \\
  --output site.ifc`}
              </pre>
              <div className="mt-4 flex flex-wrap gap-2">
                <span className="sketch-badge">Local</span>
                <span className="sketch-badge">All Features</span>
                <span className="sketch-badge">Direct Output</span>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t-2 border-sketch-black bg-sketch-paper py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-3">
              <div className="font-tech font-bold">IFC/SITE</div>
              <span className="text-sketch-gray">•</span>
              <span className="text-sm text-sketch-gray">
                Swiss Terrain to BIM
              </span>
            </div>
            <div className="flex items-center gap-6">
              <a
                href="https://github.com/louistrue/ifc-site"
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-sketch-gray hover:text-sketch-black transition-colors"
              >
                GitHub
              </a>
              <a
                href="/docs"
                className="text-sm text-sketch-gray hover:text-sketch-black transition-colors"
              >
                API Docs
              </a>
            </div>
          </div>
          <div className="mt-8 pt-8 border-t border-sketch-pale text-center">
            <p className="text-xs text-sketch-gray">
              Built with Swiss geodata from swisstopo, geo.admin.ch, and OpenStreetMap
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}
