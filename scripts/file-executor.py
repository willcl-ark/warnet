#!/usr/bin/env python
import os
import signal
import subprocess
import sys
import threading
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

keep_running = True
processes = []


def signal_handler(*_):
    global keep_running
    keep_running = False
    for process in processes:
        process.kill()
    print("Signal received, shutting down...")


class NewExecutableHandler(FileSystemEventHandler):
    def on_created(self, event):
        print(event)
        if not event.is_directory and os.access(event.src_path, os.X_OK) and keep_running:
            print(f"Running new executable detected: {event.src_path}")
            thread = threading.Thread(target=self.run_executable, args=(event.src_path,))
            thread.start()

    def run_executable(self, path):
        process = subprocess.Popen(path, shell=True)
        processes.append(process)
        process.wait()
        processes.remove(process)


def watch_directory(path="."):
    event_handler = NewExecutableHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=False)
    observer.start()
    try:
        while keep_running:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    if len(sys.argv) < 2:
        print("No directory to watch passed to watchdog")
        sys.exit(0)

    dir_path = sys.argv[1]
    watch_directory(dir_path)
