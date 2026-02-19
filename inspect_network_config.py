#!/usr/bin/env python3
"""
Docker Network Configuration Inspector
Inspects and displays network configuration for debugging.
"""

import subprocess
import json
import sys

def run_command(cmd):
    """Run a command and return the output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1

def inspect_container(container_name):
    """Inspect a container's network configuration."""
    print(f"\n🔍 Inspecting {container_name}")
    print("=" * 50)

    # Get container network info
    cmd = f"docker inspect {container_name} --format='{{{{json .NetworkSettings}}}}'"
    stdout, stderr, code = run_command(cmd)

    if code != 0:
        print(f"❌ Error inspecting container: {stderr}")
        return False

    try:
        network_info = json.loads(stdout)

        # Basic network info
        print(f"Network Mode: {network_info.get('NetworkMode', 'N/A')}")

        # Ports
        ports = network_info.get('Ports', {})
        if ports:
            print("Port Mappings:")
            for internal_port, external_bindings in ports.items():
                if external_bindings:
                    for binding in external_bindings:
                        print(f"  {internal_port} -> {binding.get('HostIp', '0.0.0.0')}:{binding.get('HostPort', 'N/A')}")
                else:
                    print(f"  {internal_port} (not mapped)")
        else:
            print("Port Mappings: None (likely using host networking)")

        # Networks
        networks = network_info.get('Networks', {})
        if networks:
            print("Networks:")
            for network_name, network_config in networks.items():
                ip_address = network_config.get('IPAddress', 'N/A')
                gateway = network_config.get('Gateway', 'N/A')
                print(f"  {network_name}: IP={ip_address}, Gateway={gateway}")

        # Extra hosts
        extra_hosts = network_info.get('ExtraHosts', [])
        if extra_hosts:
            print("Extra Hosts:")
            for host in extra_hosts:
                print(f"  {host}")

        return True

    except json.JSONDecodeError as e:
        print(f"❌ Error parsing network info: {e}")
        return False

def check_docker_networks():
    """List Docker networks."""
    print("\n🌐 Docker Networks")
    print("=" * 50)

    stdout, stderr, code = run_command("docker network ls")
    if code == 0:
        print(stdout)
    else:
        print(f"❌ Error listing networks: {stderr}")

def check_port_bindings():
    """Check what ports Docker is binding."""
    print("\n🔌 Docker Port Bindings")
    print("=" * 50)

    # Check for our specific ports
    for port in [3111, 8511]:
        stdout, stderr, code = run_command(f"docker port trader_intelligence_v2_frontend_1 {port} 2>/dev/null || echo 'Not bound'")
        if "Not bound" not in stdout and stdout:
            print(f"Port {port}: {stdout}")
        else:
            # Try backend container
            stdout, stderr, code = run_command(f"docker port trader_intelligence_v2_backend_1 {port} 2>/dev/null || echo 'Not bound'")
            if "Not bound" not in stdout and stdout:
                print(f"Port {port}: {stdout}")
            else:
                print(f"Port {port}: Not bound (may be using host networking)")

def test_host_docker_internal():
    """Test host.docker.internal resolution from containers."""
    print("\n🏠 host.docker.internal Resolution Test")
    print("=" * 50)

    containers = ['trader_intelligence_v2_frontend_1', 'trader_intelligence_v2_backend_1']

    for container in containers:
        print(f"\nTesting from {container}:")

        # Test if container exists and is running
        stdout, stderr, code = run_command(f"docker inspect {container} --format='{{{{.State.Status}}}}' 2>/dev/null")
        if code != 0:
            print(f"  ❌ Container not found")
            continue

        if stdout != "running":
            print(f"  ❌ Container is not running (status: {stdout})")
            continue

        # Test nslookup
        stdout, stderr, code = run_command(f"docker exec {container} nslookup host.docker.internal 2>/dev/null")
        if code == 0 and "can't resolve" not in stdout.lower():
            print(f"  ✅ DNS resolution works")
            # Extract IP from nslookup output
            lines = stdout.split('\n')
            for line in lines:
                if 'Address:' in line and '127.0.0.53' not in line:
                    ip = line.split('Address:')[1].strip()
                    print(f"     Resolves to: {ip}")
                    break
        else:
            print(f"  ❌ DNS resolution failed")

        # Test ping (if available)
        stdout, stderr, code = run_command(f"docker exec {container} ping -c 1 -W 2 host.docker.internal 2>/dev/null")
        if code == 0:
            print(f"  ✅ Ping successful")
        else:
            print(f"  ❌ Ping failed (this may be normal if ping is not installed)")

def main():
    """Main inspection function."""
    print("🔍 DOCKER NETWORK CONFIGURATION INSPECTOR")
    print("=" * 60)

    # Check Docker is running
    stdout, stderr, code = run_command("docker info >/dev/null 2>&1")
    if code != 0:
        print("❌ Docker is not running or not accessible")
        return 1

    # Check container status
    print("\n📋 Container Status")
    print("=" * 50)
    stdout, stderr, code = run_command("docker ps --filter 'name=trader_intelligence_v2' --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
    if code == 0:
        print(stdout)
    else:
        print(f"❌ Error checking containers: {stderr}")
        return 1

    # Inspect containers
    containers = ['trader_intelligence_v2_frontend_1', 'trader_intelligence_v2_backend_1']
    for container in containers:
        inspect_container(container)

    # Check Docker networks
    check_docker_networks()

    # Check port bindings
    check_port_bindings()

    # Test host.docker.internal
    test_host_docker_internal()

    print("\n" + "=" * 60)
    print("✅ Network inspection complete!")
    print("📚 See NETWORK_CONNECTIVITY_GUIDE.md for troubleshooting help")

    return 0

if __name__ == "__main__":
    sys.exit(main())