"""Recompute a descriptive comparison of archived CPU calibrations; no objective.

The comparison has no acceptance threshold and never selects a runtime or a
temperature. Complete CP sets and continuous actions are reported separately.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from jev_tune.primitives import softmax

ROOT = Path(__file__).resolve().parents[1]
BASE = "research/results/calibration_runtime_sources/"
LEFT = BASE + "calibration_runtime_root_default_v0100"
RIGHT = BASE + "calibration_runtime_default"
RESULT = BASE + "root_vs_hosted_analysis.json"


def diff(a, b):
    a, b = np.asarray(a), np.asarray(b)
    d = np.abs(a-b)
    return {"max_abs_per_axis": d.max(axis=tuple(i for i in range(d.ndim) if i != 1)).tolist()
            if d.ndim >= 2 else d.tolist(), "different_values": int(np.count_nonzero(a != b)),
            "max_abs": float(d.max())}


def sets(p, q):
    return (1-p) <= np.asarray(q)[None, :, None]


def setdiff(a, b):
    d = a != b
    return {"different_options_per_axis": d.sum(axis=(0, 2)).tolist(),
            "different_state_axes_per_axis": d.any(axis=2).sum(axis=0).tolist(),
            "first_different_state_axes": np.argwhere(d.any(axis=2))[:10].tolist()}


def actiondiff(runner, p, q, p2, q2):
    def decode(probabilities, threshold):
        decisions = [runner.action(row, {"qhat_per_axis": threshold}) for row in probabilities]
        return SimpleNamespace(**{name: np.stack([getattr(d, name) for d in decisions])
                                  for name in ("step", "held", "escalate")})
    a, b = decode(p, q), decode(p2, q2)
    return {"step_max_abs_per_axis": np.abs(a.step-b.step).max(axis=0).tolist(),
            "different_step_states_per_axis": (a.step != b.step).sum(axis=0).tolist(),
            "held_disagreements_per_axis": (a.held != b.held).sum(axis=0).tolist(),
            "escalate_disagreements_per_axis": (a.escalate != b.escalate).sum(axis=0).tolist(),
            "nonzero_steps_per_axis_left": (a.step != 0).sum(axis=0).tolist(),
            "scope": "Unchanged action decoder on initial states only; no objective or later trajectory replay"}


def compare(root=ROOT):
    root = Path(root).resolve()
    left, right = root/LEFT, root/RIGHT
    ld, rd = [json.loads((p/"diagnosis.json").read_text(encoding="utf-8")) for p in (left, right)]
    la, ra = [np.load(p/"canonical_arrays.npz", allow_pickle=False) for p in (left, right)]
    for directory, diagnosis in ((left, ld), (right, rd)):
        assert hashlib.sha256((directory/"canonical_arrays.npz").read_bytes()).hexdigest() == diagnosis["canonical_arrays_sha256"]
        assert diagnosis["additional_objective_evaluations"] == 0
        assert diagnosis["model_hashes_before"] == diagnosis["model_hashes_after"]
    reference_dir = root/BASE/"calibration_runtime_original_isa"
    reference = json.loads((reference_dir/"diagnosis.json").read_text(encoding="utf-8"))
    assert reference["original_48_check"]["returncode"] == rd["original_48_check"]["returncode"] == 1
    assert ld["original_48_check"]["returncode"] == 0
    assert reference["input_hashes"] == rd["input_hashes"] == ld["input_hashes"]
    assert hashlib.sha256((reference_dir/"canonical_arrays.npz").read_bytes()).hexdigest() == reference["canonical_arrays_sha256"]
    with np.load(reference_dir/"canonical_arrays.npz", allow_pickle=False) as constrained:
        assert set(constrained.files) == set(ra.files)
        for key in ra.files:
            assert constrained[key].dtype == ra[key].dtype and constrained[key].shape == ra[key].shape
            assert constrained[key].tobytes() == ra[key].tobytes(), "Predefined ISA arm arrays differ"
    spec = importlib.util.spec_from_file_location("_runtime_actual_action", root/"scripts/45_nonpid_transfer.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    rows = []
    assert len(ld["rows"]) == len(rd["rows"]) == 12
    for l, r in zip(ld["rows"], rd["rows"]):
        seed, n = l["seed"], l["n_temperature"]
        assert (seed, n) == (r["seed"], r["n_temperature"])
        lt, rt = [[a["refit_temperature"] for a in item["axes"]] for item in (l, r)]
        saved = [a["recorded_temperature"] for a in l["axes"]]
        row = {"seed": seed, "n_temperature": n, "axes": [
            {"axis": i, "saved_T": saved[i], "root_refit_T": lt[i], "hosted_refit_T": rt[i],
             "delta_T": rt[i]-lt[i], "hosted_delta_NLL": b["delta_nll"],
             "hosted_NLL_ULP_distance": b["nll_ulp_distance"]}
            for i, b in enumerate(r["axes"])], "populations": {}}
        test_left, test_right = la[f"seed_{seed}_test_logits"], ra[f"seed_{seed}_test_logits"]
        for key in ("cp256", "saved_calibration_population"):
            lp, rp = l[key], r[key]
            prefix, other = lp["array_prefix"], rp["array_prefix"]
            entry = {"n_calibration": lp["n_calibration"], "axes": []}
            for ax in range(2):
                ls, rs = lp["refit_t_order_statistic"][ax], rp["refit_t_order_statistic"][ax]
                entry["axes"].append({"axis": ax, "root_rank": ls["rank"], "hosted_rank": rs["rank"],
                    "root_kth_index": ls["kth_index"], "hosted_kth_index": rs["kth_index"],
                    "root_qhat": ls["qhat"], "hosted_qhat": rs["qhat"], "delta_qhat": rs["qhat"]-ls["qhat"],
                    "sorted_identity_position_differences": int(np.count_nonzero(
                        la[prefix+"_sort_refit_t"][:, ax] != ra[other+"_sort_refit_t"][:, ax]))})
            lq, rq = [[a["qhat"] for a in item["refit_t_order_statistic"]] for item in (lp, rp)]
            lc, rc = la[prefix+"_probabilities_refit_t"], ra[other+"_probabilities_refit_t"]
            tl, tr = [softmax(z, temperature=np.asarray(t)[None, :, None])
                      for z, t in ((test_left, lt), (test_right, rt))]
            entry.update(CP_probability_cross_runtime_refit_difference=diff(lc, rc),
                CP_complete_set_cross_runtime_refit_difference=setdiff(sets(lc, lq), sets(rc, rq)),
                test_probability_cross_runtime_refit_difference=diff(tl, tr),
                test_complete_set_cross_runtime_refit_difference=setdiff(sets(tl, lq), sets(tr, rq)),
                test_action_cross_runtime_refit_difference=actiondiff(runner, tl, lq, tr, rq))
            if lp["saved_qhat"] is not None:
                sl, sr = [softmax(z, temperature=np.asarray(saved)[None, :, None]) for z in (test_left, test_right)]
                entry["unchanged_saved_policy_test_action_difference"] = actiondiff(
                    runner, sl, lp["saved_qhat"], sr, lp["saved_qhat"])
            row["populations"][key] = entry
        rows.append(row)
    arraydiff = {k: diff(la[k], ra[k]) for k in la.files if k.endswith("_logits")}
    result = {"schema_version": 1,
        "scope": "Post-incident initial-state numerical comparison; no new independent data or whole-trajectory equivalence",
        "inputs": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (left/"diagnosis.json", right/"diagnosis.json", left/"canonical_arrays.npz", right/"canonical_arrays.npz")},
        "root_original_48": ld["original_48_check"], "hosted_original_48": rd["original_48_check"],
        "logit_differences": arraydiff, "rows": rows, "additional_objective_evaluations": 0,
        "summary": {"max_logits_difference": max(v["max_abs"] for v in arraydiff.values()),
            "max_temperature_difference": max(abs(a["delta_T"]) for row in rows for a in row["axes"]),
            "max_qhat_difference": max(abs(a["delta_qhat"]) for row in rows for p in row["populations"].values() for a in p["axes"]),
            "max_refit_step_difference": max(max(p["test_action_cross_runtime_refit_difference"]["step_max_abs_per_axis"])
                for row in rows for p in row["populations"].values()),
            "changed_CP_options": sum(sum(p["CP_complete_set_cross_runtime_refit_difference"]["different_options_per_axis"])
                for row in rows for p in row["populations"].values()),
            "changed_test_options": sum(sum(p["test_complete_set_cross_runtime_refit_difference"]["different_options_per_axis"])
                for row in rows for p in row["populations"].values())}}
    return result


def render(value):
    summary = value["summary"]
    row = "| logits | temperature | CP threshold | initial-state decoded step |\n| ---: | ---: | ---: | ---: |\n| "
    row += " | ".join(f"{summary[key]:.17g}" for key in (
        "max_logits_difference", "max_temperature_difference", "max_qhat_difference", "max_refit_step_difference")) + " |"
    return f"""# Numerical reproducibility boundary / 数值复现边界

[English](#english) · [简体中文](#简体中文)

## English

The original strict cross-CPU refit **failed**. The retained [hosted failure](../research/results/calibration_runtime_ci_failure_v0100.json) and [full log](../research/results/calibration_runtime_sources/windows_failure_log.txt) are evidence of that failure, not a passing replay. The original `45`, `46`, `48`, model files, fit algorithm and their tolerances remain unchanged. The predefined AVX2 diagnostic also failed; no further ISA setting was selected to obtain a pass. Git history is retained.

The original CPU is Intel i9-13950HX; the hosted CPU is AMD EPYC 9V45. Recorded package versions agree, which does not imply identical elementary operations. The archived default and predefined ISA arms have identical arrays. On the compared original/hosted initial-state arrays, maximum absolute differences are generated below:

{row}

Changed complete CP options in the compared calibration populations: {summary['changed_CP_options']}; changed test options: {summary['changed_test_options']}. These are observations on the archived cases, not a guarantee for unseen boundary cases. Continuous steps differ. Neither complete closed-loop trajectory equivalence nor identical outcomes on another CPU follows from unchanged CP sets. The deeper source of the first differing MLP operation was not captured; OpenBLAS architecture names alone do not explain a PyTorch forward pass.

The replacement automatic evidence obligation is explicitly post-incident: [52](../scripts/52_verify_recorded_transfer.py) independently validates the **recorded original-machine evidence**, with Decimal interval forward/softmax checks, a loss-based temperature certificate, exact CP ranks and recorded sets, complete action-to-measurement links and independently rerun objectives. It does not claim to reproduce every original floating branch, prove training causality, or certify the new backend's rollout. Its explicit binary64 and faithful elementary-function assumptions are recorded in the [audit library](../scripts/calibration_numeric_audit.py). Original strict failures remain separate results; a passing evidence audit never renames them as passes.

Across numerical backends, verify the inference and action mapping again. If recalibration is needed, use independent temperature/CP labels and verify the resulting policy; recalibration alone does not recover identical actions or extend coverage to reached states. Published fit timings remain observations on the original host. The non-PID `negative_stop` decision, sample counts, thresholds, acquisition costs and negative policy result are unchanged.

Recompute this descriptive comparison with `python scripts/54_compare_calibration_runtimes.py`; run the recorded-evidence audit with `python scripts/52_verify_recorded_transfer.py --check`. The former executes no objectives. Every latter objective replay is separately receipted, including failures; it is verification work on the same samples. The earlier hosted failure consumed the count retained in its JSON; its receipt file was not exported, so the log is the available source. [Runtime protocol](../research/protocols/calibration_runtime_v0100.json) documents the failed predefined diagnostic; the separate recorded-evidence protocol freezes the new audit obligations before their full execution.

## 简体中文

原严格跨CPU重新拟合检查**失败**。[托管失败记录](../research/results/calibration_runtime_ci_failure_v0100.json)与[完整日志](../research/results/calibration_runtime_sources/windows_failure_log.txt)保留的是失败证据。原`45`、`46`、`48`、模型、拟合算法和容差全部不变；预先指定的AVX2诊断也失败，没有继续寻找能通过的ISA设置。Git历史按用户要求保留。

原CPU为Intel i9-13950HX，托管CPU为AMD EPYC 9V45。软件版本相同不等于底层运算逐位相同；归档的默认与预定ISA组数组逐位一致。原机与托管初态数组的最大绝对差异如下，由脚本生成：

{row}

比较中校准总体的完整CP选项变化{summary['changed_CP_options']}个，测试选项变化{summary['changed_test_options']}个。这只描述归档样本，不保证未见边界样本；连续动作确有差异，集合相同不能推出完整闭环轨迹或异机结果相同。未保存首个产生差异的MLP逐层运算，不能仅凭OpenBLAS架构名解释PyTorch前向差异。

自动证据检查改为明确标记的事后义务：[52](../scripts/52_verify_recorded_transfer.py)通过Decimal区间前向/概率核查、基于目标值的温度证书、严格CP分位秩与记录集合、完整动作到实测候选链及独立目标重放，核验**原机记录证据**。它不声称原浮点分支在异机一致，不证明训练因果真实性，也不认证新后端的整段运行。binary64和基本函数faithful舍入假设见[数值库](../scripts/calibration_numeric_audit.py)。原严格失败始终单列；证据审计通过也不能把失败改称通过。

跨数值后端必须重新验证推理及动作映射；如需重标定，使用独立温度/CP标签，并重新验证产生的策略。重标定本身不能恢复相同动作，也不能把覆盖边界扩展至到达状态。拟合耗时仍是原宿主的观测；非PID的`negative_stop`、样本量、阈值、采集成本和策略负结果全部保留。

用`python scripts/54_compare_calibration_runtimes.py`重算描述性比较，用`python scripts/52_verify_recorded_transfer.py --check`审计记录证据。前者不调用目标函数；后者每次重放都单独保存含失败的计账凭据，不构成新增独立样本。早先托管失败消耗的次数保存在其JSON内；当时未导出receipt文件，可用证据为完整日志。[数值运行协议](../research/protocols/calibration_runtime_v0100.json)记录失败的预定诊断，另有记录证据协议在完整执行新审计前冻结新义务。
"""


def check(root=ROOT):
    actual = compare(root)
    stored = json.loads((Path(root)/RESULT).read_text(encoding="utf-8"))
    assert actual == stored, "Archived runtime comparison changed"
    assert (Path(root)/"docs/NUMERICAL_REPRODUCIBILITY.md").read_text(encoding="utf-8") == render(actual), "Numerical boundary document changed"
    return {"ok": True, "scope": actual["scope"], "additional_verification_objective_evaluations": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        value = compare()
        (ROOT/RESULT).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        (ROOT/"docs/NUMERICAL_REPRODUCIBILITY.md").write_text(render(value), encoding="utf-8")
        print(json.dumps(value["summary"]))
    else:
        print(json.dumps(check()))
