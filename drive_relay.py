import os
import sys
import json
import time
import subprocess
import shutil
from pathlib import Path

# Josie absolute paths
PROJECT_ROOT = Path("D:/Josie")
RCLONE_EXE = Path(r"C:\Users\dusti\OneDrive\Documents\rclone.exe")
RCLONE_REMOTE = "gdrive:Josie Project/_JOSIE_CONTROL"

LOCAL_INBOX = PROJECT_ROOT / "data" / "private" / "relay_inbox"
LOCAL_RESULTS = PROJECT_ROOT / "data" / "private" / "relay_results"

# Ensure directories exist
LOCAL_INBOX.mkdir(parents=True, exist_ok=True)
LOCAL_RESULTS.mkdir(parents=True, exist_ok=True)

# Add mission_manager to path so we can import it
sys.path.insert(0, str(PROJECT_ROOT))
from mission_manager.dispatcher import MissionManager
from mission_manager.ingress import continue_mission


def sync_inbox():
    """Use rclone to move new missions from Google Drive to local inbox."""
    try:
        subprocess.run(
            [str(RCLONE_EXE), "move", f"{RCLONE_REMOTE}/INBOX", str(LOCAL_INBOX), "--include", "*.json", "--quiet"],
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"[RELAY] rclone sync failed. Is OAuth configured? Run: rclone config")
        return False
    except FileNotFoundError:
        print(f"[RELAY] rclone.exe not found at {RCLONE_EXE}")
        return False
    return True


def upload_results():
    """Use rclone to move receipts from local results to Google Drive."""
    try:
        subprocess.run(
            [str(RCLONE_EXE), "move", str(LOCAL_RESULTS), f"{RCLONE_REMOTE}/RESULTS", "--quiet"],
            check=True
        )
    except subprocess.CalledProcessError:
        pass


def process_missions():
    """Process any JSON files found in the local inbox."""
    for mission_file in LOCAL_INBOX.glob("*.json"):
        print(f"[RELAY] Processing new mission: {mission_file.name}")
        try:
            plan = json.loads(mission_file.read_text(encoding="utf-8"))
            mission_id = plan.get("mission_id")
            if not mission_id:
                raise ValueError("Missing mission_id in payload")
            
            # Create the mission in the state database
            manager = MissionManager(
                mission_directory=PROJECT_ROOT / "data" / "private" / "missions",
                receipt_directory=PROJECT_ROOT / "data" / "private" / "supervisor-local-code",
                work_order_directory=PROJECT_ROOT / "data" / "private" / "supervisor-work-orders"
            )
            
            # Only create if it doesn't already exist (Idempotency)
            try:
                manager.load(mission_id)
                print(f"[RELAY] Mission {mission_id} already exists. Resuming...")
            except FileNotFoundError:
                manager.create(plan)
                print(f"[RELAY] Mission {mission_id} created.")

            # Execute the mission until blocked or complete
            outcome = continue_mission(mission_id, project_root=PROJECT_ROOT)
            
            # Write the result to the outbox
            result_file = LOCAL_RESULTS / f"{mission_id}_receipt.json"
            result_file.write_text(json.dumps(outcome, indent=2), encoding="utf-8")
            print(f"[RELAY] Mission {mission_id} finished. Receipt generated.")
            
            # Move the original plan out of the inbox so we don't reprocess it
            mission_file.unlink()

        except Exception as e:
            print(f"[RELAY] Error processing {mission_file.name}: {e}")
            # Write error receipt
            error_file = LOCAL_RESULTS / f"{mission_file.stem}_error.json"
            error_file.write_text(json.dumps({"status": "failed", "error": str(e)}), encoding="utf-8")
            mission_file.unlink()


def run_once():
    if not RCLONE_EXE.exists():
        print(f"FATAL: rclone.exe not found at {RCLONE_EXE}")
        sys.exit(1)
        
    print("[RELAY] Polling external INBOX via rclone...")
    sync_inbox()
    process_missions()
    print("[RELAY] Uploading RESULTS via rclone...")
    upload_results()

if __name__ == "__main__":
    run_once()
