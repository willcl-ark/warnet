import random

def generate_ip_addresses(containers, n):
    """
    Generate n valid random publicly routable IPv4 addresses for each container.

    :param containers: List of container names
    :param n: Number of IP addresses to generate for each container
    :return: Dictionary where each key is a container name and the value is a list of n IP addresses
    """
    # Reserved IP address ranges in CIDR notation
    reserved_ips = [
        {'start': '0.0.0.0', 'end': '0.255.255.255'},
        {'start': '10.0.0.0', 'end': '10.255.255.255'},
        {'start': '100.64.0.0', 'end': '100.127.255.255'},
        {'start': '127.0.0.0', 'end': '127.255.255.255'},
        {'start': '169.254.0.0', 'end': '169.254.255.255'},
        {'start': '172.16.0.0', 'end': '172.31.255.255'},
        {'start': '192.0.0.0', 'end': '192.0.0.255'},
        {'start': '192.0.2.0', 'end': '192.0.2.255'},
        {'start': '192.88.99.0', 'end': '192.88.99.255'},
        {'start': '192.168.0.0', 'end': '192.168.255.255'},
        {'start': '198.18.0.0', 'end': '198.19.255.255'},
        {'start': '198.51.100.0', 'end': '198.51.100.255'},
        {'start': '203.0.113.0', 'end': '203.0.113.255'},
        {'start': '224.0.0.0', 'end': '255.255.255.255'},
    ]

    def is_public(ip):
        for reserved in reserved_ips:
            if ip >= ip_to_int(reserved['start']) and ip <= ip_to_int(reserved['end']):
                return False
        return True

    def ip_to_int(ip):
        return int(''.join([f'{int(byte):08b}' for byte in ip.split('.')]), 2)

    def int_to_ip(ip):
        return '.'.join([str(ip >> (i << 3) & 0xFF) for i in range(4)[::-1]])

    result = {}
    for container_name, _ in containers:
        ips = []
        while len(ips) < n:
            ip_int = random.randint(0, (1 << 32) - 1)
            if is_public(ip_int):
                ips.append(int_to_ip(ip_int))
        result[container_name] = ips  # Use container_name as the key, which is a string

    return result

