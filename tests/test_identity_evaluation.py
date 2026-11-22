import pytest

from basketball_highlight.identity_evaluation import evaluate_identity_predictions


def prediction(track, identity, review=False):
    return {
        'needs_review': review,
        'touch': {'status': 'identified', 'local_track_id': track},
        'identity': {'identity_id': identity, 'needs_review': review},
    }


def test_metrics_separate_touch_identity_joint_coverage_and_review_cost():
    truth = [
        {'candidate_id': 'a', 'basket': 'made', 'truth_local_track_id': 't1',
         'truth_identity_id': 'person-a', 'review_cost_seconds': 4.5},
        {'candidate_id': 'b', 'basket': 'made', 'truth_local_track_id': 't2',
         'truth_identity_id': 'person-b', 'review_cost_seconds': 8},
        {'candidate_id': 'unknown', 'basket': 'unknown', 'review_cost_seconds': 2},
    ]
    predictions = {'results': {
        'a': prediction('t1', 'opaque-1'),
        'b': prediction('wrong-track', 'opaque-2', True),
        'unknown': prediction(None, None, True),
    }}
    report = evaluate_identity_predictions(truth, predictions, {'opaque-1': 'person-a'})

    assert report['labelled_events'] == {'made': 2, 'unknown': 1}
    assert report['evaluated_events'] == 2
    # Touch coverage is independent of the later identity review decision.
    assert report['last_touch'] == {'top1': .5, 'automatic_coverage': 1.0, 'automatic_precision': .5}
    assert report['identity'] == {'top1': .5, 'automatic_coverage': .5, 'automatic_precision': 1.0}
    assert report['joint_top1'] == .5
    assert report['review'] == {'automatic': 2, 'cost_seconds': 14.5}
    assert report['records'][1]['last_touch_correct'] is False
    assert report['records'][1]['identity_correct'] is False


def test_touch_level_review_does_not_count_as_automatic_coverage():
    result = prediction('t1', 'opaque-1')
    result['touch']['needs_review'] = True
    report = evaluate_identity_predictions(
        [{'candidate_id': 'a', 'basket': 'made', 'truth_local_track_id': 't1',
          'truth_identity_id': 'person-a', 'review_cost_seconds': 0}],
        {'results': {'a': result}},
    )
    assert report['last_touch']['top1'] == 0.0
    assert report['last_touch']['automatic_coverage'] == 0.0


def test_touch_review_does_not_count_as_automatic_identity_coverage():
    result = prediction('t1', 'opaque-1', review=True)
    result['touch']['needs_review'] = True
    result['identity']['needs_review'] = False
    report = evaluate_identity_predictions(
        [{'candidate_id': 'a', 'basket': 'made', 'truth_local_track_id': 't1',
          'truth_identity_id': 'person-a', 'review_cost_seconds': 0}],
        {'results': {'a': result}}, {'opaque-1': 'person-a'},
    )
    assert report['identity']['top1'] == 0.0
    assert report['identity']['automatic_coverage'] == 0.0
    assert report['review']['automatic'] == 1


def test_missing_predictions_and_truth_are_not_counted_as_correct():
    report = evaluate_identity_predictions(
        [{'candidate_id': 'a', 'basket': 'made', 'truth_local_track_id': None,
          'truth_identity_id': None, 'review_cost_seconds': 0}],
        {'results': {}},
    )
    assert report['evaluated_events'] == 0
    assert report['last_touch']['top1'] is None
    assert report['identity']['automatic_coverage'] is None
    assert report['joint_top1'] is None


def test_identity_truth_can_be_measured_before_track_aliases_are_reviewed():
    report = evaluate_identity_predictions(
        [{'candidate_id': 'a', 'basket': 'made', 'truth_local_track_id': None,
          'truth_identity_id': 'person-a', 'review_cost_seconds': 1}],
        {'results': {'a': prediction(None, 'opaque-1')}}, {'opaque-1': 'person-a'},
    )
    assert report['last_touch']['top1'] is None
    assert report['identity']['top1'] == 1.0
    assert report['joint_top1'] is None


def test_truth_cannot_invent_success_or_accept_invalid_cost():
    with pytest.raises(ValueError, match='TRUTH'):
        evaluate_identity_predictions([{'candidate_id': 'a', 'basket': 'made'}], {'results': {}})
    with pytest.raises(ValueError, match='REVIEW_COST'):
        evaluate_identity_predictions(
            [{'candidate_id': 'a', 'basket': 'made', 'truth_local_track_id': 't',
              'truth_identity_id': 'person-a', 'review_cost_seconds': -1}], {'results': {}},
        )
