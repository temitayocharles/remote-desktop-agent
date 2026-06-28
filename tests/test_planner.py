from agent_runner.planner import explicit
def test_shell(): assert explicit("shell: echo hello")["actions"][0]["type"] == "shell"
def test_browser(): assert explicit("https://example.com")["actions"][0]["type"] == "browser"
