#!/usr/bin/env python3
"""
PrintHub Agent Setup Tool
Run this ONCE on each new workstation before starting the service.
Usage: python agent_setup.py --code A3F9B2C1 --server http://printhub.hospital.internal:8000
"""
import argparse
import sys
import os

# Ensure we can import from current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_config import write_pending_registration, load_config, is_first_run

def main():
    parser = argparse.ArgumentParser(description="PrintHub Agent Setup")
    parser.add_argument("--code", help="Activation code from IT administrator")
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="PrintHub server URL")
    parser.add_argument("--status", action="store_true", help="Show current registration status")
    args = parser.parse_args()
    
    if args.status:
        config = load_config()
        if config.get("agent_id"):
            print(f"✅ Agent registered: {config['agent_id']} at location {config.get('location_id')}")
            print(f"   Server: {config.get('server_url')}")
        else:
            print("❌ Not registered. Run: python agent_setup.py --code YOUR_CODE")
        return
    
    if not args.code:
        parser.print_help()
        sys.exit(1)
        
    if not is_first_run():
        print("⚠️  Agent is already registered.")
        print("To re-register, delete 'agent_config.json' first.")
        sys.exit(1)
    
    # Normalize server URL (ensure no trailing slash)
    server_url = args.server.rstrip("/")
    
    write_pending_registration(args.code, server_url)
    print(f"✅ Activation code saved for {server_url}")
    print(f"Next steps:")
    print(f"1. Start the service: python agent_service.py start")
    print(f"2. The agent will register automatically on first start.")

if __name__ == "__main__":
    main()
