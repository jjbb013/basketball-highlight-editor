#!/usr/bin/env python3
"""Evaluate local anonymous truth; never embed video, photos, or player names."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from basketball_highlight.identity_evaluation import evaluate_identity_predictions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--truth', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.truth.read_text(encoding='utf-8'))
    report = evaluate_identity_predictions(
        data['events'], json.loads(args.predictions.read_text(encoding='utf-8')),
        data.get('identity_aliases'),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f'.{args.output.name}.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(args.output)
    print(json.dumps({key: value for key, value in report.items() if key != 'records'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
