"""Action dispatch — walk a timeline JSON and apply each action.

Called by the daemon as the `execute_timeline` RPC. Looks up target
characters by their `veraframe_handle` custom property (set by
`character_loader.load_character`) and dispatches each action to its
implementation in `actions/`.

Step 9 implements only `idle`; other action types are surfaced in the
response's `skipped` list with a `not yet implemented` reason so the caller
can verify dispatch without failing.
"""

try:
    import bpy
except ImportError:
    bpy = None

from actions import blink as blink_action
from actions import camera_cut as camera_cut_action
from actions import camera_dolly as camera_dolly_action
from actions import frown as frown_action
from actions import idle as idle_action
from actions import look_at as look_at_action
from actions import nod as nod_action
from actions import orbit as orbit_action
from actions import over_shoulder as over_shoulder_action
from actions import point_at as point_at_action
from actions import set_lighting as set_lighting_action
from actions import shake_head as shake_head_action
from actions import sit as sit_action
from actions import track_subject as track_subject_action
from actions import two_shot as two_shot_action
from actions import wave as wave_action
from actions import smile as smile_action
from actions import stand as stand_action
from actions import talk as talk_action
from actions import turn_to as turn_to_action
from actions import walk_to as walk_to_action


class ExecutorError(RuntimeError):
    """Raised when the executor cannot run at all (e.g. bpy unavailable)."""


_HANDLE_PROP = "veraframe_handle"


def execute_timeline(
    timeline: dict,
    asset_paths: dict,
    fps: int = 24,
    character_assets: dict | None = None,
) -> dict:
    """Apply the timeline to currently-loaded characters.

    `asset_paths` is the global animation map (id → absolute FBX path).
    `character_assets` is an optional per-character override map keyed by
    character handle (the timeline's character id, not the preset). When a
    character has its own entry, the dispatcher uses it instead of the
    global map — needed because user-uploaded characters can come with
    their own idle / walk FBX files baked against a non-shared rig.

    Returns `{executed: [...], skipped: [...], fps: <n>}` — every action in
    the timeline appears in exactly one of those lists.
    """
    if bpy is None:
        raise ExecutorError("bpy unavailable")

    characters = _index_characters_by_handle()
    char_assets = character_assets or {}

    def _resolve(char_id: str, anim_id: str) -> str | None:
        """Per-character override first, then the global asset map."""
        per_char = char_assets.get(char_id, {})
        if isinstance(per_char, dict) and per_char.get(anim_id):
            return per_char[anim_id]
        return asset_paths.get(anim_id)

    executed: list[dict] = []
    skipped: list[dict] = []

    # Per-shot camera binding. Each shot has a `camera` field that names the
    # default camera for its time window. We inject an implicit camera_cut at
    # each shot's start so multi-shot timelines actually switch cameras at
    # the boundary. Skipped when the user already placed an explicit
    # camera_cut at that exact frame.
    timeline = _inject_per_shot_cameras(timeline)

    # Implicit idle fill — for each character + each shot, walk the existing
    # body-pose actions sorted by start time and inject `idle` for any
    # uncovered time. Without this, gaps render as Mixamo's T-pose, which is
    # almost never what the user wants. Idle composes cleanly because it just
    # plays the loop strip during its window.
    timeline = _fill_pose_gaps_with_idle(timeline)

    # Two-pass dispatch. We run all character/body actions first, then camera
    # and scene actions. Camera primitives like `track_subject` and
    # `two_shot` need to sample character positions at specific frames, so
    # the walk_to keyframes must already be in place by the time they
    # execute. set_lighting is also in pass-2 to keep it adjacent to camera
    # work (no functional requirement).
    camera_types = {
        "camera_cut",
        "camera_dolly",
        "track_subject",
        "two_shot",
        "over_shoulder",
        "orbit",
        "set_lighting",
    }

    def _dispatch_body(action: dict) -> None:
        atype = action.get("type")
        action_id = action.get("id", "?")
        if atype == "idle":
            _dispatch_idle(action, characters, _resolve, fps, executed, skipped)
        elif atype == "walk_to":
            _dispatch_walk_to(action, characters, _resolve, fps, executed, skipped)
        elif atype == "look_at":
            _dispatch_look_at(action, characters, fps, executed, skipped)
        elif atype == "turn_to":
            _dispatch_turn_to(action, characters, fps, executed, skipped)
        elif atype == "point_at":
            _dispatch_point_at(action, characters, fps, executed, skipped)
        elif atype in ("sit", "stand"):
            _dispatch_pose(action, characters, fps, executed, skipped)
        elif atype == "talk":
            _dispatch_talk(action, characters, fps, executed, skipped)
        elif atype in ("smile", "frown", "blink"):
            _dispatch_emotion(action, characters, fps, executed, skipped)
        elif atype in ("nod", "shake_head", "wave"):
            _dispatch_gesture(action, characters, fps, executed, skipped)
        else:
            skipped.append(
                {
                    "id": action_id,
                    "type": atype,
                    "reason": f"action type '{atype}' not yet implemented",
                }
            )

    def _dispatch_camera(action: dict) -> None:
        atype = action.get("type")
        action_id = action.get("id", "?")
        if atype == "camera_cut":
            _dispatch_camera_cut(action, fps, executed, skipped)
        elif atype == "camera_dolly":
            _dispatch_camera_dolly(action, fps, executed, skipped)
        elif atype == "track_subject":
            _dispatch_track_subject(action, characters, fps, executed, skipped)
        elif atype == "two_shot":
            _dispatch_two_shot(action, characters, fps, executed, skipped)
        elif atype == "over_shoulder":
            _dispatch_over_shoulder(action, characters, fps, executed, skipped)
        elif atype == "orbit":
            _dispatch_orbit(action, characters, fps, executed, skipped)
        elif atype == "set_lighting":
            _dispatch_set_lighting(action, fps, executed, skipped)
        else:
            skipped.append(
                {
                    "id": action_id,
                    "type": atype,
                    "reason": f"camera action '{atype}' not yet implemented",
                }
            )

    for shot in timeline.get("shots", []):
        # Pass 1 — body / character actions (keyframes character armatures).
        for action in shot.get("actions", []):
            if action.get("type") not in camera_types:
                _dispatch_body(action)
        # Pass 2 — camera + scene actions (can sample character locations).
        for action in shot.get("actions", []):
            if action.get("type") in camera_types:
                _dispatch_camera(action)

    return {"executed": executed, "skipped": skipped, "fps": fps}


def _inject_per_shot_cameras(timeline: dict) -> dict:
    """Inject an implicit camera_cut at the start of every shot.

    Each Shot in the schema has a `camera` field naming the default camera
    for its duration. Without an explicit camera_cut action, the executor
    would leave the scene's load-time camera bound across shot boundaries.
    Injecting a camera_cut at shot.start ensures multi-shot timelines switch
    cameras correctly. We skip the injection when the user has already
    placed an explicit camera_cut at the same frame (so manual control wins).
    """
    if not isinstance(timeline, dict):
        return timeline
    shots = timeline.get("shots", [])
    if not isinstance(shots, list) or not shots:
        return timeline

    new_shots: list[dict] = []
    for shot in shots:
        if not isinstance(shot, dict):
            new_shots.append(shot)
            continue
        camera = shot.get("camera")
        actions = list(shot.get("actions", []))
        if camera:
            shot_start = float(shot.get("start", 0))
            has_explicit = any(
                a.get("type") == "camera_cut"
                and abs(float(a.get("start", 0)) - shot_start) < 0.05
                for a in actions
            )
            if not has_explicit:
                actions.insert(
                    0,
                    {
                        "id": f"_shot_camera_{shot.get('id', 'shot')}",
                        "type": "camera_cut",
                        "camera": camera,
                        "start": shot_start,
                        # camera_cut places a marker at start_frame; end is
                        # unused by the action but must be > start to satisfy
                        # any validator that sees it later.
                        "end": shot_start + 0.1,
                    },
                )
        new_shot = dict(shot)
        new_shot["actions"] = actions
        new_shots.append(new_shot)

    out = dict(timeline)
    out["shots"] = new_shots
    return out


# Action types that occupy the character's body (their pose). When two of
# these overlap on the same character, the second one wins on the relevant
# bones. Gaps between any of these → T-pose → looks broken → we fill with
# idle. Face-only actions (smile/frown/blink/talk) don't count — they don't
# cover the body and shouldn't trigger gap-fill.
_POSE_ACTION_TYPES = frozenset({"idle", "walk_to", "turn_to", "sit", "stand"})


def _fill_pose_gaps_with_idle(timeline: dict) -> dict:
    """Return a copy of `timeline` with implicit idle actions covering every
    character's uncovered time inside each shot.

    The gap-fill preserves the original action ordering and ids; we only add
    new entries with deterministic ids prefixed `_gap_idle_`. Operates on a
    shallow copy of each shot's actions list so the input dict isn't mutated.
    """
    if not isinstance(timeline, dict):
        return timeline
    shots = timeline.get("shots", [])
    if not isinstance(shots, list) or not shots:
        return timeline

    new_shots: list[dict] = []
    for shot in shots:
        if not isinstance(shot, dict):
            new_shots.append(shot)
            continue
        shot_start = float(shot.get("start", 0))
        shot_end = float(shot.get("end", 0))
        actions = list(shot.get("actions", []))

        # Collect every character handle that appears in this shot's pose
        # actions — those are the candidates for gap-fill.
        char_ids: set[str] = set()
        for a in actions:
            if a.get("type") in _POSE_ACTION_TYPES and a.get("character"):
                char_ids.add(str(a["character"]))

        injected: list[dict] = []
        for char_id in sorted(char_ids):
            char_pose_actions = sorted(
                (a for a in actions
                 if a.get("type") in _POSE_ACTION_TYPES and a.get("character") == char_id),
                key=lambda a: float(a.get("start", 0)),
            )
            cursor = shot_start
            for idx, a in enumerate(char_pose_actions):
                a_start = float(a.get("start", 0))
                a_end = float(a.get("end", 0))
                if a_start > cursor + 0.01:
                    injected.append(
                        {
                            "id": f"_gap_idle_{char_id}_{shot.get('id', 'shot')}_{idx}",
                            "type": "idle",
                            "character": char_id,
                            "start": cursor,
                            "end": a_start,
                        }
                    )
                cursor = max(cursor, a_end)
            if cursor < shot_end - 0.01:
                injected.append(
                    {
                        "id": f"_gap_idle_{char_id}_{shot.get('id', 'shot')}_tail",
                        "type": "idle",
                        "character": char_id,
                        "start": cursor,
                        "end": shot_end,
                    }
                )

        new_shot = dict(shot)
        new_shot["actions"] = actions + injected
        new_shots.append(new_shot)

    out = dict(timeline)
    out["shots"] = new_shots
    return out


def _dispatch_idle(
    action: dict,
    characters: dict,
    resolve_anim,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    char_id = action.get("character")
    armature = characters.get(char_id)
    if armature is None:
        skipped.append(
            {
                "id": action_id,
                "type": "idle",
                "reason": f"character '{char_id}' not loaded (no armature with that handle)",
            }
        )
        return

    fbx_path = resolve_anim(char_id, "idle")
    if not fbx_path:
        skipped.append(
            {
                "id": action_id,
                "type": "idle",
                "reason": "no idle animation path in asset_paths",
            }
        )
        return

    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)

    try:
        result = idle_action.execute(
            armature,
            fbx_path,
            start_frame,
            end_frame,
            action_id=action_id,
        )
    except idle_action.IdleActionError as e:
        skipped.append({"id": action_id, "type": "idle", "reason": str(e)})
        return

    executed.append({"id": action_id, "type": "idle", **result})


def _dispatch_walk_to(
    action: dict,
    characters: dict,
    resolve_anim,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    char_id = action.get("character")
    armature = characters.get(char_id)
    if armature is None:
        skipped.append(
            {
                "id": action_id,
                "type": "walk_to",
                "reason": f"character '{char_id}' not loaded (no armature with that handle)",
            }
        )
        return

    target_name = action.get("target")
    scene = bpy.context.scene
    target_obj = scene.objects.get(target_name) if target_name else None
    if target_obj is None and target_name in characters:
        target_obj = characters[target_name]
    if target_obj is None:
        skipped.append(
            {
                "id": action_id,
                "type": "walk_to",
                "reason": f"target '{target_name}' not found as spawn point or character",
            }
        )
        return
    target_location = (target_obj.location.x, target_obj.location.y, target_obj.location.z)

    fbx_path = resolve_anim(char_id, "walk_in_place")
    if not fbx_path:
        skipped.append(
            {
                "id": action_id,
                "type": "walk_to",
                "reason": "no walk_in_place animation path in asset_paths",
            }
        )
        return

    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)

    try:
        result = walk_to_action.execute(
            armature,
            fbx_path,
            target_location,
            start_frame,
            end_frame,
            action_id=action_id,
            style=action.get("style"),
        )
    except walk_to_action.WalkToActionError as e:
        skipped.append({"id": action_id, "type": "walk_to", "reason": str(e)})
        return

    executed.append({"id": action_id, "type": "walk_to", **result})


def _dispatch_look_at(
    action: dict,
    characters: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    char_id = action.get("character")
    armature = characters.get(char_id)
    if armature is None:
        skipped.append(
            {
                "id": action_id,
                "type": "look_at",
                "reason": f"character '{char_id}' not loaded (no armature with that handle)",
            }
        )
        return

    target_name = action.get("target")
    scene = bpy.context.scene
    target_obj = scene.objects.get(target_name) if target_name else None
    if target_obj is None and target_name in characters:
        target_obj = characters[target_name]
    if target_obj is None:
        skipped.append(
            {
                "id": action_id,
                "type": "look_at",
                "reason": f"target '{target_name}' not found as spawn point or character",
            }
        )
        return

    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)

    try:
        result = look_at_action.execute(
            armature, target_obj, start_frame, end_frame, action_id=action_id
        )
    except look_at_action.LookAtActionError as e:
        skipped.append({"id": action_id, "type": "look_at", "reason": str(e)})
        return

    executed.append({"id": action_id, "type": "look_at", **result})


def _dispatch_turn_to(
    action: dict,
    characters: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    char_id = action.get("character")
    armature = characters.get(char_id)
    if armature is None:
        skipped.append(
            {
                "id": action_id,
                "type": "turn_to",
                "reason": f"character '{char_id}' not loaded (no armature with that handle)",
            }
        )
        return

    target_name = action.get("target")
    scene = bpy.context.scene
    target_obj = scene.objects.get(target_name) if target_name else None
    if target_obj is None and target_name in characters:
        target_obj = characters[target_name]
    if target_obj is None:
        skipped.append(
            {
                "id": action_id,
                "type": "turn_to",
                "reason": f"target '{target_name}' not found as spawn point or character",
            }
        )
        return

    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)

    try:
        result = turn_to_action.execute(
            armature, target_obj, start_frame, end_frame, action_id=action_id
        )
    except turn_to_action.TurnToActionError as e:
        skipped.append({"id": action_id, "type": "turn_to", "reason": str(e)})
        return

    executed.append({"id": action_id, "type": "turn_to", **result})


def _dispatch_point_at(
    action: dict,
    characters: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    char_id = action.get("character")
    armature = characters.get(char_id)
    if armature is None:
        skipped.append(
            {
                "id": action_id,
                "type": "point_at",
                "reason": f"character '{char_id}' not loaded (no armature with that handle)",
            }
        )
        return

    target_name = action.get("target")
    scene = bpy.context.scene
    target_obj = scene.objects.get(target_name) if target_name else None
    if target_obj is None and target_name in characters:
        target_obj = characters[target_name]
    if target_obj is None:
        skipped.append(
            {
                "id": action_id,
                "type": "point_at",
                "reason": f"target '{target_name}' not found as spawn point or character",
            }
        )
        return

    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)

    try:
        result = point_at_action.execute(
            armature, target_obj, start_frame, end_frame, action_id=action_id
        )
    except point_at_action.PointAtActionError as e:
        skipped.append({"id": action_id, "type": "point_at", "reason": str(e)})
        return

    executed.append({"id": action_id, "type": "point_at", **result})


_POSE_HANDLERS = {
    "sit": (sit_action.execute, sit_action.SitActionError),
    "stand": (stand_action.execute, stand_action.StandActionError),
}


def _dispatch_pose(
    action: dict,
    characters: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    atype = action.get("type")
    char_id = action.get("character")
    armature = characters.get(char_id)
    if armature is None:
        skipped.append(
            {
                "id": action_id,
                "type": atype,
                "reason": f"character '{char_id}' not loaded (no armature with that handle)",
            }
        )
        return

    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)
    handler, error_cls = _POSE_HANDLERS[atype]
    try:
        result = handler(armature, start_frame, end_frame, action_id=action_id)
    except error_cls as e:
        skipped.append({"id": action_id, "type": atype, "reason": str(e)})
        return

    executed.append({"id": action_id, "type": atype, **result})


def _dispatch_talk(
    action: dict,
    characters: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    char_id = action.get("character")
    armature = characters.get(char_id)
    if armature is None:
        skipped.append(
            {
                "id": action_id,
                "type": "talk",
                "reason": f"character '{char_id}' not loaded (no armature with that handle)",
            }
        )
        return

    text = action.get("text")
    if not text:
        skipped.append({"id": action_id, "type": "talk", "reason": "text is required"})
        return

    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)
    try:
        result = talk_action.execute(
            armature,
            text=text,
            start_frame=start_frame,
            end_frame=end_frame,
            action_id=action_id,
            emotion=action.get("emotion"),
        )
    except talk_action.TalkActionError as e:
        skipped.append({"id": action_id, "type": "talk", "reason": str(e)})
        return

    executed.append({"id": action_id, "type": "talk", **result})


_EMOTION_HANDLERS = {
    "smile": smile_action.execute,
    "frown": frown_action.execute,
    "blink": blink_action.execute,
}


def _dispatch_emotion(
    action: dict,
    characters: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    atype = action.get("type")
    char_id = action.get("character")
    armature = characters.get(char_id)
    if armature is None:
        skipped.append(
            {
                "id": action_id,
                "type": atype,
                "reason": f"character '{char_id}' not loaded (no armature with that handle)",
            }
        )
        return

    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)
    handler = _EMOTION_HANDLERS[atype]
    try:
        result = handler(armature, start_frame, end_frame, action_id=action_id)
    except Exception as e:  # noqa: BLE001 — surface as skipped rather than crash dispatch
        skipped.append({"id": action_id, "type": atype, "reason": str(e)})
        return

    executed.append({"id": action_id, "type": atype, **result})


def _dispatch_camera_cut(
    action: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    camera_name = action.get("camera")
    if not camera_name:
        skipped.append({"id": action_id, "type": "camera_cut", "reason": "no camera name"})
        return

    start_frame = int(action["start"] * fps)
    try:
        result = camera_cut_action.execute(
            bpy.context.scene, camera_name, start_frame, action_id=action_id
        )
    except camera_cut_action.CameraCutActionError as e:
        skipped.append({"id": action_id, "type": "camera_cut", "reason": str(e)})
        return

    executed.append({"id": action_id, "type": "camera_cut", **result})


_GESTURE_HANDLERS = {
    "nod": nod_action.execute,
    "shake_head": shake_head_action.execute,
    "wave": wave_action.execute,
}


def _dispatch_gesture(
    action: dict,
    characters: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    atype = action.get("type")
    char_id = action.get("character")
    armature = characters.get(char_id)
    if armature is None:
        skipped.append(
            {
                "id": action_id,
                "type": atype,
                "reason": f"character '{char_id}' not loaded",
            }
        )
        return

    handler = _GESTURE_HANDLERS.get(atype)
    if handler is None:
        skipped.append({"id": action_id, "type": atype, "reason": "no gesture handler"})
        return

    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)
    try:
        result = handler(armature, start_frame, end_frame, action_id=action_id)
    except Exception as e:  # noqa: BLE001
        skipped.append({"id": action_id, "type": atype, "reason": str(e)})
        return

    executed.append({"id": action_id, "type": atype, **result})


def _dispatch_track_subject(
    action: dict,
    characters: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    char_id = action.get("character")
    armature = characters.get(char_id)
    if armature is None:
        skipped.append(
            {
                "id": action_id,
                "type": "track_subject",
                "reason": f"character '{char_id}' not loaded",
            }
        )
        return
    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)
    try:
        result = track_subject_action.execute(
            armature, start_frame, end_frame, action_id=action_id
        )
    except track_subject_action.TrackSubjectError as e:
        skipped.append({"id": action_id, "type": "track_subject", "reason": str(e)})
        return
    executed.append({"id": action_id, "type": "track_subject", **result})


def _dispatch_two_shot(
    action: dict,
    characters: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    a_id = action.get("a")
    b_id = action.get("b")
    a_armature = characters.get(a_id)
    b_armature = characters.get(b_id)
    if a_armature is None or b_armature is None:
        missing = [name for name, arm in [(a_id, a_armature), (b_id, b_armature)] if arm is None]
        skipped.append(
            {
                "id": action_id,
                "type": "two_shot",
                "reason": f"character(s) not loaded: {missing}",
            }
        )
        return
    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)
    try:
        result = two_shot_action.execute(
            a_armature, b_armature, start_frame, end_frame, action_id=action_id
        )
    except two_shot_action.TwoShotError as e:
        skipped.append({"id": action_id, "type": "two_shot", "reason": str(e)})
        return
    executed.append({"id": action_id, "type": "two_shot", **result})


def _dispatch_orbit(
    action: dict,
    characters: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    target_name = action.get("target")
    if not target_name:
        skipped.append({"id": action_id, "type": "orbit", "reason": "no target"})
        return
    # Target can be a character handle OR a scene spawn-point Empty by name.
    target_obj = characters.get(target_name)
    if target_obj is None:
        scene = bpy.context.scene
        target_obj = scene.objects.get(target_name)
    if target_obj is None:
        skipped.append(
            {
                "id": action_id,
                "type": "orbit",
                "reason": f"target '{target_name}' not found as character or scene object",
            }
        )
        return
    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)
    degrees = float(action.get("degrees", 90.0))
    try:
        result = orbit_action.execute(
            target_obj, start_frame, end_frame, degrees, action_id=action_id
        )
    except orbit_action.OrbitError as e:
        skipped.append({"id": action_id, "type": "orbit", "reason": str(e)})
        return
    executed.append({"id": action_id, "type": "orbit", **result})


def _dispatch_over_shoulder(
    action: dict,
    characters: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    a_id = action.get("a")
    b_id = action.get("b")
    a_armature = characters.get(a_id)
    b_armature = characters.get(b_id)
    if a_armature is None or b_armature is None:
        missing = [name for name, arm in [(a_id, a_armature), (b_id, b_armature)] if arm is None]
        skipped.append(
            {
                "id": action_id,
                "type": "over_shoulder",
                "reason": f"character(s) not loaded: {missing}",
            }
        )
        return
    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)
    try:
        result = over_shoulder_action.execute(
            a_armature, b_armature, start_frame, end_frame, action_id=action_id
        )
    except over_shoulder_action.OverShoulderError as e:
        skipped.append({"id": action_id, "type": "over_shoulder", "reason": str(e)})
        return
    executed.append({"id": action_id, "type": "over_shoulder", **result})


def _dispatch_camera_dolly(
    action: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    from_name = action.get("from_camera")
    to_name = action.get("to_camera")
    if not from_name or not to_name:
        skipped.append(
            {
                "id": action_id,
                "type": "camera_dolly",
                "reason": "from_camera and to_camera are required",
            }
        )
        return

    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)
    try:
        result = camera_dolly_action.execute(
            bpy.context.scene,
            from_name,
            to_name,
            start_frame,
            end_frame,
            action_id=action_id,
        )
    except camera_dolly_action.CameraDollyActionError as e:
        skipped.append({"id": action_id, "type": "camera_dolly", "reason": str(e)})
        return

    executed.append({"id": action_id, "type": "camera_dolly", **result})


def _dispatch_set_lighting(
    action: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    preset = action.get("preset")
    if not preset:
        skipped.append(
            {"id": action_id, "type": "set_lighting", "reason": "preset is required"}
        )
        return

    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)
    try:
        result = set_lighting_action.execute(
            bpy.context.scene, preset, start_frame, end_frame, action_id=action_id
        )
    except set_lighting_action.SetLightingActionError as e:
        skipped.append({"id": action_id, "type": "set_lighting", "reason": str(e)})
        return

    executed.append({"id": action_id, "type": "set_lighting", **result})


def _index_characters_by_handle() -> dict:
    """Map `veraframe_handle` -> armature object for every loaded character."""
    out: dict[str, object] = {}
    for obj in bpy.data.objects:
        if obj.type != "ARMATURE":
            continue
        handle = obj.get(_HANDLE_PROP)
        if handle:
            out[handle] = obj
    return out


__all__ = ["ExecutorError", "execute_timeline"]
