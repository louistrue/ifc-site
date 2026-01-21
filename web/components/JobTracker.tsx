'use client'

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Download, Loader2, CheckCircle2, XCircle, Clock, FileBox, Image as ImageIcon, Boxes, Sparkles } from 'lucide-react'
import { JobStatus, getJobStatus, getDownloadUrl } from '@/lib/api'

interface JobTrackerProps {
  jobId: string
  onComplete?: () => void
  onError?: (error: string) => void
  onStatusChange?: (status: 'pending' | 'running' | 'completed' | 'failed' | 'expired') => void
}

// Fun Swiss-themed loading messages
const LOADING_MESSAGES = [
  'Summoning Swiss precision...',
  'Consulting the mountains...',
  'Melting chocolate for fuel...',
  'Asking permission from cows...',
  'Yodeling to the satellites...',
  'Polishing the Matterhorn...',
  'Counting cheese holes...',
  'Winding the clockwork...',
  'Sharpening the army knife...',
  'Brewing fondue algorithms...',
  'Negotiating with gnomes...',
  'Calibrating cuckoo clocks...',
  'Herding digital sheep...',
  'Consulting the Swiss guard...',
  'Untangling alpine spaghetti...',
]

const statusConfig = {
  pending: {
    icon: Clock,
    label: 'Queued',
    color: 'text-sketch-gray',
    bg: 'bg-sketch-pale',
    border: 'border-sketch-gray',
  },
  running: {
    icon: Loader2,
    label: 'Generating',
    color: 'text-sketch-black',
    bg: 'bg-amber-50',
    border: 'border-amber-400',
  },
  completed: {
    icon: CheckCircle2,
    label: 'Complete',
    color: 'text-green-700',
    bg: 'bg-green-50',
    border: 'border-green-400',
  },
  failed: {
    icon: XCircle,
    label: 'Failed',
    color: 'text-red-700',
    bg: 'bg-red-50',
    border: 'border-red-400',
  },
  expired: {
    icon: Clock,
    label: 'Expired',
    color: 'text-sketch-gray',
    bg: 'bg-sketch-pale',
    border: 'border-sketch-gray',
  },
}

export default function JobTracker({ jobId, onComplete, onError, onStatusChange }: JobTrackerProps) {
  const [status, setStatus] = useState<JobStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [polling, setPolling] = useState(true)
  const [loadingMessage, setLoadingMessage] = useState(LOADING_MESSAGES[0])
  const [messageIndex, setMessageIndex] = useState(0)

  // Rotate loading messages while running
  useEffect(() => {
    if (status?.status !== 'running') return

    const interval = setInterval(() => {
      setMessageIndex(prev => {
        const next = (prev + 1) % LOADING_MESSAGES.length
        setLoadingMessage(LOADING_MESSAGES[next])
        return next
      })
    }, 2500)

    return () => clearInterval(interval)
  }, [status?.status])

  useEffect(() => {
    if (!polling) return

    const pollStatus = async () => {
      try {
        const jobStatus = await getJobStatus(jobId)
        setStatus(jobStatus)
        onStatusChange?.(jobStatus.status)

        if (jobStatus.status === 'completed') {
          setPolling(false)
          onComplete?.()
        } else if (jobStatus.status === 'failed') {
          setPolling(false)
          setError(jobStatus.error || 'Generation failed')
          onError?.(jobStatus.error || 'Generation failed')
        } else if (jobStatus.status === 'expired') {
          setPolling(false)
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to get status'
        if (message.includes('404') || message.toLowerCase().includes('not found')) {
          setError('Job expired or server restarted. Please generate again.')
          setStatus({ status: 'expired' } as JobStatus)
          onStatusChange?.('expired')
        } else {
          setError(message)
        }
        setPolling(false)
      }
    }

    pollStatus()
    const interval = setInterval(pollStatus, 2000)
    return () => clearInterval(interval)
  }, [jobId, polling, onComplete, onError, onStatusChange])

  const config = status ? statusConfig[status.status] : statusConfig.pending
  const StatusIcon = config.icon
  const isRunning = status?.status === 'running'
  const isPending = !status || status?.status === 'pending'

  return (
    <motion.div
      className={`sketch-card transition-colors duration-300 ${config.border} border-l-4`}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <motion.div
            className={`p-2 ${config.bg} border border-sketch-black`}
            animate={isRunning ? { scale: [1, 1.05, 1] } : {}}
            transition={{ duration: 1, repeat: Infinity }}
          >
            <StatusIcon
              size={20}
              className={`${config.color} ${isRunning ? 'animate-spin' : ''}`}
            />
          </motion.div>
          <div>
            <p className="font-mono text-sm font-medium">{config.label}</p>
            <p className="text-[10px] text-sketch-gray font-mono">
              Job: {jobId.slice(0, 8)}...
            </p>
          </div>
        </div>

        {/* Animated dots for running state */}
        {isRunning && (
          <div className="flex gap-1">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                className="w-2 h-2 bg-sketch-black rounded-full"
                animate={{ opacity: [0.3, 1, 0.3] }}
                transition={{
                  duration: 1,
                  repeat: Infinity,
                  delay: i * 0.2,
                }}
              />
            ))}
          </div>
        )}

        {/* Sparkle for completed */}
        {status?.status === 'completed' && (
          <motion.div
            initial={{ scale: 0, rotate: -180 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ type: 'spring', stiffness: 200 }}
          >
            <Sparkles className="text-green-600" size={20} />
          </motion.div>
        )}
      </div>

      {/* Fun loading message */}
      <AnimatePresence mode="wait">
        {(isRunning || isPending) && (
          <motion.div
            key={loadingMessage}
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="mb-4 text-center"
          >
            <p className="text-sm text-sketch-gray italic font-mono">
              {isPending ? 'Waiting in queue...' : loadingMessage}
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Progress visualization */}
      <div className="relative h-3 bg-sketch-pale border border-sketch-black mb-6 overflow-hidden">
        <motion.div
          className={`absolute inset-y-0 left-0 ${status?.status === 'completed' ? 'bg-green-500' : status?.status === 'failed' ? 'bg-red-500' : 'bg-sketch-black'}`}
          initial={{ width: '0%' }}
          animate={{
            width: status?.status === 'completed' ? '100%' :
                   status?.status === 'failed' ? '100%' :
                   status?.status === 'running' ? '70%' :
                   status?.status === 'pending' ? '5%' : '0%'
          }}
          transition={{ duration: 0.5 }}
        />
        {isRunning && (
          <motion.div
            className="absolute inset-y-0 w-24 bg-gradient-to-r from-transparent via-white/40 to-transparent"
            animate={{ x: ['-100%', '500%'] }}
            transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
          />
        )}
      </div>

      {/* Error */}
      <AnimatePresence>
        {error && (
          <motion.div
            className="p-3 bg-red-50 border-2 border-red-200 mb-4"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <p className="text-sm text-red-700 font-mono">{error}</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Success celebration */}
      <AnimatePresence>
        {status?.status === 'completed' && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-center mb-4"
          >
            <p className="text-green-700 font-mono text-sm">
              Your site model is ready!
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Downloads */}
      <AnimatePresence>
        {status?.status === 'completed' && status.download_url && (
          <motion.div
            className="space-y-3"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <p className="tech-label mb-3">Available Downloads</p>

            {/* IFC Download */}
            <motion.a
              href={getDownloadUrl(status.download_url)}
              className="sketch-btn w-full flex items-center justify-center gap-3 hover:bg-green-50 transition-colors"
              download
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <FileBox size={18} />
              <span>Download IFC</span>
              <span className="text-sketch-gray text-xs">
                {status.output_name}
              </span>
            </motion.a>

            {/* glTF Download */}
            {status.gltf_download_url && (
              <motion.a
                href={getDownloadUrl(status.gltf_download_url)}
                className="sketch-btn w-full flex items-center justify-center gap-3 hover:bg-blue-50 transition-colors"
                download
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <Boxes size={18} />
                <span>Download glTF</span>
                <span className="text-sketch-gray text-xs">
                  {status.gltf_output_name}
                </span>
              </motion.a>
            )}

            {/* Texture Download */}
            {status.texture_download_url && (
              <motion.a
                href={getDownloadUrl(status.texture_download_url)}
                className="sketch-btn w-full flex items-center justify-center gap-3 hover:bg-purple-50 transition-colors"
                download
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <ImageIcon size={18} />
                <span>Download Texture</span>
                <span className="text-sketch-gray text-xs">
                  {status.texture_output_name}
                </span>
              </motion.a>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
