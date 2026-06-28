from agent_runner.planner import explicit


def test_shell():
    assert explicit("shell: echo hello")["actions"][0]["type"] == "shell"


def test_browser():
    assert explicit("https://example.com")["actions"][0]["type"] == "browser"


def test_chatgpt_image_workflow():
    plan = explicit("Open ChatGPT and create a hyper-realistic image of a beer and save the photo in desktop")
    action = plan["actions"][0]
    assert action["type"] == "browser_workflow"
    assert action["value"]["workflow"] == "chatgpt_image"
    assert action["value"]["destination"] == "~/Desktop/generated-image.png"
