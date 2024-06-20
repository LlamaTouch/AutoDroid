import os
import sys
import time

import requests

from tools import (
    FINISHED,
    get_action_descv2,
    get_action_from_views_actions,
    parse_views,
)

sys.path.append(os.environ.get("AGENTENV_PATH"))
from environment import AgentEnv

CONFIGS = {
    "ANDROID_SCREENSHOT_DIR": "",
    "ANDROID_XML_DIR": "",
}
DEVICE = os.environ.get("DEVICE", "emulator-5554")
TASK_METADATA_PATH = "./llamatouch_task_metadata.tsv"
TASK_METADATA_URL = "https://raw.githubusercontent.com/LlamaTouch/LlamaTouch/main/dataset/llamatouch_task_metadata.tsv"

response = requests.get(TASK_METADATA_URL)
with open(TASK_METADATA_PATH, "w") as f:
    f.write(response.content)


class AndroidController(AgentEnv):
    def __init__(self, device_serial, local_output_path, max_steps=30, task_id=0):
        os.system(f"adb connect {device_serial}")
        print(f"{device_serial=}, {local_output_path=}")
        super().__init__(
            device_serial=device_serial,
            local_output_path=local_output_path,
            max_steps=max_steps,
            instruction_fp=TASK_METADATA_PATH,
        )
        # self.device = device
        self.screenshot_dir = CONFIGS["ANDROID_SCREENSHOT_DIR"]
        self.xml_dir = CONFIGS["ANDROID_XML_DIR"]
        self.width, self.height = self.get_device_size()
        self.backslash = "\\"
        self.instu_idx += task_id

    def tap(self, tl, br):
        x, y = (tl[0] + br[0]) // 2, (tl[1] + br[1]) // 2
        w, h = self.get_device_size()
        x /= w
        y /= h
        action = f"action_type: dual_point, touch_point: [{x}, {y}], lift_point: [{x}, {y}], typed_text: ''"
        ret = self.post_action(action)
        return ret

    def text(self, input_str):
        input_str = input_str.replace(" ", "%s")
        input_str = input_str.replace("'", "")
        action = f"action_type: type, touch_point: [-1.0, -1.0], lift_point: [-1.0, -1.0], typed_text: '{input_str}'"
        ret = self.post_action(action)
        return ret

    def long_press(self, tl, br, duration=1000):
        x, y = (tl[0] + br[0]) // 2, (tl[1] + br[1]) // 2
        w, h = self.get_device_size()
        x /= w
        y /= h
        action = f"action_type: dual_point, touch_point: [{x}, {y}], lift_point: [{x}, {y}], typed_text: ''"
        ret = self.post_action(action)
        return ret

    def swipe(self, tl, br, direction, dist="short", quick=False):
        unit_dist = int(self.width / 10)
        if dist == "long":
            unit_dist *= 3
        elif dist == "medium":
            unit_dist *= 2
        x, y = (tl[0] + br[0]) // 2, (tl[1] + br[1]) // 2
        if direction == "up":
            offset = 0, -2 * unit_dist
        elif direction == "down":
            offset = 0, 2 * unit_dist
        elif direction == "left":
            offset = -1 * unit_dist, 0
        elif direction == "right":
            offset = unit_dist, 0
        else:
            return "ERROR"
        duration = 100 if quick else 400

        w, h = self.get_device_size()
        xbegin = x / w
        ybegin = y / w
        xend = (x + offset[0]) / w
        yend = (y + offset[1]) / h
        action = f"action_type: dual_point, touch_point: [{xbegin}, {ybegin}], lift_point: [{xend}, {yend}], typed_text: ''"
        ret = self.post_action(action)
        return ret


def run_on_agentenv(
    device: str, task_metadata_filepath: str, first_n_episodes: int = 0
):
    ac = AndroidController(
        device_serial=device,
        local_output_path="exec_output",
        max_steps=15,
    )

    import pandas as pd

    data = pd.read_csv(task_metadata_filepath, sep="\t")
    data = data.head(first_n_episodes) if first_n_episodes > 0 else data

    for index, row in data.iterrows():
        try:
            task_description = row["description"]
            epi = row["episode"]
            print(f"exec {index}-th epi: {epi}, {task_description}")

            # check whether this task is completed
            # check whether folder:
            epi_path = os.path.join(ac.local_output_path, epi)
            # if there is files in epi_path, go to the next task
            check_path = os.path.join(epi_path, "screenshot")
            if os.path.exists(check_path) and len(os.listdir(check_path)) > 0:
                continue

            action_history = [f"- start from the home screen"]
            thought_history = [f"my goal is to finish the task {task_description}"]

            # go to the HOME page
            ac.reset_env()
            time.sleep(3)
            # go to the launcher page
            os.system(f"adb -s {device} shell input swipe 500 1500 500 500")
            time.sleep(3)

            step = 0
            while not ac.episode_done():
                if step > 15:
                    break
                step += 1
                raw_views = ac.get_state()["view_hierarchy"]
                views = parse_views(raw_views)

                action, candidate_actions, target_view, thought, prompt, response = (
                    get_action_from_views_actions(
                        task_description=task_description,
                        views=views,
                        action_history=action_history,
                        thought_history=thought_history,
                    )
                )

                # print("selected action: ", action)

                if action == FINISHED:
                    ac.post_action(
                        "action_type: STATUS_TASK_COMPLETE, touch_point: [-1.0, -1.0], lift_point: [-1.0, -1.0], typed_text: ''"
                    )
                    break

                action_history.append(get_action_descv2(action, target_view))
                thought_history.append(thought)

                if action.event_type == "key":
                    if action.name == "BACK":
                        ac.post_action(
                            "action_type: PRESS_BACK, touch_point: [-1.0, -1.0], lift_point: [-1.0, -1.0], typed_text: ''"
                        )

                elif action.event_type == "click":
                    tl, br = action.view["bounds"]
                    ac.tap(tl, br)

                elif action.event_type == "long_click":
                    tl, br = action.view["bounds"]
                    ac.long_press(tl, br)

                elif action.event_type == "swipe":
                    act = f"action_type: dual_point, touch_point: [{action.start_x}, {action.start_y}], lift_point: [{action.end_x}, {action.end_y}], typed_text: ''"
                    ac.post_action(act)

                elif action.event_type == "set_text":
                    ac.text(action.text)

                else:
                    raise Exception(f"Error action event type: {action.event_type}")

            os.rename(
                os.path.join("exec_output", "captured_data"),
                os.path.join("exec_output", epi),
            )

        except Exception as e:
            print(f"Error in epi {epi}: {e}")
            # remove content in folder os.path.join("exec_output", "captured_data")
            os.system(f"rm -r {os.path.join('exec_output', 'captured_data')}")
            import traceback

            traceback.print_exc()
            continue


if __name__ == "__main__":
    run_on_agentenv(
        device=DEVICE, 
        task_metadata_filepath=TASK_METADATA_PATH,
        first_n_episodes=10,
    )
