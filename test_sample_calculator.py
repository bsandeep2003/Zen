import subprocess
import sys
import os

def main():
    # Path to the actual test script inside the backend directory
    script_path = os.path.join(os.path.dirname(__file__), "backend", "test_sample_calculator.py")
    # Execute the test script using the same Python interpreter
    result = subprocess.run([sys.executable, script_path], capture_output=True, text=True)
    # Forward the output and exit code
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
