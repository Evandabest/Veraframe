/**
 * Asset selection + upload UI shown at the top of the controls panel.
 *
 * Users pick one scene and any number of characters from the current
 * registry. Selection is hard-constraining: the LLM will be told to
 * use exactly these and nothing else. Info "i" icons explain the file
 * format requirements for users who want to upload their own.
 */

import { useState } from 'react'
import type {
  RegistrySummary,
  RegistrySceneSummary,
  RegistryCharacterSummary
} from '../../../preload'
import { InfoTip } from './InfoTip'

export interface AssetsPanelProps {
  registry: RegistrySummary
  selectedSceneId: string | null
  selectedCharacterIds: string[]
  onSelectScene: (id: string) => void
  onToggleCharacter: (id: string, checked: boolean) => void
  onAddScene: () => void
  onAddCharacter: () => void
  onRemoveScene: (id: string) => void
  onRemoveCharacter: (id: string) => void
  onEditCharacter: (id: string) => void
  onRefresh: () => void
  disabled?: boolean
}

export function AssetsPanel(props: AssetsPanelProps): React.JSX.Element {
  const {
    registry,
    selectedSceneId,
    selectedCharacterIds,
    onSelectScene,
    onToggleCharacter,
    onAddScene,
    onAddCharacter,
    onRemoveScene,
    onRemoveCharacter,
    onEditCharacter,
    onRefresh,
    disabled = false
  } = props

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-neutral-800 bg-neutral-900 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-neutral-200">Assets</h2>
        <button
          type="button"
          onClick={onRefresh}
          disabled={disabled}
          title="Re-scan the assets directories"
          className="rounded border border-neutral-700 px-2 py-0.5 text-[11px] text-neutral-400 hover:bg-neutral-800 disabled:opacity-50"
        >
          ↻ Refresh
        </button>
      </div>

      <SceneRow
        scenes={registry.scenes}
        selectedSceneId={selectedSceneId}
        onSelectScene={onSelectScene}
        onAddScene={onAddScene}
        onRemoveScene={onRemoveScene}
        disabled={disabled}
      />

      <CharacterRow
        characters={registry.characters}
        selectedCharacterIds={selectedCharacterIds}
        onToggleCharacter={onToggleCharacter}
        onAddCharacter={onAddCharacter}
        onRemoveCharacter={onRemoveCharacter}
        onEditCharacter={onEditCharacter}
        disabled={disabled}
      />
    </div>
  )
}

interface SceneRowProps {
  scenes: RegistrySceneSummary[]
  selectedSceneId: string | null
  onSelectScene: (id: string) => void
  onAddScene: () => void
  onRemoveScene: (id: string) => void
  disabled: boolean
}

function SceneRow({
  scenes,
  selectedSceneId,
  onSelectScene,
  onAddScene,
  onRemoveScene,
  disabled
}: SceneRowProps): React.JSX.Element {
  const selectedScene = scenes.find((s) => s.id === selectedSceneId) ?? null
  const canRemoveSelected = Boolean(selectedScene && selectedScene.userProvided)

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <label className="text-sm font-medium leading-none text-neutral-300">Scene</label>
        <InfoTip label="What a scene needs">
          <p className="font-semibold text-neutral-100">Scenes</p>
          <p className="mt-1">
            Drop a folder under{' '}
            <code className="font-mono text-neutral-300">~/Library/Application Support/Veraframe/assets/scenes/&lt;id&gt;/</code>{' '}
            (or use <strong>+ Add scene</strong>) containing:
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            <li>
              <code className="font-mono">scene.blend</code>{' '}
              <strong>or</strong> <code className="font-mono">scene.fbx</code>{' '}
              — the geometry, including Empty objects for spawn points and
              Camera objects for presets, all named exactly as listed in the
              manifest.
            </li>
            <li>
              <code className="font-mono">scene.json</code> — manifest with{' '}
              <code className="font-mono">id</code>,{' '}
              <code className="font-mono">display_name</code>,{' '}
              <code className="font-mono">blend_file</code> (the actual file
              name, with extension),{' '}
              <code className="font-mono">spawn_points</code>,{' '}
              <code className="font-mono">camera_presets</code>,{' '}
              <code className="font-mono">lighting_presets</code>.
            </li>
          </ul>
          <p className="mt-2 text-neutral-400">
            <strong>Character facing:</strong> set each Empty's rotation in
            Blender to control where the character looks when they spawn there.
            Leave the rotation at identity (0,0,0) to auto-rotate the character
            toward the active camera.
          </p>
          <p className="mt-2 text-neutral-400">
            If no scene is selected, the first available scene from the registry is used.
          </p>
        </InfoTip>
      </div>
      <div className="flex gap-2">
        <select
          value={selectedSceneId ?? ''}
          onChange={(e) => onSelectScene(e.target.value)}
          disabled={disabled || scenes.length === 0}
          className="flex-1 rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm focus:border-neutral-500 focus:outline-none disabled:opacity-50"
        >
          {scenes.length === 0 && <option value="">No scenes installed</option>}
          {scenes.map((s) => (
            <option key={s.id} value={s.id}>
              {s.displayName}
              {s.userProvided ? ' (yours)' : ''}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={onAddScene}
          disabled={disabled}
          className="rounded-md border border-emerald-500 bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-200 hover:bg-emerald-500/30 disabled:opacity-50"
        >
          + Add
        </button>
        {canRemoveSelected && selectedScene && (
          <button
            type="button"
            onClick={() => onRemoveScene(selectedScene.id)}
            disabled={disabled}
            title={`Remove ${selectedScene.displayName}`}
            className="rounded-md border border-red-500/60 bg-red-500/10 px-2 py-1 text-xs text-red-200 hover:bg-red-500/25 disabled:opacity-50"
          >
            ×
          </button>
        )}
      </div>
      {selectedScene && (
        <p className="text-[11px] text-neutral-500">
          spawns: {selectedScene.spawnPoints.join(', ') || '—'} · cameras:{' '}
          {selectedScene.cameraPresets.join(', ') || '—'}
        </p>
      )}
    </div>
  )
}

interface CharacterRowProps {
  characters: RegistryCharacterSummary[]
  selectedCharacterIds: string[]
  onToggleCharacter: (id: string, checked: boolean) => void
  onAddCharacter: () => void
  onRemoveCharacter: (id: string) => void
  onEditCharacter: (id: string) => void
  disabled: boolean
}

function CharacterRow({
  characters,
  selectedCharacterIds,
  onToggleCharacter,
  onAddCharacter,
  onRemoveCharacter,
  onEditCharacter,
  disabled
}: CharacterRowProps): React.JSX.Element {
  const selectedSet = new Set(selectedCharacterIds)

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <label className="text-sm font-medium leading-none text-neutral-300">Characters</label>
        <InfoTip label="What a character needs">
          <p className="font-semibold text-neutral-100">Characters</p>
          <p className="mt-1">
            Drop a folder under{' '}
            <code className="font-mono text-neutral-300">~/Library/Application Support/Veraframe/assets/characters/&lt;id&gt;/</code>{' '}
            (or use <strong>+ Add character</strong>) containing:
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            <li>
              <code className="font-mono">character.fbx</code> — humanoid mesh
              + skeleton.
            </li>
            <li>
              <code className="font-mono">idle.fbx</code> +{' '}
              <code className="font-mono">walk_in_place.fbx</code> — Mixamo-style
              NLA clips on the same skeleton.
            </li>
            <li>
              <code className="font-mono">character.json</code> — manifest
              with <code className="font-mono">id</code>,{' '}
              <code className="font-mono">display_name</code>,{' '}
              <code className="font-mono">mesh_file</code>,{' '}
              <code className="font-mono">rig_type</code> (defaults to{' '}
              <code className="font-mono">mixamo</code>),{' '}
              <code className="font-mono">animations</code> (paths to the FBX
              clips above).
            </li>
          </ul>
          <p className="mt-2 font-semibold text-neutral-100">Rig conventions</p>
          <ul className="mt-1 list-disc space-y-1 pl-4">
            <li>
              <strong>Body — Mixamo bone names</strong> (required).{' '}
              <code className="font-mono">mixamorig:Hips</code>,{' '}
              <code className="font-mono">mixamorig:Head</code>, etc. Drives
              <em> walk_to</em>, <em>idle</em>, <em>turn_to</em>,{' '}
              <em>look_at</em>, <em>point_at</em>, <em>sit</em>,{' '}
              <em>stand</em>. Mixamo exports already follow this naming;
              VRoid Studio characters work after running them through
              Mixamo's auto-rigger.
            </li>
            <li>
              <strong>Face — VRM-style shape keys</strong> (optional). Names
              like <code className="font-mono">Joy</code>,{' '}
              <code className="font-mono">Angry</code>,{' '}
              <code className="font-mono">Sorrow</code>,{' '}
              <code className="font-mono">Fun</code>,{' '}
              <code className="font-mono">Neutral</code>, the visemes{' '}
              <code className="font-mono">A / I / U / E / O</code>, and{' '}
              <code className="font-mono">Blink</code> /{' '}
              <code className="font-mono">Blink_L</code> /{' '}
              <code className="font-mono">Blink_R</code>. Drive{' '}
              <em>smile</em>, <em>frown</em>, <em>blink</em>, <em>talk</em>{' '}
              lip-sync. Missing them just makes those actions no-ops — the
              character will still walk and idle normally.
            </li>
          </ul>
          <p className="mt-2 font-semibold text-neutral-100">Have a VRM character?</p>
          <p className="mt-1 text-neutral-400">
            Bring the VRM into Blender, run it through{' '}
            <a
              href="https://www.mixamo.com/"
              className="text-blue-300 underline"
              target="_blank"
              rel="noreferrer"
            >
              Mixamo
            </a>
            's auto-rigger (or hand-name your bones to Mixamo's convention),
            then export to FBX with shape keys preserved. VRM's face
            blendshape names already match what the smile / frown / blink /
            talk actions expect.
          </p>
          <p className="mt-2 text-neutral-400">
            Tick characters you want available for the LLM. Uncheck all to let
            the LLM pick from the full pool. ✎ swaps individual files on a
            user-uploaded character; × removes one entirely.
          </p>
        </InfoTip>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {characters.length === 0 && (
          <p className="text-[11px] text-neutral-500">No characters installed.</p>
        )}
        {characters.map((c) => {
          const checked = selectedSet.has(c.id)
          return (
            <div
              key={c.id}
              className={`flex items-center gap-1.5 rounded border px-2 py-1 text-xs ${
                checked
                  ? 'border-blue-500 bg-blue-500/15 text-blue-100'
                  : 'border-neutral-700 bg-neutral-950 text-neutral-300'
              } ${disabled ? 'opacity-50' : ''}`}
            >
              <label
                className={`flex items-center gap-1.5 ${disabled ? '' : 'cursor-pointer'}`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => onToggleCharacter(c.id, e.target.checked)}
                  disabled={disabled}
                  className="h-3 w-3 accent-blue-500"
                />
                <span>
                  {c.displayName}
                  {c.userProvided ? ' (yours)' : ''}
                </span>
              </label>
              {c.userProvided && (
                <>
                  <button
                    type="button"
                    onClick={() => onEditCharacter(c.id)}
                    disabled={disabled}
                    title={`Edit ${c.displayName} (swap files)`}
                    className="ml-1 rounded text-neutral-400 hover:text-neutral-100 disabled:opacity-50"
                  >
                    ✎
                  </button>
                  <button
                    type="button"
                    onClick={() => onRemoveCharacter(c.id)}
                    disabled={disabled}
                    title={`Remove ${c.displayName}`}
                    className="rounded text-red-300 hover:text-red-100 disabled:opacity-50"
                  >
                    ×
                  </button>
                </>
              )}
            </div>
          )
        })}
        <button
          type="button"
          onClick={onAddCharacter}
          disabled={disabled}
          className="rounded-md border border-emerald-500 bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-200 hover:bg-emerald-500/30 disabled:opacity-50"
        >
          + Add
        </button>
      </div>
    </div>
  )
}

// Suppress unused-var warnings in build for the helper components when
// tree-shaken — they're exported only to satisfy the linter.
void useState
