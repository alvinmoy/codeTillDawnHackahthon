#!/usr/bin/env bash
# One command to run all of Sayam.
#
#   bash run_sayam.sh                 # full demo (camera + vitals + notes + voice)
#   bash run_sayam.sh --no-vitals     # skip Presage vitals
#   bash run_sayam.sh --no-notes      # skip the notes brain
#
# Starts the Reachy Mini daemon, waits for the robot to be ready (auto-recovers
# if the daemon is wedged), then launches the app.
cd "$(dirname "$0")"
source reachy_mini_env/bin/activate

robot_ready() {
  [ "$(curl -s -o /dev/null -w '%{http_code}' -m2 \
      http://localhost:8000/api/state/present_head_pose 2>/dev/null)" = "200" ]
}

start_daemon() {
  echo "Starting Reachy Mini daemon..."
  reachy-mini-daemon > /tmp/reachy_daemon.log 2>&1 &
}

wait_ready() {  # wait up to ~50s
  for _ in $(seq 1 25); do robot_ready && return 0; sleep 2; done
  return 1
}

# Start the daemon if nothing is serving on :8000.
curl -fsS -m2 http://localhost:8000/docs >/dev/null 2>&1 || start_daemon

echo "Waiting for the robot to wake up..."
if ! wait_ready; then
  # Wedged daemon — clean restart once and wait again.
  echo "Daemon not ready; doing a clean restart..."
  pkill -9 -f reachy-mini-daemon 2>/dev/null || true
  sleep 3
  start_daemon
  if ! wait_ready; then
    echo "Robot still not ready. Check the cable, then see /tmp/reachy_daemon.log"
    exit 1
  fi
fi

echo "Robot ready. Launching Sayam..."
cd sayam
exec python live_view.py "$@"
