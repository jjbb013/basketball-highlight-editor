"""Compare anonymous local truth with identity predictions without media or names."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _metrics(correct: int, automatic: int, total: int) -> dict[str, float | None]:
    return {
        'top1': _ratio(correct, total),
        'automatic_coverage': _ratio(automatic, total),
        'automatic_precision': _ratio(correct, automatic),
    }


def evaluate_identity_predictions(
    truth_rows: Sequence[Mapping],
    predictions: Mapping,
    identity_aliases: Mapping[str, str] | None = None,
) -> dict:
    """Return separate touch, identity, joint, abstention and review metrics.

    Truth uses anonymous IDs and an optional mapping from opaque algorithm
    identity IDs to those labels. Missing truth/predictions never count correct.
    """
    results = predictions.get('results', {})
    if not isinstance(results, Mapping):
        raise ValueError('PREDICTIONS_INVALID')
    aliases = dict(identity_aliases or {})
    seen = set()
    records = []
    totals = {'made': 0, 'missed': 0, 'unknown': 0}
    touch_correct = touch_auto = touch_total = 0
    identity_correct = identity_auto = identity_total = 0
    joint_correct = joint_total = reviewed = 0
    review_cost = 0.0
    for row in truth_rows:
        candidate_id = str(row.get('candidate_id', ''))
        basket = row.get('basket')
        if not candidate_id or candidate_id in seen or basket not in totals:
            raise ValueError('TRUTH_INVALID')
        seen.add(candidate_id)
        totals[basket] += 1
        cost = row.get('review_cost_seconds', 0)
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
            raise ValueError('REVIEW_COST_INVALID')
        review_cost += cost
        truth_track = row.get('truth_local_track_id')
        truth_identity = row.get('truth_identity_id')
        if basket == 'made' and not all(key in row for key in ('truth_local_track_id', 'truth_identity_id')):
            raise ValueError('TRUTH_INCOMPLETE')
        touch_eligible = basket == 'made' and bool(truth_track)
        identity_eligible = basket == 'made' and bool(truth_identity)
        joint_eligible = touch_eligible and identity_eligible
        result = results.get(candidate_id) or {}
        touch = result.get('touch') or {}
        identity = result.get('identity') or {}
        touch_automatic = touch.get('status') == 'identified' and bool(touch.get('local_track_id'))
        identity_automatic = bool(identity.get('identity_id')) and not identity.get('needs_review', True)
        correct_touch = touch_eligible and touch_automatic and touch['local_track_id'] == truth_track
        correct_identity = identity_eligible and identity_automatic and aliases.get(
            identity['identity_id'], identity['identity_id'],
        ) == truth_identity
        joint = correct_touch and correct_identity and not result.get('needs_review', True)
        needs_review = bool(result.get('needs_review', True))
        touch_correct += int(correct_touch)
        touch_auto += int(touch_eligible and touch_automatic)
        touch_total += int(touch_eligible)
        identity_correct += int(correct_identity)
        identity_auto += int(identity_eligible and identity_automatic)
        identity_total += int(identity_eligible)
        joint_correct += int(joint)
        joint_total += int(joint_eligible)
        reviewed += int(needs_review)
        records.append({
            'candidate_id': candidate_id,
            'basket': basket,
            'evaluated': joint_eligible,
            'last_touch_correct': correct_touch if touch_eligible else None,
            'identity_correct': correct_identity if identity_eligible else None,
            'joint_correct': joint if joint_eligible else None,
            'needs_review': needs_review,
            'review_cost_seconds': cost,
        })
    return {
        'schema_version': 1,
        'algorithm_version': predictions.get('algorithm_version'),
        'labelled_events': {label: count for label, count in totals.items() if count},
        'evaluated_events': max(touch_total, identity_total),
        'last_touch': _metrics(touch_correct, touch_auto, touch_total),
        'identity': _metrics(identity_correct, identity_auto, identity_total),
        'joint_top1': _ratio(joint_correct, joint_total),
        'review': {'automatic': reviewed, 'cost_seconds': review_cost},
        'records': records,
    }
