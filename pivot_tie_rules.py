import pickle
import pandas as pd

data = pickle.load(open("BARDUSDT_snapshot.pkl", "rb"))
df = data["bars15"].sort_index()

cases = [
    ("2026-11-11 08:00", "HIGH", 1),
    ("2026-11-11 08:15", "HIGH", 0),
    ("2026-11-11 13:15", "LOW", 0),
    ("2026-11-11 13:30", "LOW", 1),
    ("2026-11-11 17:15", "HIGH", 1),
    ("2026-11-11 19:45", "HIGH", 1),
    ("2026-11-11 21:45", "LOW", 0),
    ("2026-11-12 00:15", "HIGH", 0),
    ("2026-11-12 00:30", "HIGH", 0),
    ("2026-11-12 00:45", "HIGH", 1),
    ("2026-11-12 11:00", "HIGH", 1),
    ("2026-11-13 05:00", "HIGH", 0),
    ("2026-11-13 05:30", "HIGH", 0),
]

records = []

for timestamp, kind, pine in cases:
    ts = pd.Timestamp(timestamp)

    if ts not in df.index:
        print("MISSING:", timestamp)
        continue

    pos = df.index.get_loc(ts)
    if pos < 4 or pos + 4 >= len(df):
        print("INSUFFICIENT:", timestamp)
        continue

    col = "high" if kind == "HIGH" else "low"
    window = df.iloc[pos-4:pos+5][col].astype(float).to_numpy()
    candidate = window[4]
    extreme = window.max() if kind == "HIGH" else window.min()

    offsets = [
        i - 4 for i, value in enumerate(window)
        if value == extreme
    ]

    left = [x for x in offsets if x < 0]
    right = [x for x in offsets if x > 0]

    records.append({
        "time": timestamp,
        "kind": kind,
        "pine": pine,
        "left": len(left),
        "right": len(right),
        "total": len(offsets),
        "leftmost": offsets[0] == 0,
        "rightmost": offsets[-1] == 0,
    })

if len(records) != len(cases):
    print("Some cases were missing; audit is incomplete.")

def evaluate(name, rule):
    correct = []
    wrong = []

    for r in records:
        predicted = int(bool(rule(r)))
        if predicted == r["pine"]:
            correct.append(r["time"])
        else:
            wrong.append((r["time"], r["pine"], predicted))

    return len(correct), name, wrong

rules = [
    ("Reject all ties", lambda r: r["total"] == 1),
    ("Accept leftmost", lambda r: r["leftmost"]),
    ("Accept rightmost", lambda r: r["rightmost"]),
    ("No left ties", lambda r: r["left"] == 0),
    ("No right ties", lambda r: r["right"] == 0),
    ("Only left ties", lambda r: r["left"] > 0 and r["right"] == 0),
    ("Only right ties", lambda r: r["right"] > 0 and r["left"] == 0),
    ("HIGH leftmost / LOW rightmost",
     lambda r: r["leftmost"] if r["kind"] == "HIGH" else r["rightmost"]),
    ("HIGH rightmost / LOW leftmost",
     lambda r: r["rightmost"] if r["kind"] == "HIGH" else r["leftmost"]),
]

# Exhaustive count-threshold rules.
for max_left in range(5):
    for max_right in range(5):
        rules.append((
            f"left<={max_left} AND right<={max_right}",
            lambda r, a=max_left, b=max_right:
                r["left"] <= a and r["right"] <= b
        ))

        rules.append((
            f"left<={max_left} OR right<={max_right}",
            lambda r, a=max_left, b=max_right:
                r["left"] <= a or r["right"] <= b
        ))

# Different count thresholds for highs and lows.
for hl in range(5):
    for hr in range(5):
        for ll in range(5):
            for lr in range(5):
                rules.append((
                    f"H({hl},{hr}) L({ll},{lr})",
                    lambda r, a=hl, b=hr, c=ll, d=lr:
                        (r["left"] <= a and r["right"] <= b)
                        if r["kind"] == "HIGH"
                        else (r["left"] <= c and r["right"] <= d)
                ))

results = [evaluate(name, rule) for name, rule in rules]
results.sort(key=lambda x: (-x[0], x[1]))

print("\nPIVOT TIE RULE AUDIT")
print("Cases:", len(records))
print("\nTOP 20 RULES")
for score, name, wrong in results[:20]:
    print(f"{score}/{len(records)} | {name}")
    if score == len(records):
        print("  PERFECT MATCH on these cases")

print("\nBEST RULE DETAILS")
best_score, best_name, best_wrong = results[0]
print("Rule:", best_name)
print("Accuracy:", f"{best_score}/{len(records)}")

if best_wrong:
    print("Mismatches:")
    for timestamp, pine, predicted in best_wrong:
        print(f"  {timestamp} | Pine={pine} | Rule={predicted}")
else:
    print("No mismatches.")

print("\nCASE FEATURES")
for r in records:
    print(
        f'{r["time"]} | {r["kind"]} | Pine={r["pine"]} '
        f'| left={r["left"]} right={r["right"]} '
        f'| leftmost={r["leftmost"]} rightmost={r["rightmost"]}'
    )

print("\nNo project engine files were changed.")
