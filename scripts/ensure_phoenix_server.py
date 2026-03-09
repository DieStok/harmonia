#!/usr/bin/env python3
"""
Ensure a Phoenix tracing server is running.

Called by exec_apptainer_harmonia.sh before launching experiments.
Manages a singleton Phoenix server via screen + optional SLURM.

Usage:
    ensure_phoenix_server.py [--mode submit|slurm] [--port 6006]
                             [--timeout 120] [--phoenix-dir .phoenix]

Output (stdout):
    PHOENIX_ENDPOINT=http://<host>:<port>

Exit codes:
    0: Server running, endpoint printed
    1: Failed to start server
"""

import argparse
import fcntl
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Ensure Phoenix tracing server is running")
    parser.add_argument("--mode", choices=["submit", "slurm"], default="submit",
                        help="Where to run Phoenix (default: submit node)")
    parser.add_argument("--port", type=int, default=6006,
                        help="Phoenix server port (default: 6006)")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Max seconds to wait for server to start (default: 120)")
    parser.add_argument("--phoenix-dir", type=str, default=".phoenix",
                        help="Phoenix working directory (default: .phoenix)")
    return parser.parse_args()


def check_screen_session(session_name: str) -> bool:
    """Check if a screen session exists and has a running process."""
    result = subprocess.run(
        ["screen", "-ls", session_name],
        capture_output=True, text=True,
    )
    return session_name in result.stdout


def check_slurm_job(job_name: str) -> dict | None:
    """Check if a SLURM job with the given name is running. Returns job info or None."""
    result = subprocess.run(
        ["squeue", "-u", os.environ.get("USER", ""), "--name", job_name,
         "--states=RUNNING,PENDING", "-h", "-o", "%i %N %T"],
        capture_output=True, text=True,
    )
    lines = result.stdout.strip().split("\n")
    for line in lines:
        parts = line.split()
        if len(parts) >= 3:
            return {"job_id": parts[0], "node": parts[1], "state": parts[2]}
    return None


def wait_for_http(url: str, timeout: int) -> bool:
    """Poll URL until it returns 200 or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False


def wait_for_slurm_running(job_name: str, timeout: int) -> dict | None:
    """Wait for SLURM job to reach RUNNING state."""
    start = time.time()
    while time.time() - start < timeout:
        info = check_slurm_job(job_name)
        if info and info["state"] == "RUNNING":
            return info
        time.sleep(5)
    return None


def find_phoenix_command() -> str | None:
    """Find the phoenix command in the project .venv."""
    script_dir = Path(__file__).resolve().parent.parent
    venv_phoenix = script_dir / ".venv" / "bin" / "phoenix"
    if venv_phoenix.exists():
        return str(venv_phoenix)
    # Fallback: check PATH
    phoenix = shutil.which("phoenix")
    return phoenix


def main():
    args = parse_args()
    script_dir = Path(__file__).resolve().parent.parent
    phoenix_dir = (script_dir / args.phoenix_dir).resolve()
    phoenix_dir.mkdir(parents=True, exist_ok=True)

    lock_file = phoenix_dir / "server.lock"
    session_name = "phoenix-tracing"
    slurm_job_name = "llm-tracing-phoenix-arize"

    # Acquire file lock
    lock_fd = open(lock_file, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # Another process is managing the server, wait for lock
        print("Waiting for lock...", file=sys.stderr)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

    try:
        if args.mode == "submit":
            return _handle_submit_mode(args, phoenix_dir, session_name)
        else:
            return _handle_slurm_mode(args, phoenix_dir, slurm_job_name, session_name)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


def _handle_submit_mode(args, phoenix_dir, session_name):
    """Handle submit-node mode: run Phoenix in a screen session on this node."""
    import socket
    hostname = socket.gethostname().split(".")[0]  # Short hostname (e.g., hpcs05)
    # Use hostname so endpoint is reachable from compute nodes too
    endpoint = f"http://{hostname}:{args.port}"
    local_endpoint = f"http://localhost:{args.port}"

    # Check if already running
    if check_screen_session(session_name):
        # Verify it's actually responding (check locally first, faster)
        if wait_for_http(local_endpoint, timeout=10):
            print(f"Phoenix already running on {hostname}:{args.port} "
                  f"(screen session: {session_name})", file=sys.stderr)
            print(f"PHOENIX_ENDPOINT={endpoint}")
            return 0
        else:
            # Screen exists but not responding — kill and restart
            print(f"Screen session {session_name} exists but not responding, restarting...",
                  file=sys.stderr)
            subprocess.run(["screen", "-S", session_name, "-X", "quit"],
                           capture_output=True)
            time.sleep(2)

    # Start Phoenix
    phoenix_cmd = find_phoenix_command()
    if not phoenix_cmd:
        print("Error: phoenix command not found. Install arize-phoenix in .venv.",
              file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["PHOENIX_WORKING_DIR"] = str(phoenix_dir)
    env["PHOENIX_PORT"] = str(args.port)

    cmd = [
        "screen", "-dmS", session_name,
        phoenix_cmd, "serve",
    ]

    print(f"Starting Phoenix server on {hostname} (port {args.port})...", file=sys.stderr)
    subprocess.run(cmd, env=env)

    # Wait for server to be ready
    if wait_for_http(local_endpoint, timeout=args.timeout):
        print(f"Phoenix started on {hostname}:{args.port} "
              f"(screen session: {session_name}, pid via 'screen -ls')", file=sys.stderr)
        print(f"PHOENIX_ENDPOINT={endpoint}")
        return 0
    else:
        print(f"Error: Phoenix server failed to start within {args.timeout}s",
              file=sys.stderr)
        return 1


def _handle_slurm_mode(args, phoenix_dir, slurm_job_name, session_name):
    """Handle SLURM mode: run Phoenix as a SLURM job."""

    # Check if SLURM job already running
    job_info = check_slurm_job(slurm_job_name)
    if job_info and job_info["state"] == "RUNNING":
        node = job_info["node"]
        endpoint = f"http://{node}:{args.port}"
        if wait_for_http(endpoint, timeout=10):
            print(f"PHOENIX_ENDPOINT={endpoint}")
            return 0

    phoenix_cmd = find_phoenix_command()
    if not phoenix_cmd:
        print("Error: phoenix command not found. Install arize-phoenix in .venv.",
              file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["PHOENIX_WORKING_DIR"] = str(phoenix_dir)
    env["PHOENIX_PORT"] = str(args.port)

    # Submit via screen + srun so it persists
    # Phoenix uses PHOENIX_PORT env var (not --port CLI flag)
    srun_cmd = (
        f"PHOENIX_WORKING_DIR={phoenix_dir} PHOENIX_PORT={args.port} "
        f"srun --job-name={slurm_job_name} --account=compgen "
        f"--time=08:00:00 --mem=2G --cpus-per-task=1 --nice=1000 "
        f"{phoenix_cmd} serve"
    )

    cmd = ["screen", "-dmS", session_name, "bash", "-c", srun_cmd]

    print(f"Submitting Phoenix server as SLURM job ({slurm_job_name})...", file=sys.stderr)
    subprocess.run(cmd, env=env)

    # Wait for job to start running
    print("Waiting for SLURM job to reach RUNNING state...", file=sys.stderr)
    job_info = wait_for_slurm_running(slurm_job_name, timeout=args.timeout)
    if not job_info:
        print(f"Error: SLURM job did not start within {args.timeout}s", file=sys.stderr)
        return 1

    node = job_info["node"]
    endpoint = f"http://{node}:{args.port}"

    # Wait for HTTP
    if wait_for_http(endpoint, timeout=60):
        print(f"PHOENIX_ENDPOINT={endpoint}")
        return 0
    else:
        print(f"Error: Phoenix server on {node} not responding after startup",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
