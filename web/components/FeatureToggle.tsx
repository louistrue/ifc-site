'use client'

import { motion } from 'framer-motion'
import { LucideIcon } from 'lucide-react'

interface FeatureToggleProps {
  icon: LucideIcon
  label: string
  description: string
  checked: boolean
  onChange: (checked: boolean) => void
  experimental?: boolean
}

export default function FeatureToggle({
  icon: Icon,
  label,
  description,
  checked,
  onChange,
  experimental,
}: FeatureToggleProps) {
  return (
    <motion.label
      className={`
        relative flex items-start gap-4 p-4 cursor-pointer
        border-2 transition-all duration-200
        ${checked
          ? 'border-sketch-black bg-sketch-white shadow-sketch'
          : 'border-sketch-pale bg-sketch-paper hover:border-sketch-gray'
        }
      `}
      whileHover={{ scale: 1.01 }}
      whileTap={{ scale: 0.99 }}
    >
      <input
        type="checkbox"
        className="sketch-checkbox mt-1 flex-shrink-0"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <Icon size={16} className="text-sketch-gray flex-shrink-0" />
          <span className="font-mono text-sm font-medium truncate">{label}</span>
          {experimental && (
            <span className="sketch-badge text-[10px] bg-sketch-pale">
              Beta
            </span>
          )}
        </div>
        <p className="text-xs text-sketch-gray mt-1 leading-relaxed">
          {description}
        </p>
      </div>
      {checked && (
        <motion.div
          className="absolute top-2 right-2 w-2 h-2 bg-sketch-black rounded-full"
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: 'spring', stiffness: 500, damping: 30 }}
        />
      )}
    </motion.label>
  )
}
