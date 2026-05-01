import time
import random
import os

# --- CONFIGURATION ---
# The massive log file you downloaded from Kaggle
SOURCE_LOG_FILE = "HDFS.log" 
# The live file your Grafana/Monitor script is watching
TARGET_LOG_FILE = "system_logs.txt" 

print("========================================")
print(" Autonomous HDFS Log Generator Started")
print("========================================")

# Verify source file exists
if not os.path.exists(SOURCE_LOG_FILE):
    print(f"[ERROR] Could not find {SOURCE_LOG_FILE}.")
    print("Please make sure your massive HDFS dataset is in this folder.")
    exit()

print(f"Reading from: {SOURCE_LOG_FILE}")
print(f"Streaming to: {TARGET_LOG_FILE}")
print("Press Ctrl+C to stop the stream.\n")

try:
    with open(SOURCE_LOG_FILE, 'r', encoding='latin-1') as source:
        # Open target file in 'append' mode
        with open(TARGET_LOG_FILE, 'a', encoding='latin-1') as target:
            lines_sent = 0
            
            for line in source:
                target.write(line)
                target.flush() # Force Windows to write it to disk immediately
                lines_sent += 1
                
                if lines_sent % 50 == 0:
                    print(f"Streamed {lines_sent} logs autonomously...")
                
                # Simulate realistic real-time delays (between 0.05 and 0.3 seconds)
                # This makes the Grafana graphs look incredibly natural and alive!
                time.sleep(random.uniform(3, 9))

except KeyboardInterrupt:
    print("\nLog Generator stopped by user.")