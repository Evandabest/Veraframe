"""Render — drive Blender's render engine and stitch the result into an MP4.

Called by the daemon as the `render` RPC. Configures EEVEE Next at 720p / 24
fps / low samples (matching the locked MVP render decision) and renders the
active scene over the given frame range.

Blender's macOS distribution doesn't ship with FFmpeg support, so we render
to a PNG sequence and stitch it into an MP4 with the system `ffmpeg`
subprocess. Set `FFMPEG_PATH` to override the executable location.

The active camera is set to the first `CAMERA`-type object in the scene if
none is currently set. Camera-cut / dolly actions (Step 15) override this at
execute time.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    import bpy
except ImportError:
    bpy = None


_PREFERRED_ENGINES = ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE")


class RenderError(RuntimeError):
    """Raised when the render can't be set up or completes unsuccessfully."""


# Render-quality presets. Draft trades fidelity for speed (down-resolution + 1
# sample) so edit-iterate loops feel responsive; hifi matches the original
# defaults used through the MVP. Callers can still pass explicit
# resolution_x/y/samples to override.
_QUALITY_PRESETS: dict[str, dict[str, int]] = {
    "draft": {"resolution_x": 854, "resolution_y": 480, "samples": 1},
    "hifi": {"resolution_x": 1280, "resolution_y": 720, "samples": 16},
}


def render(
    start_frame: int,
    end_frame: int,
    output_path: str,
    *,
    resolution_x: int | None = None,
    resolution_y: int | None = None,
    fps: int = 24,
    samples: int | None = None,
    quality: str = "hifi",
    keep_frames: bool = False,
) -> dict:
    """Render the active scene to an MP4 at `output_path` for the given frames.

    Returns `{video_path, frame_start, frame_end, frame_count, duration_s,
    engine, camera, frames_dir}` (the last is None if frames were cleaned up).
    """
    if bpy is None:
        raise RenderError("bpy unavailable")

    scene = bpy.context.scene
    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    preset = _QUALITY_PRESETS.get(quality, _QUALITY_PRESETS["hifi"])
    rx = resolution_x if resolution_x is not None else preset["resolution_x"]
    ry = resolution_y if resolution_y is not None else preset["resolution_y"]
    sa = samples if samples is not None else preset["samples"]

    camera = _ensure_camera(scene)
    engine = _select_engine(scene)
    _configure_render(scene, rx, ry, fps, sa)

    frames_dir = Path(tempfile.mkdtemp(prefix="veraframe_render_"))
    # Blender appends frame numbers to the filepath. Trailing `/` makes the
    # prefix interpreted as a directory + empty stem, so files become
    # `<dir>/0001.png` etc.
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.filepath = str(frames_dir) + "/"
    scene.frame_start = int(start_frame)
    scene.frame_end = int(end_frame)

    # Manual per-frame render. `bpy.ops.render.render(animation=True)` does
    # not reliably re-evaluate timeline markers between frames in
    # --background mode. We iterate ourselves and explicitly resolve the
    # active camera from markers (`_camera_at_frame`) and force
    # `scene.camera` before each `write_still` so camera_cut actually
    # switches mid-animation.
    pad = 4
    for frame in range(int(start_frame), int(end_frame) + 1):
        scene.frame_set(frame)
        scene.camera = _camera_at_frame(scene, frame, default=camera)
        scene.render.filepath = str(frames_dir / f"{frame:0{pad}d}")
        bpy.ops.render.render(write_still=True)

    png_files = sorted(frames_dir.glob("*.png"))
    if not png_files:
        raise RenderError(f"Blender produced no frames in {frames_dir}")

    _encode_mp4(png_files[0], out, fps, frame_count=len(png_files))

    if not out.exists():
        raise RenderError(f"ffmpeg finished but no MP4 at {out}")

    if not keep_frames:
        shutil.rmtree(frames_dir, ignore_errors=True)
        kept_dir = None
    else:
        kept_dir = str(frames_dir)

    frame_count = int(end_frame) - int(start_frame) + 1
    return {
        "video_path": str(out),
        "frame_start": int(start_frame),
        "frame_end": int(end_frame),
        "frame_count": frame_count,
        "duration_s": frame_count / fps,
        "engine": engine,
        "camera": camera.name,
        "frames_dir": kept_dir,
    }


# ---------------------------------------------------------------------------


def _camera_at_frame(scene, frame: int, *, default):
    """Return the camera bound to the closest marker at or before `frame`,
    or `default` if no such marker exists."""
    best_camera = default
    best_frame = -(1 << 31)
    for marker in scene.timeline_markers:
        if marker.camera is None:
            continue
        if best_frame < marker.frame <= frame:
            best_frame = marker.frame
            best_camera = marker.camera
    return best_camera


def _ensure_camera(scene):
    camera = scene.camera
    if camera is not None:
        return camera
    cameras = [obj for obj in scene.objects if obj.type == "CAMERA"]
    if not cameras:
        raise RenderError(f"no camera in scene '{scene.name}'; cannot render without one")
    scene.camera = cameras[0]
    return cameras[0]


def _select_engine(scene) -> str:
    available = {
        e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    }
    engine = next((e for e in _PREFERRED_ENGINES if e in available), None)
    if engine is None:
        raise RenderError(
            f"no supported EEVEE engine available; tried {_PREFERRED_ENGINES}, "
            f"found {sorted(available)}"
        )
    scene.render.engine = engine
    return engine


def _configure_render(scene, resolution_x: int, resolution_y: int, fps: int, samples: int) -> None:
    scene.render.resolution_x = resolution_x
    scene.render.resolution_y = resolution_y
    scene.render.resolution_percentage = 100
    scene.render.fps = fps
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = samples


def _find_ffmpeg() -> str:
    env_path = os.environ.get("FFMPEG_PATH", "").strip()
    if env_path:
        if not Path(env_path).is_file():
            raise RenderError(f"FFMPEG_PATH points to a nonexistent file: {env_path}")
        return env_path
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RenderError("ffmpeg not found. Install via `brew install ffmpeg` or set FFMPEG_PATH.")


def _encode_mp4(first_frame: Path, out: Path, fps: int, frame_count: int) -> None:
    """Stitch the PNG sequence in `first_frame.parent` into an H.264 MP4."""
    ffmpeg = _find_ffmpeg()
    # PNG sequence: detect zero-padded numeric pattern from the first file.
    stem = first_frame.stem
    pad = len(stem)
    # If stem isn't purely digits, bail with a clear message.
    if not stem.isdigit():
        raise RenderError(
            f"unexpected frame filename '{first_frame.name}'; expected zero-padded digits"
        )
    pattern = str(first_frame.parent / f"%0{pad}d.png")
    start_num = int(stem)

    cmd = [
        ffmpeg,
        "-y",  # overwrite
        "-framerate",
        str(fps),
        "-start_number",
        str(start_num),
        "-i",
        pattern,
        "-frames:v",
        str(frame_count),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RenderError(f"ffmpeg failed (exit {result.returncode}):\n{result.stderr.strip()}")


__all__ = ["RenderError", "render"]
