import time
import json
import pickle
import torch
import torch.nn as nn
import re
from collections import deque
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# --- CONFIGURATION ---
LOG_FILE_TO_WATCH = "system_logs.txt"  # The file you want to monitor
MODEL_PATH = "best_model.pth"
PARSER_PATH = "drain3_state.bin"
MAP_PATH = "template_map.json"

# InfluxDB Config (Fill these in from Phase 2)
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "DyIC3hEVIw8Acp2CVmF1qfPqpRZo6d1PU-pgP-pKtm4wUgdKqTwDCsxZc_KIQ0ZAup2Qlm23Jfzu9FlzYrBJIw=="
INFLUX_ORG = "IIT PATNA"
INFLUX_BUCKET = "logs_bucket"

# --- MODEL DEFINITION (Must match exactly) ---
class DeepLog(nn.Module):
    def __init__(self, n_templates, embedding_dim=256, hidden_size=256, num_layers=2):
        super(DeepLog, self).__init__()
        self.embedding = nn.Embedding(n_templates, embedding_dim)
        # Note: We use dropout=0 because we are in eval mode, but structure must match
        self.lstm = nn.LSTM(input_size=embedding_dim, hidden_size=hidden_size, num_layers=num_layers, batch_first=True, dropout=0.2)
        self.fc = nn.Linear(hidden_size, n_templates)

    def forward(self, x):
        embedded_x = self.embedding(x)
        lstm_out, _ = self.lstm(embedded_x)
        out = self.fc(lstm_out[:, -1, :])
        return out

# --- SETUP ---
print("Loading system...")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 1. Load Mappings
with open(MAP_PATH, 'r') as f:
    template_to_int = json.load(f)
n_templates = len(template_to_int)

# 2. Load Parser
with open(PARSER_PATH, 'rb') as f:
    parser = pickle.load(f)

# 3. Load Model
model = DeepLog(n_templates).to(device)
model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
model.eval()

# 4. Setup InfluxDB Client
write_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = write_client.write_api(write_options=SYNCHRONOUS)

# 5. Initialize Sliding Window
# We keep the last 10 events in memory
window_size = 10
sequence_buffer = deque(maxlen=window_size)
# Pre-fill buffer with padding (0) so it works immediately
for _ in range(window_size):
    sequence_buffer.append(0)

print(f"System Monitor Running... watching {LOG_FILE_TO_WATCH}")

# --- MAIN LOOP (Real-Time Tailing) ---
def follow(thefile):
    thefile.seek(0, 2) # Go to the end of the file
    while True:
        line = thefile.readline()
        if not line:
            time.sleep(0.1) # Sleep briefly
            continue
        yield line

events_seen = 0 # <--- NEW: Counter to track warm-up

with open(LOG_FILE_TO_WATCH, "r", encoding='latin-1') as logfile:
    loglines = follow(logfile)
    
    for line in loglines:
        line = line.strip()
        if not line: continue

        # 1. Parse Log
        result = parser.add_log_message(line)
        template_id = result["cluster_id"]

        # 2. Convert to Int
        event_id = template_to_int.get(str(template_id), 0)

        # 3. Form Sequence from Buffer
        current_window = list(sequence_buffer)
        input_tensor = torch.tensor([current_window], dtype=torch.long).to(device)

        # 4. Predict (ONLY IF WARMED UP)
        events_seen += 1
        if events_seen > window_size:
            with torch.no_grad():
                output = model(input_tensor)
                _, top_k = torch.topk(output, k=4, dim=1)
                top_k = top_k.cpu().numpy()[0]
                is_anomaly = 1 if event_id not in top_k else 0
        else:
            # Assume normal while building context buffer
            is_anomaly = 0 

        # 5. Update Buffer for next turn
        sequence_buffer.append(event_id)

        # 6. Send to Grafana (InfluxDB)
        point = Point("log_events") \
            .field("is_anomaly", is_anomaly) \
            .field("raw_log", line) \
            .tag("status", "Anomaly" if is_anomaly else "Normal")
            
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        
        # 7. Print Status to Terminal
        if events_seen <= window_size:
            print(f"[WARM-UP {events_seen}/10] {line[:60]}...")
        elif is_anomaly:
            print(f"[ALERT] Anomaly Detected! Log: {line[:60]}...")
        else:
            print(f"[OK] {line[:60]}...")