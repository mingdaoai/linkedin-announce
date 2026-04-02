#!/usr/bin/env uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3>=1.26.0",
# ]
# ///
import os
import subprocess
import sys

def test_ssh_connection():
    ssh_key_path = os.path.expanduser("~/.p_a/qmicro.pem")
    username = "designclub"
    hostname = "ec2-44-235-82-128.us-west-2.compute.amazonaws.com"
    
    print(f"Testing SSH connection to {hostname} with key: {ssh_key_path}")
    
    # First check if key file exists
    if not os.path.exists(ssh_key_path):
        print(f"ERROR: SSH key file not found at {ssh_key_path}")
        return False
    
    print(f"SSH key file exists, permissions: {oct(os.stat(ssh_key_path).st_mode)[-3:]}")
    
    # Test SSH connection with a simple command
    ssh_command = [
        "ssh",
        "-i", ssh_key_path,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        f"{username}@{hostname}",
        "echo 'SSH connection test successful' && hostname && date"
    ]
    
    print(f"Running SSH command: {' '.join(ssh_command)}")
    
    try:
        result = subprocess.run(ssh_command, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            print("SUCCESS: SSH connection test passed!")
            print(f"Output:\n{result.stdout}")
            return True
        else:
            print(f"FAILED: SSH connection test failed with exit code {result.returncode}")
            print(f"stderr:\n{result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("FAILED: SSH connection timed out after 15 seconds")
        return False
    except Exception as e:
        print(f"FAILED: Exception during SSH test: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_ssh_connection()
    sys.exit(0 if success else 1)