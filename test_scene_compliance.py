"""Static compliance gate for maintained standalone scene files."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from manim import Tex, UP

from vivacity_base_scene import VivacityScene
from app.scene_compliance import assert_no_static_connectors


ROOT = Path(__file__).parent
_root_scene_files = {
    path for path in ROOT.glob("*_scene.py")
    if not path.name.startswith("scratch_") and path.name != "vivacity_base_scene.py"
}
_root_scene_files.add(ROOT / "test_manual_render_round8.py")
_scenes_dir = ROOT / "scenes"
if _scenes_dir.exists():
    _root_scene_files.update(_scenes_dir.rglob("*.py"))
# Custom high-quality scenes rendered directly (not through template pipeline)
# are exempt from managed-scene compliance checks.
_CUSTOM_HQ_PREFIXES = ("taylor_pro", "taylor_portrait", "fourier_laplace", "derivative", "character")
MANAGED_SCENE_FILES = tuple(
    sorted(p for p in _root_scene_files
           if not any(prefix in p.stem for prefix in _CUSTOM_HQ_PREFIXES))
)


def _tree(filepath: Path):
    return ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))


def _class_nodes(filepath: Path):
    return [node for node in ast.walk(_tree(filepath)) if isinstance(node, ast.ClassDef)]


def _assert_scene_bases(filepath: Path):
    for node in _class_nodes(filepath):
        bases = {base.id for base in node.bases if isinstance(base, ast.Name)}
        if "Scene" in bases:
            raise AssertionError(
                f"{filepath}: {node.name} subclasses raw Scene; must subclass VivacityScene"
            )
        if "VivacityScene" not in bases:
            raise AssertionError(
                f"{filepath}: {node.name} must subclass VivacityScene"
            )


def _assert_no_raw_transforms(filepath: Path):
    for node in ast.walk(_tree(filepath)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in {"Transform", "ReplacementTransform"}:
            raise AssertionError(
                f"{filepath}:{node.lineno}: raw {node.func.id} found; use self.safe_swap()"
            )
        if isinstance(node.func, ast.Attribute) and node.func.attr == "animate":
            raise AssertionError(
                f"{filepath}:{node.lineno}: raw .animate found in a maintained scene"
            )


def _assert_no_static_tracked_labels(filepath: Path):
    for node in ast.walk(_tree(filepath)):
        if not isinstance(node, ast.FunctionDef) or node.name != "construct":
            continue
        has_tracker = any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "ValueTracker"
            for child in ast.walk(node)
        )
        if not has_tracker:
            continue
        updater_names = {
            call.func.value.id
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "add_updater"
            and isinstance(call.func.value, ast.Name)
        }
        for child in node.body:
            if not isinstance(child, ast.Assign) or not isinstance(child.value, ast.Call):
                continue
            if not isinstance(child.value.func, ast.Name):
                continue
            if child.value.func.id not in {"Tex", "MathTex", "Text"}:
                continue
            for target in child.targets:
                if (
                    isinstance(target, ast.Name)
                    and "label" in target.id.lower()
                    and target.id not in updater_names
                ):
                    raise AssertionError(
                        f"{filepath}:{child.lineno}: {target.id} is a static text label in a scene with ValueTracker; use always_redraw or live_value_label"
                    )


def _assert_no_static_tracked_geometry(filepath: Path):
    """Reject bars/rectangles created once in a tracked scene.

    A tracker-driven collection must be constructed inside ``always_redraw``;
    otherwise the scene can display a tracker label that changes while the
    geometry remains frozen.
    """
    for node in ast.walk(_tree(filepath)):
        if not isinstance(node, ast.FunctionDef) or node.name != "construct":
            continue
        has_tracker = any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "ValueTracker"
            for child in ast.walk(node)
        )
        if not has_tracker:
            continue
        dynamic_geometry_lines = {
            child.lineno
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "always_redraw"
            for child in ast.walk(call)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id in {"Rectangle", "RoundedRectangle", "BarChart"}
        }
        for child in ast.walk(node):
            if not isinstance(child, ast.Assign) or not isinstance(child.value, ast.Call):
                continue
            if not isinstance(child.value.func, ast.Name) or child.value.func.id not in {
                "Rectangle", "RoundedRectangle", "BarChart"
            }:
                continue
            if child.value.lineno not in dynamic_geometry_lines:
                target = next((t.id for t in child.targets if isinstance(t, ast.Name)), "geometry")
                raise AssertionError(
                    f"{filepath}:{child.lineno}: {target} is static tracked geometry in a scene with ValueTracker; use always_redraw"
                )


def _assert_no_static_connectors(filepath: Path):
    assert_no_static_connectors(filepath)


def test_all_managed_scenes_use_vivacity_base():
    for filepath in MANAGED_SCENE_FILES:
        _assert_scene_bases(filepath)


def test_no_raw_transform_calls():
    for filepath in MANAGED_SCENE_FILES:
        _assert_no_raw_transforms(filepath)


def test_no_static_labels_for_tracked_values():
    for filepath in MANAGED_SCENE_FILES:
        _assert_no_static_tracked_labels(filepath)


def test_no_static_geometry_for_tracked_values():
    for filepath in MANAGED_SCENE_FILES:
        _assert_no_static_tracked_geometry(filepath)


def test_no_static_connectors():
    for filepath in MANAGED_SCENE_FILES:
        _assert_no_static_connectors(filepath)


class _DeliberatelyOverlappingScene(VivacityScene):
    def construct(self):
        first = Tex("first").move_to(UP)
        second = Tex("second").move_to(UP)
        self._check_overlap(first, "top")
        self._check_overlap(second, "top")


def test_runtime_overlap_guard_rejects_deliberate_overlap():
    with pytest.raises(AssertionError, match="Overlap detected in 'top' zone"):
        _DeliberatelyOverlappingScene().construct()


def test_known_bad_scene_is_rejected(tmp_path):
    bad_scene = tmp_path / "bad_scene.py"
    bad_scene.write_text(
        "from manim import *\n"
        "class Bad(Scene):\n"
        "    def construct(self):\n"
        "        self.play(Transform(Text('a'), Text('b')))\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="raw Scene|raw Transform"):
        _assert_scene_bases(bad_scene)
    with pytest.raises(AssertionError, match="raw Transform"):
        _assert_no_raw_transforms(bad_scene)


def test_known_bad_static_geometry_is_rejected(tmp_path):
    bad_scene = tmp_path / "bad_geometry_scene.py"
    bad_scene.write_text(
        "from manim import *\n"
        "from vivacity_base_scene import VivacityScene\n"
        "class BadGeometry(VivacityScene):\n"
        "    def construct(self):\n"
        "        tracker = ValueTracker(0)\n"
        "        bars = Rectangle(height=1)\n"
        "        self.add(bars)\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="static tracked geometry"):
        _assert_no_static_tracked_geometry(bad_scene)


def test_known_bad_static_connector_is_rejected(tmp_path):
    bad_scene = tmp_path / "bad_connector_scene.py"
    bad_scene.write_text(
        "from manim import *\n"
        "from vivacity_base_scene import VivacityScene\n"
        "class BrokenConnectorScene(VivacityScene):\n"
        "    def construct(self):\n"
        "        a = Circle().shift(LEFT * 2)\n"
        "        b = Circle().shift(RIGHT * 2)\n"
        "        connector = Line(a.get_right(), b.get_left())\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="static connector"):
        _assert_no_static_connectors(bad_scene)
