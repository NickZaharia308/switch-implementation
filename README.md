# Tema 1 - Implementare Switch

## Copyright 2024 Zaharia Nicusor-Alexandru 335CA

### Solved tasks - 1 2 3

### Project Idea

The project implements a switch that is capable of forwarding frames based on the hosts's VLANs and eliminating the loops in the topology.
The main code is written in `switch.py`.

### Structure

- `switch.py` - the main area where the implementation can be found
- `wrapper.py` - helper functions
- `README.md` - contains the implementation description

### Tasks descriptions and Workflow

1. The forwarding process is straight forward and it's implemented following the instructions in the homework description.
To check if the destination is unicast, the code is as it follows:

```python
def check_if_unicast(dest_mac):
    return dest_mac & 0x010000000000 == 0
```

The documentation used for this can be found [here](https://forum.huawei.com/enterprise/en/multicast-mac-address-vs-broadcast-mac-address-vs-unicast-mac-address/thread/667283450236911616-667213852955258880) and [here](https://en.wikipedia.org/wiki/MAC_address#Unicast_vs._multicast_(I/G_bit)).
If the address isn't unicast a flooding will be made on all interfaces except the one that the packet came from.

2. VLAN implementation came with some challenges that I will describe later.
First, I read the configs file for the switch, where the first line contained the switch priority (that is used in the following task) and the following lines contained access ports followed by the VLAN of the host folloed by trunk ports.
The ports have the following structure in the file:

```
r-1 2
rr-0-1 T
```

First interface is assigned to an access port, where the host is placed in the second VLAN.
Second interface represents a trunk port.
Both lines were initially stored in two different dictionaries (one for access and one for trunks) where the mapping was made between an interface (name, not number) and the VLAN / letter (letters for trunk ports that are used in the following task to represent the status of the port).
The problem was that the dictionaries mapped interfaces names to values, while the `MAC_table` mapped interfaces values to values.
The decision that I made was to map everything from name to value and create a function that returned an interface value based on the interface's name (the one that does the other way around was already available).
For each forwarding there were 2 cases, each with another 2 cases (4 in total).
Those were based on the type of the source and the type of the destination (trunk vs. access).

3. STP was pretty well explained (theory and code-wise) in the homework description.
However a video that helped me was [this one](https://www.youtube.com/watch?v=6MW5P6Ci7lw).
The part that took me a while was thread communication in Python, that was managed using some global variables.
A function to create a minimal BPDU header was also created.
Those headers are identified by the multicast MAC destination address `01:80:C2:00:00:00`.
BPDU frames are treated separately before the forwarding process.
After solving some broadcast storm problems (thanks to the questions already addressed on the homework's forum) and with some minor interventions to the forwarding process, STP was solved.

### Feedback

- Interesting homework with challenging tasks
- Learned more about switches
- Took a little bit more than expected
- Given that `send_to_link(interface, length, eth_frame)` works with interface values and not interface names, it would've been helpful if in the config files the interfaces were also represented as values (altough I would keep somewhere, like in the homework description, the names used for interfaces because it is easier to understand with names than it is with simple numerical values).