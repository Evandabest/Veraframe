/**
 * Verb catalog for the action palette.
 *
 * Mirrors `ActionType` in `planner/schema.py`, grouped into the families the
 * user sees in the floating palette. Each verb carries a short description
 * shown on hover and a default natural-language prompt seed — when the user
 * drops a chip on a lane, that seed is auto-typed into ActionEditor so the
 * existing LLM flow can pick parameters.
 *
 * Keep this file in sync with `planner/schema.py::ActionType`. The verb
 * catalog test asserts coverage so a new action type in the schema fails
 * the suite if a chip wasn't added here.
 */

export type VerbFamily =
  | 'locomotion'
  | 'gesture'
  | 'face'
  | 'head'
  | 'pose'
  | 'speech'
  | 'camera'
  | 'stage'
  | 'motion'

export interface VerbDef {
  /** Matches `ActionType` from the schema. */
  type: string
  /** Human-friendly label for the chip. */
  label: string
  /** Short blurb shown in the chip tooltip. */
  description: string
  /** Default prompt seeded into ActionEditor when this chip is dropped. */
  promptSeed: string
  /** True for camera_cut, set_lighting, etc. — actions that target the
   *  scene lane, not a specific character. The palette routes drops on
   *  the scene lane through these verbs. */
  scene: boolean
}

export interface VerbFamilyDef {
  id: VerbFamily
  label: string
  verbs: VerbDef[]
}

export const VERB_FAMILIES: VerbFamilyDef[] = [
  {
    id: 'locomotion',
    label: 'Locomotion',
    verbs: [
      {
        type: 'walk_to',
        label: 'walk_to',
        description: 'Move the character to a named target (door, robot_station, etc.)',
        promptSeed: 'walk to ',
        scene: false
      },
      {
        type: 'idle',
        label: 'idle',
        description: 'Hold a standing idle pose for the duration of the slot',
        promptSeed: 'stay idle',
        scene: false
      },
      {
        type: 'turn_to',
        label: 'turn_to',
        description: 'Rotate to face a named target without translating',
        promptSeed: 'turn to face ',
        scene: false
      }
    ]
  },
  {
    id: 'pose',
    label: 'Pose',
    verbs: [
      {
        type: 'sit',
        label: 'sit',
        description: 'Sit down on the nearest sit-able prop',
        promptSeed: 'sit down',
        scene: false
      },
      {
        type: 'stand',
        label: 'stand',
        description: 'Return to standing from a sitting pose',
        promptSeed: 'stand up',
        scene: false
      }
    ]
  },
  {
    id: 'gesture',
    label: 'Gesture',
    verbs: [
      {
        type: 'wave',
        label: 'wave',
        description: 'One-armed wave with the right arm',
        promptSeed: 'wave',
        scene: false
      },
      {
        type: 'nod',
        label: 'nod',
        description: 'Quick head nod (yes)',
        promptSeed: 'nod',
        scene: false
      },
      {
        type: 'shake_head',
        label: 'shake_head',
        description: 'Head shake left/right (no)',
        promptSeed: 'shake head',
        scene: false
      },
      {
        type: 'point_at',
        label: 'point_at',
        description: 'Point at a named target with the right arm',
        promptSeed: 'point at ',
        scene: false
      }
    ]
  },
  {
    id: 'head',
    label: 'Head',
    verbs: [
      {
        type: 'look_at',
        label: 'look_at',
        description: 'Track a named target with the eyes/head',
        promptSeed: 'look at ',
        scene: false
      }
    ]
  },
  {
    id: 'face',
    label: 'Face',
    verbs: [
      {
        type: 'smile',
        label: 'smile',
        description: 'Brief smile face shape',
        promptSeed: 'smile',
        scene: false
      },
      {
        type: 'frown',
        label: 'frown',
        description: 'Brief frown face shape',
        promptSeed: 'frown',
        scene: false
      },
      {
        type: 'blink',
        label: 'blink',
        description: 'Single blink',
        promptSeed: 'blink',
        scene: false
      }
    ]
  },
  {
    id: 'speech',
    label: 'Speech',
    verbs: [
      {
        type: 'talk',
        label: 'talk',
        description: 'Speak a line; if audio generation is enabled the line is rendered as a voice clip',
        promptSeed: 'say "',
        scene: false
      }
    ]
  },
  {
    id: 'camera',
    label: 'Camera',
    verbs: [
      {
        type: 'camera_cut',
        label: 'camera_cut',
        description: 'Switch to a named camera preset (wide, close, etc.)',
        promptSeed: 'cut to the wide camera',
        scene: true
      },
      {
        type: 'camera_dolly',
        label: 'camera_dolly',
        description: 'Smooth dolly between two camera presets',
        promptSeed: 'dolly from the wide camera to the close camera',
        scene: true
      },
      {
        type: 'track_subject',
        label: 'track_subject',
        description: 'Follow a character behind their shoulder while they move',
        promptSeed: 'track ',
        scene: true
      },
      {
        type: 'two_shot',
        label: 'two_shot',
        description: 'Frame both characters from a side angle',
        promptSeed: 'two-shot of ',
        scene: true
      },
      {
        type: 'over_shoulder',
        label: 'over_shoulder',
        description: 'Over-the-shoulder framing from one character toward another',
        promptSeed: 'over the shoulder of ',
        scene: true
      },
      {
        type: 'orbit',
        label: 'orbit',
        description: 'Slow orbit around a character or target',
        promptSeed: 'orbit around ',
        scene: true
      }
    ]
  },
  {
    id: 'stage',
    label: 'Stage',
    verbs: [
      {
        type: 'set_lighting',
        label: 'set_lighting',
        description: 'Switch to a named lighting preset (day, night, emergency, etc.)',
        promptSeed: 'set lighting to ',
        scene: true
      }
    ]
  },
  {
    id: 'motion',
    label: 'Motion clip',
    verbs: [
      {
        type: 'play_clip',
        label: 'play_clip',
        description: 'Play a pre-baked motion clip on a character (Mixamo dance, custom kick, etc.)',
        promptSeed: 'play the ',
        scene: false
      }
    ]
  }
]

/** All action types declared in the schema, mirrored here for the
 *  coverage test. Keep in sync with `planner/schema.py::ActionType`. */
export const KNOWN_ACTION_TYPES: readonly string[] = [
  'walk_to',
  'idle',
  'turn_to',
  'look_at',
  'point_at',
  'sit',
  'stand',
  'smile',
  'frown',
  'blink',
  'talk',
  'nod',
  'shake_head',
  'wave',
  'camera_cut',
  'camera_dolly',
  'track_subject',
  'two_shot',
  'over_shoulder',
  'orbit',
  'set_lighting',
  'play_clip'
]

export function allVerbs(): VerbDef[] {
  return VERB_FAMILIES.flatMap((f) => f.verbs)
}

export function verbByType(type: string): VerbDef | undefined {
  return allVerbs().find((v) => v.type === type)
}
