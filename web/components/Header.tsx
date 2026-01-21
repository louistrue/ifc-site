'use client'

import { motion } from 'framer-motion'

export default function Header() {
  return (
    <header className="border-b-2 border-sketch-black bg-sketch-white/80 backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <motion.div
            className="flex items-center gap-3"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
          >
            <div className="relative">
              <svg
                width="40"
                height="40"
                viewBox="0 0 40 40"
                className="stroke-sketch-black"
                strokeWidth="2"
                fill="none"
              >
                {/* Terrain lines */}
                <motion.path
                  d="M5 30 L15 20 L20 25 L30 15 L35 20"
                  initial={{ pathLength: 0 }}
                  animate={{ pathLength: 1 }}
                  transition={{ duration: 1, delay: 0.2 }}
                />
                {/* Building */}
                <motion.rect
                  x="18" y="8" width="8" height="12"
                  initial={{ pathLength: 0 }}
                  animate={{ pathLength: 1 }}
                  transition={{ duration: 0.8, delay: 0.5 }}
                />
                {/* Ground */}
                <motion.line
                  x1="5" y1="32" x2="35" y2="32"
                  strokeDasharray="4 2"
                  initial={{ pathLength: 0 }}
                  animate={{ pathLength: 1 }}
                  transition={{ duration: 0.6, delay: 0.8 }}
                />
              </svg>
            </div>
            <div>
              <h1 className="font-tech text-lg font-bold tracking-tight">
                IFC<span className="text-sketch-gray">/</span>SITE
              </h1>
              <p className="text-[10px] text-sketch-gray uppercase tracking-widest">
                Swiss Terrain Generator
              </p>
            </div>
          </motion.div>

          {/* Navigation */}
          <motion.nav
            className="hidden md:flex items-center gap-6"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.3 }}
          >
            <a
              href="#generator"
              className="tech-label hover:text-sketch-black transition-colors"
            >
              Generator
            </a>
            <a
              href="#features"
              className="tech-label hover:text-sketch-black transition-colors"
            >
              Features
            </a>
            <a
              href="https://github.com/louistrue/ifc-site"
              target="_blank"
              rel="noopener noreferrer"
              className="sketch-btn text-xs py-2 px-4"
            >
              GitHub
            </a>
          </motion.nav>
        </div>
      </div>
    </header>
  )
}
