# Framework
from ETS2LA.Events import *
from ETS2LA.Plugin import *
import Plugins.Map.data as mapdata

import time
import math

class Plugin(ETS2LAPlugin):
    
    description = PluginDescription(
        name="Automatic Shifting (Manual Transmission)",
        version="1.0.0",
        description="This plugin will automatically shift whilst having a manual transmission, please note that this does not have an eco mode.",
        modules=["Traffic", "TruckSimAPI", "SDKController"],
        listen=["*.py"],
        tags=["Base"],
        fps_cap=10
    )
    
    author = Author(
        name="Playzzero97",
        url="https://github.com/Playzzero97",
        icon="https://avatars.githubusercontent.com/u/219891638?v=4"
    )

    def init(self):
        self.controller = self.modules.SDKController.SCSController()
        self.UPSHIFT_RPM = 2000
        self.DOWNSHIFT_RPM = 1100

        self.shift_state = {
            "gearup": 0,
            "geardown": 0
        }
        self.shift_duration = 1

    def run(self):
        data = self.modules.TruckSimAPI.run()

        current_rpm = data['truckFloat']['engineRpm']
        current_gear = data['truckInt']['gear']
        speed = data['truckFloat']['speed']

        max_gear = data['configUI']['gears']
        min_drive_gear = 1

        if current_gear != 0 and speed > 1.0:
            if current_rpm > self.UPSHIFT_RPM and current_gear < max_gear:
                self.shift_state["gearup"] = self.shift_duration
            elif current_rpm <= self.DOWNSHIFT_RPM and current_gear > min_drive_gear:
                self.shift_state["geardown"] = self.shift_duration

        self.controller.gearup = self.shift_state["gearup"] > 0
        self.controller.geardown = self.shift_state["geardown"] > 0

        if self.shift_state["gearup"] > 0:
            self.shift_state["gearup"] -= 1
        if self.shift_state["geardown"] > 0:
            self.shift_state["geardown"] -= 1



