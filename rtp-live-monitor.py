#!/usr/bin/env python3
import curses
import socket
import struct
import time
import os
import netifaces  # pip install netifaces

RTP_HEADER_LEN = 12

def parse_rtp(packet):
    """Return True if packet is RTP."""
    if len(packet) < RTP_HEADER_LEN:
        return False
    version = packet[0] >> 6
    return version == 2

def select_interface_curses(stdscr):
    """Curses-based NIC selection menu."""
    curses.curs_set(0)
    stdscr.clear()
    interfaces = [iface for iface in os.listdir('/sys/class/net') if iface != "lo"]
    if not interfaces:
        stdscr.addstr(0, 0, "No interfaces found!")
        stdscr.refresh()
        time.sleep(2)
        return None

    selected = 0
    while True:
        stdscr.clear()
        stdscr.addstr(0, 0, "Select network interface (Use Up/Down, Enter to select)")
        for idx, iface in enumerate(interfaces):
            if idx == selected:
                stdscr.addstr(idx + 2, 2, f"> {iface}", curses.A_REVERSE)
            else:
                stdscr.addstr(idx + 2, 2, f"  {iface}")
        stdscr.refresh()
        key = stdscr.getch()
        if key == curses.KEY_UP and selected > 0:
            selected -= 1
        elif key == curses.KEY_DOWN and selected < len(interfaces) - 1:
            selected += 1
        elif key in (curses.KEY_ENTER, 10, 13):
            return interfaces[selected]

def main(stdscr, iface):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(200)

    # Get host IPs for the interface
    iface_addrs = netifaces.ifaddresses(iface)
    host_ips = []
    if netifaces.AF_INET in iface_addrs:
        host_ips = [i['addr'] for i in iface_addrs[netifaces.AF_INET]]

    # Raw socket bound to selected interface
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(3))
    sock.bind((iface, 0))

    stats = {"rx": 0, "tx": 0, "last_rx": 0, "last_tx": 0}
    last_time = time.time()

    while True:
        try:
            frame, addr = sock.recvfrom(65535)
        except BlockingIOError:
            continue
        except Exception:
            continue

        # Ethernet type
        eth_type = struct.unpack("!H", frame[12:14])[0]
        if eth_type != 0x0800:
            continue

        # IP header
        ip_header = frame[14:34]
        try:
            ver_ihl, tos, length, ident, flags, ttl, proto, checksum, src, dst = struct.unpack("!BBHHHBBHII", ip_header)
        except:
            continue

        if proto != 17:
            continue  # UDP only

        ihl = (ver_ihl & 0x0F) * 4
        udp_offset = 14 + ihl

        # IPs
        src_ip = socket.inet_ntoa(struct.pack("!I", src))
        dst_ip = socket.inet_ntoa(struct.pack("!I", dst))

        # UDP header
        try:
            udp_header = frame[udp_offset:udp_offset + 8]
            src_port, dst_port, length, checksum = struct.unpack("!HHHH", udp_header)
        except:
            continue

        # Only RTP port range (adjust if needed)
        if not (10000 <= src_port <= 65000 or 10000 <= dst_port <= 65000):
            continue

        rtp_data = frame[udp_offset + 8:]
        if parse_rtp(rtp_data):
            if dst_ip in host_ips:
                stats["rx"] += 1
            else:
                stats["tx"] += 1

        # Update UI every second
        now = time.time()
        if now - last_time > 1:
            rx_diff = stats["rx"] - stats["last_rx"]
            tx_diff = stats["tx"] - stats["last_tx"]
            stats["last_rx"] = stats["rx"]
            stats["last_tx"] = stats["tx"]
            last_time = now

            stdscr.clear()
            stdscr.addstr(0, 2, f"RTP LIVE MONITOR ({iface}) — Press Q to Quit")
            stdscr.addstr(2, 2, f"RX packets: {stats['rx']} (+{rx_diff}/s)")
            stdscr.addstr(3, 2, f"TX packets: {stats['tx']} (+{tx_diff}/s)")

            rx_bar = "#" * min(rx_diff, 50)
            tx_bar = "#" * min(tx_diff, 50)
            stdscr.addstr(5, 2, "RX Level: " + rx_bar)
            stdscr.addstr(6, 2, "TX Level: " + tx_bar)

            direction = "<--" if rx_diff > tx_diff else "-->"
            stdscr.addstr(8, 2, f"Direction: {direction}")

            stdscr.refresh()

        # Quit key
        try:
            key = stdscr.getkey()
            if key.lower() == 'q':
                break
        except:
            pass

if __name__ == "__main__":
    def wrapped(stdscr):
        iface = select_interface_curses(stdscr)
        if iface:
            main(stdscr, iface)
    curses.wrapper(wrapped)