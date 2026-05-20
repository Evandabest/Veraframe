"""Build the `dark_lab` demo scene programmatically.

Run via:

    blender --background --python build.py -- --output scene.blend

Produces a minimal lab: a floor, one back wall, a point light, three named
empties as spawn points (`door`, `center_room`, `robot_station`), and one
camera named `wide`. Everything is created via direct `bpy.data` datablock
construction (no operators) so the script doesn't depend on viewport context.
"""

import sys

import bpy

EMPTY_LOCATIONS: dict[str, tuple[float, float, float]] = {
    "door": (-5.0, 0.0, 0.0),
    "center_room": (0.0, 0.0, 0.0),
    "robot_station": (3.0, 0.0, 0.0),
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


def _add_plane(name: str, size: float, location: tuple[float, float, float]) -> None:
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    s = size / 2
    verts = [(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)]
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    _link(obj)


def _add_box(
    name: str,
    size: float,
    location: tuple[float, float, float],
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> None:
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    s = size / 2
    verts = [
        (-s, -s, -s),
        (s, -s, -s),
        (s, s, -s),
        (-s, s, -s),
        (-s, -s, s),
        (s, -s, s),
        (s, s, s),
        (-s, s, s),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.scale = scale
    _link(obj)


def _add_point_light(name: str, location: tuple[float, float, float], energy: float) -> None:
    light_data = bpy.data.lights.new(name=f"{name}_data", type="POINT")
    light_data.energy = energy
    obj = bpy.data.objects.new(name, light_data)
    obj.location = location
    _link(obj)


def _add_empty(name: str, location: tuple[float, float, float]) -> None:
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.5
    obj.location = location
    _link(obj)


def _add_camera(
    name: str,
    location: tuple[float, float, float],
    rotation: tuple[float, float, float],
) -> None:
    camera_data = bpy.data.cameras.new(name=f"{name}_data")
    obj = bpy.data.objects.new(name, camera_data)
    obj.location = location
    obj.rotation_euler = rotation
    _link(obj)


def build() -> None:
    _wipe()
    _add_plane("Floor", size=20.0, location=(0.0, 0.0, 0.0))
    _add_box("Wall_Back", size=2.0, location=(0.0, 5.0, 1.5), scale=(10.0, 0.5, 3.0))
    _add_point_light("MainLight", location=(0.0, 0.0, 5.0), energy=300.0)
    for name, loc in EMPTY_LOCATIONS.items():
        _add_empty(name, loc)
    # Camera looking toward the origin from south, slightly elevated.
    _add_camera("wide", location=(0.0, -10.0, 3.0), rotation=(1.2, 0.0, 0.0))


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
