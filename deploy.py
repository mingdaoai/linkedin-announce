#!/usr/bin/env uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3>=1.26.0",
# ]
# ///
import os
import subprocess
import tempfile
import boto3
import json
import time
import sys
from datetime import datetime

# target machine uses tcsh, so command syntax is different from bash
# target machine has virtualenv installed in ~/venv

def get_instance_hostname(instance_id):
    print(f"Attempting to get hostname for instance ID: {instance_id}")
    ec2 = boto3.client('ec2')
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        # Prefer public DNS name, fall back to public IP
        hostname = instance.get('PublicDnsName') or instance.get('PublicIpAddress')
        if not hostname:
            raise Exception("Instance has no public DNS name or IP address")
        print(f"Successfully retrieved hostname: {hostname}")
        return hostname
    except Exception as e:
        print(f"Failed to get instance hostname: {str(e)}")
        return None

def run_remote_command(hostname, command):
    print(f"Running remote command on {hostname}: {command}")
    ssh_key_path = os.path.expandvars(os.environ["HOME"] + "/p_a/qmicro.pem")
    username = "designclub"
    
    ssh_command = [
        "ssh",
        "-i", ssh_key_path,
        "-o", "StrictHostKeyChecking=no",
        f"{username}@{hostname}",
        command
    ]
    
    result = subprocess.run(ssh_command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Command failed: {result.stderr}")
        return False
    print(f"Command succeeded: {result.stdout}")
    return True

def refresh_linkedin_token():
    """Run linkedin_signin.py to refresh the token"""
    linkedin_signin_path = os.path.expanduser('~/mingdao/python/linkedinApi/linkedin_signin.py')
    if not os.path.exists(linkedin_signin_path):
        print(f"Error: linkedin_signin.py not found at {linkedin_signin_path}")
        return False
    
    print("Running LinkedIn sign-in to refresh token...")
    result = subprocess.run([sys.executable, linkedin_signin_path], 
                          capture_output=False)
    return result.returncode == 0

def deploy_files(hostname):
    print(f"Starting deployment to {hostname}")
    ssh_key_path = os.path.expandvars(os.environ["HOME"] + "/p_a/qmicro.pem")
    username = "designclub"
    
    try:
        # Validate LinkedIn token expiration
        print("Validating LinkedIn token expiration")
        token_path = os.path.expandvars(os.environ["HOME"] + "/.mingdaoai/linkedin_token.json")
        
        # Check if token file exists
        if not os.path.exists(token_path):
            print(f"LinkedIn token file not found at {token_path}")
            response = input("Would you like to refresh the token now? (y/n): ").strip().lower()
            if response == 'y':
                if refresh_linkedin_token():
                    print("Token refreshed successfully. Continuing with deployment...")
                else:
                    print("Failed to refresh token. Exiting.")
                    return False
            else:
                print("Token file is required. Exiting.")
                return False
        else:
            with open(token_path, 'r') as f:
                token_data = json.load(f)
                expires_at = token_data.get('expires_at')
                current_time = int(time.time())
                
                if expires_at:
                    # Convert timestamps to local time
                    expires_local = datetime.fromtimestamp(expires_at).strftime('%Y-%m-%d %H:%M:%S')
                    current_local = datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')
                    
                    print(f"Current local time: {current_local}")
                    print(f"Token expires at local time: {expires_local}")
                    
                    if current_time >= expires_at:
                        print("\n" + "="*60)
                        print("WARNING: LinkedIn token has expired!")
                        print("="*60)
                        response = input("Would you like to refresh the token now? (y/n): ").strip().lower()
                        if response == 'y':
                            if refresh_linkedin_token():
                                print("Token refreshed successfully. Continuing with deployment...")
                            else:
                                print("Failed to refresh token. Exiting.")
                                return False
                        else:
                            print("Deployment cancelled. Please refresh the token manually.")
                            return False
                    else:
                        print("LinkedIn token is valid")
                else:
                    print("Warning: Token file does not have expires_at field")
        
        # Create remote directory
        print("Creating remote directory ~/linkedin-announce")
        run_remote_command(hostname, 'mkdir -p ~/linkedin-announce')
        
        # Get the current script's directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Files to transfer
        files_to_transfer = [
            'linkedin_poster.py',
            'linkedin_api.py',
            'video_list.txt',
            'history.txt',
            'videoUtil.py'
        ]
        
        # Transfer each file using scp
        for file in files_to_transfer:
            local_path = os.path.join(current_dir, file)
            if os.path.exists(local_path):
                print(f"Transferring file: {file}")
                
                # Special handling for videoUtil.py symlink
                if file == 'videoUtil.py' and os.path.islink(local_path):
                    # Create a temporary file with the actual content
                    with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
                        with open(os.path.realpath(local_path), 'r') as source_file:
                            temp_file.write(source_file.read())
                        temp_file.flush()
                        
                        # Use the temporary file for SCP
                        scp_command = [
                            "scp",
                            "-i", ssh_key_path,
                            "-o", "StrictHostKeyChecking=no",
                            temp_file.name,
                            f"{username}@{hostname}:~/linkedin-announce/{file}"
                        ]
                        result = subprocess.run(scp_command, capture_output=True, text=True)
                        os.unlink(temp_file.name)
                else:
                    # Normal file transfer
                    scp_command = [
                        "scp",
                        "-i", ssh_key_path,
                        "-o", "StrictHostKeyChecking=no",
                        local_path,
                        f"{username}@{hostname}:~/linkedin-announce/"
                    ]
                    result = subprocess.run(scp_command, capture_output=True, text=True)
                
                if result.returncode == 0:
                    print(f"Transferred {file} successfully")
                    # Make executable
                    run_remote_command(hostname, f'chmod +x ~/linkedin-announce/{file}')
                else:
                    print(f"Warning: Failed to transfer {file}: {result.stderr}")
            else:
                print(f"Warning: {file} not found locally")
        
        # Transfer LinkedIn token - Required for LinkedIn API authentication
        print("Transferring LinkedIn token")
        run_remote_command(hostname, 'mkdir -p ~/.mingdaoai')
        
        if os.path.exists(token_path):
            scp_command = [
                "scp",
                "-i", ssh_key_path,
                "-o", "StrictHostKeyChecking=no",
                token_path,
                f"{username}@{hostname}:~/.mingdaoai/"
            ]
            result = subprocess.run(scp_command, capture_output=True, text=True)
            if result.returncode == 0:
                print("LinkedIn token transferred successfully")
                # Verify the token was transferred correctly
                verify_command = f"ls -la ~/.mingdaoai/linkedin_token.json"
                if run_remote_command(hostname, verify_command):
                    print("LinkedIn token verification successful")
                else:
                    print("Warning: Could not verify LinkedIn token on remote server")
            else:
                print(f"Error: Failed to transfer LinkedIn token: {result.stderr}")
                return False
        else:
            print(f"Error: LinkedIn token file not found at {token_path}")
            return False
        
        # Install required Python packages
        print("Installing required Python packages")
        run_remote_command(hostname, '~/venv/bin/pip3 install boto3')
        
        # Setup cron job
        print("Setting up cron job")
        cron_command = '30 9 * * * cd ~/linkedin-announce; ~/venv/bin/python3 linkedin_poster.py >> ~/linkedin-announce/cron.log 2>&1'
        
        # Get existing crontab
        print("Retrieving existing crontab")
        temp_cron = subprocess.run(
            ["ssh", "-i", ssh_key_path, f"{username}@{hostname}", "crontab -l"],
            capture_output=True,
            text=True
        )
        
        # Create new crontab content
        crontab_lines = []
        if temp_cron.returncode == 0:
            crontab_lines = [line for line in temp_cron.stdout.splitlines() if 'linkedin_poster.py' not in line]
        crontab_lines.append(cron_command)
        
        # Write to temporary file
        print("Writing new crontab to temporary file")
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_file.write('\n'.join(crontab_lines) + '\n')
            temp_file.flush()
            
            # Upload and install new crontab
            print("Uploading new crontab")
            scp_command = [
                "scp",
                "-i", ssh_key_path,
                "-o", "StrictHostKeyChecking=no",
                temp_file.name,
                f"{username}@{hostname}:~/temp_crontab"
            ]
            subprocess.run(scp_command, check=True)
        
        # Install the new crontab
        print("Installing new crontab")
        run_remote_command(hostname, '/usr/bin/crontab ~/temp_crontab; /bin/rm ~/temp_crontab')
        os.unlink(temp_file.name)
        
        print("Deployment completed successfully!")
        print("Cron job installed to run at 9:30 AM daily")
        
    except Exception as e:
        print(f"Deployment failed: {str(e)}")
        return False
    
    return True

def main():
    instance_id = "i-063a96df297aba7ec"
    print(f"Starting deployment process for instance ID: {instance_id}")
    hostname = get_instance_hostname(instance_id)
    if hostname:
        deploy_files(hostname)
    else:
        print("Failed to get instance hostname")

if __name__ == "__main__":
    main() 