"""Bind a real human profile to one prepared formal-review slot."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.formal_review import FORMAL_ROUND_ID, FormalReviewError, FormalReviewStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vincula un perfil humano real a un slot formal preparado.")
    parser.add_argument("--database", type=Path, default=ROOT / "outputs/human_review/firepa_human_review.sqlite3")
    parser.add_argument("--round-id", default=FORMAL_ROUND_ID)
    parser.add_argument("--slot-id", required=True, choices=("HUMAN_SLOT_A", "HUMAN_SLOT_B"))
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--expertise", required=True, choices=("protocol_trained_reviewer", "remote_sensing_specialist", "domain_expert"))
    parser.add_argument("--training-version", default="labeling-protocol-v1")
    args = parser.parse_args(argv)
    try:
        with FormalReviewStore(args.database) as store:
            store.initialize()
            round_row = store.connection.execute(
                "SELECT status, execution_status FROM formal_review_rounds WHERE round_id = ?",
                (args.round_id,),
            ).fetchone()
            slot = store.connection.execute(
                "SELECT profile_id, status FROM formal_review_slots WHERE round_id = ? AND slot_id = ?",
                (args.round_id, args.slot_id),
            ).fetchone()
            if round_row is None or round_row["status"] != "prepared" or round_row["execution_status"] != "not_started":
                raise FormalReviewError("La ronda no está en prepared/not_started")
            if slot is None or (slot["profile_id"] is not None and slot["profile_id"] != args.profile_id):
                raise FormalReviewError("El slot no está disponible para este binding")
            other = store.connection.execute(
                "SELECT slot_id FROM formal_review_slots WHERE round_id = ? AND profile_id = ? AND slot_id <> ?",
                (args.round_id, args.profile_id, args.slot_id),
            ).fetchone()
            if other is not None:
                raise FormalReviewError("Un mismo perfil no puede ocupar ambos slots")
            store.register_human_profile(args.profile_id, args.expertise, training_version=args.training_version)
            store.bind_slot(args.round_id, args.slot_id, args.profile_id)
    except FormalReviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"bound_slot={args.slot_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
