import pickle
import pandas as pd
from collections import Counter

data = pickle.load(open("BARDUSDT_snapshot.pkl", "rb"))
df = data["bars15"].sort_index()

LENGTH = 4

for kind, column in [("HIGH", "high"), ("LOW", "low")]:
    values = df[column].astype(float).to_numpy()
    patterns = Counter()
    examples = {}
    total_ties = 0
    candidate_is_extreme = 0

    for pos in range(LENGTH, len(values) - LENGTH):
        window = values[pos-LENGTH:pos+LENGTH+1]
        candidate = values[pos]

        extreme = window.max() if kind == "HIGH" else window.min()

        if candidate != extreme:
            continue

        candidate_is_extreme += 1

        offsets = tuple(
            i - LENGTH
            for i, value in enumerate(window)
            if value == extreme
        )

        if len(offsets) <= 1:
            continue

        total_ties += 1
        patterns[offsets] += 1

        if offsets not in examples:
            examples[offsets] = df.index[pos]

    print(f"\n{'=' * 65}")
    print(f"{kind} PIVOT TIE AUDIT")
    print(f"Candidate extrema: {candidate_is_extreme}")
    print(f"Tied candidate windows: {total_ties}")
    print(f"Distinct tie patterns: {len(patterns)}")

    print("\nMOST COMMON PATTERNS")
    for pattern, count in patterns.most_common(25):
        print(
            f"Offsets={str(pattern):20s} "
            f"Count={count:3d} "
            f"Example={examples[pattern]}"
        )

    print("\nTIE POSITION SUMMARY")
    left_only = sum(
        count for pattern, count in patterns.items()
        if all(x < 0 for x in pattern if x != 0)
        and 0 in pattern
    )
    right_only = sum(
        count for pattern, count in patterns.items()
        if all(x > 0 for x in pattern if x != 0)
        and 0 in pattern
    )
    both_sides = sum(
        count for pattern, count in patterns.items()
        if any(x < 0 for x in pattern)
        and any(x > 0 for x in pattern)
    )

    print("Ties only to the left:", left_only)
    print("Ties only to the right:", right_only)
    print("Ties on both sides:", both_sides)

print("\nAudit complete. No engine files changed.")
