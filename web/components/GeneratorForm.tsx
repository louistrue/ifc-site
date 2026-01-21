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
} from 'lucide-react'
import FeatureToggle from './FeatureToggle'
import JobTracker from './JobTracker'
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
  egrid: string
  address: string // For Lucky Draw - backend resolves to EGRID
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
}

// Limits to prevent abuse
const LIMITS = {
  MAX_RADIUS: 500,       // Max 500m radius
  MIN_RADIUS: 50,        // Min 50m radius
  MAX_RESOLUTION: 15,    // Coarsest resolution
  MIN_RESOLUTION: 2,     // Finest resolution
  MAX_FEATURES: 5,       // Max features at once
}

// Calculate adaptive resolution based on radius
function getAdaptiveResolution(radius: number): number {
  // More generous - finer detail at all sizes
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

// Easter egg: Konami code tracker
const KONAMI_CODE = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a']

const defaultState: FormState = {
  egrid: '',
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
  radius: 200,           // Sensible default
  resolution: 10,        // Medium resolution
  outputName: 'site_model.ifc',
}

export default function GeneratorForm() {
  const [form, setForm] = useState<FormState>(defaultState)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeJobs, setActiveJobs] = useState<ActiveJob[]>([])
  const [luckyPick, setLuckyPick] = useState<typeof LUCKY_LOCATIONS[0] | null>(null)
  const [loadingMsg, setLoadingMsg] = useState(LOADING_MESSAGES[0])
  const [konamiIndex, setKonamiIndex] = useState(0)
  const [secretMode, setSecretMode] = useState(false)

  // Rotate loading message while submitting
  useEffect(() => {
    if (!isSubmitting) return
    const interval = setInterval(() => {
      setLoadingMsg(LOADING_MESSAGES[Math.floor(Math.random() * LOADING_MESSAGES.length)])
    }, 2000)
    return () => clearInterval(interval)
  }, [isSubmitting])

  // Konami code easter egg
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === KONAMI_CODE[konamiIndex]) {
        const next = konamiIndex + 1
        if (next === KONAMI_CODE.length) {
          setSecretMode(true)
          setKonamiIndex(0)
          // Auto-fill with a fun location
          const secret = LUCKY_LOCATIONS.find(l => l.name.includes('Toblerone')) || LUCKY_LOCATIONS[0]
          setLuckyPick(secret)
          setForm(prev => ({ ...prev, egrid: '', address: secret.address }))
        } else {
          setKonamiIndex(next)
        }
      } else {
        setKonamiIndex(0)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [konamiIndex])

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
          // Don't allow enabling more features - revert
          updated[key] = false as FormState[K]
          setError(`Maximum ${LIMITS.MAX_FEATURES} features at once to ensure fast generation`)
          setTimeout(() => setError(null), 3000)
        }
      }

      return updated
    })

    if (key === 'egrid') {
      setLuckyPick(null) // Clear lucky pick when manually editing
      setForm((prev) => ({ ...prev, address: '' })) // Clear address when using manual EGRID
    }
  }

  const enableRecommended = () => {
    // Enable a sensible set that fits within limits
    setForm((prev) => ({
      ...prev,
      includeRoads: true,
      includeBuildings: true,
      includeForest: true,
      includeWater: true,
      // Leave railways and satellite off to stay within limit
      includeRailways: false,
      includeSatellite: false,
      exportGltf: false,
    }))
  }

  const luckyDraw = () => {
    const pick = LUCKY_LOCATIONS[Math.floor(Math.random() * LUCKY_LOCATIONS.length)]
    setLuckyPick(pick)
    setForm((prev) => ({ ...prev, egrid: '', address: pick.address }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      // Use address for Lucky Draw, egrid for manual input
      const request: GenerateRequest = {
        ...(form.address ? { address: form.address } : { egrid: form.egrid }),
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

      // Add to active jobs list
      setActiveJobs((prev) => [
        {
          id: result.job_id,
          location: form.address || form.egrid,
          name: luckyPick?.name,
        },
        ...prev,
      ])

      // Reset form for next generation
      setForm((prev) => ({ ...prev, egrid: '', address: '' }))
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

  return (
    <div className="space-y-8">
      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-8">
        {/* Location Input */}
        <section className="sketch-card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <MapPin size={18} className="text-sketch-gray" />
              <h3 className="font-mono font-medium">Location</h3>
              {secretMode && (
                <span className="text-[10px] px-2 py-0.5 bg-gradient-to-r from-purple-500 to-pink-500 text-white animate-pulse">
                  SECRET MODE
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={luckyDraw}
              className="sketch-btn py-2 px-3 flex items-center gap-2 text-xs hover:rotate-3 transition-transform"
              title="Try your luck with a random Swiss location!"
            >
              <Dices size={14} className="hover:animate-bounce" />
              Lucky Draw
            </button>
          </div>

          {/* Lucky Pick Display */}
          <AnimatePresence>
            {luckyPick && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="mb-4 p-3 bg-sketch-paper border-2 border-dashed border-sketch-gray"
              >
                <div className="flex items-center gap-2">
                  <Dices size={16} className="text-sketch-gray" />
                  <span className="font-mono text-sm font-medium">{luckyPick.name}</span>
                </div>
                <p className="text-xs text-sketch-gray mt-1">{luckyPick.desc}</p>
              </motion.div>
            )}
          </AnimatePresence>

          <div>
            <label className="tech-label block mb-2">Swiss EGRID</label>
            <input
              type="text"
              value={luckyPick ? luckyPick.address : form.egrid}
              onChange={(e) => updateForm('egrid', e.target.value)}
              placeholder="CH999979659148"
              className="sketch-input font-mono"
              pattern={luckyPick ? undefined : "^CH[0-9]{9,18}$"}
              required={!luckyPick}
              disabled={!!luckyPick}
            />
            <p className="text-xs text-sketch-gray mt-2">
              {luckyPick ? (
                <>Using address: {luckyPick.address} — <button type="button" onClick={() => { setLuckyPick(null); setForm(prev => ({ ...prev, address: '' })) }} className="underline hover:text-sketch-black">Clear &amp; enter EGRID</button></>
              ) : (
                <>Swiss cadastral identifier — or try <button type="button" onClick={luckyDraw} className="underline hover:text-sketch-black">Lucky Draw</button></>
              )}
            </p>
          </div>
        </section>

        {/* Features Grid */}
        <section className="sketch-card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Settings2 size={18} className="text-sketch-gray" />
              <h3 className="font-mono font-medium">Features</h3>
              <span className={`text-[10px] px-2 py-0.5 border ${
                countActiveFeatures(form) >= LIMITS.MAX_FEATURES
                  ? 'border-red-400 bg-red-50 text-red-600'
                  : 'border-sketch-gray bg-sketch-pale text-sketch-gray'
              }`}>
                {countActiveFeatures(form)}/{LIMITS.MAX_FEATURES}
              </span>
            </div>
            <button
              type="button"
              onClick={enableRecommended}
              className="flex items-center gap-1 text-xs font-mono text-sketch-gray hover:text-sketch-black transition-colors"
            >
              <Sparkles size={14} />
              Recommended
            </button>
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
              icon={Building2}
              label="Buildings"
              description="3D buildings from CityGML"
              checked={form.includeBuildings}
              onChange={(v) => updateForm('includeBuildings', v)}
            />
            <FeatureToggle
              icon={Car}
              label="Roads"
              description="Road network geometry"
              checked={form.includeRoads}
              onChange={(v) => updateForm('includeRoads', v)}
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
              description="Rail tracks and stations"
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
        <section className="sketch-card">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="w-full flex items-center justify-between"
          >
            <div className="flex items-center gap-2">
              <Settings2 size={18} className="text-sketch-gray" />
              <h3 className="font-mono font-medium">Advanced Settings</h3>
            </div>
            <motion.div
              animate={{ rotate: showAdvanced ? 180 : 0 }}
              transition={{ duration: 0.2 }}
            >
              <ChevronDown size={20} className="text-sketch-gray" />
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
                  {/* Info box */}
                  <div className="p-3 bg-sketch-pale border border-sketch-gray text-xs text-sketch-gray">
                    Resolution adapts automatically to radius for optimal performance.
                    Larger areas use coarser resolution to keep file sizes manageable.
                  </div>

                  {/* Radius */}
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

                  {/* Resolution - read-only, set by adaptive logic */}
                  <div>
                    <div className="flex justify-between mb-2">
                      <label className="tech-label">Resolution (auto)</label>
                      <span className="font-mono text-sm">{form.resolution}m</span>
                    </div>
                    <div className="h-2 bg-sketch-pale border border-sketch-gray relative">
                      <div
                        className="absolute inset-y-0 left-0 bg-sketch-black"
                        style={{ width: `${((form.resolution - LIMITS.MIN_RESOLUTION) / (LIMITS.MAX_RESOLUTION - LIMITS.MIN_RESOLUTION)) * 100}%` }}
                      />
                    </div>
                    <p className="text-[10px] text-sketch-gray mt-1">
                      {form.resolution <= 5 ? 'Fine detail' : form.resolution <= 10 ? 'Medium detail' : 'Optimized for large area'}
                    </p>
                  </div>

                  {/* Output Name */}
                  <div>
                    <label className="tech-label block mb-2">Output Filename</label>
                    <input
                      type="text"
                      value={form.outputName}
                      onChange={(e) => updateForm('outputName', e.target.value)}
                      placeholder="site_model.ifc"
                      className="sketch-input font-mono"
                    />
                  </div>

                  {/* Export glTF */}
                  <div className="flex items-center gap-3 p-3 bg-sketch-paper border border-sketch-pale">
                    <input
                      type="checkbox"
                      className="sketch-checkbox"
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
          className={`sketch-btn-primary w-full py-4 text-base flex items-center justify-center gap-3 disabled:opacity-50 ${secretMode ? 'bg-gradient-to-r from-purple-600 to-pink-600 border-purple-700' : ''}`}
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

        {/* Subtle hint */}
        <p className="text-center text-[10px] text-sketch-gray/50 mt-3 select-none">
          Made with Swiss precision · v0.1 · {secretMode ? 'You found the secret!' : '↑↑↓↓←→←→BA'}
        </p>
      </form>

      {/* Active Jobs - shown below form so user sees them after clicking generate */}
      <AnimatePresence>
        {activeJobs.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="space-y-4"
          >
            <div className="flex items-center gap-2 text-sketch-gray">
              <Loader2 size={16} className="animate-spin" />
              <span className="text-sm font-mono">Active generations ({activeJobs.length})</span>
            </div>
            {activeJobs.map((job) => (
              <motion.div
                key={job.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="relative"
              >
                <div className="absolute -top-2 -left-2 sketch-badge-dark text-[10px] z-10">
                  {job.name || job.location.slice(0, 16)}...
                </div>
                <JobTracker
                  jobId={job.id}
                  onComplete={() => {}}
                  onError={(err) => setError(err)}
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
