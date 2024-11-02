#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

# Broadcast MAC address
BROADCAST_MAC = b'\xff\xff\xff\xff\xff\xff'

def parse_ethernet_header(data):
    # Unpack the header fields from the byte array
    #dest_mac, src_mac, ethertype = struct.unpack('!6s6sH', data[:14])
    dest_mac = data[0:6]
    src_mac = data[6:12]
    
    # Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
    ether_type = (data[12] << 8) + data[13]

    vlan_id = -1
    # Check for VLAN tag (0x8100 in network byte order is b'\x81\x00')
    if ether_type == 0x8200:
        vlan_tci = int.from_bytes(data[14:16], byteorder='big')
        vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID
        ether_type = (data[16] << 8) + data[17]

    return dest_mac, src_mac, ether_type, vlan_id

def create_vlan_tag(vlan_id):
    # 0x8100 for the Ethertype for 802.1Q
    # vlan_id & 0x0FFF ensures that only the last 12 bits are used
    return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def send_bdpu_every_sec():
    while True:
        # TODO Send BDPU every second if necessary
        time.sleep(1)

# Checks if the address is unicast
def check_if_unicast(dest_mac):
    return dest_mac & 0x010000000000 == 0

# Read info from the config file
def read_config_file(file_path):
    switch_priority = -1
    access_ports = []
    trunk_ports = []

    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip()
            if switch_priority == -1:
                switch_priority = int(line.split()[1])

            elif line.startswith("r-"):
                parts = line.split()

                interface = parts[0]
                vlan_id = int(parts[1])
                access_ports.append((interface, vlan_id))

            elif line.startswith("rr-"):
                parts = line.split()

                interface = parts[0]
                trunk = parts[1]
                trunk_ports.append((interface, trunk))
    
    return switch_priority, access_ports, trunk_ports

def get_802_1Q_tag(vlan_id):
    tpid = 0x8200
    tci = (0 << 13) | (0 << 12) | vlan_id
    return struct.pack('!HH', tpid, tci)


def main():
    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_ret value + 1
    switch_id = sys.argv[1]

    num_interfaces = wrapper.init(sys.argv[2:])
    interfaces = range(0, num_interfaces)

    print("# Starting switch with id {}".format(switch_id), flush=True)
    print("[INFO] Switch MAC", ':'.join(f'{b:02x}' for b in get_switch_mac()))

    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bdpu_every_sec)
    t.start()

    # Printing interface names
    for i in interfaces:
        print(get_interface_name(i))

    # Deined variables
    MAC_Table = {}
    file_name = "switch_" + switch_id + ".cfg"
    file_path = "./config/" + file_name

    # Read the config file
    switch_priority, access_ports, trunk_ports = read_config_file(file_path)

    while True:
        # Note that data is of type bytes([...]).
        # b1 = bytes([72, 101, 108, 108, 111])  # "Hello"
        # b2 = bytes([32, 87, 111, 114, 108, 100])  # " World"
        # b3 = b1[0:2] + b[3:4].
        interface, data, length = recv_from_any_link()

        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)
        dest_mac_numerical = int.from_bytes(dest_mac, byteorder='big')

        # Print the MAC src and MAC dst in human readable format
        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)

        # Note. Adding a VLAN tag can be as easy as
        # tagged_frame = data[0:12] + create_vlan_tag(10) + data[12:]

        print(f'Destination MAC: {dest_mac}')
        print(f'Source MAC: {src_mac}')
        print(f'EtherType: {ethertype}')

        print("Received frame of size {} on interface {}".format(length, interface), flush=True)

        # TODO: Implement forwarding with learning
        MAC_Table[src_mac] = interface

        if check_if_unicast(dest_mac_numerical):
            if dest_mac in MAC_Table:
                send_to_link(MAC_Table[dest_mac], length, data)
            else:
                for curr_interface in interfaces:
                    if curr_interface != interface:
                        send_to_link(curr_interface, length, data)
        else:
            for curr_interface in interfaces:
                if curr_interface != interface:
                    send_to_link(curr_interface, length, data)

        # TODO: Implement VLAN support
        # TODO: Implement STP support

        # data is of type bytes.
        # send_to_link(i, length, data)

if __name__ == "__main__":
    main()
