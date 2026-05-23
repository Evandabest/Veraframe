"""play_clip action — drive a character with a user-supplied motion FBX.

Imports the clip's embedded Action once (cached per clip path), then places
it as an NLA strip on the target armature for the requested frame range.
Supports a `speed` multiplier (scales strip playback) and a `loop` flag
(strip extrapolation HOLD vs NOTHING for the simplest "loop fills the
remaining window" semantics).

Mirrors `idle.py` and `walk_to.py` — same cache invariants, same
slot-binding workaround for Blender 5.x's slotted actions.
"""

from pathlib import Path

try:
    import bpy
except ImportError:
    bpy = None


class PlayClipActionError(RuntimeError):
    """Raised when the clip can't be loaded or placed."""


# Cached `bpy.types.Action` per motion-clip FBX path. The first call for a
# given path imports the FBX, extracts the action, and discards the
# duplicate armature/mesh; subsequent calls reuse the cached action.
_LOADED_ACTIONS: dict[str, object] = {}


def clear_cache() -> None:
    """Drop all cached Action references — used by the daemon's reset
    handler after `bpy.data.batch_remove` wipes the scene."""
    _LOADED_ACTIONS.clear()


def execute(
    armature,
    clip_fbx_path: str,
    start_frame: int,
    end_frame: int,
    action_id: str = "play_clip",
    speed: float = 1.0,
    loop: bool = False,
) -> dict:
    """Place a play_clip NLA strip on `armature` for `[start_frame, end_frame]`."""
    if bpy is None:
        raise PlayClipActionError("bpy unavailable")

    action = _load_action(clip_fbx_path)
    if armature.animation_data is None:
        armature.animation_data_create()

    track = armature.animation_data.nla_tracks.new()
    track.name = f"veraframe_clip_{action_id}"

    strip = track.strips.new(name=action_id, start=int(start_frame), action=action)

    # Slot rebind (see idle.py for context — Blender 5.x slotted actions).
    if hasattr(action, "slots") and len(action.slots):
        strip.action_slot = action.slots[0]
        if hasattr(strip, "action_slot_handle"):
            strip.action_slot_handle = action.slots[0].handle

    strip.frame_end = int(end_frame)

    # Speed multiplier: scale > 1 plays faster, < 1 slower. The frame
    # window stays fixed; only the underlying action time is rescaled.
    if speed > 0 and speed != 1.0:
        try:
            strip.scale = 1.0 / speed
        except AttributeError:
            # Older Blender builds expose `time_scale` instead; ignore if
            # neither attr is available rather than failing the render.
            pass

    # When `loop` is True, repeat the clip if it's shorter than the window.
    # The simplest mapping: repeat ≥ ratio between window length and the
    # action's natural span. If False, hold the last frame (NOTHING means
    # blank — HOLD is what we want for a no-loop tail).
    if loop:
        natural_len = max(1.0, float(action.frame_range[1] - action.frame_range[0]))
        window_len = max(1.0, float(end_frame - start_frame))
        try:
            strip.repeat = max(1.0, window_len / natural_len * speed)
        except AttributeError:
            pass
        strip.extrapolation = "HOLD"
    else:
        strip.extrapolation = "HOLD"

    return {
        "armature": armature.name,
        "track": track.name,
        "frame_start": int(strip.frame_start),
        "frame_end": int(strip.frame_end),
        "extrapolation": strip.extrapolation,
        "action_name": action.name,
        "speed": speed,
        "loop": loop,
    }


def _load_action(fbx_path: str):
    """Import the motion-clip FBX (once) and return its embedded Action."""
    resolved = str(Path(fbx_path).expanduser().resolve())
    cached = _LOADED_ACTIONS.get(resolved)
    if cached is not None and cached.name in bpy.data.actions:
        return cached

    path = Path(resolved)
    if not path.is_file():
        raise PlayClipActionError(f"motion clip file not found: {path}")

    before_actions = set(bpy.data.actions.keys())
    before_objects = set(bpy.data.objects.keys())

    bpy.ops.import_scene.fbx(filepath=str(path))

    new_actions = sorted(set(bpy.data.actions.keys()) - before_actions)
    new_objects = set(bpy.data.objects.keys()) - before_objects

    # Discard the imported armature + mesh; we only want the Action datablock.
    for name in new_objects:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)

    if not new_actions:
        raise PlayClipActionError(f"no action found in {path}")

    action = bpy.data.actions[new_actions[0]]
    _LOADED_ACTIONS[resolved] = action
    return action


__all__ = ["PlayClipActionError", "execute"]
