import json
import os

from evaluator.task_trace import DatasetHelper, get_all_vh_paths
from PIL import Image

from tools import (
    FINISHED,
    get_action_descv2,
    get_action_from_views_actions,
    parse_views,
)


def dump_actions_to_file(actions, episode, output_path):
    if not os.path.exists(output_path):
        os.mkdir(output_path)
    with open(os.path.join(output_path, f"{episode}.json"), "w") as f:
        json.dump(actions, f, indent=4)


def predict_ui_actions(first_n_episodes: int = 0):
    """Predict actions on a static dataset"""
    task_metadata_path = os.environ.get("TASK_METADATA_PATH")
    gr_dataset_path = os.environ.get("GR_DATASET_PATH")

    if task_metadata_path is None or gr_dataset_path is None:
        raise EnvironmentError(
            "The TASK_METADATA_PATH and GR_DATASET_PATH environment variables must be set."
        )

    helper = DatasetHelper(
        epi_metadata_path=task_metadata_path,
        gr_dataset_path=gr_dataset_path,
    )

    all_epis = (
        helper.get_all_episodes()[:first_n_episodes]
        if first_n_episodes > 0
        else helper.get_all_episodes()
    )
    for index, epi in enumerate(all_epis):
        print(f"processing {index}-th epi: {epi}")

        task_description = helper.get_task_description_by_episode(epi)
        action_history = [f"- start from a random screen"]
        thought_history = [f"my goal is to finish the task {task_description}"]

        actions_to_be_dumped = {}

        trace = helper.load_groundtruth_trace_by_episode(epi)
        vh_paths = get_all_vh_paths(trace)
        for i in range(len(vh_paths)):
            vh_file = vh_paths[i]
            with open(vh_file.replace("xml", "vh")) as f:
                raw_views = json.load(f)
            views = parse_views(raw_views)
            action, candidate_actions, target_view, thought, prompt, response = (
                get_action_from_views_actions(
                    task_description=task_description,
                    views=views,
                    action_history=action_history,
                    thought_history=thought_history,
                )
            )
            # e.g., install - trace_0
            # vh_file: install/trace_0/emulator-5554 2024_1_22 12_37_18.png_hierarchy.txt
            # extracted ui_repr_str: emulator-5554 2024_1_22 12_37_18
            ui_repr_str = vh_file.split("/")[-1].replace(".vh", "")
            # convert actions bounds to the central point
            if action.event_type == "click":
                action_str = action.event_type.upper()

                bounds = action.view.get("bounds", "[[-1, -1], [-1, -1]]")
                param = [
                    (bounds[0][0] + bounds[1][0]) / 2,
                    (bounds[0][1] + bounds[1][1]) / 2,
                ]
            elif action.event_type == "set_text":
                action_str = action.event_type.upper()
                param = action.text
            elif action.event_type == "key":
                action_str = action.name.upper()
                param = None
            else:
                param = None

            screenshot_file = vh_file.replace("xml", "png")
            screen_width, screen_height = Image.open(screenshot_file).size

            actions_to_be_dumped[ui_repr_str] = {
                "prompt": prompt,
                "response": response,
                "event_type": action_str,
                "param": param,
                "screen_width": screen_width,
                "screen_height": screen_height,
            }

            if action == FINISHED or i == (len(vh_paths) - 1):
                dump_actions_to_file(actions_to_be_dumped, epi, "predicted_actions")
                continue

            if target_view is None:
                target_view = ""
            action_history.append(get_action_descv2(action, target_view))
            thought_history.append(thought)


if __name__ == "__main__":
    predict_ui_actions(first_n_episodes=10)
