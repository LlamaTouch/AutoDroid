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


sys.path.insert(0, os.environ.get("AGENTENV_PATH"))
from environment import AgentEnv

# config
AVD_NAME = "pixel_6a_api31"
TASK_METADATA_PATH = "./llamatouch_task_metadata.tsv"
TASK_METADATA_URL = "https://raw.githubusercontent.com/LlamaTouch/LlamaTouch/main/dataset/llamatouch_task_metadata.tsv"
emulator_controller_args = {
        "snapshot" : "default_boot",
        "port" : "5554",        # If port is occupied, please switch to 5556, 5558... and so forth
        "no-window" : "false",  # Change this to "true" to run the emulator without GUI.
    }
first_n_episodes=os.environ.get("FIRST_N_EPISODES", 10)

response = requests.get(TASK_METADATA_URL)
with open(TASK_METADATA_PATH, "w") as f:
    f.write(response.content)


class AndroidController(AgentEnv):
    def __init__(self, avd_name, emulator_controller_args, local_output_path, max_steps=30,instruction_fp="./llamatouch_task_metadata.tsv"):
        super().__init__(
            avd_name=avd_name,
            emulator_controller_args=emulator_controller_args,
            local_output_path=local_output_path,
            max_steps=max_steps,
            instruction_fp=instruction_fp,
        )
        self.width, self.height = None, None


    def tap(self, tl, br):
        x, y = (tl[0] + br[0]) // 2, (tl[1] + br[1]) // 2
        w, h = self.get_device_size()
        x /= w
        y /= h
        action = f"action_type: dual_point, touch_point: [{x}, {y}], lift_point: [{x}, {y}], typed_text: ''"
        # AgentEnv interface post_action
        ret = self.post_action(action)
        return ret

    def text(self, input_str):
        input_str = input_str.replace(" ", "%s")
        input_str = input_str.replace("'", "")
        action = f"action_type: type, touch_point: [-1.0, -1.0], lift_point: [-1.0, -1.0], typed_text: '{input_str}'"
        # AgentEnv interface post_action       
        ret = self.post_action(action)
        return ret

    def long_press(self, tl, br, duration=1000):
        x, y = (tl[0] + br[0]) // 2, (tl[1] + br[1]) // 2
        w, h = self.get_device_size()
        x /= w
        y /= h
        action = f"action_type: dual_point, touch_point: [{x}, {y}], lift_point: [{x}, {y}], typed_text: ''"
        # AgentEnv interface post_action        
        ret = self.post_action(action)
        return ret

    def swipe(self, tl, br, direction, dist="short", quick=False):
        # AgentEnv interface get the device_size
        self.width, self.height = self.get_device_size()
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


def run_on_agentenv():  

    ac = AndroidController(
        avd_name=AVD_NAME,
        emulator_controller_args=emulator_controller_args,
        local_output_path="exec_output",
        max_steps=15,
        instruction_fp=TASK_METADATA_PATH,
    )

    # setup AgentEnv
    ac.set_up()
    
    for _ in range(first_n_episodes):
        try:
            # get instruction from AgentEnv
            task_description = ac.get_instruction()
            if task_description is None:
                break

            print(f"Current instruction: {task_description}")
            
            # setup task environment if needed
            print(f"setting up task {task_description}...")
            ac.setup_task(task_description)
            
            # go to the dropdown s
            print(f"swipe up the screen")
            ac.device.swipe(500, 1500, 500, 500)
            
            time.sleep(2)

            action_history = [f"- start from the home screen"]
            thought_history = [f"my goal is to finish the task {task_description}"]

            while not ac.episode_done():
                # get view_hierarchy_json from AgentEnv
                raw_views = ac.get_state()["view_hierarchy_json"]
                views = parse_views(raw_views)

                s = time.time()
                # get autodroid agent action
                action, candidate_actions, target_view, thought, prompt, response = (
                    get_action_from_views_actions(
                        task_description=task_description,
                        views=views,
                        action_history=action_history,
                        thought_history=thought_history,
                    )
                )
                
                print("-----------------------------------------------------------------------------")
                print(f"propmt: {prompt}")
                print(f"got the action from the agent, costed time: {time.time()-s};action: {action}")
                print(f"candidate_actions: {candidate_actions}")
                print(f"target_view: {target_view}")
                print(f"thought: {thought}")

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
            
            # save the last environment state of an episode
            ac.get_state()
            # reset the environment for next task
            ac.reset_env()

        except Exception as e:
            print(f"Error in task {task_description}: {e}")
            # remove content in folder os.path.join("exec_output", "captured_data")
            os.system(f"rm -r {os.path.join('exec_output', 'captured_data')}")
            import traceback
            traceback.print_exc()

            # reset the environment and go to next task
            ac.reset_env()
            continue
    
    # Execution finished, close AgentEnv
    ac.tear_down()


if __name__ == "__main__":
    run_on_agentenv()
