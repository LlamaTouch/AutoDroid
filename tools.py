import hashlib
import os
import re

import networkx as nx
from openai import OpenAI

from droidbot.input_event import (
    KeyEvent,
    LongTouchEvent,
    ScrollEvent,
    SetTextEvent,
    TouchEvent,
    UIEvent,
)

ACTION_MISSED = None
FINISHED = "task_completed"


def get_id_from_view_desc(view_desc):
    """
    given a view(UI element), get its ID
    """
    try:
        ret = int(re.findall(r"id=(\d+)", view_desc)[0])
    except:
        print(f"error indexing id from view desc")
        print(view_desc)
        ret = -1
    return ret
    # if view_desc[0] == ' ':
    #     view_desc = view_desc[1:]
    # view_desc_list = view_desc.split(' ', 2)
    # if len(view_desc_list) > 2:
    #     if view_desc_list[2][:6] != 'class=' and view_desc_list[2][:8] != 'checked=' :  # for example: <p id=10>Up time</p>
    #         new_view_desc_list = view_desc.split(' ', 1)
    #         latter_part = new_view_desc_list[1].split('>', 1)
    #         return int(latter_part[0][3:])
    #     else:  # for example, <button id=3 class='More options' checked=False></button>
    #         return int(view_desc_list[1][3:])
    # else:  # for example, <p id=4>June</p>
    #     latter_part = view_desc_list[1].split('>', 1)
    #     # print('************', view_desc, view_without_id)
    #     return int(latter_part[0][3:])


def insert_id_into_view(view, id):
    if view[0] == " ":
        view = view[1:]
    if view[:2] == "<p":
        return view[:2] + f" id={id}" + view[2:]
    if view[:7] == "<button":
        return view[:7] + f" id={id}" + view[7:]
    if view[:6] == "<input":
        return view[:6] + f" id={id}" + view[6:]
    if view[:9] == "<checkbox":
        return view[:9] + f" id={id}" + view[9:]
    if view[:5] == "<span":
        return view[:5] + f" id={id}" + view[5:]
    import pdb

    pdb.set_trace()


def get_view_without_id(view_desc):
    """
    remove the id from the view
    """
    id = re.findall(r"id=(\d+)", view_desc)[0]
    id_string = " id=" + id
    return re.sub(id_string, "", view_desc)


# def query_gpt(prompt):
#     import requests
#     URL = os.environ['GPT_URL']  # NOTE: replace with your own GPT API
#     body = {"model":"gpt-3.5-turbo","messages":[{"role":"user","content":prompt}],"stream":True}
#     headers = {'Content-Type': 'application/json', 'path': 'v1/chat/completions'}
#     r = requests.post(url=URL, json=body, headers=headers)
#     return r.content.decode()


def delete_old_views_from_new_state(old_state, new_state, without_id=True):
    """
    remove the UI element in new_state if it also exists in the old_state
    """
    old_state_list = old_state.split(">\n")
    new_state_list = new_state.split(">\n")
    old_state_list_without_id = []
    for view in old_state_list:
        view_without_id = get_view_without_id(view)
        if view[-1] != ">":
            view = view + ">"
        if view_without_id[-1] != ">":
            view_without_id = view_without_id + ">"
        old_state_list_without_id.append(view_without_id)
    customized_new_state_list = []
    for view in new_state_list:
        view_without_id = get_view_without_id(view)
        if view[-1] != ">":
            view = view + ">"
        if view_without_id[-1] != ">":
            view_without_id = view_without_id + ">"
        if (
            view_without_id not in old_state_list_without_id
        ):  # or 'go back' in view or 'scroll' in view:
            if without_id:
                customized_new_state_list.append(view_without_id)
            else:
                customized_new_state_list.append(view)
    return customized_new_state_list


def get_item_properties_from_id(ui_state_desc, view_id):
    """
    given the element id, get the UI element property from the state prompt
    """
    # ui_state_desc = self.states[state_str]['raw_prompt']
    ui_state_list = ui_state_desc.split(">\n")
    for view_desc in ui_state_list:
        if view_desc[0] == " ":
            view_desc = view_desc[1:]
        if view_desc[-1] != ">":
            view_desc += ">"
        id = get_id_from_view_desc(view_desc)
        if id == view_id:
            return get_view_without_id(view_desc)
    return ACTION_MISSED


def get_thought(answer):
    start_index = answer.find("Thought:") + len(
        "Thought:"
    )  # Find the location of 'start'
    if start_index == -1:
        start_index = answer.find("thought:") + len("thought:")
    if start_index == -1:
        start_index = answer.find("Thought") + len("Thought")
    if start_index == -1:
        start_index = answer.find("thought") + len("thought")
    if start_index == -1:
        start_index = 0
    end_index = answer.find("}")  # Find the location of 'end'
    substring = (
        answer[start_index:end_index] if end_index != -1 else answer[start_index:]
    )
    return substring


def process_gpt_answer(answer):
    answer = answer.replace("\n", " ")
    return answer


def extract_gpt_answer(answer):
    split_answer = answer.split("4.")
    if len(split_answer) > 1:
        last_sentence = split_answer[1]
        pattern = r"id=(\d+)"
        match = re.search(pattern, last_sentence)
        try:
            id = int(match.group(0)[3:])
        except:
            id = re.search(r"\d+", last_sentence)
        return id
    else:
        return re.search(r"\d+", answer)


def make_prompt(
    task_description,
    state_prompt,
    action_history,
    thought_history=None,
    use_thoughts=False,
):
    if use_thoughts:
        history_with_thought = []
        for idx in range(len(action_history)):
            history_with_thought.append(
                action_history[idx] + " Reason: " + thought_history[idx]
            )
    else:
        history_with_thought = action_history

    introduction = """You are a smartphone assistant to help users complete tasks by interacting with mobile apps.Given a task, the previous UI actions, and the content of current UI state, your job is to decide whether the task is already finished by the previous actions, and if not, decide which UI element in current UI state should be interacted."""
    task_prompt = "Task: " + task_description
    history_prompt = "Previous UI actions: \n" + "\n".join(history_with_thought)
    full_state_prompt = "Current UI state: \n" + state_prompt
    request_prompt = """Your answer should always use the following format:1. Completing this task on a smartphone usually involves these steps: <?>.\n2. Analyses of the relations between the task and the previous UI actions and current UI state: <?>.\n3. Based on the previous actions, is the task already finished? <Y/N>. The next step should be <?/None>.\n4. Can the task be proceeded with the current UI state? <Y/N>. Fill in the blanks about the next one interaction: - id=<id number> - action=<tap/input> - input text=<text or N/A>"""
    prompt = (
        introduction
        + "\n"
        + task_prompt
        + "\n"
        + history_prompt
        + "\n"
        + full_state_prompt
        + "\n"
        + request_prompt
    )
    return prompt


def extract_action(answer):
    llm_id = "N/A"
    llm_action = "tap"
    llm_input = "N/A"
    whether_finished_answer = re.findall("3\.(.*)4\.", answer, flags=re.S)[0]
    for e in ["Yes.", "Y.", "y.", "yes.", "is already finished"]:
        if e in whether_finished_answer:
            llm_id = -1
            llm_action = "N/A"
            llm_input = "N/A"
            break
    finished_check = re.findall("4\.(.*)", answer, flags=re.S)[0]
    for e in [
        "No further interaction is required",
        "cannot be determined based on",
        "no further action is needed",
    ]:
        if e in finished_check:
            llm_id = -1
            llm_action = "N/A"
            llm_input = "N/A"
    if llm_id != -1:
        try:
            llm_id, llm_action, llm_input = re.findall(
                "- id=(N/A|-?\d+)(?:.|\\n)*-\s?action=(.+?)(?:\\n|\s)(?:.|\\n)*-\s*input text=\"?'?(N/A|\w+)\"?'?",
                answer,
            )[0]
            if llm_id == "N/A":
                llm_id = -1
            else:
                llm_id = int(llm_id)
            if "tapon" in llm_action.lower():
                llm_action = "tap"
            elif "none" in llm_action.lower():
                llm_action = "N/A"
            elif "click" in llm_action.lower():
                llm_action = "tap"
            assert llm_action in ["tap", "input", "N/A"]
        except:
            try:
                llm_id, llm_action = re.findall(
                    "-\s?id=(\d+).*-\s?action=(\w+)", answer, flags=re.S
                )[0]
                llm_id = int(llm_id)
                if (
                    "tapon" in llm_action.lower()
                    or "check" in llm_action.lower()
                    or "uncheck" in llm_action.lower()
                ):
                    llm_action = "tap"
                elif "none" in llm_action.lower():
                    llm_action = "N/A"
                assert llm_action in ["tap", "input", "N/A"]
            except:
                # just return N/A when there is exception
                llm_id = -1
                llm_action = "N/A"
                llm_input = ""
    return llm_id, llm_action, llm_input


def insert_onclick_into_prompt(state_prompt, insert_ele, target_ele_desc):
    def insert_onclick(statement, description):
        index = statement.find(">")
        inserted_statement = (
            statement[:index] + f" onclick='{description}'" + statement[index:]
        )
        return inserted_statement

    onclick_desc = "go to complete the " + target_ele_desc
    element_statements = state_prompt.split(">\n")
    elements_without_id = []
    for ele_statement in element_statements:
        ele_statement_without_id = get_view_without_id(ele_statement)
        if ele_statement_without_id[-1] != ">":
            ele_statement_without_id += ">"
        if insert_ele == ele_statement_without_id:
            ele_statement_without_id = insert_onclick(
                ele_statement_without_id, onclick_desc
            )

        elements_without_id.append(ele_statement_without_id)

    elements = []
    for id in range(len(elements_without_id)):
        elements.append(insert_id_into_view(elements_without_id[id], id))
    return "\n".join(elements)


def hash_string(string):
    byte_string = string.encode()
    # Create a hash object using the SHA-256 algorithm
    hash_obj = hashlib.sha256(byte_string)
    # Get the hashed value as a hexadecimal string
    hashed_string = hash_obj.hexdigest()
    return hashed_string


def parse_views(raw_views):
    """Derived from device_state.DeviceState.__parse_views"""
    views = []
    if not raw_views or len(raw_views) == 0:
        return views

    for view_dict in raw_views:
        # # Simplify resource_id
        # resource_id = view_dict['resource_id']
        # if resource_id is not None and ":" in resource_id:
        #     resource_id = resource_id[(resource_id.find(":") + 1):]
        #     view_dict['resource_id'] = resource_id
        views.append(view_dict)
    return views


def get_action_descv2(action, view_desc):
    """Derived from device_state.DeviceState.get_action_descv2

    Args are the results of function execution:
        action, candidate_actions, target_view, thought = _get_action_from_views_actions()
        - action: action
        - view_desc: target_view
    """
    desc = action.event_type
    if isinstance(action, KeyEvent):
        if action.name == "BACK":
            desc = "- Press BACK"
        else:
            desc = "- TapOn: " + view_desc
    if isinstance(action, UIEvent):
        if isinstance(action, LongTouchEvent):
            desc = "- LongTapOn: " + view_desc
        elif isinstance(action, SetTextEvent):
            desc = "- TapOn: " + view_desc + " InputText: " + action.text
        elif isinstance(action, ScrollEvent):
            desc = f"- Scroll{action.direction.lower()}: " + view_desc
        else:
            desc = "- TapOn: " + view_desc
    return desc


def _get_children_checked(views, children_ids):
    for childid in children_ids:
        if _safe_dict_get(views[childid], "checked", default=False):
            return True
    return False


def _remove_view_ids(views):
    removed_views = []
    for view_desc in views:
        view_desc_without_id = get_view_without_id(view_desc)
        removed_views.append(view_desc_without_id)
    return removed_views


def _safe_dict_get(view_dict, key, default=None):
    return_itm = view_dict[key] if (key in view_dict) else default
    if return_itm == None:
        return_itm = ""
    return return_itm


def _remove_ip_and_date(string, remove_candidates=None):
    if not string:
        return string
    import re

    if not remove_candidates:
        remove_candidates = [
            "hr",
            "min",
            "sec",
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sept",
            "Oct",
            "Nov",
            "Dec" "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
            "Sunday",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sun",
            "Mon",
            "Tues",
            "Wed",
            "Thur",
            "Fri",
            "Sat",
        ]  # '[0-9]+',
    for remove_candidate in remove_candidates:
        string = re.sub(remove_candidate, "", string)
    if (
        ":" in string or "::" in string or "%" in string
    ):  # ip address, hour, storage usage
        string = ""
    return string


def _merge_textv2(views, children_ids, remove_time_and_ip=False, important_view_ids=[]):
    texts, content_descriptions = [], []
    for childid in children_ids:

        if not _safe_dict_get(views[childid], "visible") or _safe_dict_get(
            views[childid], "resource_id"
        ) in ["android:id/navigationBarBackground", "android:id/statusBarBackground"]:
            # if the successor is not visible, then ignore it!
            continue

        text = _safe_dict_get(views[childid], "text", default="")
        if len(text) > 50:
            text = text[:50]

        if remove_time_and_ip:
            text = _remove_ip_and_date(text)

        if text != "":
            texts.append(text)
            important_view_ids.append([text, childid])

        content_description = _safe_dict_get(
            views[childid], "content_description", default=""
        )
        if len(content_description) > 50:
            content_description = content_description[:50]

        if remove_time_and_ip:
            content_description = _remove_ip_and_date(content_description)

        if content_description != "":
            important_view_ids.append([content_description, childid])
            content_descriptions.append(content_description)

    merged_text = "<br>".join(texts) if len(texts) > 0 else ""
    merged_desc = (
        "<br>".join(content_descriptions) if len(content_descriptions) > 0 else ""
    )
    return merged_text, merged_desc, important_view_ids


def _get_self_ancestors_property(views, view, key, default=None):
    all_views = [view] + [views[i] for i in get_all_ancestors(views, view)]
    for v in all_views:
        value = _safe_dict_get(v, key)
        if value:
            return value
    return default


def get_all_ancestors(views, view_dict):
    """
    Get temp view ids of the given view's ancestors
    :param view_dict: dict, an element of DeviceState.views
    :return: list of int, each int is an ancestor node id
    """
    result = []
    parent_id = _safe_dict_get(view_dict, "parent", -1)
    if 0 <= parent_id < len(views):
        result.append(parent_id)
        result += get_all_ancestors(views, views[parent_id])
    return result


def _get_ancestor_id(views, view, key, default=None):
    if _safe_dict_get(view, key=key, default=False):
        return view["temp_id"]
    all_views = [view] + [views[i] for i in get_all_ancestors(views, view)]
    for v in all_views:
        value = _safe_dict_get(v, key)
        if value:
            return v["temp_id"]
    return default


def _build_view_graph(views):
    view_graph = nx.DiGraph()
    for view_id in range(1, len(views)):
        view = views[view_id]
        parentid = view["parent"]
        view_graph.add_edge(parentid, view_id)
    return view_graph


def _extract_all_children(views, id):
    view_graph = _build_view_graph(views)
    successors = []
    successors_of_view = nx.dfs_successors(view_graph, source=id, depth_limit=100)
    for k, v in successors_of_view.items():
        for successor_id in v:
            if successor_id not in successors and successor_id != id:
                successors.append(successor_id)
    return successors


def get_described_actions(
    views,
    prefix="",
    remove_time_and_ip=False,
    merge_buttons=True,
    add_edit_box=True,
    add_check_box=True,
    add_pure_text=True,
):
    """
    Args:
        - views: view hierarchy in json
    Return:
        - state_desc
        - available_actions
        - views_without_id
        - important_view_ids
    """
    enabled_view_ids = []
    for view_dict in views:
        # exclude navigation bar if exists
        if _safe_dict_get(view_dict, "visible") and _safe_dict_get(
            view_dict, "resource_id"
        ) not in [
            "android:id/navigationBarBackground",
            "android:id/statusBarBackground",
        ]:
            enabled_view_ids.append(view_dict["temp_id"])

    text_frame = "<p id=@ text='&'>#</p>"
    btn_frame = "<button id=@ text='&'>#</button>"
    checkbox_frame = "<checkbox id=@ checked=$ text='&'>#</checkbox>"
    input_frame = "<input id=@ text='&'>#</input>"

    view_descs = []
    available_actions = []
    removed_view_ids = []

    important_view_ids = []

    for view_id in enabled_view_ids:
        if view_id in removed_view_ids:
            continue
        view = views[view_id]
        clickable = _get_self_ancestors_property(views, view, "clickable")
        scrollable = _safe_dict_get(view, "scrollable")
        checkable = _get_self_ancestors_property(views, view, "checkable")
        long_clickable = _get_self_ancestors_property(views, view, "long_clickable")
        editable = _safe_dict_get(view, "editable")
        actionable = clickable or scrollable or checkable or long_clickable or editable
        checked = _safe_dict_get(view, "checked", default=False)
        selected = _safe_dict_get(view, "selected", default=False)
        content_description = _safe_dict_get(view, "content_description", default="")
        view_text = _safe_dict_get(view, "text", default="")
        view_class = _safe_dict_get(view, "class").split(".")[-1]
        if not content_description and not view_text and not scrollable:  # actionable?
            continue

        if editable:
            view_desc = input_frame.replace("@", str(len(view_descs))).replace(
                "#", view_text
            )
            if content_description:
                view_desc = view_desc.replace("&", content_description)
            else:
                view_desc = view_desc.replace(" text='&'", "")
            view_descs.append(view_desc)
            available_actions.append(SetTextEvent(view=view, text="HelloWorld"))
            important_view_ids.append([content_description + view_text, view_id])

        elif checkable:
            view_desc = (
                checkbox_frame.replace("@", str(len(view_descs)))
                .replace("#", view_text)
                .replace("$", str(checked or selected))
            )
            if content_description:
                view_desc = view_desc.replace("&", content_description)
            else:
                view_desc = view_desc.replace(" text='&'", "")
            view_descs.append(view_desc)
            if add_check_box:
                available_actions.append(TouchEvent(view=view))
            else:
                available_actions.append(None)
        elif clickable:  # or long_clickable
            if merge_buttons:
                # below is to merge buttons, led to bugs
                clickable_ancestor_id = _get_ancestor_id(
                    views, view=view, key="clickable"
                )
                if not clickable_ancestor_id:
                    clickable_ancestor_id = _get_ancestor_id(
                        views, view=view, key="checkable"
                    )
                clickable_children_ids = _extract_all_children(
                    views=views, id=clickable_ancestor_id
                )

                if view_id not in clickable_children_ids:
                    clickable_children_ids.append(view_id)

                view_text, content_description, important_view_ids = _merge_textv2(
                    views,
                    clickable_children_ids,
                    remove_time_and_ip,
                    important_view_ids,
                )
                checked = _get_children_checked(views, clickable_children_ids)
                # end of merging buttons
            if not view_text and not content_description:
                continue
            view_desc = btn_frame.replace("@", str(len(view_descs))).replace(
                "#", view_text
            )
            if content_description:
                view_desc = view_desc.replace("&", content_description)
            else:
                view_desc = view_desc.replace(" text='&'", "")
            view_descs.append(view_desc)

            available_actions.append(TouchEvent(view=view))
            if merge_buttons:
                for clickable_child in clickable_children_ids:
                    if (
                        clickable_child in enabled_view_ids
                        and clickable_child != view_id
                    ):
                        removed_view_ids.append(clickable_child)

        elif scrollable:
            continue
        else:

            if remove_time_and_ip:
                view_text = _remove_ip_and_date(view_text)
                content_description = _remove_ip_and_date(content_description)

            view_desc = text_frame.replace("@", str(len(view_descs))).replace(
                "#", view_text
            )

            if content_description:
                view_desc = view_desc.replace("&", content_description)
            else:
                view_desc = view_desc.replace(" text='&'", "")
            view_descs.append(view_desc)

            important_view_ids.append([content_description + view_text, view_id])

            available_actions.append(TouchEvent(view=view))
    view_descs.append(f"<button id={len(view_descs)}>go back</button>")
    available_actions.append(KeyEvent(name="BACK"))
    # state_desc = 'The current state has the following UI elements: \n' #views and corresponding actions, with action id in parentheses:\n '
    state_desc = prefix  #'Given a screen, an instruction, predict the id of the UI element to perform the insturction. The screen has the following UI elements: \n'
    # state_desc = 'You can perform actions on a contacts app, the current state of which has the following UI views and corresponding actions, with action id in parentheses:\n'
    state_desc += "\n".join(view_descs)

    views_without_id = _remove_view_ids(view_descs)
    # print(views_without_id)
    return state_desc, available_actions, views_without_id, important_view_ids


def get_action_from_views_actions(
    task_description: str,
    action_history,
    thought_history,
    views=None,
    candidate_actions=None,
    state_strs=None,
    current_state=None,
):
    """
    get action choice from LLM based on a list of views and corresponding actions

    Execution flow:
        - [High priority] If the *current_state* is not None, the *views* param
            can be None; *state_prompt* and *candidate_actions* will be extracted
            from *current_state* to construct the LLM prompt.
                - Question: What does *current_state.get_described_actions* do?
                - Answer: It is an important function for simplifying the UI state
                according to the input views.

        - [Low priority] If the *current_state* is None, the *views* param will
            be used established the UI state for prompting LLM.
    """
    state_prompt, candidate_actions, _, _ = get_described_actions(views=views)
    state_str = hash_string(get_described_actions(views, remove_time_and_ip=True)[0])
    prompt = make_prompt(
        task_description=task_description,
        state_prompt=state_prompt,
        action_history=action_history,
        thought_history=thought_history,
    )

    # ids = [str(idx) for idx, i in enumerate(candidate_actions)]
    ids = str([i for i in range(len(candidate_actions))])

    # print(
    #     "********************************** prompt: **********************************"
    # )
    # print(prompt)
    # print(
    #     "********************************** end of prompt **********************************"
    # )

    response = query_gpt(prompt)

    # print(f"response: {response}")
    idx, action_type, input_text = extract_action(response)

    # print(f"candidate actions: {candidate_actions}")

    idx = int(idx)
    selected_action = candidate_actions[idx]

    selected_view_description = get_item_properties_from_id(
        ui_state_desc=state_prompt, view_id=idx
    )
    thought = get_thought(response)

    return (
        selected_action,
        candidate_actions,
        selected_view_description,
        thought,
        prompt,
        response,
    )


def query_gpt(prompt):
    client = OpenAI(api_key=os.environ["OPENAI_APIKEY"], base_url=os.environ["OPENAI_BASEURL"])
    retry = 0
    completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        # "gpt-3.5-turbo" points to "gpt-3.5-turbo-0125"
        # model="gpt-4-0125-preview",
        model="gpt-4o-2024-05-13",
        # model="gpt-3.5-turbo",
        temperature=0,
        seed=0x1110,
        timeout=60,
    )
    res = completion.choices[0].message.content
    return res
