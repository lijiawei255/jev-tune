"""Check newly archived observation arithmetic, preserving the original 54 failure.

This obligation is distinct from exact cross-machine recomputation: nonlinear
outputs are recorded observations, certified conditionally by independent
Decimal envelopes. Equality counts, ranks, full sets and differences are rebuilt
exactly from recorded arrays, never guessed from overlapping intervals.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
from decimal import localcontext
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULT = "research/results/calibration_runtime_observations_v0100.json"
BASE = "research/results/calibration_runtime_sources/"
LEFT, RIGHT = BASE+"calibration_runtime_root_default_v0100", BASE+"calibration_runtime_default"
REFERENCE = BASE+"calibration_runtime_original_isa"
ORIGINAL = BASE+"root_vs_hosted_analysis.json"
PROTOCOL = "research/protocols/runtime_comparison_observations_v0100.json"
LABELS = ("original_comparison_machine", "default_hosted_observer")
SCOPE = "One observation machine decodes two archived input populations; these are not actions actually executed on two machines. No objectives, trajectories, training or new independent data."


def input_names():
    return [directory+"/"+name for directory in (LEFT, RIGHT, REFERENCE)
            for name in ("diagnosis.json", "canonical_arrays.npz")] + [
        ORIGINAL, "research/results/nonpid_transfer/report.json", "research/results/nonpid_transfer/raw.json.gz",
        "research/protocols/nonpid_transfer_v0100.json", "models/calibration.json", "docs/NUMERICAL_REPRODUCIBILITY.md"] + [
        f"research/results/nonpid_transfer/{kind}_{seed}.json" for kind in ("model", "calibration") for seed in (101, 202, 303)]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_module(root, name):
    spec = importlib.util.spec_from_file_location("observed_verify_"+name, root/"scripts"/(name+".py"))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path, text=False):
    data = Path(path).read_bytes()
    return hashlib.sha256(data.replace(b"\r\n", b"\n") if text else data).hexdigest()


def difference(left, right):
    delta = np.abs(left-right)
    return {"max_abs_per_axis": delta.max(axis=tuple(i for i in range(delta.ndim) if i != 1)).tolist()
            if delta.ndim >= 2 else delta.tolist(), "different_values": int(np.count_nonzero(left != right)),
            "max_abs": float(delta.max())}


def full_sets(p, q):
    return (1-p) <= np.asarray(q)[None, :, None]


def set_difference(left, right):
    changed = left != right
    return {"different_options_per_axis": changed.sum(axis=(0, 2)).tolist(),
            "different_state_axes_per_axis": changed.any(axis=2).sum(axis=0).tolist(),
            "first_different_state_axes": np.argwhere(changed.any(axis=2))[:10].tolist()}


def action_difference(left, right):
    return {"step_max_abs_per_axis": np.abs(left["step"]-right["step"]).max(axis=0).tolist(),
            "different_step_states_per_axis": (left["step"] != right["step"]).sum(axis=0).tolist(),
            "held_disagreements_per_axis": (left["held"] != right["held"]).sum(axis=0).tolist(),
            "escalate_disagreements_per_axis": (left["escalate"] != right["escalate"]).sum(axis=0).tolist(),
            "nonzero_steps_per_axis_left": (left["step"] != 0).sum(axis=0).tolist(),
            "scope": "Unchanged action decoder on initial states only; no objective or later trajectory replay"}


def strict_rank(probabilities, labels, identities, saved):
    scores = 1-np.take_along_axis(probabilities, labels[..., None], -1)[..., 0]
    order = np.argsort(scores, axis=0, kind="stable")
    rank = int(np.ceil((len(labels)+1)*.9))
    require(len(saved) == probabilities.shape[1], "rank axis shape differs")
    for axis, row in enumerate(saved):
        index = int(order[rank-1, axis]) if rank <= len(labels) else None
        threshold = float(scores[index, axis]) if index is not None else 1.
        require(row["axis"] == axis and row["rank"] == rank and row["qhat"] == threshold,
                "strict rank/qhat differs from recorded probabilities")
        require(row["kth_index"] == index and row["kth_identity"] == (identities[index] if index is not None else None),
                "strict kth identity differs")
    return order


def step_enclosures(probabilities, numeric):
    """Independent use of frozen interval primitives for the unchanged decoder."""
    with localcontext() as ctx:
        ctx.prec = numeric.PRECISION
        I = numeric.Interval
        d = [I(value) for value in (-.2, -.05, 0., .05, .2)]
        mean = numeric.rounded(numeric._sum_boxes(d)/I(5))
        centered = [numeric.rounded(value-mean) for value in d]
        reference = numeric.rounded(numeric._sum_boxes([numeric._square_box(v) for v in centered])/I(5))
        floor = numeric._d(1e-6)
        reference = I(max(floor, reference.lo), max(floor, reference.hi))
        squared = [numeric._square_box(v) for v in d]
        result = []
        for state in probabilities:
            row = []
            for axis in state:
                p = [I(float(value)) for value in axis]
                mu = numeric._dot_boxes(p, d)
                second = numeric._dot_boxes(p, squared)
                variance = numeric.rounded(second-numeric._square_box(mu))
                variance = I(max(numeric.D(0), variance.lo), max(numeric.D(0), variance.hi))
                ratio = numeric.rounded(numeric.rounded(I(1)*variance)/reference)
                gate = numeric.rounded(I(1)/numeric.rounded(I(1)+ratio))
                row.append(numeric._clip_box(numeric.rounded(mu*gate), -.2, .2))
            result.append(row)
        return result


def verify_recorded_steps(probabilities, steps, numeric, enclosures=None):
    require(steps.shape == probabilities.shape[:-1] and steps.dtype == np.dtype("float64")
            and np.isfinite(steps).all(), "recorded action shape/dtype/finite differs")
    enclosures = enclosures if enclosures is not None else step_enclosures(probabilities, numeric)
    for i, row in enumerate(enclosures):
        for axis, enclosure in enumerate(row):
            require(enclosure.contains(steps[i, axis]), "recorded step outside independent decoder envelope")
    return enclosures


def verify_test_probabilities(logits, temperatures, recorded, numeric):
    require(recorded.dtype == np.dtype("float64") and recorded.shape == logits.shape
            and recorded.ndim == 3 and recorded.shape[1:] == (2, 5)
            and np.isfinite(recorded).all() and (recorded >= 0).all()
            and (recorded <= 1).all(), "test probability shape/dtype/finite changed")
    for row, probability in zip(logits, recorded):
        numeric.audit_softmax(row, temperatures, probability)


def verify_original_exit(original, rebuilt, old, docs_equal, stdout, stderr):
    """Admit only the specific retained exact-comparison failure, never exit 1 alone."""
    if rebuilt != old:
        require(original["returncode"] == 1, "original 54 comparison failure exit differs")
        require(stderr.rstrip().endswith("AssertionError: Archived runtime comparison changed")
                and "54_compare_calibration_runtimes.py" in stderr and ", in check" in stderr
                and "assert actual == stored" in stderr,
                "exit 1 is not the known frozen 54 assertion")
    else:
        require(docs_equal and original["returncode"] == 0, "original 54 unexpected failure")
        require(json.loads(stdout) == {"ok": True, "scope": rebuilt["scope"],
                "additional_verification_objective_evaluations": 0}, "original 54 success output differs")


def verify_array_manifest(archive, manifest):
    require(set(archive.files) == set(manifest), "array manifest key set differs")
    for key in archive.files:
        value, item = archive[key], manifest[key]
        require(list(value.shape) == item["shape"] and value.dtype.str == item["dtype"]
                and hashlib.sha256(value.tobytes()).hexdigest() == item["sha256"],
                "array shape/dtype/bytes differ: "+key)


def verify_action_flags_and_sets(p, q, held, escalate, sets):
    for value in (held, escalate):
        require(value.dtype == np.dtype("bool") and value.shape == p.shape[:-1] and not value.any(),
                "monitor action flag differs")
    require(sets.dtype == np.dtype("bool") and sets.shape == p.shape
            and np.array_equal(sets, full_sets(p, q)), "recorded complete sets differ")


def expected_cases(ld, rd):
    result = []
    require(len(ld["rows"]) == len(rd["rows"]) == 12, "twelve comparison rows required")
    require([(r["seed"], r["n_temperature"]) for r in ld["rows"]]
            == [(seed, n) for seed in (101, 202, 303) for n in (16, 32, 64, 128)], "fixed row roster differs")
    for l, r in zip(ld["rows"], rd["rows"]):
        require((l["seed"], l["n_temperature"]) == (r["seed"], r["n_temperature"]), "side row mapping differs")
        for population in ("cp256", "saved_calibration_population"):
            for side, row in (("root", l), ("hosted", r)):
                source = row[population]
                for kind in ("refit", "saved"):
                    temp_key = "refit_temperature" if kind == "refit" else "recorded_temperature"
                    if kind == "refit":
                        q = [a["qhat"] for a in source["refit_t_order_statistic"]]
                        role = "archived side refit rank threshold"
                    elif l[population]["saved_qhat"] is not None:
                        q, role = l[population]["saved_qhat"], "shared frozen left saved threshold, as in 54"
                    else:
                        q = [a["qhat"] for a in source["recorded_t_order_statistic"]]
                        role = "archived side recorded-temperature rank threshold"
                    seed, n = l["seed"], l["n_temperature"]
                    cp_source = source["array_prefix"]+"_probabilities_"+("refit" if kind == "refit" else "recorded")+"_t"
                    result.append({"id": f"case_{len(result):03d}", "seed": seed, "n_temperature": n,
                        "population": population, "side": side, "temperature_kind": kind,
                        "temperatures": [a[temp_key] for a in row["axes"]], "qhat": q, "qhat_scope": role,
                        "n_cp": source["n_calibration"], "test_probabilities": f"test_p_{side}_{seed}_{n}_{kind}",
                        "CP_probabilities": "cp_"+side+"_"+cp_source, "CP_source_key": cp_source, "scope": SCOPE})
    return result


def reconstruct54(root, ld, rd, la, ra, observed_cases, archive, observed_byte_hashes):
    by_case = {(c["seed"], c["n_temperature"], c["population"], c["side"], c["temperature_kind"]): c for c in observed_cases}
    def values(seed, n, population, side, kind):
        case = by_case[seed, n, population, side, kind]
        return {"p": archive[case["test_probabilities"]], **{field: archive[case["id"]+"_"+field] for field in ("step", "held", "escalate")}}
    rows = []
    for l, r in zip(ld["rows"], rd["rows"]):
        seed, n = l["seed"], l["n_temperature"]
        lt, rt = [[a["refit_temperature"] for a in v["axes"]] for v in (l, r)]
        row = {"seed": seed, "n_temperature": n, "axes": [{"axis": i,
            "saved_T": l["axes"][i]["recorded_temperature"], "root_refit_T": lt[i], "hosted_refit_T": rt[i],
            "delta_T": rt[i]-lt[i], "hosted_delta_NLL": a["delta_nll"], "hosted_NLL_ULP_distance": a["nll_ulp_distance"]}
            for i, a in enumerate(r["axes"])], "populations": {}}
        for population in ("cp256", "saved_calibration_population"):
            lp, rp = l[population], r[population]
            entry = {"n_calibration": lp["n_calibration"], "axes": []}
            for axis in range(2):
                ls, rs = lp["refit_t_order_statistic"][axis], rp["refit_t_order_statistic"][axis]
                entry["axes"].append({"axis": axis, "root_rank": ls["rank"], "hosted_rank": rs["rank"],
                    "root_kth_index": ls["kth_index"], "hosted_kth_index": rs["kth_index"],
                    "root_qhat": ls["qhat"], "hosted_qhat": rs["qhat"], "delta_qhat": rs["qhat"]-ls["qhat"],
                    "sorted_identity_position_differences": int(np.count_nonzero(la[lp["array_prefix"]+"_sort_refit_t"][:, axis] != ra[rp["array_prefix"]+"_sort_refit_t"][:, axis]))})
            lq, rq = [[a["qhat"] for a in v["refit_t_order_statistic"]] for v in (lp, rp)]
            lc, rc = la[lp["array_prefix"]+"_probabilities_refit_t"], ra[rp["array_prefix"]+"_probabilities_refit_t"]
            left, right = values(seed, n, population, "root", "refit"), values(seed, n, population, "hosted", "refit")
            entry.update(CP_probability_cross_runtime_refit_difference=difference(lc, rc),
                CP_complete_set_cross_runtime_refit_difference=set_difference(full_sets(lc, lq), full_sets(rc, rq)),
                test_probability_cross_runtime_refit_difference=difference(left["p"], right["p"]),
                test_complete_set_cross_runtime_refit_difference=set_difference(full_sets(left["p"], lq), full_sets(right["p"], rq)),
                test_action_cross_runtime_refit_difference=action_difference(left, right))
            if lp["saved_qhat"] is not None:
                entry["unchanged_saved_policy_test_action_difference"] = action_difference(
                    values(seed, n, population, "root", "saved"), values(seed, n, population, "hosted", "saved"))
            row["populations"][population] = entry
        rows.append(row)
    logits = {key: difference(la[key], ra[key]) for key in la.files if key.endswith("_logits")}
    return {"schema_version": 1, "scope": "Post-incident initial-state numerical comparison; no new independent data or whole-trajectory equivalence",
        "inputs": {name+"/"+file: observed_byte_hashes[name+"/"+file] for name in (LEFT, RIGHT) for file in ("diagnosis.json", "canonical_arrays.npz")},
        "root_original_48": ld["original_48_check"], "hosted_original_48": rd["original_48_check"],
        "logit_differences": logits, "rows": rows, "additional_objective_evaluations": 0,
        "summary": {"max_logits_difference": max(v["max_abs"] for v in logits.values()),
            "max_temperature_difference": max(abs(a["delta_T"]) for row in rows for a in row["axes"]),
            "max_qhat_difference": max(abs(a["delta_qhat"]) for row in rows for p in row["populations"].values() for a in p["axes"]),
            "max_refit_step_difference": max(max(p["test_action_cross_runtime_refit_difference"]["step_max_abs_per_axis"]) for row in rows for p in row["populations"].values()),
            "changed_CP_options": sum(sum(p["CP_complete_set_cross_runtime_refit_difference"]["different_options_per_axis"]) for row in rows for p in row["populations"].values()),
            "changed_test_options": sum(sum(p["test_complete_set_cross_runtime_refit_difference"]["different_options_per_axis"]) for row in rows for p in row["populations"].values())}}


def check_observation(root, directory):
    root, directory = Path(root).resolve(), Path(directory).resolve()
    observed = read(directory/"observation.json")
    require(observed["schema_version"] == 1 and observed["scope"] == SCOPE
            and observed["additional_objective_evaluations"] == observed["gradient_steps"] == 0, "observation identity/scope changed")
    producer = load_module(root, "57_observe_runtime_comparison")
    require(observed["protocol"] == PROTOCOL and observed["label"] in LABELS, "protocol/observer label changed")
    _, current_sources = producer.check_frozen_sources(root)
    require(set(observed["source_hashes"]) == set(producer.SOURCES), "source hash set incomplete")
    require(observed["source_hashes_after"] == observed["source_hashes"] == current_sources,
            "source snapshot changed during/after observation")
    require(observed["input_hashes_after"] == observed["input_hashes"], "input snapshot changed during observation")
    for name, expected in observed["source_hashes"].items():
        require(sha(root/name, text=True) == expected, "observation source changed: "+name)
        import subprocess
        blob = subprocess.check_output(["git", "show", observed["git_revision"]+":"+name], cwd=root)
        require(hashlib.sha256(blob.replace(b"\r\n", b"\n")).hexdigest() == expected,
                "source/revision binding differs: "+name)
    require(set(observed["input_hashes"]) == set(input_names()), "bound input hash set incomplete")
    for name, item in observed["input_hashes"].items():
        require(item["text_normalized"] == (Path(name).suffix in {".json", ".md"}), "input hash scope changed")
        require(sha(root/name, text=item["text_normalized"]) == item["sha256"], "bound input changed: "+name)
        raw = (root/name).read_bytes()
        alternatives = {hashlib.sha256(raw).hexdigest()}
        if item["text_normalized"]:
            lf = raw.replace(b"\r\n", b"\n")
            alternatives.update(hashlib.sha256(value).hexdigest() for value in (lf, lf.replace(b"\n", b"\r\n")))
        require(item["observed_byte_sha256"] in alternatives, "observed byte identity not supported by bound input text: "+name)
    require(observed["environment_file"] == "environment.json" and observed["actual_54_file"] == "actual_54_comparison.json",
            "observation output path mapping differs")
    require(sha(directory/"environment.json") == observed["environment_sha256"], "environment changed")
    env = read(directory/"environment.json")
    require(env["additional_objective_evaluations"] == 0, "environment scope changed")
    require(sha(directory/"arrays.npz") == observed["arrays_sha256"], "observation archive bytes changed")
    require(sha(directory/"actual_54_comparison.json") == observed["actual_54_sha256"], "actual comparison bytes changed")
    numeric = load_module(root, "calibration_numeric_audit")
    with ExitStack() as stack:
        la, ra, reference, archive = [stack.enter_context(np.load(path, allow_pickle=False)) for path in
            (root/LEFT/"canonical_arrays.npz", root/RIGHT/"canonical_arrays.npz", root/REFERENCE/"canonical_arrays.npz", directory/"arrays.npz")]
        ld, rd, ref = [read(root/name/"diagnosis.json") for name in (LEFT, RIGHT, REFERENCE)]
        for name, diagnosis in ((LEFT, ld), (RIGHT, rd), (REFERENCE, ref)):
            require(sha(root/name/"canonical_arrays.npz") == diagnosis["canonical_arrays_sha256"], "original archive identity changed")
            require(diagnosis["additional_objective_evaluations"] == diagnosis["training_gradient_steps"] == 0
                    and diagnosis["model_hashes_before"] == diagnosis["model_hashes_after"], "original scope/flags changed")
        require(ref["input_hashes"] == rd["input_hashes"] == ld["input_hashes"], "original input identities differ")
        require(ld["original_48_check"]["returncode"] == 0 and rd["original_48_check"]["returncode"] == ref["original_48_check"]["returncode"] == 1, "original 48 failure flags changed")
        require(set(reference.files) == set(ra.files), "ISA archive keys changed")
        for key in reference.files:
            require(reference[key].shape == ra[key].shape and reference[key].dtype == ra[key].dtype
                    and reference[key].tobytes() == ra[key].tobytes(), "predefined ISA-arm bytes differ")
        cases = expected_cases(ld, rd)
        require(observed["cases"] == cases, "observed case roster/provenance differs")
        verify_array_manifest(archive, observed["arrays"])
        expected_keys, seen_p, seen_cp, step_cache = set(), set(), set(), {}
        split_seed = read(root/"research/protocols/nonpid_transfer_v0100.json")["splits"]["conformal"]["seed"]
        for case in cases:
            source_archive = la if case["side"] == "root" else ra
            diagnosis = ld if case["side"] == "root" else rd
            source_row = next(r for r in diagnosis["rows"] if (r["seed"], r["n_temperature"]) == (case["seed"], case["n_temperature"]))
            source = source_row[case["population"]]
            pkey, cpkey, prefix = case["test_probabilities"], case["CP_probabilities"], case["id"]
            expected_keys.update([pkey, cpkey]+[prefix+"_"+field for field in ("step", "held", "escalate", "sets")])
            cp = archive[cpkey]
            require(cp.dtype == np.dtype("float64") and cp.shape == (case["n_cp"], 2, 5)
                    and cp.tobytes() == source_archive[case["CP_source_key"]].tobytes(), "CP must use exact original archived probabilities")
            require(np.isfinite(cp).all() and (cp >= 0).all() and (cp <= 1).all(), "invalid CP probability")
            if cpkey not in seen_cp:
                verify_test_probabilities(source_archive[f"seed_{case['seed']}_conformal_logits"][:case["n_cp"]],
                                          case["temperatures"], cp, numeric)
                with localcontext() as ctx:
                    ctx.prec = numeric.PRECISION
                    for state in cp:
                        for row in state:
                            total = numeric.Interval(0)
                            for value in row: total = total+numeric.Interval(float(value))
                            bound = (numeric.Interval(numeric.gamma(len(row)))*numeric.Interval(len(row))).hi
                            require((total-numeric.Interval(1)).magnitude() <= bound, "CP row normalization not certified")
                seen_cp.add(cpkey)
            suffix = "refit" if case["temperature_kind"] == "refit" else "recorded"
            order = strict_rank(cp, source_archive[f"seed_{case['seed']}_conformal_labels"][:case["n_cp"]],
                [f"{split_seed}:{i}" for i in range(case["n_cp"])], source[suffix+"_t_order_statistic"])
            require(order.tobytes() == source_archive[source["array_prefix"]+"_sort_"+suffix+"_t"].tobytes(), "full sorted order changed")
            p = archive[pkey]
            require(p.dtype == np.dtype("float64") and p.shape == (256, 2, 5) and np.isfinite(p).all(), "test probability shape/dtype/finite changed")
            if pkey not in seen_p:
                verify_test_probabilities(source_archive[f"seed_{case['seed']}_test_logits"], case["temperatures"], p, numeric)
                seen_p.add(pkey)
                step_cache[pkey] = step_enclosures(p, numeric)
            steps = archive[prefix+"_step"]
            verify_recorded_steps(p, steps, numeric, step_cache[pkey])
            verify_action_flags_and_sets(p, case["qhat"], archive[prefix+"_held"], archive[prefix+"_escalate"], archive[prefix+"_sets"])
        require(set(archive.files) == expected_keys, "extra or omitted recorded arrays")
        rebuilt = reconstruct54(root, ld, rd, la, ra, cases, archive,
                                {name: item["observed_byte_sha256"] for name, item in observed["input_hashes"].items()})
        require(rebuilt == read(directory/"actual_54_comparison.json"), "derived comparison differs from recorded arrays")
    original = observed["original_54_check"]
    for kind in ("stdout", "stderr"):
        require(original[kind+"_file"] == "original_54_check."+kind+".txt", "execution log path differs")
        require(sha(directory/original[kind+"_file"]) == original[kind+"_sha256"], "original 54 execution log changed")
    old = read(root/ORIGINAL)
    renderer = load_module(root, "54_compare_calibration_runtimes")
    docs_equal = (root/"docs/NUMERICAL_REPRODUCIBILITY.md").read_text(encoding="utf-8") == renderer.render(rebuilt)
    stdout = (directory/original["stdout_file"]).read_text(encoding="utf-8")
    stderr = (directory/original["stderr_file"]).read_text(encoding="utf-8")
    verify_original_exit(original, rebuilt, old, docs_equal, stdout, stderr)
    return {"ok": True, "observation": directory.relative_to(root).as_posix(), "label": observed["label"],
            "observation_sha256": sha(directory/"observation.json"), "cases": len(cases),
            "unique_test_probability_arrays": len(seen_p), "recorded_comparison_summary": rebuilt["summary"],
            "unique_CP_probability_arrays": len(seen_cp),
            "original_54_returncode": original["returncode"], "original_54_failure_preserved": original["returncode"] != 0,
            "conditional_certificate": True, "assumptions": numeric.ASSUMPTIONS, "scope": SCOPE,
            "additional_objective_evaluations": 0, "gradient_steps": 0}


def render(result):
    keys = ("max_logits_difference", "max_temperature_difference", "max_qhat_difference",
            "max_refit_step_difference", "changed_CP_options", "changed_test_options")
    table = "| observer | cases | test arrays | original 54 exit | max logits | max T | max q | max step | CP options | test options |\n"
    table += "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
    for row in result["observations"]:
        values = [row["label"], row["cases"], row["unique_test_probability_arrays"], row["original_54_returncode"]]
        values += [row["recorded_comparison_summary"][key] for key in keys]
        table += "| "+" | ".join(str(value) for value in values)+" |\n"
    return ("# Runtime observations / 运行时观察\n\n[English](#english) · [简体中文](#简体中文)\n\n## English\n\n"
        "Each observer decodes two archived input populations on one machine. These are post-incident observations, "
        "not historical actions executed on two machines. The original [numerical comparison](NUMERICAL_REPRODUCIBILITY.md) "
        "also records steps decoded on its comparison machine. Frozen 54's strict default failure remains a failure. "
        "58 checks recorded observation consistency conditionally on the numerical library's binary64 and faithful "
        "elementary-function assumptions; it proves neither future bitwise identity nor trajectory identity.\n\n"+table+
        "\n## 简体中文\n\n每个观察端在同一台机器上解码两份归档输入。这是故障后的新观察，不是两台机器历史上实际执行的动作。"
        "原数值比较页的步长同样由其比较机解码。冻结54的默认严格复算失败仍是失败。58在数值库明确的binary64及基本函数faithful"
        "舍入假设下核验记录观察的一致性，不证明未来逐位一致或闭环轨迹一致。表中数字逐项读取机器结果。\n\n"+table)


def check(root=ROOT, observations=None):
    root = Path(root).resolve()
    stored = None
    if observations is None:
        stored = read(root/RESULT)
        observations = [root/r["observation"] for r in stored["observations"]]
    directories = [Path(path) if Path(path).is_absolute() else root/path for path in observations]
    require(len(directories) == 2 and sorted(read(path/"observation.json")["label"] for path in directories) == sorted(LABELS),
            "exactly one complete observation per preregistered observer required")
    rows = [check_observation(root, path) for path in directories]
    require(all(row["cases"] == 96 for row in rows), "each observer must contain all 96 cases")
    result = {"schema_version": 1, "ok": True, "obligation": "New recorded-observation certificate; not a passing rerun of frozen 54",
              "scope": SCOPE, "observations": rows, "additional_objective_evaluations": 0, "gradient_steps": 0}
    if stored is not None:
        require(result == stored, "published runtime observation summary changed")
        require((root/"docs/RUNTIME_OBSERVATIONS.md").read_text(encoding="utf-8") == render(result),
                "runtime observation document changed")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", action="append", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = check(observations=args.observation)
    if args.write:
        require(args.observation and not (ROOT/RESULT).exists(), "new explicit summary required; refuse overwrite")
        (ROOT/RESULT).write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        (ROOT/"docs/RUNTIME_OBSERVATIONS.md").write_text(render(result), encoding="utf-8")
    print(json.dumps(result, indent=2))
