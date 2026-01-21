'use client'

import { useState } from 'react'
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
} from 'lucide-react'
import FeatureToggle from './FeatureToggle'
import JobTracker from './JobTracker'
import { createJob, GenerateRequest } from '@/lib/api'

interface FormState {
  // Input
  inputType: 'egrid' | 'address'
  egrid: string
  address: string
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

const defaultState: FormState = {
  inputType: 'egrid',
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
  radius: 500,
  resolution: 10,
  outputName: 'site_model.ifc',
}

export default function GeneratorForm() {
  const [form, setForm] = useState<FormState>(defaultState)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)

  const updateForm = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const enableAll = () => {
    setForm((prev) => ({
      ...prev,
      includeRoads: true,
      includeBuildings: true,
      includeForest: true,
      includeWater: true,
      includeRailways: true,
      includeSatellite: true,
      exportGltf: true,
    }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setJobId(null)
    setIsSubmitting(true)

    try {
      const request: GenerateRequest = {
        ...(form.inputType === 'egrid' ? { egrid: form.egrid } : { address: form.address }),
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
      setJobId(result.job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start generation')
    } finally {
      setIsSubmitting(false)
    }
  }

  const resetForm = () => {
    setJobId(null)
    setError(null)
  }

  return (
    <div className="space-y-8">
      {/* Job Tracker */}
      <AnimatePresence>
        {jobId && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
          >
            <JobTracker
              jobId={jobId}
              onComplete={() => {}}
              onError={(err) => setError(err)}
            />
            <button
              onClick={resetForm}
              className="mt-4 text-sm text-sketch-gray hover:text-sketch-black transition-colors font-mono"
            >
              ← Generate another
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Form */}
      {!jobId && (
        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Location Input */}
          <section className="sketch-card">
            <div className="flex items-center gap-2 mb-4">
              <MapPin size={18} className="text-sketch-gray" />
              <h3 className="font-mono font-medium">Location</h3>
            </div>

            {/* Input Type Toggle */}
            <div className="flex border-2 border-sketch-black mb-4">
              <button
                type="button"
                onClick={() => updateForm('inputType', 'egrid')}
                className={`flex-1 py-2 px-4 text-sm font-mono transition-colors ${
                  form.inputType === 'egrid'
                    ? 'bg-sketch-black text-white'
                    : 'bg-sketch-white hover:bg-sketch-paper'
                }`}
              >
                EGRID
              </button>
              <button
                type="button"
                onClick={() => updateForm('inputType', 'address')}
                className={`flex-1 py-2 px-4 text-sm font-mono transition-colors ${
                  form.inputType === 'address'
                    ? 'bg-sketch-black text-white'
                    : 'bg-sketch-white hover:bg-sketch-paper'
                }`}
              >
                Address
              </button>
            </div>

            {form.inputType === 'egrid' ? (
              <div>
                <label className="tech-label block mb-2">Swiss EGRID</label>
                <input
                  type="text"
                  value={form.egrid}
                  onChange={(e) => updateForm('egrid', e.target.value)}
                  placeholder="CH999979659148"
                  className="sketch-input font-mono"
                  pattern="^CH[0-9]{9,18}$"
                  required
                />
                <p className="text-xs text-sketch-gray mt-2">
                  Swiss cadastral identifier (e.g., CH999979659148)
                </p>
              </div>
            ) : (
              <div>
                <label className="tech-label block mb-2">Swiss Address</label>
                <input
                  type="text"
                  value={form.address}
                  onChange={(e) => updateForm('address', e.target.value)}
                  placeholder="Bundesplatz 3, Bern"
                  className="sketch-input"
                  required
                />
                <p className="text-xs text-sketch-gray mt-2">
                  Will be resolved to EGRID automatically
                </p>
              </div>
            )}
          </section>

          {/* Features Grid */}
          <section className="sketch-card">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Settings2 size={18} className="text-sketch-gray" />
                <h3 className="font-mono font-medium">Features</h3>
              </div>
              <button
                type="button"
                onClick={enableAll}
                className="flex items-center gap-1 text-xs font-mono text-sketch-gray hover:text-sketch-black transition-colors"
              >
                <Sparkles size={14} />
                Enable all
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
                    {/* Radius */}
                    <div>
                      <div className="flex justify-between mb-2">
                        <label className="tech-label">Radius</label>
                        <span className="font-mono text-sm">{form.radius}m</span>
                      </div>
                      <input
                        type="range"
                        min="100"
                        max="2000"
                        step="50"
                        value={form.radius}
                        onChange={(e) => updateForm('radius', Number(e.target.value))}
                        className="w-full"
                      />
                    </div>

                    {/* Resolution */}
                    <div>
                      <div className="flex justify-between mb-2">
                        <label className="tech-label">Resolution</label>
                        <span className="font-mono text-sm">{form.resolution}m</span>
                      </div>
                      <input
                        type="range"
                        min="5"
                        max="50"
                        step="5"
                        value={form.resolution}
                        onChange={(e) => updateForm('resolution', Number(e.target.value))}
                        className="w-full"
                      />
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
            className="sketch-btn-primary w-full py-4 text-base flex items-center justify-center gap-3 disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <Loader2 size={20} className="animate-spin" />
                Starting Generation...
              </>
            ) : (
              <>
                Generate IFC Model
              </>
            )}
          </button>
        </form>
      )}
    </div>
  )
}
