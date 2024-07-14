To get predicted action on each GUI, run the following commands:

```bash
TASK_METADATA_PATH= \
GR_DATASET_PATH= \
OPENAI_APIKEY= \
OPENAI_BASEURL= \
python3 main_action_prediction.py
```

To run tasks on AgentEnv, first download AgentEnv, then run the following commands:

```bash
AGENTENV_PATH= \
FIRST_N_EPISODES= \
OPENAI_APIKEY= \
OPENAI_BASEURL= \
python3 main_exec_testbed3.py
```

FIRST_N_EPISODES means running the first few tasks of the LlamaTouch dataset.