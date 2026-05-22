"""Build the `classroom` demo scene from a downloaded FBX + textures.

Imports `source/Classroom.fbx`, rebinds the textures sitting in `textures/`
(the FBX references them by basename, which Blender's importer does not
always resolve), adds named spawn-point empties, a wide + close camera, a
sun + fill light, then packs all externals into the .blend so the result is
self-contained.

Run via:

    blender --background --python build.py -- --output scene.blend
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
import mathutils

HERE = Path(__file__).resolve().parent
FBX_PATH = HERE / "source" / "Classroom.fbx"
TEXTURES_DIR = HERE / "textures"


# Spawn points sized to the FBX's bounds (X: ±4, Y: ±5, Z: 0..3.4).
# Layout discovered by probe renders:
#   -Y wall = front of room (blackboard, teacher area)
#   +Y wall = back of room (door)
#   +X wall = lockers ("casiers")
#   chairs/desks run in rows in the middle
# Mixamo characters face -Y at rest, so a door→center walk reads as the
# student walking toward the camera (which sits at +Y looking -Y).
EMPTY_LOCATIONS: dict[str, tuple[float, float, float]] = {
    "door": (-2.0, 4.0, 0.0),          # back-left, near the back wall
    "center_room": (0.0, 0.0, 0.0),    # middle of the room
    "teacher_desk": (0.0, -3.5, 0.0),  # front center, in front of the blackboard
    "student_desk": (2.0, -1.0, 0.0),  # among the student chair rows
}


def _wipe() -> None:
    for collection_name in (
        "objects",
        "meshes",
        "materials",
        "armatures",
        "cameras",
        "lights",
        "images",
        "actions",
        "node_groups",
        "collections",
    ):
        collection = getattr(bpy.data, collection_name, None)
        if collection is None:
            continue
        bpy.data.batch_remove(list(collection))


def _link(obj) -> None:
    bpy.context.scene.collection.objects.link(obj)


def _import_classroom() -> None:
    if not FBX_PATH.is_file():
        raise SystemExit(f"build.py: FBX not found at {FBX_PATH}")
    bpy.ops.import_scene.fbx(filepath=str(FBX_PATH), use_image_search=True)


def _rebind_textures() -> int:
    """Point every Image datablock at the matching file in `textures/`.

    Sketchfab-style FBX exports often bake absolute Windows paths
    (`/mnt/.../maps/foo.png`); Blender stores those as the image filepath
    and can't pack/render them. We build a basename→path index of the
    textures/ folder and rebind each image whose name (or original filepath
    basename) matches an entry, stripping any `.001`-style numeric suffix.
    """
    if not TEXTURES_DIR.is_dir():
        return 0
    by_basename = {p.name: p for p in TEXTURES_DIR.iterdir() if p.is_file()}

    def _find(candidate_names: list[str]) -> Path | None:
        for cand in candidate_names:
            if cand in by_basename:
                return by_basename[cand]
        return None

    rebound = 0
    for image in bpy.data.images:
        # Names to try: image.name, basename of current filepath, name with
        # numeric suffix stripped (e.g. "foo.png.001" → "foo.png").
        from_filepath = (
            Path(image.filepath_raw).name if image.filepath_raw else ""
        )
        stripped = image.name
        # Strip a trailing ".NNN" only if NNN is purely digits — that's
        # Blender's collision-disambiguation suffix.
        if "." in stripped and stripped.rsplit(".", 1)[1].isdigit():
            stripped = stripped.rsplit(".", 1)[0]

        target = _find([image.name, from_filepath, stripped])
        if target is None:
            continue
        image.filepath = str(target)
        try:
            image.reload()
        except RuntimeError:
            pass
        rebound += 1
    return rebound


def _add_empty(name: str, location: tuple[float, float, float]) -> None:
    obj = bpy.data.objects.new(name, None)
    obj.location = location
    obj.empty_display_size = 0.3
    _link(obj)


def _add_camera_looking_at(
    name: str,
    location: tuple[float, float, float],
    look_at: tuple[float, float, float],
    lens: float = 35.0,
):
    cam_data = bpy.data.cameras.new(f"{name}_data")
    cam_data.lens = lens
    obj = bpy.data.objects.new(name, cam_data)
    obj.location = location
    direction = mathutils.Vector(
        (look_at[0] - location[0], look_at[1] - location[1], look_at[2] - location[2])
    )
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    _link(obj)
    return obj


def _add_sun(name: str, energy: float = 3.0) -> None:
    light_data = bpy.data.lights.new(name=f"{name}_data", type="SUN")
    light_data.energy = energy
    obj = bpy.data.objects.new(name, light_data)
    obj.location = (0.0, -4.0, 5.0)
    obj.rotation_euler = (
        mathutils.Vector((0.0, 0.5, -1.0)).to_track_quat("Z", "Y").to_euler()
    )
    _link(obj)


def _add_area(name: str, location: tuple[float, float, float], energy: float = 50.0) -> None:
    light_data = bpy.data.lights.new(name=f"{name}_data", type="AREA")
    light_data.energy = energy
    light_data.size = 4.0
    obj = bpy.data.objects.new(name, light_data)
    obj.location = location
    # Aim downward to fill the room from the ceiling.
    obj.rotation_euler = (0.0, 0.0, 0.0)
    _link(obj)


def _set_world_background(color: tuple[float, float, float], strength: float) -> None:
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (*color, 1.0)
    bg.inputs[1].default_value = strength


def build() -> None:
    _wipe()
    _import_classroom()
    rebound = _rebind_textures()
    print(f"[build] rebound {rebound} texture images")

    _add_sun("KeyLight", energy=4.0)
    _add_area("CeilingFill", location=(0.0, 0.0, 3.0), energy=80.0)
    _set_world_background(color=(0.4, 0.45, 0.5), strength=0.6)

    for name, loc in EMPTY_LOCATIONS.items():
        _add_empty(name, loc)

    # Wide shot from the back of the room, looking toward the front
    # (blackboard wall). Stays INSIDE the room — the FBX has walls at
    # X = ±4 and Y = ±5, so a camera outside that box renders just wall.
    wide = _add_camera_looking_at(
        "wide", location=(0.0, 4.5, 1.8), look_at=(0.0, -3.0, 1.4), lens=28.0
    )
    # Tighter angle aimed at the student chair rows from the front.
    _add_camera_looking_at(
        "close_student", location=(-1.5, -2.5, 1.7), look_at=(2.0, 0.0, 1.5), lens=40.0
    )
    bpy.context.scene.camera = wide

    # Pack all externals into the .blend so the saved file is self-contained
    # — no broken texture refs if someone moves the .blend without the
    # textures/ folder.
    bpy.ops.file.pack_all()


def _parse_output_arg() -> str:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    for i, arg in enumerate(argv):
        if arg == "--output" and i + 1 < len(argv):
            return argv[i + 1]
    raise SystemExit("build.py: --output <path> is required")


if __name__ == "__main__":
    output_path = _parse_output_arg()
    build()
    bpy.ops.wm.save_as_mainfile(filepath=output_path)
    print(f"[build] saved {output_path}")
