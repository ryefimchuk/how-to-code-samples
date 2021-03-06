# Copyright (c) 2015 - 2016 Intel Corporation.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import print_function
from importlib import import_module
from datetime import datetime
from pkg_resources import resource_filename
from bottle import Bottle, static_file, request, HTTPResponse, template, TEMPLATE_PATH
from .config import HARDWARE_CONFIG
from .scheduler import SCHEDULER
from .log import log
from .sms import send_sms

class Runner(object):

    def __init__(self):

        self.project_name = "Plant Light System"

        board_name = HARDWARE_CONFIG.kit
        board_module = "{0}.hardware.{1}".format(__package__, board_name)
        board_class_name = "{0}Board".format(board_name.capitalize())
        self.board = getattr(import_module(board_module), board_class_name)()

        self.schedule = {}

        self.moisture = []

        resource_package = __name__
        package_root = resource_filename(resource_package, "")
        TEMPLATE_PATH.insert(0, package_root)

        self.server = Bottle()
        self.server.route("/", callback=self.serve_index)
        self.server.route("/styles.css", callback=self.serve_css)
        self.server.route("/on", callback=self.get_on)
        self.server.route("/off", callback=self.get_off)
        self.server.route("/schedule", method="GET", callback=self.get_schedule)
        self.server.route("/schedule", method="PUT", callback=self.put_schedule)

        self.monitor_moisture_job = SCHEDULER.add_job(
            self.monitor_moisture,
            "interval",
            minutes=15
        )

        self.monitor_lights_job = SCHEDULER.add_job(
            self.monitor_lights,
            "cron",
            hour="0-23"
        )

    def start(self):

        """
        Start runner.
        """

        self.monitor_moisture()

        self.server.run(
            host="0.0.0.0",
            port=3000
        )

    # hardware methods

    def monitor_moisture(self):

        moisture_value = self.board.sample_moisture()

        print("Running scheduled moisture check. Moisture: {0}".format(moisture_value))

        log("moisture({0})".format(moisture_value))

        self.moisture.append({
            "time": datetime.utcnow(),
            "value": moisture_value
        })

        self.moisture = self.moisture[-20:]

    def monitor_lights(self):

        current_hour = datetime.utcnow().hour

        print("Running scheduled light check for hour {0}.".format(current_hour))

        light_condition = self.schedule.get(str(current_hour), {
            "on": False,
            "off": False
        })

        light_assertion = True if light_condition["on"] else False

        if light_assertion:
            self.check_on()
        else:
            self.check_off()

    def check_on(self):

        log("lights-on")
        lux = self.board.sample_lux()

        # assert on condition
        if lux < 2:
            print("Light on check failed. Lux: {0}.".format(lux))
            self.alert()
        else:
            print("Light on check passed.")

    def check_off(self):

        log("lights-off")
        lux = self.board.sample_lux()

        # assert off condition
        if lux > 4:
            print("Light off check failed. Lux: {0}.".format(lux))
            self.alert()
        else:
            print("Light off check passed.")

    def alert(self):

        print("Lighting alert triggered.")
        self.board.write_message("Lighting alert")
        send_sms("Lighting alert.")

    # server methods

    def serve_index(self):

        """
        Serve the 'index.html' file.
        """

        output = template("index", moisture=self.moisture)
        return output

    def serve_css(self):

        """
        Serve the 'styles.css' file.
        """

        resource_package = __name__
        resource_path = "styles.css"
        package_root = resource_filename(resource_package, "")
        return static_file(resource_path, root=package_root)

    def get_on(self):

        print("Received manual lights off check.")
        self.check_on()
        return HTTPResponse(status=200)

    def get_off(self):

        print("Received manual lights off check.")
        self.check_off()
        return HTTPResponse(status=200)

    def get_schedule(self):

        return {
            "data": self.schedule
        }

    def put_schedule(self):

        print("Received updated lighting schedule.")
        self.schedule = request.json
        return HTTPResponse(status=200)
