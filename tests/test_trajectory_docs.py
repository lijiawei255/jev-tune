"""Generated research prose must follow evidence and preserve the old failure."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('trajectory_docs_tests', ROOT/'scripts/33_sync_trajectory_docs.py')
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


@pytest.fixture
def evidence():
    """Synthetic values exercise formatting only; never published as results."""
    diagnosis = {'status': 'post_hoc_diagnostic_only',
                 'fixed_path_feasibility': {'mandatory_harm_plants': 7, 'n': 10}}
    monitor = {'n_plants': 10, 'trajectory_harm': {'events': 3, 'upper': .5},
               'first_stage_execution': {'lower': .8}, 'final_cost': {'mean': 1., 'p90': 2.},
               'simulation_counts': {'operating': 100}}
    primary = copy.deepcopy(monitor)
    primary.update({'trajectory_harm': {'events': 0, 'upper': .08},
                    'final_cost': {'mean': 1.2, 'p90': 1.8}, 'simulation_counts': {'operating': 50}})
    checks = dict(trajectory_risk_upper=True, first_stage_execution_lower=True,
                  empirical_mean_cost_noninferior=False, empirical_p90_cost_noninferior=True,
                  operating_budget_noninferior=True, integrity=True)
    trajectory = {
        'completed_utc': 'synthetic-test-only',
        'protocol': {'specification': {
            'primary_candidate': 'trajectory_selected',
            'acceptance': {'trajectory_harm_one_sided_95_upper_max': .1,
                           'first_stage_execution_one_sided_95_lower_min': .5},
            'candidates': {'scales': [1., .5, .25]},
            'calibration': {'target_reached': 2000, 'initial_cap_per_stage': 20000},
            'evaluation': {'arms': ['monitor', 'trajectory_selected']},
        }},
        'evaluation': {'monitor': monitor, 'trajectory_selected': primary},
        'acceptance': {'passed': False, 'checks': checks, 'failed': ['empirical_mean_cost_noninferior']},
        'integrity': {'raw_verified': True},
        'deployment': {'status': 'research_only', 'enabled': False,
                       'primary_candidate': 'trajectory_selected', 'generic_python_c_matlab_enabled': False},
        'simulation_counts': {'total': 1000, 'training_total': 500, 'calibration_total': 300, 'evaluation_total': 200},
    }
    return diagnosis, trajectory


def populate(root, evidence):
    diagnosis, trajectory = evidence
    validity = {'status': 'post_hoc_implementation_validity_audit',
                'frozen_numerical_acceptance': copy.deepcopy(trajectory['acceptance']),
                'canonical_per_object_mapping_established': False,
                'cp_exchangeability_established': False,
                'trajectory_event_independence_established': False,
                'deployment_allowed': False}
    for name, data in ((docs.DIAGNOSIS, diagnosis), (docs.TRAJECTORY, trajectory), (docs.VALIDITY, validity)):
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding='utf-8')
    (root/'docs').mkdir(exist_ok=True)
    for name in ('README.md', 'README.zh-CN.md'):
        (root/name).write_text('# Readme\n<!-- joint-risk-rollout:start -->\nV1 FAILED\n<!-- joint-risk-rollout:end -->\n', encoding='utf-8')
    for name in ('docs/ARCHITECTURE.md', 'docs/TRANSFER.md'):
        (root/name).write_text('# Document\n\n## English\n\nExisting text.\n\n## 简体中文\n\n原文。\n', encoding='utf-8')
    registry = {'claims': []}
    docs.register_available_claims(registry, root)
    (root/'docs/claims.json').write_text(json.dumps(registry), encoding='utf-8')
    docs.sync_documents(root)


def test_complete_generated_blocks_and_registry_are_checked(tmp_path, evidence):
    populate(tmp_path, evidence)
    assert docs.check_generated_sections(tmp_path) == []
    path = tmp_path/'README.md'
    original = path.read_text(encoding='utf-8')
    assert 'V1 FAILED' in original
    assert 'new preregistered study FAIL' in original
    assert '1.200000/1.000000' in original
    assert 'empirical_mean_cost_noninferior' in original
    assert '<!-- claim:trajectory_' not in original
    docs.sync_documents(tmp_path)
    assert path.read_text(encoding='utf-8') == original
    path.write_text(original.replace('it is not a single-factor causal experiment',
                                     'it is a single-factor causal experiment'), encoding='utf-8')
    assert any('README.md' in x for x in docs.check_generated_sections(tmp_path))


def test_missing_final_result_does_not_generate_a_status(tmp_path, evidence):
    (tmp_path/'research/results').mkdir(parents=True)
    (tmp_path/docs.DIAGNOSIS).write_text(json.dumps(evidence[0]), encoding='utf-8')
    assert docs.check_generated_sections(tmp_path)
    assert not (tmp_path/'README.md').exists()
    registry = {'claims': []}
    docs.register_available_claims(registry, tmp_path)
    assert all(c['source'] == docs.DIAGNOSIS for c in registry['claims'])


def test_pass_status_is_dynamic_and_cannot_override_failed_cost(evidence):
    diagnosis, trajectory = evidence
    trajectory['acceptance']['passed'] = True
    with pytest.raises(ValueError, match='acceptance'):
        docs.rendered_sections(diagnosis, trajectory)
    trajectory['evaluation']['trajectory_selected']['final_cost']['mean'] = .9
    trajectory['acceptance']['checks']['empirical_mean_cost_noninferior'] = True
    trajectory['acceptance']['failed'] = []
    trajectory['deployment'].update(status='validated_research_scope_only', enabled=True)
    rendered = docs.rendered_sections(diagnosis, trajectory)['README.md'][0][1]
    assert 'new preregistered study PASS' in rendered
    assert 'defaults remain unchanged' in rendered


def test_incomplete_result_or_generic_deployment_is_rejected(evidence):
    diagnosis, trajectory = evidence
    trajectory.pop('completed_utc')
    with pytest.raises(ValueError, match='completed'):
        docs.rendered_sections(diagnosis, trajectory)
    trajectory['completed_utc'] = 'synthetic'
    trajectory['deployment']['generic_python_c_matlab_enabled'] = True
    with pytest.raises(ValueError, match='research-only'):
        docs.rendered_sections(diagnosis, trajectory)


def test_duplicate_blocks_and_changed_claim_sources_fail(tmp_path, evidence):
    populate(tmp_path, evidence)
    path = tmp_path/'docs/claims.json'
    registry = json.loads(path.read_text(encoding='utf-8'))
    registry['claims'][-1]['path'] = 'not_the_original_field'
    path.write_text(json.dumps(registry), encoding='utf-8')
    assert any('claims:' in x for x in docs.check_generated_sections(tmp_path))
    sections = docs.rendered_sections(*evidence)['README.md']
    block = docs._block(*sections[0])
    with pytest.raises(ValueError, match='duplicate'):
        docs.update_document(block+'\n'+block, 'README.md', sections)


def test_numerical_diagnostic_counts_are_sourced_and_remain_post_hoc(evidence):
    pairing = {'status': 'post_hoc_numerical_diagnostic_only', 'changes_acceptance_or_thresholds': False,
               'arms': {'control': {'n_matched_proposal_rows': 17, 'different_proposal_rows_exact': 4,
                                    'max_abs_base_step_difference': .000003}}}
    batch = {'additional_independent_evidence': False, 'acceptance_recomputed': False,
             'additional_simulation_counts': {'total': 2},
             'batches': {'3': {'relative_to_reference_row': {'base_step_max_abs': .000001}}}}
    rendered = docs.rendered_sections(*evidence, pairing=pairing, batch=batch)
    en = rendered['docs/ARCHITECTURE.md'][0][1]
    assert '4/17 matched proposal rows' in en
    assert '3e-06' in en and '1e-06' in en
    assert '2 additional diagnostic simulations' in en
    assert 'not independent observations' in en
    assert 'boundaries remain unchanged' in en
    batch['acceptance_recomputed'] = True
    with pytest.raises(ValueError, match='post-hoc'):
        docs.rendered_sections(*evidence, batch=batch)


def test_unestablished_validity_remains_separate_from_nominal_acceptance(tmp_path, evidence):
    populate(tmp_path, evidence)
    text = (tmp_path/'README.md').read_text(encoding='utf-8')
    assert 'nominal one-sided 95%' in text
    assert 'NOT ESTABLISHED; deployment_allowed=false' in text
    assert 'not established exact CP/PAC guarantees' in text
    assert 'additional failure beyond the frozen numerical acceptance' in text
    validity = json.loads((tmp_path/docs.VALIDITY).read_text(encoding='utf-8'))
    validity['deployment_allowed'] = True
    with pytest.raises(ValueError, match='prohibit deployment'):
        docs.validity_note(evidence[1], validity)
    (tmp_path/docs.VALIDITY).unlink()
    assert docs.check_generated_sections(tmp_path)
