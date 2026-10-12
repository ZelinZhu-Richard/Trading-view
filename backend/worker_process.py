"""Owned process identity/descendant tracking, never arbitrary PID termination."""
import os
import signal

import psutil


class ProcessTree:
    def __init__(self, process: psutil.Process):
        self.root = process
        self.created = process.create_time()
        self.descendants = {}

    def refresh(self):
        if self.root.is_running() and self.root.create_time() == self.created:
            try:
                for child in self.root.children(recursive=True):
                    # psutil Process caches creation identity and checks PID reuse for
                    # is_running, terminate, kill, and children.
                    self.descendants[(child.pid, child.create_time())] = child
            except psutil.NoSuchProcess:
                pass
        return [p for p in [self.root, *self.descendants.values()]
                if p.is_running() and p.status() != psutil.STATUS_ZOMBIE]

    def rss(self):
        total = 0
        for process in self.refresh():
            try:
                total += process.memory_info().rss
            except psutil.NoSuchProcess:
                pass
        return total

    def terminate(self, include_root=True):
        try:
            self.refresh()
        except (PermissionError, psutil.AccessDenied):
            pass  # Still stop known identities/the owned session when discovery fails.
        targets = [*self.descendants.values(), *([self.root] if include_root else [])]
        if include_root and os.name == 'posix' and self.root.is_running():
            try:
                if self.root.create_time() == self.created and os.getpgid(self.root.pid) == self.root.pid:
                    os.killpg(self.root.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        for process in targets:
            try:
                if process.is_running():
                    process.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(targets, timeout=.6)
        for process in alive:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        _, remaining = psutil.wait_procs(alive, timeout=.6)
        return [p for p in remaining if p.is_running() and p.status() != psutil.STATUS_ZOMBIE]
