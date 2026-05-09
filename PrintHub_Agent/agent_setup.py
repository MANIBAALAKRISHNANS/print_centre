#!/usr/bin/env python3
"""
PrintHub Agent Setup Tool
Run this ONCE on each new workstation before starting the service.

Usage:
  python agent_setup.py --code A3F9B2C1 --server http://192.168.1.50:8000
  python agent_setup.py --code A3F9B2C1 --server https://printhub.hospital.local --no-verify
  python agent_setup.py --status
  python agent_setup.py --reset
"""
import argparse
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_config import write_pending_registration, load_config, is_first_run, clear_credentials


def main():
    parser = argparse.ArgumentParser(
        description="PrintHub Agent Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--code",      help="Activation code from IT administrator (8 characters)")
    parser.add_argument("--server",    default="http://127.0.0.1:8000", help="PrintHub server URL")
    parser.add_argument("--no-verify", action="store_true",
                        help="Disable TLS certificate verification (for self-signed certs)")
    parser.add_argument("--status",    action="store_true", help="Show current registration status")
    parser.add_argument("--reset",     action="store_true",
                        help="Clear stored credentials to allow re-registration")
    args = parser.parse_args()

    if args.status:
        config = load_config()
        if config.get("agent_id"):
            print(f"Agent ID : {config['agent_id']}")
            print(f"Location : {config.get('location_id', 'unknown')}")
            print(f"Server   : {config.get('server_url', 'unknown')}")
            print(f"TLS      : {'disabled (--no-verify)' if not config.get('tls_verify', True) else 'enabled'}")
        elif config.get("pending_activation_code"):
            print(f"Status   : Pending registration")
            print(f"Server   : {config.get('server_url', 'unknown')}")
        else:
            print("Status   : Not configured")
            print("Run      : python agent_setup.py --code YOUR_CODE --server SERVER_URL")
        return

    if args.reset:
        confirm = input("This will delete all credentials and de-register this agent. Continue? [y/N] ")
        if confirm.strip().lower() != "y":
            print("Aborted.")
            sys.exit(0)
        clear_credentials()
        print("Credentials cleared. Run agent_setup.py --code ... to re-register.")
        return

    if not args.code:
        parser.print_help()
        sys.exit(1)

    code = args.code.strip().upper()
    if len(code) != 8:
        print(f"ERROR: Activation code must be exactly 8 characters (got {len(code)}).")
        sys.exit(1)

    if not is_first_run():
        print("WARNING: Agent is already registered.")
        print("Use --reset first if you want to re-register this machine.")
        sys.exit(1)

    server_url = args.server.rstrip("/")
    tls_verify = not args.no_verify

    write_pending_registration(code, server_url, tls_verify)

    print(f"\nActivation code saved.")
    print(f"  Server : {server_url}")
    print(f"  TLS    : {'disabled (self-signed cert)' if not tls_verify else 'enabled'}")
    print(f"\nNext steps:")
    print(f"  Windows : python agent_service.py install  (then: python agent_service.py start)")
    print(f"  macOS   : bash install_agent.sh")
    print(f"  Manual  : python agent.py")
    print(f"\nThe agent will self-register on first start.")


if __name__ == "__main__":
    main()
