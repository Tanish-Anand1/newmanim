"""Run pipeline with real-time logging to a file."""
import sys, os, subprocess, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_pipeline_output.txt")

with open(log_file, "w", encoding="utf-8") as f:
    f.write(f"Pipeline started at {time.strftime('%H:%M:%S')}\n")
    f.flush()

    proc = subprocess.Popen(
        [sys.executable, "run_job.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    for line in proc.stdout:
        f.write(line)
        f.flush()

    proc.wait()
    f.write(f"\nPipeline finished at {time.strftime('%H:%M:%S')} exit_code={proc.returncode}\n")
    f.flush()

print(f"Done. See {log_file}", flush=True)