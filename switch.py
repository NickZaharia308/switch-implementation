#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

# Defined global variabiles
file_path = ""
own_bridge_id, root_bridge_id, root_path_cost = -1, -1, -1
root_port = -1
name_to_interface = {}


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

def send_bdpu_every_sec(trunk_ports):
    global own_bridge_id, root_bridge_id, root_path_cost
    while True:
        # Send BDPU every second if necessary
        if own_bridge_id == root_bridge_id:
            for interface in trunk_ports.keys():
                send_bdpu(interface)
        time.sleep(1)

# Creates a BPDU packet and sends it on the interface
def send_bdpu(interface):
    global own_bridge_id, root_bridge_id, root_path_cost
    source_MAC = get_switch_mac()
    dest_MAC = b'\x01\x80\xc2\x00\x00\x00'
    data = dest_MAC + source_MAC + root_bridge_id.to_bytes(4, byteorder='big') + own_bridge_id.to_bytes(4, byteorder='big') + root_path_cost.to_bytes(4, byteorder='big')
    length = len(data)
    send_to_link(get_interface_value(interface), length, data)

# Checks if the address is unicast
def check_if_unicast(dest_mac):
    return dest_mac & 0x010000000000 == 0

# Reads info from the config file
def read_config_file(file_path):
    switch_priority = -1
    access_ports = {}
    trunk_ports = {}

    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip()

            # Switch priority is the first line in the file
            if switch_priority == -1:
                switch_priority = int(line.split()[0])

            # Access ports are marked with "r-" in the config file
            elif line.startswith("r-"):
                parts = line.split()

                interface = parts[0]
                vlan_id = int(parts[1])
                access_ports[interface] = vlan_id

            # Trunk ports are marked with "rr-" in the config file
            elif line.startswith("rr-"):
                parts = line.split()

                interface = parts[0]
                trunk = parts[1]
                trunk_ports[interface] = trunk
    
    return switch_priority, access_ports, trunk_ports

# Returns the interface number from the interface name
def get_interface_value(interface_name):
    global name_to_interface

    if interface_name in name_to_interface:
        return name_to_interface[interface_name]
    return -1

# Initializes the switch for STP
def init_stp(trunk_ports, priority, access_ports):
    global own_bridge_id, root_bridge_id, root_path_cost

    # Set trunk_ports as blocked
    for interface in trunk_ports.keys():
        trunk_ports[interface] = "B"

    # Set the switch as root bridge
    own_bridge_id = priority
    root_bridge_id = priority
    root_path_cost = 0

    # If the switch is the root bridge, set all the ports as designated
    if own_bridge_id == root_bridge_id:
        for interface in trunk_ports.keys():
            trunk_ports[interface] = "D"


def main():
    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_ret value + 1
    switch_id = sys.argv[1]

    num_interfaces = wrapper.init(sys.argv[2:])
    interfaces = range(0, num_interfaces)

    # Deined variables
    MAC_Table = {}
    file_name = "switch" + switch_id + ".cfg"
    global file_path
    file_path = "./configs/" + file_name

    # Create the name to interface mapping
    global name_to_interface
    for interface in interfaces:
        name_to_interface[get_interface_name(interface)] = interface

    # Read the config file
    switch_priority, access_ports, trunk_ports = read_config_file(file_path)
    
    # Initialize the switch for STP
    global own_bridge_id, root_bridge_id, root_path_cost, root_port
    am_i_root = True
    init_stp(trunk_ports, switch_priority, access_ports)

    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bdpu_every_sec, args=(trunk_ports,))
    t.start()
    

    while True:
        # Note that data is of type bytes([...]).
        # b1 = bytes([72, 101, 108, 108, 111])  # "Hello"
        # b2 = bytes([32, 87, 111, 114, 108, 100])  # " World"
        # b3 = b1[0:2] + b[3:4].
        interface, data, length = recv_from_any_link()

        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)
        dest_mac_numerical = int.from_bytes(dest_mac, byteorder='big')

        # Get the MAC src and MAC dst in human readable format
        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)

        # Implement forwarding with learning
        MAC_Table[src_mac] = get_interface_name(interface)

        # Check if the packet is a BPDU
        if dest_mac_numerical == 0x0180c2000000:
            # Extract the fields from the BPDU
            root_bridge_id_packet = int.from_bytes(data[12:16], byteorder='big')
            own_bridge_id_packet = int.from_bytes(data[16:20], byteorder='big')
            root_path_cost_packet = int.from_bytes(data[20:24], byteorder='big')

            # Check if the priority is better (lower) than the current one
            if root_bridge_id_packet < root_bridge_id:
                root_bridge_id = root_bridge_id_packet
                root_path_cost = root_path_cost_packet + 10
                root_port = get_interface_name(interface)

                if am_i_root:
                    am_i_root = False
                    for current_interface in trunk_ports.keys():
                        if root_port != current_interface:
                            trunk_ports[current_interface] = "B"
                
                # Set the root port as designated
                if trunk_ports[root_port] == "B":
                    trunk_ports[root_port] = "D"
            
                # Send BPDU on all trunk ports
                for current_interface in trunk_ports.keys():
                    source_MAC = get_switch_mac()
                    dest_MAC = b'\x01\x80\xc2\x00\x00\x00'
                    data_temp = dest_MAC + source_MAC + root_bridge_id.to_bytes(4, byteorder='big') + own_bridge_id.to_bytes(4, byteorder='big') + root_path_cost.to_bytes(4, byteorder='big')
                    length_temp = len(data_temp)
                    send_to_link(get_interface_value(current_interface), length_temp, data_temp)

            elif root_bridge_id_packet == root_bridge_id:
                if root_port == -1:
                    continue
                elif root_port == get_interface_name(interface) and root_path_cost_packet + 10 < root_path_cost:
                    root_path_cost = root_path_cost_packet + 10
                elif root_port != get_interface_name(interface):
                    if root_path_cost_packet > root_path_cost:
                        trunk_ports[get_interface_name(interface)] = "D"

            elif own_bridge_id_packet == own_bridge_id:
                trunk_ports[get_interface_name(interface)] = "B"
            else:
                continue
            
            if own_bridge_id == root_bridge_id:
                for current_interface in trunk_ports.keys():
                    trunk_ports[current_interface] = "D"
            continue

        # Forward process
        if check_if_unicast(dest_mac_numerical):
            if dest_mac in MAC_Table:
                # Check if packet should have 802.1Q header (it is sent to a trunk port)
                if MAC_Table[dest_mac] in trunk_ports and trunk_ports[MAC_Table[dest_mac]] == "D":
                    
                    # Check if the packet arrived from an access port (should add 802.1Q header)
                    if get_interface_name(interface) in access_ports:
                        vlan_id = access_ports[get_interface_name(interface)]
                        data_temp = data[0:12] + create_vlan_tag(vlan_id) + data[12:]
                        length_temp = length + 4
                        send_to_link(get_interface_value(MAC_Table[dest_mac]), length_temp, data_temp)
                    # Else the header is already there, just forward the packet
                    else:
                        send_to_link(get_interface_value(MAC_Table[dest_mac]), length, data)
                elif MAC_Table[dest_mac] in access_ports:
                    # If the packet is sent to an access port, and the sender is an access port
                    # check if they are in the same VLAN
                    if get_interface_name(interface) in access_ports:
                        if access_ports[get_interface_name(interface)] != access_ports[MAC_Table[dest_mac]]:
                            continue
                    # If the packet is sent to an access port, and
                    # the sender is a trunk port, remove the 802.1Q header
                    if get_interface_name(interface) in trunk_ports and vlan_id == access_ports[MAC_Table[dest_mac]]:
                        data_temp = data[0:12] + data[16:]
                        length_temp = length - 4
                        send_to_link(get_interface_value(MAC_Table[dest_mac]), length_temp, data_temp)
                    elif get_interface_name(interface) in trunk_ports and vlan_id != access_ports[MAC_Table[dest_mac]]:
                        continue
                    else:
                        send_to_link(get_interface_value(MAC_Table[dest_mac]), length, data)
            else:
                for curr_interface in interfaces:
                    if curr_interface != interface:
                        curr_interface_name = get_interface_name(curr_interface)
                        # Check if packet should have 802.1Q header (it is sent to a trunk port)
                        if curr_interface_name in trunk_ports and trunk_ports[curr_interface_name] == "D":
                            
                            # Check if the packet arrived from an access port (should add 802.1Q header)
                            if get_interface_name(interface) in access_ports:
                                vlan_id = access_ports[get_interface_name(interface)]
                                data_temp = data[0:12] + create_vlan_tag(vlan_id) + data[12:]
                                length_temp = length + 4
                                send_to_link(curr_interface, length_temp, data_temp)
                            # Else the header is already there, just forward the packet
                            else:
                                send_to_link(curr_interface, length, data)
                        elif curr_interface_name in access_ports:
                            # If the packet is sent to an access port, and the sender is an access port
                            # check if they are in the same VLAN
                            if get_interface_name(interface) in access_ports:
                                if access_ports[get_interface_name(interface)] != access_ports[curr_interface_name]:
                                    continue
                            # If the packet is sent to an access port, and
                            # the sender is a trunk port, remove the 802.1Q header
                            if get_interface_name(interface) in trunk_ports and vlan_id == access_ports[curr_interface_name]:
                                data_temp = data[0:12] + data[16:]
                                length_temp = length - 4
                                send_to_link(curr_interface, length_temp, data_temp)
                            elif get_interface_name(interface) in trunk_ports and vlan_id != access_ports[curr_interface_name]:
                                continue
                            else:
                                send_to_link(curr_interface, length, data)
        else:
            for curr_interface in interfaces:
                if curr_interface != interface:
                    curr_interface_name = get_interface_name(curr_interface)
                    # Check if packet should have 802.1Q header (it is sent to a trunk port)
                    if curr_interface_name in trunk_ports and trunk_ports[curr_interface_name] == "D":
                        
                        # Check if the packet arrived from an access port (should add 802.1Q header)
                        if get_interface_name(interface) in access_ports:
                            vlan_id = access_ports[get_interface_name(interface)]
                            data_temp = data[0:12] + create_vlan_tag(vlan_id) + data[12:]
                            length_temp = length + 4
                            send_to_link(curr_interface, length_temp, data_temp)
                        # Else the header is already there, just forward the packet
                        else:
                            send_to_link(curr_interface, length, data)
                    elif curr_interface_name in access_ports:
                        # If the packet is sent to an access port, and the sender is an access port
                        # check if they are in the same VLAN
                        if get_interface_name(interface) in access_ports:
                            if access_ports[get_interface_name(interface)] != access_ports[curr_interface_name]:
                                continue
                        # If the packet is sent to an access port, and
                        # the sender is a trunk port, remove the 802.1Q header
                        if get_interface_name(interface) in trunk_ports and vlan_id == access_ports[curr_interface_name]:
                            data_temp = data[0:12] + data[16:]
                            length_temp = length - 4
                            send_to_link(curr_interface, length_temp, data_temp)
                        elif get_interface_name(interface) in trunk_ports and vlan_id != access_ports[curr_interface_name]:
                            continue
                        else:
                            send_to_link(curr_interface, length, data)


if __name__ == "__main__":
    main()
