const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'

export interface GenerateRequest {
  egrid?: string
  address?: string
  center_x?: number
  center_y?: number
  include_terrain?: boolean
  radius?: number
  resolution?: number
  attach_to_solid?: boolean
  include_site_solid?: boolean
  densify?: number
  include_roads?: boolean
  road_buffer?: number
  road_recess?: number
  roads_as_separate_elements?: boolean
  include_forest?: boolean
  forest_spacing?: number
  forest_threshold?: number
  include_water?: boolean
  include_buildings?: boolean
  include_railways?: boolean
  include_bridges?: boolean
  include_satellite_overlay?: boolean
  embed_imagery?: boolean
  imagery_resolution?: number
  imagery_year?: number
  export_gltf?: boolean
  apply_texture_to_buildings?: boolean
  output_name?: string
  include_all?: boolean
}

export interface JobStatus {
  status: 'pending' | 'running' | 'completed' | 'failed' | 'expired'
  download_url?: string
  output_name?: string
  gltf_download_url?: string
  gltf_output_name?: string
  texture_download_url?: string
  texture_output_name?: string
  error?: string
}

export interface JobCreateResponse {
  job_id: string
}

// Helper to ensure value is a string (handles edge cases where API might return unexpected types)
function ensureString(value: unknown): string | undefined {
  if (value === null || value === undefined) return undefined
  if (typeof value === 'string') return value
  if (typeof value === 'object') return undefined // Don't stringify objects
  return String(value)
}

export async function createJob(request: GenerateRequest): Promise<JobCreateResponse> {
  try {
    const response = await fetch(`${API_URL}/jobs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }

    return response.json()
  } catch (err) {
    // Better error messages for network/CORS issues
    if (err instanceof TypeError) {
      throw new Error(`Cannot connect to API. Please check that the server at ${API_URL} is running and CORS is properly configured.`)
    }
    throw err
  }
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const response = await fetch(`${API_URL}/jobs/${jobId}`)

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  const data = await response.json()

  // Sanitize response to ensure URL/name fields are strings
  return {
    status: data.status,
    download_url: ensureString(data.download_url),
    output_name: ensureString(data.output_name),
    gltf_download_url: ensureString(data.gltf_download_url),
    gltf_output_name: ensureString(data.gltf_output_name),
    texture_download_url: ensureString(data.texture_download_url),
    texture_output_name: ensureString(data.texture_output_name),
    error: ensureString(data.error),
  }
}

export function getDownloadUrl(path: string | undefined): string {
  if (!path || typeof path !== 'string') {
    console.error('Invalid download path:', path)
    return '#'
  }
  return `${API_URL}${path}`
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/health`)
    return response.ok
  } catch {
    return false
  }
}
