#!/usr/bin/env python3
"""Isolated, deterministic UDP payload fault injection; no host qdisc changes."""
import collections
import heapq
import selectors
import socket
import threading
import time
import queue


class Relay:
    def __init__(self, target):
        self.target = target
        self.selector = selectors.DefaultSelector()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.setblocking(False)
        self.port = self.listener.getsockname()[1]
        self.selector.register(self.listener, selectors.EVENT_READ, None)
        self.upstream = {}
        self.mode = "normal"
        self.counts = collections.Counter()
        self.queue = []
        self.sequence = 0
        self.delayed_initial = set()
        self.commands = queue.Queue()
        self.last_seen = {}
        self.retired = []
        self.last_sweep = time.monotonic()
        self.running = True
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def set_mode(self, mode):
        if mode not in {"normal", "loss-delay-reorder", "initial-reorder", "blackhole", "mtu1280", "handshake-blackhole"}:
            raise ValueError(mode)
        self.mode = mode

    def schedule(self, sock, data, destination, direction):
        mode = self.mode
        self.counts[mode + ":" + direction + ":packets"] += 1
        n = self.counts[mode + ":" + direction + ":packets"]
        if mode == "blackhole" or (mode == "handshake-blackhole" and direction == "server"):
            self.counts[mode + ":" + direction + ":dropped"] += 1
            return
        if mode == "mtu1280" and len(data) > 1280:
            self.counts[mode + ":" + direction + ":oversize_dropped"] += 1
            return
        delay = 0
        if mode == "initial-reorder":
            delay = .02
            if direction == "client" and sock not in self.delayed_initial:
                self.delayed_initial.add(sock)
                delay = .12
                self.counts[mode + ":client:first_datagram_delayed"] += 1
            # QUIC v1 Retry has an unprotected long-header type. Let any
            # erroneously emitted Initial CONNECTION_CLOSE arrive first.
            if direction == "server" and len(data) >= 5 and data[0] & 0xf0 == 0xf0 and data[1:5] == b"\0\0\0\1":
                delay = .2
                self.counts[mode + ":server:retry_delayed"] += 1
        if mode == "loss-delay-reorder":
            if n % 13 == 0:
                self.counts[mode + ":" + direction + ":dropped"] += 1
                return
            delay = 0.02
            if n % 7 == 0:
                delay += 0.06
                self.counts[mode + ":" + direction + ":extra_delayed"] += 1
        self.sequence += 1
        heapq.heappush(self.queue, (time.monotonic() + delay, self.sequence, sock, data, destination))
        if mode == "loss-delay-reorder" and n % 17 == 0:
            self.sequence += 1
            heapq.heappush(self.queue, (time.monotonic() + delay + .005, self.sequence, sock, data, destination))
            self.counts[mode + ":" + direction + ":duplicated"] += 1

    def rebind(self):
        done=threading.Event();result={}
        self.commands.put(("rebind",done,result))
        if not done.wait(2):raise RuntimeError("relay rebind command timed out")
        return result["mappings"]

    def new_upstream(self,peer):
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1",0));sock.setblocking(False)
        self.upstream[peer]=sock
        self.selector.register(sock,selectors.EVENT_READ,peer)
        self.last_seen[peer]=time.monotonic()
        return sock

    def run(self):
        while self.running:
            while not self.commands.empty():
                command,done,result=self.commands.get_nowait()
                mappings=[]
                for peer,old in list(self.upstream.items()):
                    sock=self.new_upstream(peer)
                    mappings.append({"before":old.getsockname()[1],"after":sock.getsockname()[1]})
                    # Keep old receive path briefly: delayed traffic may still be valid.
                    self.retired.append((time.monotonic()+2,old))
                result["mappings"]=mappings;done.set()
            for key, _ in self.selector.select(.005):
                try:
                    data, peer = key.fileobj.recvfrom(65536)
                except (BlockingIOError, OSError):
                    continue
                if key.data is None:
                    sock = self.upstream.get(peer)
                    if sock is None:
                        sock = self.new_upstream(peer)
                    self.last_seen[peer]=time.monotonic()
                    self.schedule(sock, data, self.target, "client")
                else:
                    self.schedule(self.listener, data, key.data, "server")
            now = time.monotonic()
            if now-self.last_sweep>1:
                for peer,seen in list(self.last_seen.items()):
                    if now-seen>30:
                        sock=self.upstream.pop(peer);self.last_seen.pop(peer)
                        self.retired.append((now+.2,sock))
                for deadline,sock in list(self.retired):
                    if deadline<now:
                        self.selector.unregister(sock);self.delayed_initial.discard(sock);sock.close()
                        self.retired.remove((deadline,sock))
                self.last_sweep=now
            while self.queue and self.queue[0][0] <= now:
                _, _, sock, data, target = heapq.heappop(self.queue)
                try:
                    sock.sendto(data, target)
                except OSError:
                    self.counts["send_errors"] += 1

    def close(self):
        self.running = False
        self.thread.join(timeout=1)
        for sock in [self.listener] + list(self.upstream.values()) + [s for _,s in self.retired]:
            sock.close()
        self.selector.close()
