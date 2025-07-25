import httpx
import time

import app.explorations.domain as explorations

BASE_URL = "http://localhost:8000"


def main():
    count = 0
    with httpx.Client() as client:
        while True:
            try:
                create_resp = client.post(
                    f"{BASE_URL}/explorations/",
                    json=explorations.ExplorationParameters().model_dump(),
                )
                time.sleep(0.5)
                create_resp.raise_for_status()
                exploration_id = create_resp.json()
                stop_resp = client.post(f"{BASE_URL}/explorations/{exploration_id}/stop")
                stop_resp.raise_for_status()
                count += 1
                print(f"[{count}] Created and stopped exploration {exploration_id}")
            except Exception as e:
                print("Error:", e)
            time.sleep(0.5)


if __name__ == "__main__":
    main()
