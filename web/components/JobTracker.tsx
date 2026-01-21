'use client'

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Download, Loader2, CheckCircle2, XCircle, Clock, FileBox, Image as ImageIcon, Boxes } from 'lucide-react'
import { JobStatus, getJobStatus, getDownloadUrl } from '@/lib/api'

interface JobTrackerProps {
  jobId: string
  onComplete?: () => void
  onError?: (error: string) => void
}

const statusConfig = {
  pending: {
    icon: Clock,
    label: 'Queued',
    color: 'text-sketch-gray',
    bg: 'bg-sketch-pale',
  },
  running: {
    icon: Loader2,
    label: 'Generating',
    color: 'text-sketch-black',
    bg: 'bg-sketch-white',
  },
  completed: {
    icon: CheckCircle2,
    label: 'Complete',
    color: 'text-green-700',
    bg: 'bg-green-50',
  },
  failed: {
    icon: XCircle,
    label: 'Failed',
    color: 'text-red-700',
    bg: 'bg-red-50',
  },
  expired: {
    icon: Clock,
    label: 'Expired',
    color: 'text-sketch-gray',
    bg: 'bg-sketch-pale',
  },
}

export default function JobTracker({ jobId, onComplete, onError }: JobTrackerProps) {
  const [status, setStatus] = useState<JobStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [polling, setPolling] = useState(true)

  useEffect(() => {
    if (!polling) return

    const pollStatus = async () => {
      try {
        const jobStatus = await getJobStatus(jobId)
        setStatus(jobStatus)

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
        // Handle job not found (e.g., after server restart)
        if (message.includes('404') || message.toLowerCase().includes('not found')) {
          setError('Job expired or server restarted. Please generate again.')
          setStatus({ status: 'expired' })
        } else {
          setError(message)
        }
        setPolling(false)
      }
    }

    pollStatus()
    const interval = setInterval(pollStatus, 2000)
    return () => clearInterval(interval)
  }, [jobId, polling, onComplete, onError])

  const config = status ? statusConfig[status.status] : statusConfig.pending
  const StatusIcon = config.icon

  return (
    <motion.div
      className="sketch-card"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`p-2 ${config.bg} border border-sketch-black`}>
            <StatusIcon
              size={20}
              className={`${config.color} ${status?.status === 'running' ? 'animate-spin' : ''}`}
            />
          </div>
          <div>
            <p className="font-mono text-sm font-medium">{config.label}</p>
            <p className="text-[10px] text-sketch-gray font-mono">
              Job: {jobId.slice(0, 8)}...
            </p>
          </div>
        </div>
        {status?.status === 'running' && (
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
      </div>

      {/* Progress visualization */}
      <div className="relative h-2 bg-sketch-pale border border-sketch-black mb-6 overflow-hidden">
        <motion.div
          className="absolute inset-y-0 left-0 bg-sketch-black"
          initial={{ width: '0%' }}
          animate={{
            width: status?.status === 'completed' ? '100%' :
                   status?.status === 'running' ? '60%' :
                   status?.status === 'pending' ? '10%' : '0%'
          }}
          transition={{ duration: 0.5 }}
        />
        {status?.status === 'running' && (
          <motion.div
            className="absolute inset-y-0 w-20 bg-gradient-to-r from-transparent via-white/30 to-transparent"
            animate={{ x: ['-100%', '400%'] }}
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
            <a
              href={getDownloadUrl(status.download_url)}
              className="sketch-btn w-full flex items-center justify-center gap-3"
              download
            >
              <FileBox size={18} />
              <span>Download IFC</span>
              <span className="text-sketch-gray text-xs">
                {status.output_name}
              </span>
            </a>

            {/* glTF Download */}
            {status.gltf_download_url && (
              <a
                href={getDownloadUrl(status.gltf_download_url)}
                className="sketch-btn w-full flex items-center justify-center gap-3"
                download
              >
                <Boxes size={18} />
                <span>Download glTF</span>
                <span className="text-sketch-gray text-xs">
                  {status.gltf_output_name}
                </span>
              </a>
            )}

            {/* Texture Download */}
            {status.texture_download_url && (
              <a
                href={getDownloadUrl(status.texture_download_url)}
                className="sketch-btn w-full flex items-center justify-center gap-3"
                download
              >
                <ImageIcon size={18} />
                <span>Download Texture</span>
                <span className="text-sketch-gray text-xs">
                  {status.texture_output_name}
                </span>
              </a>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
