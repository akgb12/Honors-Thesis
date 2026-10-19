#!/usr/bin/env bash
# Starts, stops and reports on the local SeaweedFS S3-compatible server.
# Usage: bash scripts/dev_storage.sh start|stop|status
# Data lives in storage/seaweedfs, the log in .cache/seaweedfs.log, the pid in .cache/seaweedfs.pid.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
cd "$root"
data_dir="storage/seaweedfs"
log_file=".cache/seaweedfs.log"
pid_file=".cache/seaweedfs.pid"
s3_url="http://localhost:8333"

is_running() {
  [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

s3_status() {
  curl -s -o /dev/null -w "%{http_code}" "$s3_url" || true
}

case "${1:-}" in
  start)
    if is_running; then
      echo "SeaweedFS already running (pid $(cat "$pid_file"))"
      exit 0
    fi
    command -v weed >/dev/null || { echo "weed not found: brew install seaweedfs"; exit 1; }
    mkdir -p "$data_dir" .cache
    nohup weed mini -dir="$data_dir" -ip=127.0.0.1 -ip.bind=127.0.0.1 -admin.ui=false >"$log_file" 2>&1 &
    echo $! >"$pid_file"
    for _ in $(seq 1 60); do
      code="$(s3_status)"
      if [ "$code" != "000" ]; then
        echo "SeaweedFS S3 answering on $s3_url (HTTP $code, pid $(cat "$pid_file"))"
        exit 0
      fi
      if ! is_running; then
        echo "SeaweedFS exited early; see $log_file"
        exit 1
      fi
      sleep 1
    done
    echo "SeaweedFS did not answer within 60 s; see $log_file"
    exit 1
    ;;
  stop)
    if is_running; then
      kill "$(cat "$pid_file")"
      echo "Stopped SeaweedFS"
    else
      echo "SeaweedFS is not running"
    fi
    rm -f "$pid_file"
    ;;
  status)
    if is_running; then
      echo "running (pid $(cat "$pid_file")), S3 HTTP $(s3_status)"
    else
      echo "not running"
      exit 1
    fi
    ;;
  *)
    echo "Usage: bash scripts/dev_storage.sh start|stop|status"
    exit 2
    ;;
esac
