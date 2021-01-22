import csv
import threading
import time
from pkg_resources import resource_filename

import flag
from pyais.stream import UDPStream


class ShipDatabase(object):
    STATIC_MSGS = [5, 24]
    POSITION_MSGS = [1, 2, 3, 18]
    STATIC_FIELDS = [
        "shipname",
        "imo",
        "shiptype",
        "destination",
        "draught",
        "to_bow",
        "to_stern",
        "to_port",
        "to_starboard",
    ]
    POSITION_FIELDS = ["lat", "lon", "status", "heading", "course", "speed"]

    def __init__(self, host, port):
        self.host = host
        self.port = port

        self.ships = {}

        self.countries = self.readcsv("mid")
        self.shiptypes = self.readcsv("shiptype")
        self.statuses = self.readcsv("status")

        self.message_callbacks = []

        self.lock = threading.Lock()

        listener = threading.Thread(target=self.run, args=())
        listener.daemon = True
        listener.start()

    @staticmethod
    def readcsv(filename):
        d = {}
        path = resource_filename("aistweet", "data/{}.csv".format(filename))
        with open(path, newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                d[int(row[0])] = row[1]
        return d

    def add_message(self, data, t):
        # get the MMSI
        mmsi = int(data["mmsi"])

        with self.lock:
            # create a new ship entry if necessary
            if not mmsi in self.ships:
                self.ships[mmsi] = {
                    "ais_class": "B" if data["type"] in [18, 24] else "A"
                }
                for key in self.STATIC_FIELDS + self.POSITION_FIELDS:
                    self.ships[mmsi][key] = None

            # bump latest update time
            self.ships[mmsi]["last_update"] = t

            # handle static messages
            if data["type"] in self.STATIC_MSGS:
                for key in self.STATIC_FIELDS:
                    self.ships[mmsi][key] = data[key]
                # TODO: eta?

            # handle position reports
            if data["type"] in self.POSITION_MSGS:
                for key in self.POSITION_FIELDS:
                    self.ships[mmsi][key] = data[key]

        return mmsi

    def __getitem__(self, mmsi):
        with self.lock:
            return self.ships[mmsi]

    def flag(self, mmsi):
        try:
            return flag.flag(self.countries[int(str(mmsi)[:3])])
        except KeyError:
            return flag.flag("ZZ")

    def ship_type(self, mmsi):
        with self.lock:
            try:
                return self.shiptypes[self.ships[mmsi]["shiptype"]]
            except KeyError:
                return "Unknown Type"

    def status(self, mmsi):
        with self.lock:
            try:
                return self.statuses[self.ships[mmsi]["status"]]
            except KeyError:
                return None

    def dimensions(self, mmsi):
        with self.lock:
            try:
                return (
                    self.ships[mmsi]["to_bow"] + self.ships[mmsi]["to_stern"],
                    self.ships[mmsi]["to_port"] + self.ships[mmsi]["to_starboard"],
                )
            except TypeError:
                return (0, 0)

    def run(self):
        for msg in UDPStream(self.host, self.port):
            data = msg.decode()
            if data["type"] in self.STATIC_MSGS + self.POSITION_MSGS:
                t = time.time()
                mmsi = self.add_message(data, t)
                for callback in self.message_callbacks:
                    callback(mmsi, t)