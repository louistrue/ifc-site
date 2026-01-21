import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        sketch: {
          black: '#1a1a1a',
          dark: '#2d2d2d',
          mid: '#4a4a4a',
          gray: '#6b6b6b',
          light: '#9a9a9a',
          pale: '#c4c4c4',
          paper: '#f5f5f5',
          white: '#fafafa',
          accent: '#3d3d3d',
        }
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        sketch: ['Caveat', 'cursive'],
        tech: ['Space Mono', 'monospace'],
      },
      animation: {
        'sketch-draw': 'sketchDraw 0.8s ease-out forwards',
        'sketch-fill': 'sketchFill 0.5s ease-out 0.3s forwards',
        'float': 'float 6s ease-in-out infinite',
        'pulse-slow': 'pulse 3s ease-in-out infinite',
      },
      keyframes: {
        sketchDraw: {
          '0%': { strokeDashoffset: '1000' },
          '100%': { strokeDashoffset: '0' },
        },
        sketchFill: {
          '0%': { fillOpacity: '0' },
          '100%': { fillOpacity: '0.1' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
      },
      backgroundImage: {
        'grid-sketch': `url("data:image/svg+xml,%3Csvg width='40' height='40' viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cpath d='M0 0h40v40H0z'/%3E%3Cpath d='M0 20h40M20 0v40' stroke='%23e5e5e5' stroke-width='0.5'/%3E%3C/g%3E%3C/svg%3E")`,
        'dots-sketch': `url("data:image/svg+xml,%3Csvg width='20' height='20' viewBox='0 0 20 20' xmlns='http://www.w3.org/2000/svg'%3E%3Ccircle cx='1' cy='1' r='1' fill='%23d4d4d4'/%3E%3C/svg%3E")`,
      },
      boxShadow: {
        'sketch': '3px 3px 0 0 #1a1a1a',
        'sketch-sm': '2px 2px 0 0 #1a1a1a',
        'sketch-lg': '5px 5px 0 0 #1a1a1a',
        'sketch-inner': 'inset 2px 2px 0 0 rgba(0,0,0,0.1)',
      },
    },
  },
  plugins: [],
}
export default config
