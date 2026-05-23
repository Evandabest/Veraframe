import { useEffect, useRef, useState } from 'react'
import { TimelinePanel, type PendingActionEdit } from './components/TimelinePanel'
import { ActionEditor } from './components/ActionEditor'
import { AssetsPanel } from './components/AssetsPanel'
import { VerbPalette } from './components/VerbPalette'
import { TakesPanel } from './components/TakesPanel'
import { RangeEditPanel } from './components/RangeEditPanel'
import { ScreenplayPreview } from './components/ScreenplayPreview'
import { mergeRangeEdit } from './range-edit'
import { formatTimelineMarkdown } from './docs'
import { frozenInWindow, toggleFrozen } from './frozen'
import type { Timeline as TimelineFull, TimelineAction as TLAction } from './timeline-types'
import { verbByType } from './verbs'
import { compileScriptToPrompt, parseScript } from './script'
import {
  captureTake,
  deleteTake as deleteTakeFn,
  renameTake as renameTakeFn,
  findTake,
  type Take
} from './takes'
import { AssetUploadModal, type AssetKind } from './components/AssetUploadModal'
import { EditCharacterModal } from './components/EditCharacterModal'
import { CharacterLibraryModal } from './components/CharacterLibraryModal'
import { AddMotionClipModal } from './components/AddMotionClipModal'
import { EditSceneModal } from './components/EditSceneModal'
import { AddCharacterModal } from './components/AddCharacterModal'
import type { RegistrySummary, DaemonState } from '../../preload'

interface TimelineAction {
  id: string
  type: string
  character?: string
  start: number
  end: number
  [key: string]: unknown
}

interface MutableTimeline {
  scene: string
  characters: Array<{ id: string; preset: string; spawn: string }>
  shots: Array<{ id: string; start: number; end: number; camera: string; actions: TimelineAction[] }>
  [key: string]: unknown
}

type LLMProvider = 'openai' | 'anthropic' | 'gemini' | 'ollama'

const PROVIDER_DEFAULT_MODEL: Record<LLMProvider, string> = {
  openai: 'gpt-4o',
  anthropic: 'claude-3-5-sonnet-20241022',
  gemini: 'gemini-3.1-flash-lite',
  ollama: 'llama3.1'
}

const PROVIDER_LABEL: Record<LLMProvider, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
  ollama: 'Ollama (local)'
}

type RenderState =
  | { status: 'idle' }
  | { status: 'running'; startedAt: number }
  | {
      status: 'success'
      renderId: string
      videoUrl: string
      durationSec: number
      timeline: Record<string, unknown>
      elapsedMs: number
    }
  | { status: 'error'; message: string; elapsedMs: number }

function App(): React.JSX.Element {
  const [mode, setMode] = useState<'mock' | 'llm'>('mock')
  const [prompt, setPrompt] = useState('')

  // Asset pool. Loaded from main at startup; refreshed on upload / explicit
  // refresh. The first scene becomes the default selection. Characters default
  // to all-selected so the LLM has the widest pool to pick from.
  const [registry, setRegistry] = useState<RegistrySummary>({
    scenes: [],
    characters: [],
    motions: []
  })
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null)
  const [selectedCharacterIds, setSelectedCharacterIds] = useState<string[]>([])
  const [uploadKind, setUploadKind] = useState<AssetKind | null>(null)
  const [editCharacterId, setEditCharacterId] = useState<string | null>(null)
  const [editSceneId, setEditSceneId] = useState<string | null>(null)
  const [addCharacterOpen, setAddCharacterOpen] = useState(false)

  const applyRegistry = (next: RegistrySummary): void => {
    setRegistry(next)
    setSelectedSceneId((prev) => {
      if (prev && next.scenes.some((s) => s.id === prev)) return prev
      return next.scenes[0]?.id ?? null
    })
    setSelectedCharacterIds((prev) => {
      // Drop characters that vanished; keep selected ones that still exist.
      const stillThere = prev.filter((id) => next.characters.some((c) => c.id === id))
      if (stillThere.length > 0) return stillThere
      return next.characters.map((c) => c.id)
    })
  }

  useEffect(() => {
    window.veraframe.getRegistry().then(applyRegistry)
  }, [])

  const refreshRegistry = async (): Promise<void> => {
    const result = await window.veraframe.rescanRegistry()
    if (result.ok) applyRegistry(result.registry)
  }

  const onToggleCharacter = (id: string, checked: boolean): void => {
    setSelectedCharacterIds((prev) =>
      checked ? Array.from(new Set([...prev, id])) : prev.filter((x) => x !== id)
    )
  }

  const onUploadSubmitted = async (): Promise<void> => {
    setUploadKind(null)
    await refreshRegistry()
  }

  const onRemoveScene = async (id: string): Promise<void> => {
    const scene = registry.scenes.find((s) => s.id === id)
    if (!scene) return
    if (!window.confirm(`Remove the user-uploaded scene "${scene.displayName}"? This deletes its files.`)) {
      return
    }
    const response = await window.veraframe.removeScene(id)
    if (response.ok) await refreshRegistry()
    else window.alert(`Remove failed: ${response.error}`)
  }

  const onRemoveCharacter = async (id: string): Promise<void> => {
    const character = registry.characters.find((c) => c.id === id)
    if (!character) return
    if (!window.confirm(`Remove the user-uploaded character "${character.displayName}"? This deletes its files.`)) {
      return
    }
    const response = await window.veraframe.removeCharacter(id)
    if (response.ok) await refreshRegistry()
    else window.alert(`Remove failed: ${response.error}`)
  }

  const [provider, setProvider] = useState<LLMProvider>('openai')
  const [model, setModel] = useState<string>(PROVIDER_DEFAULT_MODEL.openai)
  // Hardcoded localhost; advanced users can set OLLAMA_API_BASE in their shell.
  const ollamaHost = 'http://localhost:11434'
  const [ollamaModels, setOllamaModels] = useState<string[] | null>(null)
  const [ollamaError, setOllamaError] = useState<string | null>(null)
  const [ollamaLoading, setOllamaLoading] = useState(false)
  const [enhancing, setEnhancing] = useState(false)
  const [enhanceError, setEnhanceError] = useState<string | null>(null)
  const [pendingEnhanced, setPendingEnhanced] = useState<string | null>(null)
  const reviewRef = useRef<HTMLDivElement | null>(null)

  const onEnhance = async (): Promise<void> => {
    if (!prompt.trim()) return
    setEnhanceError(null)
    setPendingEnhanced(null)
    setEnhancing(true)
    const response = await window.veraframe.enhancePrompt({
      prompt,
      provider,
      model: model.trim() || undefined,
      ollamaHost: undefined
    })
    setEnhancing(false)
    if (response.ok) {
      setPendingEnhanced(response.prompt)
    } else {
      setEnhanceError(response.error)
    }
  }

  const onAcceptEnhanced = (): void => {
    if (pendingEnhanced) setPrompt(pendingEnhanced)
    setPendingEnhanced(null)
  }

  const onRejectEnhanced = (): void => {
    setPendingEnhanced(null)
  }

  // Scroll the review panel into view as soon as it appears.
  useEffect(() => {
    if (pendingEnhanced && reviewRef.current) {
      reviewRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [pendingEnhanced])

  const refreshOllamaModels = async (): Promise<void> => {
    setOllamaLoading(true)
    setOllamaError(null)
    const response = await window.veraframe.listOllamaModels(ollamaHost)
    setOllamaLoading(false)
    if (response.ok) {
      setOllamaModels(response.models)
      // If the current model isn't in the new list, default to the first
      // available one (or leave it if list is empty so user sees the error).
      if (response.models.length > 0 && !response.models.includes(model)) {
        setModel(response.models[0])
      }
    } else {
      setOllamaModels([])
      setOllamaError(response.error)
    }
  }

  // Auto-fetch when the user selects Ollama.
  useEffect(() => {
    if (provider === 'ollama') {
      refreshOllamaModels()
    } else {
      setOllamaModels(null)
      setOllamaError(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider])
  const [state, setState] = useState<RenderState>({ status: 'idle' })
  const [quality, setQuality] = useState<'draft' | 'hifi'>('hifi')
  const [generateAudio, setGenerateAudio] = useState(false)
  // Step 52 — walk_to uses a foot-aligned stride formula by default. The
  // toggle lets users A/B against the legacy duration-only behavior.
  const [physicsPostPass, setPhysicsPostPass] = useState(true)
  // Project-level style lock. When set, the daemon injects defaults into
  // every shot (e.g. set_lighting at shot start) unless the author already
  // authored the same kind of action at the shot's start.
  const [projectStyle, setProjectStyle] = useState<{ lighting?: string }>({})
  const [verbPaletteOpen, setVerbPaletteOpen] = useState(false)
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [addMotionOpen, setAddMotionOpen] = useState(false)

  const onRemoveMotion = async (id: string): Promise<void> => {
    const r = await window.veraframe.removeMotion(id)
    if (r.ok) await refreshRegistry()
  }

  const onExportDocumentation = async (
    range: { start: number; end: number } | null
  ): Promise<void> => {
    if (state.status !== 'success') return
    const tl = state.timeline as unknown as TimelineFull
    const md = formatTimelineMarkdown(tl, {
      projectName: projectPath ? projectPath.replace(/^.*[\\/]/, '').replace(/\..+$/, '') : undefined,
      range
    })
    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
    const defaultName = range
      ? `veraframe-doc-${range.start.toFixed(0)}s-${range.end.toFixed(0)}s.md`
      : `veraframe-doc-${stamp}.md`
    await window.veraframe.saveDocumentation({ content: md, defaultName })
  }
  // Prompt format (Step 46 + Step 40):
  // - 'free'       — one prose prompt; the LLM picks the timing.
  // - 'script'     — @<time> <prompt> per line, parsed locally.
  // - 'screenplay' — full screenplay prose; LLM breaks it down into
  //                  segments shown in a preview before render.
  const [promptFormat, setPromptFormat] = useState<'free' | 'script' | 'screenplay'>('free')
  const scriptMode = promptFormat === 'script'
  // Screenplay breakdown state (Step 40). `proposed` is non-null while
  // the preview panel is showing; cleared by Approve or Cancel.
  const [screenplayProposed, setScreenplayProposed] = useState<
    Array<{ start: number; end: number | null; prompt: string }> | null
  >(null)
  const [screenplayBusy, setScreenplayBusy] = useState(false)
  const [screenplayError, setScreenplayError] = useState<string | null>(null)
  // Takes / branches: snapshots of the timeline + render the user can
  // flip between non-destructively. Persisted in the project file.
  const [takes, setTakes] = useState<Take[]>([])
  const [activeTakeId, setActiveTakeId] = useState<string | null>(null)
  // Natural-language range edit (Step 48). `selectedRange` is set by a
  // shift+drag on the timeline; the prompt panel shows whenever it's set.
  const [selectedRange, setSelectedRange] = useState<{ start: number; end: number } | null>(null)
  const [rangeEditing, setRangeEditing] = useState(false)
  const [rangeEditError, setRangeEditError] = useState<string | null>(null)
  // Frozen action ids (Step 49). Renderer-only metadata persisted in the
  // project file. The LLM never sees this — it's a guard rail that
  // prevents range-edits / accidental rewrites from clobbering blocks
  // the user has explicitly approved.
  const [frozenActionIds, setFrozenActionIds] = useState<string[]>([])

  const onToggleFreeze = (actionId: string): void => {
    setFrozenActionIds((prev) => toggleFrozen(prev, actionId))
  }
  const videoRef = useRef<HTMLVideoElement | null>(null)

  const onProviderChange = (next: LLMProvider): void => {
    setProvider(next)
    // Switch the model field to the preferred default for the new provider —
    // but only if the user hadn't customized it for the current provider.
    if (model === PROVIDER_DEFAULT_MODEL[provider]) {
      setModel(PROVIDER_DEFAULT_MODEL[next])
    }
  }

  // --- Project save / open ---
  // A project file (.veraframe JSON) snapshots editor state. Saving a project
  // does NOT bundle the rendered MP4 (that's separate via Save Video). Opening
  // a project restores the controls; if a timeline is in the file we trigger
  // a direct-mode re-render so the video editor comes back populated.
  const [projectPath, setProjectPath] = useState<string | null>(null)
  const [projectNote, setProjectNote] = useState<string | null>(null)

  const onSaveProject = async (): Promise<void> => {
    setProjectNote(null)
    const currentTimeline =
      state.status === 'success' ? state.timeline : null
    const response = await window.veraframe.saveProject({
      selectedScene: selectedSceneId,
      selectedCharacters: selectedCharacterIds,
      prompt,
      mode,
      provider,
      model,
      timeline: currentTimeline,
      projectStyle,
      takes,
      frozenActionIds
    })
    if (response.ok) {
      setProjectPath(response.path)
      setProjectNote(`Saved to ${response.path}`)
    } else if (response.error !== 'save canceled') {
      setProjectNote(`Save failed: ${response.error}`)
    }
  }

  const onOpenProject = async (): Promise<void> => {
    setProjectNote(null)
    const response = await window.veraframe.openProject()
    if (!response.ok) {
      if (response.error !== 'open canceled') {
        setProjectNote(`Open failed: ${response.error}`)
      }
      return
    }
    const p = response.project
    setProjectPath(response.path)
    setMode(p.mode)
    setPrompt(p.prompt)
    setProvider(p.provider as LLMProvider)
    setModel(p.model)
    setSelectedSceneId(p.selectedScene)
    setSelectedCharacterIds(p.selectedCharacters)
    setProjectStyle(p.projectStyle ?? {})
    setTakes(p.takes ?? [])
    setActiveTakeId(null)
    setFrozenActionIds(p.frozenActionIds ?? [])
    if (p.timeline) {
      // Re-render the stored timeline so the user gets back the video editor
      // populated. This is a direct-mode render — no LLM, no mock fixture.
      const startedAt = Date.now()
      setState({ status: 'running', startedAt })
      const renderResp = await window.veraframe.render({
        mode: 'direct',
        timeline: p.timeline,
        quality,
        projectStyle,
        physicsPostPass
      })
      const elapsedMs = Date.now() - startedAt
      if (renderResp.ok) {
        setState({
          status: 'success',
          renderId: renderResp.renderId,
          videoUrl: renderResp.videoUrl,
          durationSec: renderResp.durationSec,
          timeline: renderResp.timeline,
          elapsedMs
        })
      } else {
        setState({ status: 'error', message: renderResp.error, elapsedMs })
        setProjectNote(`Loaded project but re-render failed: ${renderResp.error}`)
      }
    } else {
      setState({ status: 'idle' })
      setProjectNote(`Loaded project (no saved timeline — click Render to materialize).`)
    }
  }

  const onNewProject = (): void => {
    if (!window.confirm('Discard the current project state and start fresh?')) return
    setProjectPath(null)
    setProjectNote(null)
    setPrompt('')
    setMode('mock')
    setState({ status: 'idle' })
    setTakes([])
    setActiveTakeId(null)
    setFrozenActionIds([])
    // Selections stay — they're driven by the registry which doesn't change.
  }

  const onSaveTake = (): void => {
    if (state.status !== 'success') return
    const t = captureTake(takes, {
      timeline: state.timeline,
      renderId: state.renderId,
      videoUrl: state.videoUrl,
      durationSec: state.durationSec,
      prompt
    })
    setTakes((prev) => [...prev, t])
    setActiveTakeId(t.id)
  }

  const onRestoreTake = (id: string): void => {
    const t = findTake(takes, id)
    if (!t) return
    setState({
      status: 'success',
      renderId: t.renderId,
      videoUrl: t.videoUrl,
      durationSec: t.durationSec,
      timeline: t.timeline as Record<string, unknown>,
      elapsedMs: 0
    })
    setPrompt(t.prompt)
    setActiveTakeId(t.id)
  }

  const onRenameTake = (id: string, name: string): void => {
    setTakes((prev) => renameTakeFn(prev, id, name))
  }

  const onDeleteTake = (id: string): void => {
    setTakes((prev) => deleteTakeFn(prev, id))
    if (activeTakeId === id) setActiveTakeId(null)
  }

  const onCancelRangeEdit = (): void => {
    setSelectedRange(null)
    setRangeEditError(null)
    setRangeEditing(false)
  }

  const onSubmitRangeEdit = async (promptText: string): Promise<void> => {
    if (!selectedRange || state.status !== 'success') return
    if (selectedRange.end <= selectedRange.start + 0.1) {
      setRangeEditError('Range is too short — drag a wider window.')
      return
    }
    const tlBefore = state.timeline as unknown as TimelineFull
    // Refuse if any locked action overlaps the selected window.
    const allActions = (tlBefore.shots ?? []).flatMap((s) => s.actions)
    const blocking = frozenInWindow(allActions, frozenActionIds, selectedRange)
    if (blocking.length > 0) {
      const names = blocking.map((a) => `${a.type}(${a.id})`).join(', ')
      setRangeEditError(
        `Range overlaps locked action(s): ${names}. Right-click them to unlock, or narrow the selection.`
      )
      return
    }
    setRangeEditing(true)
    setRangeEditError(null)

    const response = await window.veraframe.editRange({
      prompt: promptText,
      scene: tlBefore.scene,
      start: selectedRange.start,
      end: selectedRange.end,
      timelineContext: state.timeline,
      provider,
      model: model.trim() || undefined
    })

    if (!response.ok) {
      setRangeEditError(response.error)
      setRangeEditing(false)
      return
    }

    let merged: ReturnType<typeof mergeRangeEdit>
    try {
      merged = mergeRangeEdit(
        tlBefore,
        selectedRange,
        response.actions as unknown as TLAction[]
      )
    } catch (err) {
      setRangeEditError((err as Error).message)
      setRangeEditing(false)
      return
    }

    // Splice the changed window into the existing video. The new actions
    // all live in [selectedRange.start, selectedRange.end] by construction
    // (the subprocess clamps them), so a splice covers the right slice.
    const previousRenderId = state.renderId
    const previousDurationSec = state.durationSec
    const startedAt = Date.now()
    setState({ status: 'running', startedAt })
    const renderResp = await window.veraframe.render({
      mode: 'direct',
      timeline: merged.timeline as unknown as Record<string, unknown>,
      incremental: {
        previousRenderId,
        changedWindow: { start: selectedRange.start, end: selectedRange.end },
        operation: 'splice'
      },
      quality,
      generateAudio,
      projectStyle,
      physicsPostPass
    })
    const elapsedMs = Date.now() - startedAt
    setRangeEditing(false)

    if (renderResp.ok) {
      setState({
        status: 'success',
        renderId: renderResp.renderId,
        videoUrl: renderResp.videoUrl,
        durationSec: renderResp.durationSec || previousDurationSec,
        timeline: renderResp.timeline,
        elapsedMs
      })
      setSelectedRange(null)
      setActiveTakeId(null)
    } else {
      setState({ status: 'error', message: renderResp.error, elapsedMs })
      setRangeEditError(renderResp.error)
    }
  }

  const onBreakdownScreenplay = async (): Promise<void> => {
    if (!prompt.trim()) return
    setScreenplayBusy(true)
    setScreenplayError(null)
    const response = await window.veraframe.breakdownScreenplay({
      text: prompt,
      provider,
      model: model.trim() || undefined
    })
    setScreenplayBusy(false)
    if (!response.ok) {
      setScreenplayError(response.error)
      setScreenplayProposed([])
      return
    }
    setScreenplayProposed(
      response.segments.map((s) => ({ start: s.start, end: s.end, prompt: s.prompt }))
    )
  }

  const onApproveScreenplay = async (
    segments: Array<{ start: number; end: number | null; prompt: string }>
  ): Promise<void> => {
    if (segments.length === 0) return
    // Compile the approved segments into a structured prompt; reuse the
    // exact same downstream pipeline that Script mode uses.
    const compiled = compileScriptToPrompt(
      segments.map((s) => ({ start: s.start, end: s.end, prompt: s.prompt, line: 0 }))
    )
    setScreenplayProposed(null)
    setScreenplayError(null)
    const startedAt = Date.now()
    setState({ status: 'running', startedAt })
    const response = await window.veraframe.render({
      mode: 'llm',
      prompt: compiled,
      provider,
      model: model.trim() || undefined,
      selectedScene: selectedSceneId ?? undefined,
      selectedCharacters:
        selectedCharacterIds.length > 0 ? selectedCharacterIds : undefined,
      quality,
      generateAudio,
      projectStyle,
      physicsPostPass
    })
    const elapsedMs = Date.now() - startedAt
    if (response.ok) {
      setState({
        status: 'success',
        renderId: response.renderId,
        videoUrl: response.videoUrl,
        durationSec: response.durationSec,
        timeline: response.timeline,
        elapsedMs
      })
    } else {
      setState({ status: 'error', message: response.error, elapsedMs })
    }
  }

  const onRender = async (): Promise<void> => {
    if (mode === 'llm' && !prompt.trim()) return
    if (mode === 'llm' && promptFormat === 'screenplay') {
      // Screenplay mode goes through the preview first; the Render
      // button shows "Break down" in that case (see below).
      await onBreakdownScreenplay()
      return
    }
    // Destructive-path guard: a full Render replaces the current
    // timeline + video with a fresh LLM-generated pair. Per-block edits,
    // range edits, retimes, and timeline extensions are additive and
    // don't need the warning — only this entry point does.
    if (state.status === 'success') {
      const ok = window.confirm(
        'Render will replace your current timeline and video with a fresh ' +
          'LLM-generated render from the prompt. Any edits, locked actions, ' +
          'and the existing video will be discarded.\n\n' +
          'Save the current state as a Take first if you want to keep it.\n\n' +
          'Continue with re-render?'
      )
      if (!ok) return
    }
    // In script mode, compile the timestamped lines into a structured prompt
    // before sending to the LLM. If parsing produces errors we leave the raw
    // text alone — the UI surfaces the error inline.
    let effectivePrompt = prompt
    if (mode === 'llm' && scriptMode) {
      const parsed = parseScript(prompt)
      if (parsed.errors.length === 0 && parsed.segments.length > 0) {
        effectivePrompt = compileScriptToPrompt(parsed.segments)
      }
    }
    const startedAt = Date.now()
    setState({ status: 'running', startedAt })
    const response = await window.veraframe.render({
      mode,
      prompt: mode === 'llm' ? effectivePrompt : undefined,
      provider: mode === 'llm' ? provider : undefined,
      model: mode === 'llm' ? model.trim() || undefined : undefined,
      ollamaHost: undefined,
      selectedScene: mode === 'llm' ? selectedSceneId ?? undefined : undefined,
      selectedCharacters:
        mode === 'llm' && selectedCharacterIds.length > 0 ? selectedCharacterIds : undefined,
      quality,
      generateAudio,
      projectStyle,
      physicsPostPass
    })
    const elapsedMs = Date.now() - startedAt
    if (response.ok) {
      setState({
        status: 'success',
        renderId: response.renderId,
        videoUrl: response.videoUrl,
        durationSec: response.durationSec,
        timeline: response.timeline,
        elapsedMs
      })
    } else {
      setState({ status: 'error', message: response.error, elapsedMs })
    }
  }

  // Live tick (1Hz) while a render is in progress so the elapsed counter
  // updates. Stops as soon as the render leaves the running state.
  const [renderTick, setRenderTick] = useState(0)
  useEffect(() => {
    if (state.status !== 'running') return
    const id = setInterval(() => setRenderTick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [state.status])
  const liveElapsedSec =
    state.status === 'running' ? Math.floor((Date.now() - state.startedAt) / 1000) : 0
  // Reference renderTick so the dependency is "used" — re-renders are what
  // drives the visible counter forward.
  void renderTick

  // Daemon health banner. Main pushes status events whenever the daemon
  // crashes / restarts; we surface a banner near the header so the user
  // knows why a render might be unavailable.
  const [daemonStatus, setDaemonStatus] = useState<{ state: DaemonState; detail?: string }>({
    state: 'starting'
  })
  useEffect(() => {
    window.veraframe.getDaemonState().then(({ state }) => {
      setDaemonStatus({ state })
    })
    return window.veraframe.onDaemonStatus((event) => setDaemonStatus(event))
  }, [])

  // Subscribe to per-step progress events from main; reset when a new render
  // starts.
  const [currentStep, setCurrentStep] = useState<{ step: string; detail?: string } | null>(null)
  useEffect(() => {
    if (state.status === 'running') setCurrentStep(null)
  }, [state.status])
  useEffect(() => {
    const unsubscribe = window.veraframe.onRenderStatus((event) => {
      setCurrentStep(event)
    })
    return unsubscribe
  }, [])

  const [saveNote, setSaveNote] = useState<string | null>(null)
  const onSave = async (renderId: string): Promise<void> => {
    setSaveNote(null)
    const response = await window.veraframe.saveRender(renderId)
    if (response.ok) {
      setSaveNote(`Saved to ${response.path}`)
    } else if (response.error !== 'save canceled') {
      setSaveNote(`Save failed: ${response.error}`)
    }
  }

  const onSeek = (timeSec: number): void => {
    if (videoRef.current) {
      videoRef.current.currentTime = timeSec
    }
  }

  // --- Per-block edit / add flow ---
  // The flow has two stages. Stage 1: user clicks a block (or "+") and
  // types a prompt; we call the LLM and surface the proposed Action. Stage
  // 2: user accepts or rejects. Accept replaces the timeline locally and
  // kicks off a render with mode='direct' (no LLM, just executor + render).
  interface EditorTarget {
    laneId: string
    startSec: number
    /** Locked end (edit flow). Undefined when adding — LLM picks duration. */
    endSec: number | null
    original: TimelineAction | null
    /** Seed for the prompt textarea — non-empty when opened via a verb-
     *  palette drop so the user starts with the verb already typed. */
    initialPrompt?: string
  }
  const [editor, setEditor] = useState<EditorTarget | null>(null)
  const [pendingAction, setPendingAction] = useState<TimelineAction | null>(null)
  const [generatingAction, setGeneratingAction] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const closeEditor = (): void => {
    setEditor(null)
    setPendingAction(null)
    setActionError(null)
    setGeneratingAction(false)
  }

  const onEditAction = (action: TimelineAction, laneId: string): void => {
    setEditor({
      laneId,
      startSec: action.start,
      endSec: action.end, // locked for edits
      original: action
    })
    setPendingAction(null)
    setActionError(null)
  }

  const onAddAction = (laneId: string, startSec: number): void => {
    if (state.status !== 'success') return
    // No pre-determined end — the LLM picks a sensible duration based on the
    // action type it chooses (1-2s for face expressions, 3-5s for walks, etc).
    setEditor({ laneId, startSec, endSec: null, original: null })
    setPendingAction(null)
    setActionError(null)
  }

  const onPaletteDrop = (laneId: string, startSec: number, verbType: string): void => {
    if (state.status !== 'success') return
    const verb = verbByType(verbType)
    if (!verb) return
    // Snap drop time to one-tenth of a second so the user gets a clean value
    // in ActionEditor.
    const snapped = Math.round(startSec * 10) / 10
    setEditor({
      laneId,
      startSec: snapped,
      endSec: null,
      original: null,
      initialPrompt: verb.promptSeed
    })
    setPendingAction(null)
    setActionError(null)
    setVerbPaletteOpen(false)
  }

  const onGenerateAction = async (promptText: string): Promise<void> => {
    if (!editor || state.status !== 'success') return
    setGeneratingAction(true)
    setActionError(null)
    const tl = state.timeline as unknown as MutableTimeline
    const targetId = editor.original?.id ?? `act_${Date.now().toString(36)}`
    const response = await window.veraframe.generateAction({
      prompt: promptText,
      scene: tl.scene,
      character: editor.laneId,
      actionId: targetId,
      start: editor.startSec,
      end: editor.endSec ?? undefined,
      timelineContext: state.timeline,
      provider,
      model: model.trim() || undefined
    })
    setGeneratingAction(false)
    if (response.ok) {
      setPendingAction(response.action as TimelineAction)
    } else {
      setActionError(response.error)
    }
  }

  const onAcceptAction = async (): Promise<void> => {
    if (!editor || !pendingAction || state.status !== 'success') return
    const previousRenderId = state.renderId
    const previousDurationSec = state.durationSec
    const tl = JSON.parse(JSON.stringify(state.timeline)) as MutableTimeline

    const targetShot = tl.shots[0]
    if (!targetShot) {
      setActionError('Timeline has no shot to append to.')
      return
    }
    if (editor.original) {
      targetShot.actions = targetShot.actions.map((a) =>
        a.id === editor.original!.id ? pendingAction : a
      )
    } else {
      targetShot.actions = [...targetShot.actions, pendingAction]
    }
    // Grow the shot if the new action extends past the current end so the
    // render pipeline derives a larger durationSec.
    if (pendingAction.end > targetShot.end) {
      targetShot.end = pendingAction.end
    }
    closeEditor()

    // Pick the incremental strategy:
    // - Adding new content past the previous video's end → append the tail.
    // - Editing inside the existing video (or filling an inner gap)
    //   → splice the changed window into the previous video.
    const isExtension =
      !editor.original && pendingAction.start >= previousDurationSec - 0.05
    const incremental = isExtension
      ? {
          previousRenderId,
          changedWindow: { start: previousDurationSec, end: pendingAction.end },
          operation: 'append' as const
        }
      : {
          previousRenderId,
          changedWindow: { start: pendingAction.start, end: pendingAction.end },
          operation: 'splice' as const
        }

    const startedAt = Date.now()
    setState({ status: 'running', startedAt })
    const response = await window.veraframe.render({
      mode: 'direct',
      timeline: tl as unknown as Record<string, unknown>,
      incremental,
      quality,
      generateAudio,
      projectStyle,
      physicsPostPass
    })
    const elapsedMs = Date.now() - startedAt
    if (response.ok) {
      setState({
        status: 'success',
        renderId: response.renderId,
        videoUrl: response.videoUrl,
        durationSec: response.durationSec,
        timeline: response.timeline,
        elapsedMs
      })
    } else {
      setState({ status: 'error', message: response.error, elapsedMs })
    }
  }

  const onRejectAction = (): void => {
    setPendingAction(null)
    setActionError(null)
  }

  // Drag-to-retime: user dragged an action block's edge to a new start/end.
  // We mutate the timeline, compute the affected window (union of the old
  // and new spans), and trigger an incremental render. If the new end is
  // past the previous video's end, we append instead of splice.
  const onRetimeAction = async (
    action: TimelineAction,
    newStart: number,
    newEnd: number
  ): Promise<void> => {
    if (state.status !== 'success') return
    const previousRenderId = state.renderId
    const previousDurationSec = state.durationSec
    const tl = JSON.parse(JSON.stringify(state.timeline)) as MutableTimeline
    const targetShot = tl.shots[0]
    if (!targetShot) return
    const oldAction = targetShot.actions.find((a) => a.id === action.id)
    if (!oldAction) return
    const oldStart = oldAction.start
    const oldEnd = oldAction.end
    oldAction.start = newStart
    oldAction.end = newEnd
    if (newEnd > targetShot.end) targetShot.end = newEnd

    // Affected window = union of old and new spans. Anything outside this
    // can be safely reused from the previous render.
    const affectedStart = Math.min(oldStart, newStart)
    const affectedEnd = Math.max(oldEnd, newEnd)

    const isExtension = affectedEnd > previousDurationSec - 0.05
    const incremental = isExtension
      ? {
          previousRenderId,
          changedWindow: { start: previousDurationSec, end: affectedEnd },
          operation: 'append' as const
        }
      : {
          previousRenderId,
          changedWindow: { start: affectedStart, end: affectedEnd },
          operation: 'splice' as const
        }

    const startedAt = Date.now()
    setState({ status: 'running', startedAt })
    const response = await window.veraframe.render({
      mode: 'direct',
      timeline: tl as unknown as Record<string, unknown>,
      incremental,
      quality,
      generateAudio,
      projectStyle,
      physicsPostPass
    })
    const elapsedMs = Date.now() - startedAt
    if (response.ok) {
      setState({
        status: 'success',
        renderId: response.renderId,
        videoUrl: response.videoUrl,
        durationSec: response.durationSec,
        timeline: response.timeline,
        elapsedMs
      })
    } else {
      setState({ status: 'error', message: response.error, elapsedMs })
    }
  }

  // "+ Character" mid-edit. Adds a new character + a full-shot idle to the
  // current timeline, then triggers a FULL re-render (a new character changes
  // every frame, so incremental splice/append can't help us).
  const openAddCharacter = (): void => {
    if (state.status !== 'success') {
      window.alert('Render a video first, then you can add a character to its timeline.')
      return
    }
    setAddCharacterOpen(true)
  }

  const onConfirmAddCharacter = async (payload: {
    preset: string
    spawn: string
    handle: string
  }): Promise<void> => {
    if (state.status !== 'success') return
    setAddCharacterOpen(false)

    const tl = JSON.parse(JSON.stringify(state.timeline)) as MutableTimeline
    tl.characters = [
      ...tl.characters,
      { id: payload.handle, preset: payload.preset, spawn: payload.spawn }
    ]
    // Default behavior: cover the full shot with a single idle so the new
    // character isn't stuck in T-pose. User can edit the timeline later.
    const targetShot = tl.shots[0]
    if (targetShot) {
      targetShot.actions = [
        ...targetShot.actions,
        {
          id: `act_${Date.now().toString(36)}`,
          type: 'idle',
          character: payload.handle,
          start: targetShot.start,
          end: targetShot.end
        }
      ]
    }

    const startedAt = Date.now()
    setState({ status: 'running', startedAt })
    const response = await window.veraframe.render({
      mode: 'direct',
      timeline: tl as unknown as Record<string, unknown>,
      quality,
      generateAudio,
      projectStyle,
      physicsPostPass
    })
    const elapsedMs = Date.now() - startedAt
    if (response.ok) {
      setState({
        status: 'success',
        renderId: response.renderId,
        videoUrl: response.videoUrl,
        durationSec: response.durationSec,
        timeline: response.timeline,
        elapsedMs
      })
    } else {
      setState({ status: 'error', message: response.error, elapsedMs })
    }
  }

  const pendingEditForPanel: PendingActionEdit | null =
    editor && pendingAction
      ? {
          originalActionId: editor.original?.id ?? null,
          newAction: pendingAction,
          laneId: editor.laneId
        }
      : null

  const isRunning = state.status === 'running'
  const disabledSubmit = isRunning || (mode === 'llm' && !prompt.trim())

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <div className="mx-auto flex max-w-screen-2xl flex-col gap-6 p-8">
        <header className="flex items-end justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Veraframe</h1>
            <p className="mt-1 text-sm text-neutral-400">
              Natural-language animation compiler for Blender
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onNewProject}
                disabled={isRunning}
                className="rounded-md border border-neutral-700 px-3 py-1 text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
              >
                New
              </button>
              <button
                type="button"
                onClick={() => setLibraryOpen(true)}
                title="Open the persistent character library"
                className="rounded-md border border-neutral-700 px-3 py-1 text-xs text-neutral-200 hover:bg-neutral-800"
              >
                Library
              </button>
              <button
                type="button"
                onClick={() => setVerbPaletteOpen((v) => !v)}
                title="Open the verb palette — drag chips onto lanes to add actions. Render a timeline first to enable drops."
                className={`rounded-md border px-3 py-1 text-xs ${
                  verbPaletteOpen
                    ? 'border-blue-500 bg-blue-600/20 text-blue-100'
                    : 'border-neutral-700 text-neutral-200 hover:bg-neutral-800'
                }`}
              >
                Verbs
              </button>
              <button
                type="button"
                onClick={onOpenProject}
                disabled={isRunning}
                className="rounded-md border border-neutral-700 px-3 py-1 text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
              >
                Open Project…
              </button>
              <button
                type="button"
                onClick={() => onExportDocumentation(null)}
                disabled={isRunning || state.status !== 'success'}
                title="Export the entire timeline as a Markdown doc (beat-by-beat actions, characters, scene)."
                className="rounded-md border border-neutral-700 px-3 py-1 text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
              >
                Export doc
              </button>
              <button
                type="button"
                onClick={onSaveProject}
                disabled={isRunning}
                className="rounded-md border border-emerald-500/60 bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-200 hover:bg-emerald-500/30 disabled:opacity-50"
              >
                Save Project…
              </button>
            </div>
            {projectPath && (
              <p className="text-[11px] text-neutral-500" title={projectPath}>
                {projectPath.replace(/^.*[\\/]/, '')}
              </p>
            )}
            {projectNote && (
              <p className="text-[11px] text-neutral-500 break-all">{projectNote}</p>
            )}
          </div>
        </header>

        {daemonStatus.state !== 'ready' && (
          <div
            className={`rounded-md border px-3 py-2 text-xs ${
              daemonStatus.state === 'crashed'
                ? 'border-red-500/60 bg-red-500/10 text-red-200'
                : 'border-amber-500/60 bg-amber-500/10 text-amber-200'
            }`}
          >
            <span className="font-semibold">Blender daemon: {daemonStatus.state}</span>
            {daemonStatus.detail && (
              <span className="ml-2 text-neutral-400">{daemonStatus.detail}</span>
            )}
            {daemonStatus.state === 'crashed' && (
              <button
                type="button"
                onClick={async () => {
                  const resp = await window.veraframe.restartDaemon()
                  if (!resp.ok) window.alert(`Restart failed: ${resp.error}`)
                }}
                className="ml-3 rounded border border-red-500/60 px-2 py-0.5 text-[11px] text-red-100 hover:bg-red-500/25"
              >
                Restart now
              </button>
            )}
            {daemonStatus.state !== 'crashed' && (
              <span className="ml-2 text-neutral-400">
                — Renders are paused until the daemon is ready.
              </span>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[24rem_minmax(0,1fr)] lg:items-start">
        <div className="flex flex-col gap-4">
        <AssetsPanel
          registry={registry}
          selectedSceneId={selectedSceneId}
          selectedCharacterIds={selectedCharacterIds}
          onSelectScene={setSelectedSceneId}
          onToggleCharacter={onToggleCharacter}
          onAddScene={() => setUploadKind('scene')}
          onAddCharacter={() => setUploadKind('character')}
          onRemoveScene={onRemoveScene}
          onRemoveCharacter={onRemoveCharacter}
          onEditScene={setEditSceneId}
          onEditCharacter={setEditCharacterId}
          onRefresh={refreshRegistry}
          projectLighting={projectStyle.lighting}
          onProjectLightingChange={(next) =>
            setProjectStyle((prev) =>
              next === '' ? { ...prev, lighting: undefined } : { ...prev, lighting: next }
            )
          }
          disabled={isRunning}
        />

        <TakesPanel
          takes={takes}
          activeTakeId={activeTakeId}
          canSave={state.status === 'success'}
          onSave={onSaveTake}
          onRestore={onRestoreTake}
          onRename={onRenameTake}
          onDelete={onDeleteTake}
        />

        {/* AddCharacterModal lives down below; this is just a placeholder
            comment to anchor the wiring change above. */}
        <section className="flex flex-col gap-3 rounded-lg border border-neutral-800 bg-neutral-900 p-4">
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="mode"
                value="mock"
                checked={mode === 'mock'}
                onChange={() => setMode('mock')}
                disabled={isRunning}
              />
              Mock (canned timeline, no LLM)
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="mode"
                value="llm"
                checked={mode === 'llm'}
                onChange={() => setMode('llm')}
                disabled={isRunning}
              />
              LLM (requires API key)
            </label>
            {mode === 'llm' && (
              <label className="ml-auto flex items-center gap-2 text-xs text-neutral-300">
                Format
                <select
                  value={promptFormat}
                  onChange={(e) =>
                    setPromptFormat(e.target.value as 'free' | 'script' | 'screenplay')
                  }
                  disabled={isRunning}
                  title="Prose: free description. Script: @<time> lines. Screenplay: full screenplay text, broken into beats."
                  className="rounded border border-neutral-800 bg-neutral-950 px-1.5 py-0.5 text-xs focus:border-neutral-500 focus:outline-none"
                >
                  <option value="free">Prose</option>
                  <option value="script">Script</option>
                  <option value="screenplay">Screenplay</option>
                </select>
              </label>
            )}
          </div>

          <div className="relative">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              disabled={mode !== 'llm' || isRunning}
              placeholder={
                mode === 'llm'
                  ? promptFormat === 'script'
                    ? '@0 alice walks to the door\n@4 alice waves at bob\n@6-10 they argue'
                    : promptFormat === 'screenplay'
                      ? 'INT. CLASSROOM - DAY\n\nALICE enters through the door.\n\nALICE\nWhere is the experiment?\n\nBOB\nBehind you.'
                      : 'Describe a scene, e.g. "the student walks to the center of the lab and smiles"'
                  : 'Mock mode renders a canned timeline; no prompt needed.'
              }
              className="min-h-24 w-full resize-y rounded-md border border-neutral-800 bg-neutral-950 p-3 pr-24 text-sm font-mono placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none disabled:opacity-50"
            />
            {mode === 'llm' && (
              <button
                type="button"
                onClick={onEnhance}
                disabled={enhancing || isRunning || !prompt.trim()}
                title="Rewrite your prompt using the actual scene/character/spawn names"
                className="absolute right-2 top-2 rounded-md border border-purple-500/60 bg-purple-600/30 px-2 py-1 text-xs font-medium text-purple-200 hover:bg-purple-600/50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {enhancing ? 'Enhancing…' : '✨ Enhance'}
              </button>
            )}
          </div>
          {enhanceError && (
            <p className="text-xs text-red-400">Enhance failed: {enhanceError}</p>
          )}

          {mode === 'llm' && promptFormat === 'screenplay' && (
            <ScreenplayPreview
              proposed={
                screenplayProposed === null
                  ? null
                  : (screenplayProposed.map((s) => ({
                      start: s.start,
                      end: s.end,
                      prompt: s.prompt,
                      line: 0
                    })) as unknown as Array<{
                      start: number
                      end: number | null
                      prompt: string
                      line: number
                    }>)
              }
              generating={screenplayBusy}
              error={screenplayError}
              onRebreak={onBreakdownScreenplay}
              onApprove={(segs) =>
                onApproveScreenplay(
                  segs.map((s) => ({ start: s.start, end: s.end, prompt: s.prompt }))
                )
              }
              onCancel={() => {
                setScreenplayProposed(null)
                setScreenplayError(null)
              }}
            />
          )}

          {mode === 'llm' && scriptMode && prompt.trim() !== '' && (() => {
            const parsed = parseScript(prompt)
            if (parsed.errors.length > 0) {
              return (
                <div className="rounded-md border border-red-500/40 bg-red-500/10 px-2 py-1 text-[11px] text-red-200">
                  <p className="font-semibold">Script errors</p>
                  <ul className="mt-0.5 list-disc pl-4">
                    {parsed.errors.slice(0, 4).map((e, i) => (
                      <li key={i}>line {e.line}: {e.message}</li>
                    ))}
                    {parsed.errors.length > 4 && (
                      <li>+ {parsed.errors.length - 4} more</li>
                    )}
                  </ul>
                </div>
              )
            }
            const seg = parsed.segments
            return (
              <p className="text-[11px] text-neutral-500">
                {seg.length} segment{seg.length === 1 ? '' : 's'} parsed
                {seg.length > 0 && (
                  <span>
                    {' '}— spans {seg[0].start.toFixed(1)}s to{' '}
                    {seg[seg.length - 1].end !== null
                      ? `${seg[seg.length - 1].end?.toFixed(1)}s`
                      : 'end of video'}
                  </span>
                )}
              </p>
            )
          })()}

          {pendingEnhanced && (
            <div
              ref={reviewRef}
              className="flex flex-col gap-2 rounded-md border border-emerald-500/60 bg-emerald-500/10 p-3"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-emerald-300">
                  Enhanced prompt
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={onAcceptEnhanced}
                    className="rounded-md bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500"
                  >
                    Accept
                  </button>
                  <button
                    type="button"
                    onClick={onRejectEnhanced}
                    className="rounded-md border border-neutral-700 px-3 py-1 text-xs font-medium text-neutral-200 hover:bg-neutral-800"
                  >
                    Reject
                  </button>
                </div>
              </div>
              <pre className="whitespace-pre-wrap break-words font-mono text-sm text-emerald-50">
                {pendingEnhanced}
              </pre>
            </div>
          )}

          {mode === 'llm' && (
            <div className="flex flex-col gap-2 border-t border-neutral-800 pt-3">
              <div className="grid grid-cols-[6rem_1fr] items-center gap-2">
                <label className="text-xs text-neutral-400">Provider</label>
                <select
                  value={provider}
                  onChange={(e) => onProviderChange(e.target.value as LLMProvider)}
                  disabled={isRunning}
                  className="rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm focus:border-neutral-500 focus:outline-none disabled:opacity-50"
                >
                  {(Object.keys(PROVIDER_LABEL) as LLMProvider[]).map((p) => (
                    <option key={p} value={p}>
                      {PROVIDER_LABEL[p]}
                    </option>
                  ))}
                </select>

                <label className="text-xs text-neutral-400">Model</label>
                {provider === 'ollama' ? (
                  <div className="flex gap-2">
                    <select
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      disabled={isRunning || ollamaLoading || !ollamaModels?.length}
                      className="flex-1 rounded border border-neutral-800 bg-neutral-950 px-2 py-1 font-mono text-sm focus:border-neutral-500 focus:outline-none disabled:opacity-50"
                    >
                      {ollamaLoading && <option>Loading…</option>}
                      {!ollamaLoading && ollamaModels?.length === 0 && (
                        <option>No models installed</option>
                      )}
                      {ollamaModels?.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={refreshOllamaModels}
                      disabled={isRunning || ollamaLoading}
                      className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-300 hover:bg-neutral-800 disabled:opacity-50"
                    >
                      ↻
                    </button>
                  </div>
                ) : (
                  <input
                    type="text"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    disabled={isRunning}
                    placeholder={PROVIDER_DEFAULT_MODEL[provider]}
                    className="rounded border border-neutral-800 bg-neutral-950 px-2 py-1 font-mono text-sm focus:border-neutral-500 focus:outline-none disabled:opacity-50"
                  />
                )}

              </div>
              {provider === 'ollama' && ollamaError && (
                <p className="text-xs text-red-400">{ollamaError}</p>
              )}
              {provider === 'ollama' && !ollamaError && ollamaModels?.length === 0 && (
                <p className="text-xs text-neutral-500">
                  Reached Ollama, but no models installed. Run{' '}
                  <code className="font-mono">ollama pull llama3.1</code> in a terminal.
                </p>
              )}
              {provider === 'ollama' && !ollamaError && (ollamaModels?.length ?? 0) > 0 && (
                <p className="text-xs text-neutral-500">
                  Local Ollama, no API key needed. {ollamaModels?.length} model
                  {ollamaModels?.length === 1 ? '' : 's'} available.
                </p>
              )}
              {provider !== 'ollama' && (
                <p className="text-xs text-neutral-500">
                  Set the matching <code className="font-mono">{providerKeyEnv(provider)}</code> env
                  var in the shell that launched Electron.
                </p>
              )}
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onRender}
              disabled={disabledSubmit || screenplayBusy}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-neutral-700"
            >
              {isRunning
                ? 'Rendering…'
                : promptFormat === 'screenplay' && mode === 'llm'
                  ? screenplayBusy
                    ? 'Breaking down…'
                    : 'Break down'
                  : 'Render'}
            </button>
            <div
              className="inline-flex overflow-hidden rounded-md border border-neutral-700 text-xs"
              title="Draft: low-resolution, single-sample — fast iteration. Hi-fi: full quality."
            >
              {(['draft', 'hifi'] as const).map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setQuality(q)}
                  disabled={isRunning}
                  className={`px-3 py-1.5 transition-colors ${
                    quality === q
                      ? 'bg-blue-500/30 text-blue-100'
                      : 'bg-neutral-950 text-neutral-400 hover:bg-neutral-800'
                  }`}
                >
                  {q === 'draft' ? 'Draft' : 'Hi-fi'}
                </button>
              ))}
            </div>
            <label
              className="inline-flex items-center gap-1.5 text-xs text-neutral-300"
              title="Synthesize voice audio for every talk action via Microsoft Edge TTS (no API key needed) and mux into the MP4."
            >
              <input
                type="checkbox"
                checked={generateAudio}
                onChange={(e) => setGenerateAudio(e.target.checked)}
                disabled={isRunning}
                className="h-3 w-3 accent-blue-500"
              />
              Voice
            </label>
            <label
              className="inline-flex items-center gap-1.5 text-xs text-neutral-300"
              title="When on, walk_to ties stride count to actual travel distance — feet plant where they land instead of sliding. Turn off for a pre-Step-52 A/B comparison."
            >
              <input
                type="checkbox"
                checked={physicsPostPass}
                onChange={(e) => setPhysicsPostPass(e.target.checked)}
                disabled={isRunning}
                className="h-3 w-3 accent-blue-500"
              />
              Foot-lock
            </label>
          </div>
        </section>
        </div>

        <section className="flex flex-col gap-2">
          {state.status === 'idle' && (
            <p className="text-sm text-neutral-500">No render yet.</p>
          )}
          {state.status === 'running' && (
            <div className="flex flex-col gap-1">
              <div className="flex items-baseline gap-3">
                <p className="text-sm text-neutral-400">
                  Rendering — this can take a minute or two on the first call (Blender startup).
                </p>
                <span className="font-mono text-sm tabular-nums text-neutral-300">
                  {formatElapsed(liveElapsedSec)}
                </span>
              </div>
              {currentStep && (
                <p className="font-mono text-xs text-neutral-500">
                  <span className="text-neutral-300">{STEP_LABEL[currentStep.step] ?? currentStep.step}</span>
                  {currentStep.detail && (
                    <span className="text-neutral-500"> · {currentStep.detail}</span>
                  )}
                </p>
              )}
            </div>
          )}
          {state.status === 'error' && (
            <p className="text-sm text-red-400">
              <span className="font-semibold">Render failed:</span> {state.message}{' '}
              <span className="text-neutral-500">
                (after {formatElapsed(Math.floor(state.elapsedMs / 1000))})
              </span>
            </p>
          )}
          {state.status === 'success' && (
            <>
              {/* Video sits at the top of the right column so its top edge
                  aligns with the controls panel's top edge in the grid. The
                  Save Video / "rendered in Xs" status sits beneath it. */}
              <video
                ref={videoRef}
                key={state.videoUrl}
                src={state.videoUrl}
                controls
                autoPlay
                loop
                className="w-full rounded-md border border-neutral-800"
              />
              <div className="flex items-center justify-between">
                <p className="text-sm text-neutral-400">
                  Rendered {state.durationSec.toFixed(1)}s
                  <span className="ml-2 text-neutral-500">
                    in {formatElapsed(Math.floor(state.elapsedMs / 1000))}
                  </span>
                </p>
                <button
                  type="button"
                  onClick={() => onSave(state.renderId)}
                  className="rounded-md border border-neutral-700 px-3 py-1 text-xs font-medium text-neutral-200 hover:bg-neutral-800"
                >
                  Save Video…
                </button>
              </div>
              {saveNote && (
                <p className="text-xs text-neutral-500 break-all">{saveNote}</p>
              )}
              <TimelinePanel
                timeline={state.timeline}
                videoRef={videoRef}
                durationSec={state.durationSec}
                onSeek={onSeek}
                onEditAction={onEditAction}
                onAddAction={onAddAction}
                onAddCharacter={openAddCharacter}
                onRetimeAction={onRetimeAction}
                onPaletteDrop={onPaletteDrop}
                selectedRange={selectedRange}
                onRangeSelect={setSelectedRange}
                frozenActionIds={frozenActionIds}
                onToggleFreeze={onToggleFreeze}
                pendingEdit={pendingEditForPanel}
              />
              <RangeEditPanel
                range={selectedRange}
                generating={rangeEditing}
                error={rangeEditError}
                onCancel={onCancelRangeEdit}
                onSubmit={onSubmitRangeEdit}
                onExport={() => onExportDocumentation(selectedRange)}
              />
            </>
          )}
        </section>
        </div>
      </div>

      <ActionEditor
        open={editor !== null}
        original={editor?.original ?? null}
        laneId={editor?.laneId ?? ''}
        startSec={editor?.startSec ?? 0}
        endSec={editor?.endSec ?? null}
        pendingAction={pendingAction}
        generating={generatingAction}
        error={actionError}
        initialPrompt={editor?.initialPrompt}
        onGenerate={onGenerateAction}
        onAccept={onAcceptAction}
        onReject={onRejectAction}
        onClose={closeEditor}
        onEnhance={async (text) => {
          const response = await window.veraframe.enhancePrompt({
            prompt: text,
            provider,
            model: model.trim() || undefined,
            ollamaHost: undefined
          })
          if (response.ok) return response.prompt
          throw new Error(response.error)
        }}
      />

      <AssetUploadModal
        open={uploadKind !== null}
        kind={uploadKind ?? 'scene'}
        onClose={() => setUploadKind(null)}
        onSubmitted={onUploadSubmitted}
      />

      <AddCharacterModal
        open={addCharacterOpen}
        availableCharacters={registry.characters.filter((c) => {
          // Don't offer presets that are already in the timeline. Multiple
          // characters per preset are allowed in principle, but it muddles
          // the LLM/editor; restrict here for clarity.
          if (state.status !== 'success') return true
          const tl = state.timeline as unknown as MutableTimeline
          return !tl.characters.some((existing) => existing.preset === c.id)
        })}
        scene={
          state.status === 'success'
            ? registry.scenes.find((s) => s.id === (state.timeline as unknown as MutableTimeline).scene) ?? null
            : null
        }
        existingHandles={
          state.status === 'success'
            ? (state.timeline as unknown as MutableTimeline).characters.map((c) => c.id)
            : []
        }
        onClose={() => setAddCharacterOpen(false)}
        onConfirm={onConfirmAddCharacter}
      />

      {editSceneId && (() => {
        const sc = registry.scenes.find((s) => s.id === editSceneId)
        if (!sc) return null
        return (
          <EditSceneModal
            open
            sceneId={sc.id}
            initialDisplayName={sc.displayName}
            initialSpawnPoints={sc.spawnPoints}
            initialCameraPresets={sc.cameraPresets}
            onClose={() => setEditSceneId(null)}
            onSaved={async () => {
              setEditSceneId(null)
              await refreshRegistry()
            }}
          />
        )
      })()}

      {editCharacterId && (() => {
        const ch = registry.characters.find((c) => c.id === editCharacterId)
        if (!ch) return null
        // Heuristic file paths under the user-assets dir. Surfacing them is
        // purely informational — the IPC handler resolves the actual paths
        // from the registry server-side.
        return (
          <EditCharacterModal
            open
            characterId={ch.id}
            initialDisplayName={ch.displayName}
            initialDescription={ch.description}
            initialDefaultEmotion={ch.defaultEmotion}
            initialVoice={ch.voice}
            meshPath="character.fbx"
            idlePath="idle.fbx"
            walkPath="walk_in_place.fbx"
            onClose={() => setEditCharacterId(null)}
            onSaved={async () => {
              setEditCharacterId(null)
              await refreshRegistry()
            }}
          />
        )
      })()}
      <VerbPalette open={verbPaletteOpen} onClose={() => setVerbPaletteOpen(false)} />
      <CharacterLibraryModal
        open={libraryOpen}
        characters={registry.characters}
        motions={registry.motions}
        selectedCharacterIds={selectedCharacterIds}
        onToggleCharacter={onToggleCharacter}
        onEditCharacter={(id) => {
          setLibraryOpen(false)
          setEditCharacterId(id)
        }}
        onRemoveCharacter={onRemoveCharacter}
        onAddCharacter={() => {
          setLibraryOpen(false)
          setUploadKind('character')
        }}
        onAddMotion={() => {
          setLibraryOpen(false)
          setAddMotionOpen(true)
        }}
        onRemoveMotion={onRemoveMotion}
        onClose={() => setLibraryOpen(false)}
      />
      <AddMotionClipModal
        open={addMotionOpen}
        onClose={() => setAddMotionOpen(false)}
        onSaved={async () => {
          setAddMotionOpen(false)
          await refreshRegistry()
        }}
      />
    </div>
  )
}

const STEP_LABEL: Record<string, string> = {
  llm: 'Calling LLM',
  build_mock_timeline: 'Building mock timeline',
  reset: 'Resetting Blender scene',
  load_scene: 'Loading scene',
  load_character: 'Loading character',
  execute_timeline: 'Executing actions',
  render: 'Rendering frames'
}

function formatElapsed(totalSec: number): string {
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return m > 0 ? `${m}m ${s.toString().padStart(2, '0')}s` : `${s}s`
}

function providerKeyEnv(provider: LLMProvider): string {
  switch (provider) {
    case 'openai':
      return 'OPENAI_API_KEY'
    case 'anthropic':
      return 'ANTHROPIC_API_KEY'
    case 'gemini':
      return 'GEMINI_API_KEY'
    case 'ollama':
      return ''
  }
}

export default App
