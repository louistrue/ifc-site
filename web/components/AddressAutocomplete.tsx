'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { MapPin, Loader2, Search, X } from 'lucide-react'

interface AddressSuggestion {
  label: string
  detail: string
  lat: number
  lon: number
}

interface AddressAutocompleteProps {
  value: string
  onChange: (address: string) => void
  onSelect: (suggestion: AddressSuggestion) => void
  placeholder?: string
  disabled?: boolean
  className?: string
}

// Swiss address search via geo.admin.ch API
async function searchSwissAddresses(query: string): Promise<AddressSuggestion[]> {
  if (!query || query.length < 2) return []

  try {
    const params = new URLSearchParams({
      searchText: query,
      type: 'locations',
      origins: 'address',
      limit: '8',
    })

    const response = await fetch(
      `https://api3.geo.admin.ch/rest/services/api/SearchServer?${params}`
    )

    if (!response.ok) return []

    const data = await response.json()

    return (data.results || []).map((result: any) => ({
      label: result.attrs?.label?.replace(/<[^>]*>/g, '') || '',
      detail: result.attrs?.detail || '',
      lat: result.attrs?.lat || 0,
      lon: result.attrs?.lon || 0,
    }))
  } catch (error) {
    console.error('Address search failed:', error)
    return []
  }
}

export default function AddressAutocomplete({
  value,
  onChange,
  onSelect,
  placeholder = 'Search Swiss address...',
  disabled = false,
  className = '',
}: AddressAutocompleteProps) {
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isFocused, setIsFocused] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<NodeJS.Timeout>()

  // Debounced search
  const handleSearch = useCallback((query: string) => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
    }

    if (!query || query.length < 2) {
      setSuggestions([])
      return
    }

    setIsLoading(true)
    debounceRef.current = setTimeout(async () => {
      const results = await searchSwissAddresses(query)
      setSuggestions(results)
      setIsLoading(false)
      setSelectedIndex(-1)
    }, 300)
  }, [])

  // Handle input change
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value
    onChange(newValue)
    handleSearch(newValue)
  }

  // Handle suggestion selection
  const handleSelect = (suggestion: AddressSuggestion) => {
    onChange(suggestion.label)
    onSelect(suggestion)
    setSuggestions([])
    setIsFocused(false)
    inputRef.current?.blur()
  }

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!suggestions.length) return

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex(prev =>
          prev < suggestions.length - 1 ? prev + 1 : prev
        )
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex(prev => prev > 0 ? prev - 1 : -1)
        break
      case 'Enter':
        e.preventDefault()
        if (selectedIndex >= 0 && suggestions[selectedIndex]) {
          handleSelect(suggestions[selectedIndex])
        }
        break
      case 'Escape':
        setSuggestions([])
        setIsFocused(false)
        inputRef.current?.blur()
        break
    }
  }

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setSuggestions([])
        setIsFocused(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
    }
  }, [])

  const showSuggestions = isFocused && (suggestions.length > 0 || isLoading)

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {/* Input */}
      <div className="relative">
        <div className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none">
          {isLoading ? (
            <Loader2 size={18} className="text-sketch-gray animate-spin" />
          ) : (
            <Search size={18} className="text-sketch-gray" />
          )}
        </div>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={handleInputChange}
          onFocus={() => setIsFocused(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          className="sketch-input pl-10 pr-10 font-mono"
          autoComplete="off"
        />
        {value && !disabled && (
          <button
            type="button"
            onClick={() => {
              onChange('')
              setSuggestions([])
              inputRef.current?.focus()
            }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-sketch-gray hover:text-sketch-black transition-colors"
          >
            <X size={18} />
          </button>
        )}
      </div>

      {/* Suggestions dropdown */}
      <AnimatePresence>
        {showSuggestions && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.15 }}
            className="absolute z-50 w-full mt-1 bg-white border-2 border-sketch-black shadow-sketch max-h-64 overflow-y-auto"
          >
            {isLoading ? (
              <div className="p-4 text-center text-sketch-gray">
                <Loader2 size={20} className="animate-spin mx-auto mb-2" />
                <p className="text-sm font-mono">Searching Switzerland...</p>
              </div>
            ) : suggestions.length > 0 ? (
              <ul className="py-1">
                {suggestions.map((suggestion, index) => (
                  <li key={`${suggestion.label}-${index}`}>
                    <button
                      type="button"
                      onClick={() => handleSelect(suggestion)}
                      onMouseEnter={() => setSelectedIndex(index)}
                      className={`w-full px-4 py-3 text-left flex items-start gap-3 transition-colors ${
                        index === selectedIndex
                          ? 'bg-sketch-paper'
                          : 'hover:bg-sketch-pale'
                      }`}
                    >
                      <MapPin
                        size={16}
                        className={`mt-0.5 flex-shrink-0 ${
                          index === selectedIndex ? 'text-sketch-black' : 'text-sketch-gray'
                        }`}
                      />
                      <div className="min-w-0">
                        <p className="font-mono text-sm truncate">
                          {suggestion.label}
                        </p>
                        {suggestion.detail && (
                          <p className="text-xs text-sketch-gray truncate">
                            {suggestion.detail}
                          </p>
                        )}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="p-4 text-center text-sketch-gray">
                <p className="text-sm font-mono">No addresses found</p>
              </div>
            )}

            {/* Footer hint */}
            <div className="px-4 py-2 bg-sketch-pale border-t border-sketch-gray text-[10px] text-sketch-gray">
              <span className="font-mono">↑↓</span> navigate · <span className="font-mono">↵</span> select · <span className="font-mono">esc</span> close
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
