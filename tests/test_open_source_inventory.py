"""Real file/ZIP checks for public data identity and latest-tree exclusions."""
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("inventory_test", ROOT / "scripts/50_open_source_inventory.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    calibration = {"artifacts": {"training_data_sha256": "", "calibration_data_files": {}}}
    for name in [module.TRAIN] + [f"data/calibration/{n}.npz" for n in ("temperature_fit", "cp_fit", "empirical_eval")]:
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, values=np.array([1., 2., 3.]))
        if name == module.TRAIN:
            calibration["artifacts"]["training_data_sha256"] = module.digest(path)
        else:
            calibration["artifacts"]["calibration_data_files"][path.stem] = {"path": name, "sha256": module.digest(path)}
    (tmp_path / "models").mkdir()
    for i in range(6): (tmp_path / f"models/model{i}.pt").write_bytes(b"formal model")
    (tmp_path / "models/calibration.json").write_text(json.dumps(calibration), encoding="utf-8")
    subprocess.run(["git", "add", "models"], cwd=tmp_path, check=True)
    study = tmp_path / "research/results/nonpid_transfer"; study.mkdir(parents=True)
    for stem in ("model", "calibration"):
        for seed in (101, 202, 303): (study / f"{stem}_{seed}.json").write_text("{}", encoding="utf-8")
    inventory = module.build(tmp_path)
    (tmp_path / module.INVENTORY).write_text(json.dumps(inventory), encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / module.DOC).write_text(module.render(inventory), encoding="utf-8")
    for name in ("LICENSE", "NOTICE.md"): (tmp_path / name).write_text(name, encoding="utf-8")
    return tmp_path, inventory


def test_check_without_ignored_data_and_package_requires_it(repository):
    root, inventory = repository
    for row in inventory["datasets"]: (root / row["path"]).unlink()
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}
    module.check(root)
    assert all(p.read_bytes() == data for p, data in before.items())
    with pytest.raises(AssertionError, match="Required release data missing"):
        module.package(root / "output", root)


def test_numeric_mutation_rejected(repository):
    root, inventory = repository
    np.savez(root / module.TRAIN, values=np.array([1., 2., 4.]))
    with pytest.raises(AssertionError, match="Data hash changed"):
        module.validate_data(root, inventory, required=True)


def test_exact_release_archive_paths_and_bytes(repository):
    root, inventory = repository
    target = module.package(root / "output", root)
    expected = {r["path"] for r in inventory["datasets"]} | {"LICENSE", "NOTICE.md", module.INVENTORY}
    with zipfile.ZipFile(target) as archive:
        assert set(archive.namelist()) == expected
        for name in expected: assert archive.read(name) == (root / name).read_bytes()


@pytest.mark.parametrize("name", ["private.slx", "private.mdl", "geometry.stl", "lecture.pdf", "lecture.docx", "matlab/engine/__init__.py"])
def test_latest_tree_forbidden_files_rejected(repository, name):
    root, _ = repository
    path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"private")
    with pytest.raises(AssertionError): module.scan(root)
