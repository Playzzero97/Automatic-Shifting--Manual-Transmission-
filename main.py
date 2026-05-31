from ETS2LA.Events import *
from ETS2LA.Plugin import *
from ETS2LA.UI import ETS2LAPage, ETS2LAPageLocation, TitleAndDescription, ComboboxWithTitleDescription

import json
import os
import time

class SettingsPage(ETS2LAPage):
    title = "Automatic Shifting"
    url = "/settings/automatic-shifting-sequential"
    location = ETS2LAPageLocation.SETTINGS
    refresh_rate = -1

    def handle_mode_change(self, value: str):
        if not self.plugin:
            return
        self.plugin.write_mode_to_settings(value)

    def render(self):
        TitleAndDescription(
            "Automatic Shifting mode",
            "Select the shifting behavior mode for sequential transmission.",
        )

        current_mode = "Normal"
        if self.plugin:
            current_mode = self.plugin.read_mode_from_settings()

        ComboboxWithTitleDescription(
            title="Mode",
            description="Choose a shift mode for the sequential transmission plugin.",
            options=["Eco", "Normal", "Power"],
            default=current_mode,
            changed=self.handle_mode_change,
        )


class Plugin(ETS2LAPlugin):
    
    description = PluginDescription(
        name="Automatic Shifting (Sequential Transmission)",
        version="1.0.3",
        description="This plugin will automatically shift whilst having a sequential transmission and supports Eco, Normal, and Power shift modes.",
        modules=["Traffic", "TruckSimAPI", "SDKController"],
        listen=["*.py"],
        tags=["Base"],
        fps_cap=10
    )
    pages = [SettingsPage]
    
    author = Author(
        name="Playzzero97",
        url="https://github.com/Playzzero97",
        icon="https://avatars.githubusercontent.com/u/219891638?v=4"
    )

    def init(self):
        self.controller = self.modules.SDKController.SCSController()

        self.shift_state = {
            "gearup": 0,
            "geardown": 0
        }
        self.shift_duration = 1
        self.shift_cooldown = 0.35
        self.last_shift_time = 0.0
        self.last_known_gear = 1
        self.pending_shifts = 0
        self.shift_modes = {
            "Eco": {"up": 0.5, "down": 0.3},
            "Normal": {"up": 0.70, "down": 0.58},
            "Power": {"up": 0.95, "down": 0.72},
        }

    # @events.on("toggle_modes")
    # def on_toggle_modes(self, event_object, state: bool):
    #     if not state:
    #         return  # Callback for the lift up event

    #     current_mode = self.read_mode_from_settings()
    #     modes = list(self.shift_modes.keys())
    #     next_mode = modes[(modes.index(current_mode) + 1) % len(modes)]
    #     self.write_mode_to_settings(next_mode)
    #     self.notify(f"Shift mode set to {next_mode}", "success")

    def read_mode_from_settings(self):
        settings_path = os.path.join(os.path.dirname(__file__), "settings.json")
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                mode = data.get("mode", "Normal")
        except Exception:
            mode = "Normal"

        return mode if mode in self.shift_modes else "Normal"

    def write_mode_to_settings(self, mode: str):
        if mode not in self.shift_modes:
            return
        settings_path = os.path.join(os.path.dirname(__file__), "settings.json")
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        data["mode"] = mode
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def get_thresholds(self, max_rpm: float, mode: str):
        mode_settings = self.shift_modes.get(mode, self.shift_modes["Normal"])
        rpm_target = max_rpm if max_rpm and max_rpm > 0 else 2100.0
        upshift = min(rpm_target - 150.0, max(1200.0, rpm_target * mode_settings["up"]))
        downshift = max(
            900.0,
            min(upshift - 250.0, rpm_target * mode_settings["down"]),
        )
        return upshift, downshift

    def should_upshift(self, rpm: float, speed: float, gear: int, max_gear: int, throttle: float, braking: float, upshift_rpm: float) -> bool:
        if gear >= max_gear:
            return False
        if rpm <= upshift_rpm:
            return False
        if throttle < 0.2 and rpm < upshift_rpm + 200.0:
            return False
        return True

    def should_downshift(self, rpm: float, speed: float, gear: int, min_drive_gear: int, throttle: float, braking: float, downshift_rpm: float) -> bool:
        if gear <= 1: 
            return False
        if braking > 0.4:
            return True
        if speed < 2.0:       
            return False
        if rpm > downshift_rpm:
            return False
        if speed < gear * 0.4 and throttle < 0.15:
            return True
        return False

    def run(self):
        data = self.modules.TruckSimAPI.run()

        current_rpm = data['truckFloat']['engineRpm']
        current_gear = data['truckInt']['gear']
        speed = data['truckFloat']['speed']

        max_gear = data['configUI']['gears']
        max_rpm = data['configFloat'].get('engineRpmMax', 0.0)
        mode = self.read_mode_from_settings()
        upshift_rpm, downshift_rpm = self.get_thresholds(max_rpm, mode)

        throttle = max(
            data['truckFloat'].get('gameThrottle', 0.0),
            data['truckFloat'].get('userThrottle', 0.0),
        )
        braking = max(
            data['truckFloat'].get('gameBrake', 0.0),
            data['truckFloat'].get('userBrake', 0.0),
        )

        if current_gear > 0 and current_gear != self.last_known_gear:
                self.last_known_gear = current_gear
                self.pending_shifts = 0
        elif current_gear > 0:
            self.last_known_gear = current_gear

        effective_gear = self.last_known_gear

        if current_gear != 0 and speed > 1.0 and time.time() - self.last_shift_time >= self.shift_cooldown:
            if self.should_upshift(current_rpm, speed, effective_gear, max_gear, throttle, braking, upshift_rpm):
                self.shift_state["gearup"] = self.shift_duration
                self.pending_shifts = max(0, self.pending_shifts - 1)
                self.last_shift_time = time.time()
            elif self.should_downshift(current_rpm, speed, effective_gear, 1, throttle, braking, downshift_rpm):
                if effective_gear - self.pending_shifts > 1:
                    self.shift_state["geardown"] = self.shift_duration
                    self.pending_shifts += 1
                    self.last_shift_time = time.time()

        self.controller.gearup = self.shift_state["gearup"] > 0
        self.controller.geardown = self.shift_state["geardown"] > 0

        if self.shift_state["gearup"] > 0:
            self.shift_state["gearup"] -= 1
        if self.shift_state["geardown"] > 0:
            self.shift_state["geardown"] -= 1



