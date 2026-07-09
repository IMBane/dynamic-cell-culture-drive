import pandas as pd
import matplotlib.pyplot as plt

# -----------------------
# Load CSV
# -----------------------
df = pd.read_csv("motor_movements.csv")

# -----------------------
# Normalize target positions to [-10, 10]
# -----------------------
max_abs = df["target_position"].abs().max()

if max_abs > 0:
    df["target_position"] = (
        df["target_position"] / max_abs
    ) * 10

# -----------------------
# Build time axis
# -----------------------
time = [0.0]
position = [df.iloc[0]["target_position"]]

current_time = 0.0

for _, row in df.iterrows():
    target = row["target_position"]
    move_time = row["move_duration"] / 1000.0      # Convert ms to seconds
    hold_time = row["standstill_duration"]         # Seconds

    # Motor reaches the next target
    current_time += move_time
    time.append(current_time)
    position.append(target)

    # Hold at the target position
    if hold_time > 0:
        current_time += hold_time
        time.append(current_time)
        position.append(target)

# -----------------------
# Plot
# -----------------------
plt.figure(figsize=(12, 5))
plt.plot(time, position, linewidth=2)

plt.title("Normalized Motor Target Position")
plt.xlabel("Time (s)")
plt.ylabel("Normalized Position (±10)")
plt.ylim(-10.5, 10.5)
plt.grid(True)

plt.tight_layout()
plt.show()