'use client'

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  MapPin,
  Mountain,
  Building2,
  TreePine,
  Droplets,
  Train,
  Car,
  Satellite,
  Settings2,
  Sparkles,
  ChevronDown,
  Loader2,
  AlertCircle,
  Dices,
  Plus,
  CheckCircle2,
  Zap,
} from 'lucide-react'
import FeatureToggle from './FeatureToggle'
import JobTracker from './JobTracker'
import AddressAutocomplete from './AddressAutocomplete'
import { createJob, GenerateRequest } from '@/lib/api'

// Interesting Swiss locations for Lucky Draw (using addresses that get resolved to real EGRIDs)
const LUCKY_LOCATIONS = [
  // Famous landmarks
  { address: 'Bundesplatz 3, Bern', name: 'Bundeshaus, Bern', desc: 'Federal Palace' },
  { address: 'Rämistrasse 101, Zürich', name: 'ETH Zurich', desc: 'Technical University' },
  { address: 'Kapellplatz 1, Luzern', name: 'Chapel Bridge Area', desc: 'Medieval Covered Bridge' },
  { address: 'Münsterhof 1, Zürich', name: 'Fraumünster', desc: 'Chagall Windows Church' },
  // Easter eggs - fun places
  { address: 'Toblerone 1, Bern-Brünnen', name: 'Toblerone HQ', desc: 'Where chocolate dreams come true' },
  { address: 'Schokoladenweg 1, Kilchberg', name: 'Lindt Home', desc: 'Chocolate Heaven' },
  { address: 'Victorinoxstrasse 1, Ibach', name: 'Swiss Army Knife', desc: 'MacGyver\'s Workshop' },
  { address: 'Bahnhofstrasse 1, Zürich', name: 'Rich Street', desc: 'Most expensive real estate' },
  { address: 'Dufourstrasse 50, St. Gallen', name: 'Textile Museum', desc: 'Where fashion was born' },
  { address: 'Casino-Platz 1, Montreux', name: 'Montreux Casino', desc: 'Smoke on the Water' },
  { address: 'Quai du Mont-Blanc 30, Genève', name: 'Beau-Rivage', desc: 'Where history happened' },
  { address: 'Marktgasse 1, Bern', name: 'Zytglogge Area', desc: 'Einstein\'s Clock Tower' },
  // Hidden gems
  { address: 'Creux du Van, Val-de-Travers', name: 'Swiss Canyon', desc: 'Mini Grand Canyon' },
  { address: 'Via Nassa 1, Lugano', name: 'Lugano Centro', desc: 'Mediterranean Vibes' },
  { address: 'Rathausplatz 1, Stein am Rhein', name: 'Painted Town', desc: 'Frescos Everywhere' },
]

interface FormState {
  address: string // Swiss address - backend resolves to EGRID
  // Features
  includeTerrain: boolean
  includeSiteSolid: boolean
  includeRoads: boolean
  includeBuildings: boolean
  includeForest: boolean
  includeWater: boolean
  includeRailways: boolean
  includeBridges: boolean
  includeSatellite: boolean
  exportGltf: boolean
  // Parameters
  radius: number
  resolution: number
  outputName: string
}

interface ActiveJob {
  id: string
  location: string // EGRID or address
  name?: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'expired'
}

// Limits to prevent abuse
const LIMITS = {
  MAX_RADIUS: 500,
  MIN_RADIUS: 50,
  MAX_RESOLUTION: 15,
  MIN_RESOLUTION: 2,
  MAX_FEATURES: 5,
}

// Calculate adaptive resolution based on radius
function getAdaptiveResolution(radius: number): number {
  if (radius <= 100) return 2
  if (radius <= 200) return 5
  if (radius <= 350) return 8
  return Math.round(8 + ((radius - 350) / 150) * 7)
}

// Fun loading messages - Swiss themed
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
]

const defaultState: FormState = {
  address: '',
  includeTerrain: true,
  includeSiteSolid: true,
  includeRoads: false,
  includeBuildings: false,
  includeForest: false,
  includeWater: false,
  includeRailways: false,
  includeBridges: false,
  includeSatellite: false,
  exportGltf: false,
  radius: 200,
  resolution: 5,
  outputName: 'site_model.ifc',
}

interface GeneratorFormProps {
  secretMode?: boolean
}

export default function GeneratorForm({ secretMode = false }: GeneratorFormProps) {
  const [form, setForm] = useState<FormState>(defaultState)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeJobs, setActiveJobs] = useState<ActiveJob[]>([])
  const [luckyPick, setLuckyPick] = useState<typeof LUCKY_LOCATIONS[0] | null>(null)
  const [loadingMsg, setLoadingMsg] = useState(LOADING_MESSAGES[0])

  // Apply secret mode settings when activated
  useEffect(() => {
    if (secretMode) {
      const secret = LUCKY_LOCATIONS.find(l => l.name.includes('Toblerone')) || LUCKY_LOCATIONS[0]
      setLuckyPick(secret)
      setForm(prev => ({
        ...prev,
        address: secret.address,
        includeRoads: true,
        includeBuildings: true,
        includeForest: true,
        includeWater: true,
        radius: 300,
        resolution: 2, // Maximum detail
      }))
    }
  }, [secretMode])

  // Rotate loading message while submitting
  useEffect(() => {
    if (!isSubmitting) return
    const interval = setInterval(() => {
      setLoadingMsg(LOADING_MESSAGES[Math.floor(Math.random() * LOADING_MESSAGES.length)])
    }, 2000)
    return () => clearInterval(interval)
  }, [isSubmitting])

  // Count running jobs
  const runningJobsCount = activeJobs.filter(j => j.status === 'pending' || j.status === 'running').length
  const completedJobsCount = activeJobs.filter(j => j.status === 'completed').length

  // Count active optional features (excludes terrain and site solid which are lightweight)
  const countActiveFeatures = (state: FormState): number => {
    return [
      state.includeRoads,
      state.includeBuildings,
      state.includeForest,
      state.includeWater,
      state.includeRailways,
      state.includeSatellite,
    ].filter(Boolean).length
  }

  const updateForm = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => {
      let updated = { ...prev, [key]: value }

      // Apply adaptive resolution when radius changes
      if (key === 'radius' && typeof value === 'number') {
        updated.resolution = getAdaptiveResolution(value)
      }

      // Limit feature count - disable oldest enabled feature if limit exceeded
      const featureKeys: (keyof FormState)[] = [
        'includeRoads', 'includeBuildings', 'includeForest',
        'includeWater', 'includeRailways', 'includeSatellite'
      ]
      if (featureKeys.includes(key) && value === true) {
        const activeCount = countActiveFeatures(updated)
        if (activeCount > LIMITS.MAX_FEATURES) {
          updated[key] = false as FormState[K]
          setError(`Maximum ${LIMITS.MAX_FEATURES} features at once to ensure fast generation`)
          setTimeout(() => setError(null), 3000)
        }
      }

      return updated
    })

    if (key === 'address') {
      setLuckyPick(null)
    }
  }

  const enableRecommended = () => {
    setForm((prev) => ({
      ...prev,
      includeRoads: true,
      includeBuildings: true,
      includeForest: true,
      includeWater: true,
      includeRailways: false,
      includeSatellite: false,
      exportGltf: false,
    }))
  }

  const luckyDraw = () => {
    const pick = LUCKY_LOCATIONS[Math.floor(Math.random() * LUCKY_LOCATIONS.length)]
    setLuckyPick(pick)
    setForm((prev) => ({ ...prev, address: pick.address }))
  }

  const handleJobStatusChange = (jobId: string, status: ActiveJob['status']) => {
    setActiveJobs(prev => prev.map(job =>
      job.id === jobId ? { ...job, status } : job
    ))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      const request: GenerateRequest = {
        address: form.address,
        include_terrain: form.includeTerrain,
        include_site_solid: form.includeSiteSolid,
        include_roads: form.includeRoads,
        include_buildings: form.includeBuildings,
        include_forest: form.includeForest,
        include_water: form.includeWater,
        include_railways: form.includeRailways,
        include_bridges: form.includeBridges,
        include_satellite_overlay: form.includeSatellite,
        export_gltf: form.exportGltf || form.includeSatellite,
        radius: form.radius,
        resolution: form.resolution,
        output_name: form.outputName,
      }

      const result = await createJob(request)

      setActiveJobs((prev) => [
        {
          id: result.job_id,
          location: form.address,
          name: luckyPick?.name,
          status: 'pending',
        },
        ...prev,
      ])

      setForm((prev) => ({ ...prev, address: '' }))
      setLuckyPick(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start generation')
    } finally {
      setIsSubmitting(false)
    }
  }

  const removeJob = (jobId: string) => {
    setActiveJobs((prev) => prev.filter((j) => j.id !== jobId))
  }

  // Common card class for secret mode
  const cardClass = secretMode
    ? 'sketch-card border-2 border-purple-400 bg-gradient-to-br from-purple-50/50 to-pink-50/50'
    : 'sketch-card'

  return (
    <div className="space-y-8">
      {/* Secret Mode Banner */}
      <AnimatePresence>
        {secretMode && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-gradient-to-r from-purple-600 via-pink-600 to-purple-600 text-white p-4 text-center"
          >
            <div className="flex items-center justify-center gap-3">
              <Sparkles size={20} className="animate-pulse" />
              <span className="font-mono font-bold">SECRET MODE ACTIVATED</span>
              <Sparkles size={20} className="animate-pulse" />
            </div>
            <p className="text-purple-200 text-xs mt-1">
              Toblerone HQ selected · All features enabled · Maximum detail
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-8">
        {/* Location Section */}
        <section className={cardClass}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <MapPin size={18} className={secretMode ? 'text-purple-600' : 'text-sketch-gray'} />
              <h3 className="font-mono font-medium">Location</h3>
              {secretMode && (
                <motion.span
                  initial={{ scale: 0 }}
                  animate={{ scale: [1, 1.1, 1] }}
                  transition={{ repeat: Infinity, duration: 2 }}
                  className="text-[10px] px-2 py-0.5 bg-gradient-to-r from-purple-500 to-pink-500 text-white"
                >
                  LOCKED IN
                </motion.span>
              )}
            </div>
            <button
              type="button"
              onClick={luckyDraw}
              disabled={secretMode}
              className={`py-2 px-3 flex items-center gap-2 text-xs transition-transform ${
                secretMode
                  ? 'bg-purple-100 border border-purple-300 text-purple-600 cursor-not-allowed'
                  : 'sketch-btn hover:rotate-3'
              }`}
              title={secretMode ? 'Secret location selected!' : 'Try your luck with a random Swiss location!'}
            >
              <Dices size={14} />
              {secretMode ? 'Secret Location' : 'Lucky Draw'}
            </button>
          </div>

          {/* Lucky Pick Display */}
          <AnimatePresence>
            {luckyPick && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className={`mb-4 p-3 border-2 border-dashed ${secretMode ? 'bg-purple-50 border-purple-300' : 'bg-sketch-paper border-sketch-gray'}`}
              >
                <div className="flex items-center gap-2">
                  <Dices size={16} className={secretMode ? 'text-purple-600' : 'text-sketch-gray'} />
                  <span className="font-mono text-sm font-medium">{luckyPick.name}</span>
                </div>
                <p className="text-xs text-sketch-gray mt-1">{luckyPick.desc}</p>
              </motion.div>
            )}
          </AnimatePresence>

          <div>
            <label className="tech-label block mb-2">Swiss Address</label>
            <AddressAutocomplete
              value={form.address}
              onChange={(addr) => {
                setForm(prev => ({ ...prev, address: addr }))
                if (luckyPick && addr !== luckyPick.address) {
                  setLuckyPick(null)
                }
              }}
              onSelect={(suggestion) => {
                setForm(prev => ({ ...prev, address: suggestion.label }))
                setLuckyPick(null)
              }}
              placeholder="Bundesplatz 3, Bern"
              disabled={!!luckyPick}
            />
            <p className="text-xs text-sketch-gray mt-2">
              {luckyPick ? (
                <>Selected: {luckyPick.name} — <button type="button" onClick={() => { setLuckyPick(null); setForm(prev => ({ ...prev, address: '' })) }} className="underline hover:text-sketch-black">Clear &amp; search</button></>
              ) : (
                <>Start typing to search Swiss addresses — or try <button type="button" onClick={luckyDraw} className="underline hover:text-sketch-black">Lucky Draw</button></>
              )}
            </p>
          </div>
        </section>

        {/* Features Grid */}
        <section className={cardClass}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Settings2 size={18} className={secretMode ? 'text-purple-600' : 'text-sketch-gray'} />
              <h3 className="font-mono font-medium">Features</h3>
              {secretMode ? (
                <span className="text-[10px] px-2 py-0.5 bg-gradient-to-r from-purple-500 to-pink-500 text-white flex items-center gap-1">
                  <Zap size={10} />
                  MAX POWER
                </span>
              ) : (
                <span className={`text-[10px] px-2 py-0.5 border ${
                  countActiveFeatures(form) >= LIMITS.MAX_FEATURES
                    ? 'border-red-400 bg-red-50 text-red-600'
                    : 'border-sketch-gray bg-sketch-pale text-sketch-gray'
                }`}>
                  {countActiveFeatures(form)}/{LIMITS.MAX_FEATURES}
                </span>
              )}
            </div>
            {!secretMode && (
              <button
                type="button"
                onClick={enableRecommended}
                className="flex items-center gap-1 text-xs font-mono text-sketch-gray hover:text-sketch-black transition-colors"
              >
                <Sparkles size={14} />
                Recommended
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <FeatureToggle
              icon={Mountain}
              label="Terrain"
              description="Surrounding elevation mesh"
              checked={form.includeTerrain}
              onChange={(v) => updateForm('includeTerrain', v)}
            />
            <FeatureToggle
              icon={Building2}
              label="Site Solid"
              description="Parcel boundary extrusion"
              checked={form.includeSiteSolid}
              onChange={(v) => updateForm('includeSiteSolid', v)}
            />
            <FeatureToggle
              icon={Car}
              label="Roads"
              description="Street network geometry"
              checked={form.includeRoads}
              onChange={(v) => updateForm('includeRoads', v)}
            />
            <FeatureToggle
              icon={Building2}
              label="Buildings"
              description="3D building footprints"
              checked={form.includeBuildings}
              onChange={(v) => updateForm('includeBuildings', v)}
            />
            <FeatureToggle
              icon={TreePine}
              label="Forest"
              description="Vegetation coverage"
              checked={form.includeForest}
              onChange={(v) => updateForm('includeForest', v)}
            />
            <FeatureToggle
              icon={Droplets}
              label="Water"
              description="Lakes, rivers, streams"
              checked={form.includeWater}
              onChange={(v) => updateForm('includeWater', v)}
            />
            <FeatureToggle
              icon={Train}
              label="Railways"
              description="Rail infrastructure"
              checked={form.includeRailways}
              onChange={(v) => updateForm('includeRailways', v)}
            />
            <FeatureToggle
              icon={Satellite}
              label="Satellite"
              description="Aerial imagery overlay"
              checked={form.includeSatellite}
              onChange={(v) => updateForm('includeSatellite', v)}
            />
          </div>
        </section>

        {/* Advanced Settings */}
        <section className={cardClass}>
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="w-full flex items-center justify-between"
          >
            <div className="flex items-center gap-2">
              <Settings2 size={18} className={secretMode ? 'text-purple-600' : 'text-sketch-gray'} />
              <h3 className="font-mono font-medium">Advanced Settings</h3>
              {secretMode && (
                <span className="text-[10px] px-2 py-0.5 bg-purple-100 text-purple-600 border border-purple-300">
                  2m DETAIL
                </span>
              )}
            </div>
            <motion.div
              animate={{ rotate: showAdvanced ? 180 : 0 }}
              transition={{ duration: 0.2 }}
            >
              <ChevronDown size={20} className={secretMode ? 'text-purple-600' : 'text-sketch-gray'} />
            </motion.div>
          </button>

          <AnimatePresence>
            {showAdvanced && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <div className="pt-4 space-y-4">
                  <div className="p-3 bg-sketch-pale border border-sketch-gray text-xs text-sketch-gray">
                    Resolution adapts automatically to radius for optimal performance.
                    {secretMode && ' Secret mode: Maximum detail enabled!'}
                  </div>

                  <div>
                    <div className="flex justify-between mb-2">
                      <label className="tech-label">Radius</label>
                      <span className="font-mono text-sm">{form.radius}m</span>
                    </div>
                    <input
                      type="range"
                      min={LIMITS.MIN_RADIUS}
                      max={LIMITS.MAX_RADIUS}
                      step="25"
                      value={form.radius}
                      onChange={(e) => updateForm('radius', Number(e.target.value))}
                      className="w-full"
                    />
                    <div className="flex justify-between text-[10px] text-sketch-gray mt-1">
                      <span>{LIMITS.MIN_RADIUS}m</span>
                      <span>{LIMITS.MAX_RADIUS}m max</span>
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between mb-2">
                      <label className="tech-label">Resolution (auto)</label>
                      <span className="font-mono text-sm">{form.resolution}m</span>
                    </div>
                    <div className="h-2 bg-sketch-pale border border-sketch-gray relative">
                      <div
                        className={`absolute inset-y-0 left-0 ${secretMode ? 'bg-purple-500' : 'bg-sketch-black'}`}
                        style={{ width: `${((LIMITS.MAX_RESOLUTION - form.resolution) / (LIMITS.MAX_RESOLUTION - LIMITS.MIN_RESOLUTION)) * 100}%` }}
                      />
                    </div>
                    <p className="text-[10px] text-sketch-gray mt-1">
                      {form.resolution <= 2 ? 'Maximum detail' : form.resolution <= 5 ? 'Fine detail' : form.resolution <= 8 ? 'Medium detail' : 'Optimized for large area'}
                    </p>
                  </div>

                  <div>
                    <label className="tech-label block mb-2">Output Filename</label>
                    <input
                      type="text"
                      value={form.outputName}
                      onChange={(e) => updateForm('outputName', e.target.value)}
                      className="sketch-input font-mono"
                      placeholder="site_model.ifc"
                    />
                  </div>

                  <div className="flex items-center gap-3 p-3 bg-sketch-paper border border-sketch-pale">
                    <input
                      type="checkbox"
                      id="exportGltf"
                      checked={form.exportGltf}
                      onChange={(e) => updateForm('exportGltf', e.target.checked)}
                    />
                    <div>
                      <p className="font-mono text-sm">Export glTF</p>
                      <p className="text-xs text-sketch-gray">
                        Generate GLB file alongside IFC (auto-enabled with satellite)
                      </p>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </section>

        {/* Error */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="flex items-center gap-3 p-4 bg-red-50 border-2 border-red-200"
            >
              <AlertCircle size={20} className="text-red-600 flex-shrink-0" />
              <p className="text-sm text-red-700 font-mono">{error}</p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Submit */}
        <button
          type="submit"
          disabled={isSubmitting}
          className={`w-full py-4 text-base flex items-center justify-center gap-3 disabled:opacity-50 transition-all ${
            secretMode
              ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white border-2 border-purple-700 hover:from-purple-700 hover:to-pink-700'
              : 'sketch-btn-primary'
          }`}
        >
          {isSubmitting ? (
            <>
              <Loader2 size={20} className="animate-spin" />
              <span className="animate-pulse">{loadingMsg}</span>
            </>
          ) : (
            <>
              <Plus size={20} />
              {secretMode ? 'Generate Secret Model' : 'Generate IFC Model'}
            </>
          )}
        </button>

        <p className="text-center text-[10px] text-sketch-gray/50 select-none">
          Made with Swiss precision · v0.1
        </p>
      </form>

      {/* Active Jobs */}
      <AnimatePresence>
        {activeJobs.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="space-y-4"
          >
            {/* Header with live counter */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {runningJobsCount > 0 ? (
                  <Loader2 size={16} className="animate-spin text-amber-600" />
                ) : (
                  <CheckCircle2 size={16} className="text-green-600" />
                )}
                <span className="text-sm font-mono">
                  {runningJobsCount > 0 ? (
                    <>
                      <span className="text-amber-600 font-medium">{runningJobsCount} running</span>
                      {completedJobsCount > 0 && (
                        <span className="text-sketch-gray"> · {completedJobsCount} completed</span>
                      )}
                    </>
                  ) : (
                    <span className="text-green-600 font-medium">{completedJobsCount} completed</span>
                  )}
                </span>
              </div>
              {activeJobs.length > 1 && (
                <button
                  onClick={() => setActiveJobs(prev => prev.filter(j => j.status === 'running' || j.status === 'pending'))}
                  className="text-xs text-sketch-gray hover:text-red-600 transition-colors font-mono"
                >
                  Clear completed
                </button>
              )}
            </div>

            {/* Job cards */}
            {activeJobs.map((job) => (
              <motion.div
                key={job.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="relative"
              >
                <div className={`absolute -top-2 -left-2 text-[10px] z-10 px-2 py-0.5 ${
                  job.status === 'completed'
                    ? 'bg-green-600 text-white'
                    : job.status === 'failed' || job.status === 'expired'
                    ? 'bg-red-600 text-white'
                    : 'sketch-badge-dark'
                }`}>
                  {job.name || job.location.slice(0, 16)}...
                </div>
                <JobTracker
                  jobId={job.id}
                  onComplete={() => handleJobStatusChange(job.id, 'completed')}
                  onError={() => handleJobStatusChange(job.id, 'failed')}
                  onStatusChange={(status) => handleJobStatusChange(job.id, status)}
                />
                <button
                  onClick={() => removeJob(job.id)}
                  className="mt-2 text-xs text-sketch-gray hover:text-red-600 transition-colors font-mono"
                >
                  × Dismiss
                </button>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
