#!/usr/bin/env python3
"""
Test script to validate the Copilot setup is working correctly.
This can be used by developers to verify their environment.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def check_file_exists(file_path, description):
    """Check if a file exists and print status."""
    if os.path.exists(file_path):
        print(f"✅ {description}: {file_path}")
        return True
    else:
        print(f"❌ {description}: {file_path} - NOT FOUND")
        return False


def check_json_valid(file_path, description):
    """Check if a JSON file is valid."""
    try:
        with open(file_path, 'r') as f:
            json.load(f)
        print(f"✅ {description}: Valid JSON")
        return True
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"❌ {description}: Invalid JSON - {e}")
        return False


def check_command_available(command, description):
    """Check if a command is available."""
    try:
        result = subprocess.run([command, '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version = result.stdout.strip().split('\n')[0]
            print(f"✅ {description}: {version}")
            return True
        else:
            print(f"❌ {description}: Command failed")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(f"❌ {description}: Command not found")
        return False


def main():
    """Run all validation checks."""
    print("🚀 Validating GitHub Copilot setup for U-Report...")
    print()
    
    all_good = True
    
    # Check documentation files
    docs_checks = [
        ("COPILOT_SETUP.md", "Copilot setup documentation"),
        ("README.md", "Main README"),
    ]
    
    for file_path, description in docs_checks:
        if not check_file_exists(file_path, description):
            all_good = False
    
    print()
    
    # Check VS Code configuration files
    vscode_files = [
        (".vscode/settings.json", "VS Code settings"),
        (".vscode/extensions.json", "VS Code extensions"),
        (".vscode/launch.json", "VS Code launch config"),
        (".vscode/tasks.json", "VS Code tasks"),
    ]
    
    for file_path, description in vscode_files:
        if not check_file_exists(file_path, description):
            all_good = False
        elif not check_json_valid(file_path, description):
            all_good = False
    
    print()
    
    # Check required commands
    command_checks = [
        ("python", "Python"),
        ("poetry", "Poetry"),
        ("node", "Node.js"),
        ("npm", "npm"),
    ]
    
    for command, description in command_checks:
        if not check_command_available(command, description):
            all_good = False
    
    print()
    
    # Check Poetry environment
    try:
        result = subprocess.run(['poetry', 'env', 'info'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Poetry environment: Configured")
        else:
            print("❌ Poetry environment: Not configured")
            all_good = False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ Poetry environment: Cannot check")
        all_good = False
    
    # Check if settings.py symlink exists
    if os.path.exists("ureport/settings.py"):
        print("✅ Django settings: Configured")
    else:
        print("❌ Django settings: ureport/settings.py symlink missing")
        print("   Run: ln -s ureport/settings.py.postgres ureport/settings.py")
        all_good = False
    
    print()
    
    if all_good:
        print("🎉 All checks passed! Your Copilot setup is ready.")
        print("📖 See COPILOT_SETUP.md for usage instructions.")
    else:
        print("❌ Some checks failed. Please review the setup instructions.")
        sys.exit(1)


if __name__ == "__main__":
    main()