"""Asset registry — describes what scenes, characters, animations, and actions
are available to the planner. The registry is injected into the LLM system
prompt so the model picks from a known menu instead of inventing IDs.
"""

from pathlib import Path

from pydantic import BaseModel, Field

from planner.schema import Emotion, IdleStyle, WalkStyle

# ---------------------------------------------------------------------------
# Manifest models — what each asset's manifest file on disk looks like.
# ---------------------------------------------------------------------------


class SceneManifest(BaseModel):
    id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    blend_file: str = Field(min_length=1)
    spawn_points: list[str] = Field(min_length=1)
    camera_presets: list[str] = Field(min_length=1)
    lighting_presets: list[str] = Field(default_factory=list)


class CharacterManifest(BaseModel):
    id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    mesh_file: str = Field(min_length=1)
    rig_type: str = "mixamo"
    face_blendshapes: list[str] = Field(default_factory=list)


class AnimationManifest(BaseModel):
    id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    fbx_file: str = Field(min_length=1)
    loop: bool = False
    applies_to_rig: str = "mixamo"


# ---------------------------------------------------------------------------
# Loaded specs — manifest + resolved absolute paths.
# ---------------------------------------------------------------------------


class SceneSpec(BaseModel):
    id: str
    display_name: str
    description: str
    blend_path: Path
    spawn_points: tuple[str, ...]
    camera_presets: tuple[str, ...]
    lighting_presets: tuple[str, ...]


class CharacterSpec(BaseModel):
    id: str
    display_name: str
    description: str
    mesh_path: Path
    rig_type: str
    face_blendshapes: tuple[str, ...]


class AnimationSpec(BaseModel):
    id: str
    display_name: str
    fbx_path: Path
    loop: bool
    applies_to_rig: str


# ---------------------------------------------------------------------------
# Action vocabulary — static, mirrors planner/schema.py.
# ---------------------------------------------------------------------------


class ParamSpec(BaseModel):
    name: str
    description: str
    required: bool = True
    enum: tuple[str, ...] | None = None


class ActionSpec(BaseModel):
    name: str
    description: str
    params: tuple[ParamSpec, ...]


_TIMING_PARAMS = (
    ParamSpec(name="start", description="Action start time in seconds (>= 0)."),
    ParamSpec(name="end", description="Action end time in seconds (must be > start)."),
)

_EMOTION_VALUES = tuple(e.value for e in Emotion)
_WALK_STYLE_VALUES = tuple(s.value for s in WalkStyle)
_IDLE_STYLE_VALUES = tuple(s.value for s in IdleStyle)

DEFAULT_ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="walk_to",
        description="Walk a character to a named spawn point in the active scene.",
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            ParamSpec(name="target", description="Name of a spawn point in the active scene."),
            ParamSpec(
                name="emotion",
                description="Emotional flavour applied during the walk.",
                required=False,
                enum=_EMOTION_VALUES,
            ),
            ParamSpec(
                name="style",
                description=(
                    "Gait flavour. Adjusts the walk-cycle playback speed: 'run' and "
                    "'jog' play faster, 'sneak' and 'limp' slower, 'march' is "
                    "stiffer-paced. Defaults to 'walk'."
                ),
                required=False,
                enum=_WALK_STYLE_VALUES,
            ),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="idle",
        description="Hold a character in an idle pose.",
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            ParamSpec(
                name="emotion",
                description="Emotional flavour applied during the idle.",
                required=False,
                enum=_EMOTION_VALUES,
            ),
            ParamSpec(
                name="style",
                description=(
                    "Postural flavour for the idle (e.g. 'tired' slumps, 'alert' "
                    "stands up straighter). Currently informational; the executor "
                    "uses the base idle clip regardless."
                ),
                required=False,
                enum=_IDLE_STYLE_VALUES,
            ),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="turn_to",
        description="Turn a character's body to face a target.",
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            ParamSpec(name="target", description="Spawn point or other character ID to face."),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="look_at",
        description="Make a character's head track a target.",
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            ParamSpec(name="target", description="Spawn point or other character ID to look at."),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="point_at",
        description="Make a character point at a target with their hand.",
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            ParamSpec(name="target", description="Spawn point or other character ID to point at."),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="sit",
        description="Make a character sit down.",
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="stand",
        description="Make a character stand up.",
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="smile",
        description="Apply a smile facial expression.",
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="frown",
        description="Apply a frown facial expression.",
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="blink",
        description="Play a single blink.",
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="talk",
        description=(
            "Animate a character speaking the given text. Mouth shapes are driven "
            "by viseme distribution; optional emotion blends on top."
        ),
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            ParamSpec(name="text", description="Spoken dialogue text."),
            ParamSpec(
                name="emotion",
                description="Emotional flavour applied while speaking.",
                required=False,
                enum=_EMOTION_VALUES,
            ),
            ParamSpec(
                name="look_at",
                description="Optional spawn point or character ID to look at while speaking.",
                required=False,
            ),
            ParamSpec(
                name="gesture",
                description="Optional short gesture name (e.g. 'small_step_back').",
                required=False,
            ),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="nod",
        description=(
            "Yes-nod: a short vertical head-bone pitch oscillation. Good for "
            "agreement, acknowledgement, or thanks. ~0.5-1.5s typical."
        ),
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="shake_head",
        description=(
            "No-shake: a short horizontal head-bone yaw oscillation. Disagreement, "
            "refusal, disbelief. ~0.5-1.5s typical."
        ),
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="wave",
        description=(
            "A friendly wave with the right arm. The upper arm raises and the "
            "forearm oscillates. ~1.5-3s typical. Pair with look_at(target) for "
            "directional waves."
        ),
        params=(
            ParamSpec(name="character", description="ID of a loaded character."),
            ParamSpec(
                name="target",
                description="Spawn point or character ID being waved at (optional).",
                required=False,
            ),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="camera_cut",
        description="Switch the active camera to a named preset.",
        params=(
            ParamSpec(name="camera", description="Name of a camera preset in the active scene."),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="camera_dolly",
        description="Interpolate the camera between two named presets over the action duration.",
        params=(
            ParamSpec(name="from_camera", description="Name of the starting camera preset."),
            ParamSpec(name="to_camera", description="Name of the ending camera preset."),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="track_subject",
        description=(
            "Active camera follows a character. The camera is offset behind-and-"
            "above the character and tracks their motion through the action "
            "window. Use this when a character is walking and you want the "
            "camera to follow rather than cutting between fixed presets."
        ),
        params=(
            ParamSpec(
                name="character",
                description="ID of the character handle to follow.",
            ),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="two_shot",
        description=(
            "Active camera repositions to frame TWO characters together (classic "
            "dialogue framing). Camera sits perpendicular to the line between "
            "them, distance scales with their separation so both fit in frame. "
            "Static for the action's duration."
        ),
        params=(
            ParamSpec(name="a", description="First character handle."),
            ParamSpec(name="b", description="Second character handle."),
            *_TIMING_PARAMS,
        ),
    ),
    ActionSpec(
        name="set_lighting",
        description="Switch the scene's lighting to a named preset.",
        params=(
            ParamSpec(name="preset", description="Name of a lighting preset in the active scene."),
            *_TIMING_PARAMS,
        ),
    ),
)


# ---------------------------------------------------------------------------
# Registry container + loader.
# ---------------------------------------------------------------------------


class Registry(BaseModel):
    """In-memory view of everything the planner can reference."""

    scenes: dict[str, SceneSpec]
    characters: dict[str, CharacterSpec]
    animations: dict[str, AnimationSpec]
    actions: tuple[ActionSpec, ...] = DEFAULT_ACTIONS

    def filtered(
        self,
        scene_ids: set[str] | None = None,
        character_ids: set[str] | None = None,
    ) -> "Registry":
        """Return a copy that only exposes the requested scenes / characters.

        Used to tighten the LLM's view to the user's UI selection so the
        system prompt's "Available …" sections only list what the user
        picked. `None` (default) means "keep everything for that group". An
        empty set is treated like `None` (no constraint) for symmetry with
        the UI default where "no selection" means "anything goes".
        """
        scenes = self.scenes
        if scene_ids:
            scenes = {sid: spec for sid, spec in self.scenes.items() if sid in scene_ids}
        characters = self.characters
        if character_ids:
            characters = {
                cid: spec for cid, spec in self.characters.items() if cid in character_ids
            }
        return Registry(
            scenes=scenes,
            characters=characters,
            animations=self.animations,
            actions=self.actions,
        )

    @classmethod
    def load(cls, assets_dir: Path) -> "Registry":
        """Scan an assets directory and build a Registry from its manifests.

        Expected layout::

            <assets_dir>/scenes/<scene_id>/scene.json
            <assets_dir>/characters/<character_id>/character.json
            <assets_dir>/animations/<animation_id>/animation.json
        """
        scenes = _load_scenes(assets_dir / "scenes")
        characters = _load_characters(assets_dir / "characters")
        animations = _load_animations(assets_dir / "animations")
        return cls(scenes=scenes, characters=characters, animations=animations)

    def to_system_prompt_section(self) -> str:
        """Markdown-formatted description for injection into the LLM system prompt."""
        return "\n\n".join(
            [
                self._scenes_section(),
                self._characters_section(),
                self._actions_section(),
            ]
        )

    # -- prompt section builders -------------------------------------------

    def _scenes_section(self) -> str:
        if not self.scenes:
            return "# Available scenes\n\n(none)"
        lines = ["# Available scenes"]
        for scene in self.scenes.values():
            lines.append("")
            lines.append(f"## `{scene.id}` — {scene.display_name}")
            lines.append(scene.description)
            lines.append(f"- Spawn points: {', '.join(scene.spawn_points)}")
            lines.append(f"- Camera presets: {', '.join(scene.camera_presets)}")
            if scene.lighting_presets:
                lines.append(f"- Lighting presets: {', '.join(scene.lighting_presets)}")
        return "\n".join(lines)

    def _characters_section(self) -> str:
        if not self.characters:
            return "# Available characters\n\n(none)"
        lines = ["# Available characters"]
        for character in self.characters.values():
            lines.append("")
            lines.append(f"## `{character.id}` — {character.display_name}")
            lines.append(character.description)
        return "\n".join(lines)

    def _actions_section(self) -> str:
        lines = ["# Available actions"]
        for action in self.actions:
            lines.append("")
            lines.append(f"## `{action.name}`")
            lines.append(action.description)
            for param in action.params:
                req = "required" if param.required else "optional"
                enum_part = f" — one of: {', '.join(param.enum)}" if param.enum else ""
                lines.append(f"- `{param.name}` ({req}{enum_part}): {param.description}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal loaders.
# ---------------------------------------------------------------------------


def _load_scenes(scenes_dir: Path) -> dict[str, SceneSpec]:
    if not scenes_dir.is_dir():
        return {}
    out: dict[str, SceneSpec] = {}
    for manifest_path in sorted(scenes_dir.glob("*/scene.json")):
        manifest = SceneManifest.model_validate_json(manifest_path.read_text())
        out[manifest.id] = SceneSpec(
            id=manifest.id,
            display_name=manifest.display_name,
            description=manifest.description,
            blend_path=manifest_path.parent / manifest.blend_file,
            spawn_points=tuple(manifest.spawn_points),
            camera_presets=tuple(manifest.camera_presets),
            lighting_presets=tuple(manifest.lighting_presets),
        )
    return out


def _load_characters(characters_dir: Path) -> dict[str, CharacterSpec]:
    if not characters_dir.is_dir():
        return {}
    out: dict[str, CharacterSpec] = {}
    for manifest_path in sorted(characters_dir.glob("*/character.json")):
        manifest = CharacterManifest.model_validate_json(manifest_path.read_text())
        out[manifest.id] = CharacterSpec(
            id=manifest.id,
            display_name=manifest.display_name,
            description=manifest.description,
            mesh_path=manifest_path.parent / manifest.mesh_file,
            rig_type=manifest.rig_type,
            face_blendshapes=tuple(manifest.face_blendshapes),
        )
    return out


def _load_animations(animations_dir: Path) -> dict[str, AnimationSpec]:
    if not animations_dir.is_dir():
        return {}
    out: dict[str, AnimationSpec] = {}
    for manifest_path in sorted(animations_dir.glob("*/animation.json")):
        manifest = AnimationManifest.model_validate_json(manifest_path.read_text())
        out[manifest.id] = AnimationSpec(
            id=manifest.id,
            display_name=manifest.display_name,
            fbx_path=manifest_path.parent / manifest.fbx_file,
            loop=manifest.loop,
            applies_to_rig=manifest.applies_to_rig,
        )
    return out


__all__ = [
    "ActionSpec",
    "AnimationManifest",
    "AnimationSpec",
    "CharacterManifest",
    "CharacterSpec",
    "DEFAULT_ACTIONS",
    "ParamSpec",
    "Registry",
    "SceneManifest",
    "SceneSpec",
]
