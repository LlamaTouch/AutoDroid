import copy
import os

import numpy as np
from evaluator.task_trace import DatasetHelper, TaskTrace
from evaluator.utils.visualization import plot_episode
from PIL import Image

helper = DatasetHelper()


def plot_by_folder(trace_folder: str):
    print(trace_folder)
    epi_id = trace_folder.split("/")[-1]
    task_description = helper.get_task_description_by_episode(epi_id)
    cat = helper.get_category_by_episode(epi_id).value

    trace = helper.load_testbed_trace_by_path(trace_folder)

    output_file = os.path.join(trace_folder, "agg_plot.png")
    plot_single_trace(
        epi=epi_id,
        category=cat,
        task_description=task_description,
        task_trace=trace,
        output_file=output_file,
    )


def plot_single_trace(
    epi: str,
    category: str,
    task_description: str,
    task_trace: TaskTrace,
    output_file: str,
):

    ui_infos_for_plot = []
    step_id = 0
    for ui_state in task_trace:
        current_ui_state = {
            "image": None,
            "episode_id": None,
            "category": None,
            "step_id": None,
            "goal": None,
            "result_action": [None, None],
            "result_touch_yx": None,
            "result_lift_yx": None,
            "image_height": 1140,
            "image_width": 540,
            "image_channels": 3,
            "ui_positions": None,
            "ui_text": None,
            "ui_type": None,
            "ui_state": None,
            "essential_states": None,
        }
        img = Image.open(ui_state.screenshot_path).convert("RGB")
        img_arr = np.array(img)
        current_ui_state["image_height"] = img.height
        current_ui_state["image_width"] = img.width
        current_ui_state["category"] = category
        current_ui_state["image"] = img_arr
        current_ui_state["episode_id"] = epi
        current_ui_state["step_id"] = step_id
        step_id += 1
        current_ui_state["goal"] = task_description
        # when taking testbed trace as the input, the action on the last screen
        # could be None
        if ui_state.action:
            current_ui_state["result_action"][0] = ui_state.action.action_type
            current_ui_state["result_action"][1] = ui_state.action.typed_text
            current_ui_state["result_touch_yx"] = ui_state.action.touch_point_yx
            current_ui_state["result_lift_yx"] = ui_state.action.lift_point_yx

        if ui_state.state_type == "groundtruth":
            ess = ui_state.essential_state
            current_ui_state["essential_states"] = ess
            # passing the whole ui_state for a quick implementation
            current_ui_state["ui_state"] = ui_state

        ui_infos_for_plot.append(copy.deepcopy(current_ui_state))
    plot_episode(
        ui_infos_for_plot,
        show_essential_states=False,
        show_annotations=False,
        show_actions=True,
        output_file=output_file,
    )


def plot_all(folder: str):

    from concurrent.futures import ProcessPoolExecutor

    e = ProcessPoolExecutor(max_workers=4)

    for epi_id in os.listdir(folder):
        if not epi_id.isdigit():
            continue

        epi_folder = os.path.join(folder, epi_id)
        task_description = helper.get_task_description_by_episode(epi_id)
        cat = helper.get_category_by_episode(epi_id).value

        exec_trace = helper.load_testbed_trace_by_path(epi_folder)
        output_file = os.path.join(epi_folder, "agg_plot.png")
        e.submit(
            plot_single_trace,
            epi=epi_id,
            category=cat,
            task_description=task_description,
            task_trace=exec_trace,
            output_file=output_file,
        )


if __name__ == "__main__":
    folder = "exec_output"

    import sys

    if len(sys.argv) == 1:
        plot_all(folder)
    else:
        for item in sys.argv[1:]:
            plot_by_folder(item)
