"""Set-lighting action — ramp every scene light's energy and color to a named preset.

The first time a light is touched, its rest-state energy and color are captured
as custom properties (`veraframe_baseline_*`). All subsequent presets are computed
as `baseline × multiplier` so `default` reliably returns to the captured rest state,
not whatever the previous preset left behind.

Energy and color are keyframed directly on the light *data* block — lights have
their own animation slot, distinct from object-level transforms, so this doesn't
interact with the armature NLA pipeline.
"""

try:
    import bpy
except ImportError:
    bpy = None


class SetLightingActionError(RuntimeError):
    """Raised when the set_lighting action can't be applied."""


_PRESETS: dict[str, dict] = {
    "default": {"energy_mult": 1.0, "color_tint": (1.0, 1.0, 1.0)},
    "dim": {"energy_mult": 0.2, "color_tint": (1.0, 1.0, 1.0)},
    "emergency": {"energy_mult": 0.5, "color_tint": (1.0, 0.2, 0.2)},
    "bright": {"energy_mult": 2.0, "color_tint": (1.0, 1.0, 1.0)},
}


def execute(
    scene,
    preset: str,
    start_frame: int,
    end_frame: int,
    action_id: str = "set_lighting",
) -> dict:
    if bpy is None:
        raise SetLightingActionError("bpy unavailable")

    settings = _PRESETS.get(preset)
    if settings is None:
        raise SetLightingActionError(
            f"unknown preset '{preset}'. Known: {sorted(_PRESETS)}"
        )

    s = int(start_frame)
    e = int(end_frame)
    if e < s:
        raise SetLightingActionError("end_frame must be >= start_frame")

    affected: list[str] = []
    for obj in scene.objects:
        if obj.type != "LIGHT":
            continue
        light = obj.data

        if "veraframe_baseline_energy" not in light:
            light["veraframe_baseline_energy"] = float(light.energy)
            light["veraframe_baseline_color"] = [float(c) for c in light.color]

        baseline_energy = float(light["veraframe_baseline_energy"])
        baseline_color = [float(c) for c in light["veraframe_baseline_color"]]

        current_energy = float(light.energy)
        current_color = tuple(float(c) for c in light.color)

        target_energy = baseline_energy * settings["energy_mult"]
        target_color = tuple(
            baseline_color[i] * settings["color_tint"][i] for i in range(3)
        )

        light.energy = current_energy
        light.keyframe_insert(data_path="energy", frame=s)
        for idx in range(3):
            light.color[idx] = current_color[idx]
            light.keyframe_insert(data_path="color", index=idx, frame=s)

        light.energy = target_energy
        light.keyframe_insert(data_path="energy", frame=e)
        for idx in range(3):
            light.color[idx] = target_color[idx]
            light.keyframe_insert(data_path="color", index=idx, frame=e)

        affected.append(obj.name)

    return {
        "preset": preset,
        "frame_start": s,
        "frame_end": e,
        "affected_lights": affected,
    }


def known_presets() -> list[str]:
    return sorted(_PRESETS)


__all__ = ["SetLightingActionError", "execute", "known_presets"]
