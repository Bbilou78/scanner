from pathlib import Path
import shutil

path = Path("swh_v26_engine.py")
source = path.read_text()

start = source.index("def pivot_at(")
end = source.index("\ndef prepare_htf(", start)

new_function = '''def pivot_at(values, pos, length, is_low):
    left = pos - length
    right = pos + length

    if left < 0 or right >= len(values):
        return False

    candidate = values[pos]
    left_values = values[left:pos]
    right_values = values[pos + 1:right + 1]

    if is_low:
        return (
            candidate <= np.min(left_values)
            and candidate < np.min(right_values)
        )

    return (
        candidate >= np.max(left_values)
        and candidate > np.max(right_values)
    )


'''

backup = Path("swh_v26_engine.py.bak")
if not backup.exists():
    shutil.copy2(path, backup)

path.write_text(source[:start] + new_function + source[end + 1:])

print("SUCCESS: pivot_at updated.")
print("Backup:", backup)
