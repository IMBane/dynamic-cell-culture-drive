import pandas as pd

CSV_FILE = "motor_movements.csv"

# Read CSV
df = pd.read_csv(CSV_FILE)

# Remove possible spaces from column names
df.columns = df.columns.str.strip()

# Get expected amplitude from the data
amplitude = df["target_position"].abs().max()

# Allowed sequence
expected_patterns = [
    [amplitude, 0, -amplitude, 0],
    [-amplitude, 0, amplitude, 0],
]

errors = []

# Check every point
for i, value in enumerate(df["target_position"]):

    # Current position rounded to avoid float issues
    value = round(value)

    # Position in the repeating pattern
    index = i % 4

    valid = False

    for pattern in expected_patterns:
        if value == pattern[index]:
            valid = True
            break

    if not valid:
        errors.append(
            {
                "timestamp": df.iloc[i]["timestamp"],
                "position": value,
                "expected": [
                    pattern[index] for pattern in expected_patterns
                ],
            }
        )

# Print results
if errors:
    print("❌ Invalid sinusoid detected:")
    for error in errors:
        print(
            f"Timestamp: {error['timestamp']}, "
            f"Position: {error['position']}, "
            f"Expected: {error['expected']}"
        )
else:
    print("✅ Sinusoid is correct. No errors found.")